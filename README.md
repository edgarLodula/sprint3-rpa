# Sprint 3 — Inteligência Operacional e Apoio à Decisão

> **AI for Robotic Process Automation — FIAP 2026**
> Continuação da [Sprint 2](../sprint2-RPA).

## Sobre

Duas frentes que se cruzam:

1. **Pilar 1 — Web Scraping**: três robôs (WEG, Menzel Motors, RS Delivers) que navegam catálogos de fabricantes e extraem dados técnicos de motores/controladores elétricos, gerando um JSON por produto em `data/json/` como evidência de coleta.
2. **Pilar 2 — Automação de Ocorrências**: motor de regras que avalia as leituras de sensor do banco da [Sprint 2](../sprint2-RPA), registra eventos de anomalia, atualiza o status de saúde de cada ativo (`normal` / `alerta` / `critico`) — refletido automaticamente no dashboard da Sprint 2, sem mudança nenhuma de frontend — e enriquece cada evento com contexto técnico vindo dos dados raspados pelo Pilar 1.

## Estrutura

```
sprint3-rpa/
├── main.py                    # menu único: banco / scraping / motor de regras
├── requirements.txt
├── .env.example                # credenciais do Postgres (mesmo banco da sprint2-RPA)
├── db/
│   └── init_eventos.sql        # tabela evento_alerta (aditiva — não mexe no schema da sprint2)
├── src/
│   ├── weg_page.py              # crawler + extração do catálogo WEG
│   ├── menzel_page.py           # crawler + extração do catálogo Menzel Motors
│   ├── rsdelivers_page.py       # crawler + extração da busca RS Delivers
│   ├── hydra_driver.py          # driver com failover de IP/proxy (undetected_chromedriver)
│   ├── scraping_utils.py        # helpers compartilhados entre Menzel e RS
│   ├── db.py                    # conexão com o Postgres (mesmo padrão da sprint2-RPA)
│   ├── regras_alerta.py         # motor de regras (baseline + desvio por sensor)
│   ├── contexto_tecnico.py      # ponte Pilar 1 → Pilar 2: indexa data/json/ por sensor
│   └── monitor_eventos.py       # roda as regras, grava eventos, atualiza status
└── data/
    ├── json/                    # evidência da coleta — 1 JSON por produto (weg/menzel/rsdelivers)
    └── debug/                   # HTML salvo quando um crawler não acha o esperado
```

## Pré-requisitos

- Python 3.13 + Google Chrome instalado (Pilar 1 — os 3 scrapers usam Selenium)
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

`regras_alerta.py` e `contexto_tecnico.py` não dependem de banco nem de Selenium, então têm testes unitários (não cobre os scrapers nem o `monitor_eventos.py`, que dependem de navegador/Postgres de verdade):

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
4. Todos
0. Voltar
```

Cada scraper abre seu próprio Chrome (via `undetected_chromedriver`), roda de forma independente e fecha o navegador sozinho ao terminar — se uma fonte falhar na opção "Todos", as outras continuam.

A opção 3 do menu principal (`verificar_anomalias`):
1. Lê a última leitura de cada TAG no banco.
2. Aplica o motor de regras (`regras_alerta.py`) — 5 sensores, 2 níveis de severidade (alerta/crítico).
3. Pra cada desvio encontrado, busca em `data/json/` (via `contexto_tecnico.py`) alguma referência técnica dos catálogos raspados relacionada àquele sensor, e anexa ao evento.
4. Grava tudo em `evento_alerta` e atualiza `tag.status`.

Depois de rodar, o dashboard da sprint2 (`http://localhost:5173`, com a stack rodando) já mostra os status atualizados — sem precisar mexer no frontend.

## A ponte entre os dois pilares

Os JSONs gerados pelo Pilar 1 não ficam só como evidência estática: `contexto_tecnico.py` os lê e monta um índice por sensor (casando por palavra-chave no nome do campo — ex: qualquer campo raspado contendo "temperat" vira referência do sensor `temperatura`). Quando o motor de regras detecta um desvio, esse contexto é anexado ao evento (`evento_alerta.contexto_tecnico`).

**Importante**: isso é tratado como contexto de **referência de mercado/catálogo**, não como dado exato do ativo físico específico — não existe hoje uma chave que ligue 1:1 um produto raspado a um dos 34 motores da Sprint 2 (os catálogos raspados são uma varredura geral dos sites dos fabricantes, não filtrada por esses ativos).

## Limitações conhecidas

- **Scraping WEG**: `weg.net` está atrás de bot-protection da Akamai. `undetected_chromedriver` contorna o bloqueio por fingerprint, mas sob volume alto de requisições sustentado do mesmo IP real, o site pode bloquear por rate-limit — `src/hydra_driver.py` já tem a lógica de troca de proxy pronta, mas `PROXY_POOL` está vazia (sem proxies reais configurados). Catálogo completo mapeado (~77 categorias / ~463 produtos), mas a extração integral ainda não rodou até o fim por causa disso.
- **Scraping Menzel/RS Delivers**: só testados com amostra pequena (poucos produtos / 1 página), não o catálogo/paginação completos. RS Delivers em particular retorna ~25 mil resultados pra "motores" — a paginação (`max_paginas`, default 5) é um limite prático, não um fim natural dos resultados.
- **Regras de alerta**: os limites em `src/regras_alerta.py` são uma premissa documentada (não vêm de um modelo de ML/DL — não existe um treinado neste projeto), ajustáveis conforme dados reais de falha aparecerem.
- **Contexto técnico**: cobertura depende do que já foi raspado — hoje há referências pra temperatura, tensão, corrente e rotação, mas nenhuma pra vibração (nenhum produto raspado até agora expõe esse campo).
