# Sprint 3 — Inteligência Operacional e Apoio à Decisão

> **AI for Robotic Process Automation — FIAP 2026**
> Continuação da [Sprint 2](../sprint2-RPA).

## Sobre

Duas frentes que se cruzam:

1. **Pilar 1 — Web Scraping**: quatro robôs (WEG, Menzel Motors, RS Delivers e a norma ISO 10816-3) que navegam catálogos de fabricantes e uma tabela normativa, extraindo dados técnicos de motores/controladores elétricos e limites de vibração, gerando um JSON por produto/tabela em `data/json/` como evidência de coleta.
2. **Pilar 2 — Automação de Ocorrências**: motor de regras (limites fixos por sensor) + modelo de ML (IsolationForest, não supervisionado) que avaliam as leituras de sensor do banco da [Sprint 2](../sprint2-RPA), registram eventos de anomalia, atualizam o status de saúde de cada ativo (`normal` / `alerta` / `critico`) — refletido automaticamente no dashboard da Sprint 2, sem mudança nenhuma de frontend — e enriquecem cada evento com contexto técnico vindo dos dados raspados pelo Pilar 1.

## Estrutura

```
sprint3-rpa/
├── main.py                       # menu único: banco / scraping / motor de regras
├── requirements.txt
├── .env.example                   # credenciais do Postgres (mesmo banco da sprint2-RPA)
├── db/
│   └── init_eventos.sql           # tabela evento_alerta (aditiva — não mexe no schema da sprint2)
├── src/
│   ├── weg_page.py                 # crawler + extração do catálogo WEG
│   ├── menzel_page.py              # crawler + extração do catálogo Menzel Motors
│   ├── rsdelivers_page.py          # crawler + extração da busca RS Delivers
│   ├── norma_vibracao_page.py      # scraper da tabela normativa ISO 10816-3 (zonas de vibração)
│   ├── hydra_driver.py             # driver com failover de IP/proxy (undetected_chromedriver)
│   ├── scraping_utils.py           # helpers compartilhados entre Menzel e RS
│   ├── db.py                       # conexão com o Postgres (mesmo padrão da sprint2-RPA)
│   ├── regras_alerta.py            # motor de regras (baseline + desvio por sensor)
│   ├── deteccao_anomalia_ml.py     # camada de ML (IsolationForest) — desvio multivariado
│   ├── contexto_tecnico.py         # ponte Pilar 1 → Pilar 2: indexa data/json/ por sensor
│   └── monitor_eventos.py          # roda regras + ML, grava eventos, atualiza status
├── tests/
│   ├── test_regras_alerta.py         # motor de regras isolado
│   ├── test_contexto_tecnico.py      # ponte Pilar 1 → Pilar 2 isolada
│   ├── test_deteccao_anomalia_ml.py  # camada de ML isolada (dados sintéticos)
│   └── test_monitor_eventos.py       # verificar_anomalias de ponta a ponta, com banco falso
└── data/
    ├── json/                     # evidência da coleta — 1 JSON por produto/tabela
    └── debug/                    # HTML salvo quando um crawler não acha o esperado
```

## Pré-requisitos

- Python 3.13 + Google Chrome instalado (Pilar 1 — WEG/Menzel/RS Delivers usam Selenium; a norma ISO 10816-3 usa só `requests`/HTML estático)
- **Docker Desktop rodando com a stack da [Sprint 2](../sprint2-RPA) de pé** (Pilar 2 — ver abaixo)

```bash
pip install -r requirements.txt
cp .env.example .env
```

## Pilar 2 depende da Sprint 2 estar rodando

O motor de regras conecta no **mesmo PostgreSQL** que a sprint2-RPA sobe via Docker. Sem isso de pé, as opções 1 e 3 do menu falham (erro de conexão tratado — não derruba o programa).

```bash
cd ../sprint2-RPA
cp .env.example .env          # se ainda não existir
docker compose up -d --build
docker compose exec api python main.py   # opções 2 e 3: popula localizações + importa ativos
```

O `.env.example` desta pasta já aponta pros valores padrão de dev da sprint2 (`localhost:5433`, banco `digital_twin`). Se o `.env` da sprint2 usar credenciais diferentes, ajuste aqui também.

## Testes

`regras_alerta.py`, `contexto_tecnico.py` e `deteccao_anomalia_ml.py` não dependem de banco nem de Selenium, então têm testes unitários com dados sintéticos. `monitor_eventos.py` depende de Postgres de verdade em produção, mas seu teste substitui `get_connection` por um banco falso (fixtures em memória) pra testar a lógica de ponta a ponta sem precisar da stack da sprint2 rodando. Só os 3 scrapers Selenium (`weg_page.py`, `menzel_page.py`, `rsdelivers_page.py`) ficam de fora, por dependerem de navegador/rede reais — validados manualmente (ver números abaixo).

```bash
python -m unittest discover -s tests -t .
```

## Como rodar

```bash
python main.py
```

**Menu principal:**
```
1. Testar conexão com banco (Pilar 2)
2. Web Scraping (Pilar 1)
3. Verificar anomalias e atualizar status (Pilar 2)
0. Sair
```

**Submenu de scraping (opção 2):**
```
1. WEG
2. Menzel
3. RS Delivers
4. Norma ISO 10816-3 (tabela de vibração)
5. Todos
0. Voltar
```

Cada scraper roda de forma independente e fecha o navegador sozinho ao terminar — se uma fonte falhar na opção "Todos", as outras continuam.

A opção 3 do menu principal (`verificar_anomalias`):
1. Lê a última leitura de cada TAG no banco.
2. Treina o modelo de ML (`deteccao_anomalia_ml.py`) em cima do histórico de leituras do próprio banco (se houver histórico suficiente).
3. Aplica o motor de regras (`regras_alerta.py`) — 5 sensores, 2 níveis de severidade (alerta/crítico) — e, se nenhum sensor isolado estourou limite mas o modelo de ML acha a combinação anômala, gera um desvio "multivariado" à parte.
4. Pra cada desvio encontrado, busca em `data/json/` (via `contexto_tecnico.py`) alguma referência técnica dos catálogos/normas raspados relacionada àquele sensor, e anexa ao evento.
5. Grava tudo em `evento_alerta` (incluindo se o ML concordou com o desvio e o score de anomalia) e atualiza `tag.status`.

Depois de rodar, o dashboard da sprint2 (`http://localhost:5173`, com a stack rodando) já mostra os status atualizados — sem precisar mexer no frontend.

## A camada de ML (Pilar 2)

O motor de regras (`regras_alerta.py`) avalia um sensor de cada vez contra um limite fixo — não pega o caso em que nenhum sensor isolado estourou o limite, mas a *combinação* das 5 leituras foge do padrão histórico do ativo (ex: temperatura e corrente subindo juntas, dentro do limite individual de cada uma, mas fora da correlação normal). `deteccao_anomalia_ml.py` cobre esse caso: treina um **IsolationForest** (scikit-learn) no histórico de `leitura_sensor` do próprio banco e sinaliza leituras multivariadas fora do padrão.

É não supervisionado de propósito: não existe, nesse projeto, um dataset rotulado de falha real pra treinar um classificador supervisionado — os dados da Sprint 2 são sintéticos. O IsolationForest não precisa de rótulo, só aprende a "forma" da operação normal e sinaliza o que foge dela. Se o histórico ainda for pequeno demais pra treinar (menos de 30 leituras completas), o monitor simplesmente segue só com o motor de regras — o ML é reforço, não dependência dura (ver `tests/test_deteccao_anomalia_ml.py` e `tests/test_monitor_eventos.py`).

## A ponte entre os dois pilares

Os JSONs gerados pelo Pilar 1 não ficam só como evidência estática: `contexto_tecnico.py` os lê e monta um índice por sensor (casando por palavra-chave no nome do campo — ex: qualquer campo raspado contendo "temperat" vira referência do sensor `temperatura`). Quando um desvio é detectado (por regra fixa ou pelo ML), esse contexto é anexado ao evento (`evento_alerta.contexto_tecnico`).

**Importante**: isso é tratado como contexto de **referência de mercado/catálogo/norma técnica**, não como dado exato do ativo físico específico — não existe hoje uma chave que ligue 1:1 um produto raspado a um dos 34 motores da Sprint 2 (os catálogos raspados são uma varredura geral dos sites dos fabricantes, não filtrada por esses ativos).

## Estado da coleta (Pilar 1)

| Fonte | Itens coletados | Observação |
|---|---|---|
| WEG | 54 produtos | Catálogo mapeado tem ~463 produtos; ver limitação abaixo (bloqueio por volume) |
| Menzel Motors | 10 de 11 produtos | Catálogo completo — só 1 URL falhou (ver limitação abaixo) |
| RS Delivers | 17 produtos | Amostra de 3 páginas de resultado pra "motores" (ver limitação abaixo) |
| Norma ISO 10816-3 | 1 tabela (12 valores) | Zonas de severidade de vibração A/B/C/D, 4 classes de máquina |

## Limitações conhecidas

- **Scraping WEG**: `weg.net` está atrás de bot-protection da Akamai. `undetected_chromedriver` contorna o bloqueio por fingerprint, mas sob volume alto de requisições sustentado do mesmo IP real, o site pode bloquear por rate-limit — `src/hydra_driver.py` já tem a lógica de troca de proxy pronta, mas `PROXY_POOL` está vazia (sem proxies reais configurados). Catálogo completo mapeado (~77 categorias / ~463 produtos), mas a extração integral ainda não rodou até o fim por causa disso.
  - `src/weg_page.py` agora espera um intervalo aleatório (2.5-6s, com jitter) entre a extração de cada produto, pra reduzir a chance de bater no rate-limit por volume.
  - Também testamos trocar o Chrome pelo `curl_cffi` (TLS impersonation de Chrome + reuso dos cookies do Akamai já validados pela sessão do Selenium) só na etapa de buscar a página de cada produto, que é a que gera o volume real de requests. Em teste ao vivo funcionou uma vez isoladamente, mas falhou de forma consistente (0/6) logo em seguida, mesmo com cookies frescos — indício de que o bloqueio aqui depende de telemetria comportamental que o Akamai coleta enquanto a página está de fato aberta num navegador, não só de um snapshot de cookies. Não entrou no código por não ser confiável; mantido só como registro pra não repetir a mesma investigação depois.
- **Scraping Menzel**: catálogo completo (11/11 URLs), 10 extraídos com sucesso. A última URL (`roller-table-motors`) esbarra num falso-positivo do detector de bloqueio do `hydra_driver.py` (o texto da página aciona um dos termos de bloqueio sem ser bloqueio de verdade) — o erro é isolado por produto e não afeta os outros 10.
- **Scraping RS Delivers**: a busca por "motores" retorna ~25 mil resultados e mistura produtos fora do escopo de motor (cabos, suportes antivibração, ventiladores) — a paginação (`max_paginas`) é um limite prático, não um fim natural dos resultados. Rodado com 3 páginas / 15 produtos como amostra representativa; ampliar é só subir esses dois parâmetros.
- **Regras de alerta**: os limites em `src/regras_alerta.py` são uma premissa documentada (não vêm de um dataset de falha real — os dados da Sprint 2 são sintéticos), ajustáveis conforme dados reais de falha apareçam. A camada de ML (`deteccao_anomalia_ml.py`) complementa isso pra padrões multivariados, mas também não tem rótulo de falha real pra validar contra — é não supervisionada por design, não por atalho.

## 👥 Equipe

| RM | Nome |
|---|---|
| 552574 | Bruno Fernandes Nascimento |
| 566325 | Júlia Aben Athar da Silveira |
| 565260 | Edgar Lódula de Assis |
| 565293 | Guilherme Gama Bitencourt Souza |
| 563632 | Igor Thiago Nakajima Vieira |
