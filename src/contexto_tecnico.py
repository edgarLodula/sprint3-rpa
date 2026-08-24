"""
contexto_tecnico.py
=====================
Liga o Pilar 1 (scraping) com o Pilar 2 (motor de regras). Antes disso os
dois não se conversavam: os JSONs raspados ficavam parados em data/json/ e
a sugestão de ação do motor de regras era só um texto fixo por sensor.

Como funciona: lê todos os JSONs de data/json/ e procura campos que batem
com o nome do sensor (ex: campo com "temperat" no nome vira referência do
sensor temperatura). Quando o motor de regras acha um desvio, busca aqui
se tem alguma info relacionada nos catálogos raspados e anexa no evento.

Importante: isso é um contexto de referência geral (tipo "esse modelo de
motor controller aguenta até 40°C, segundo a RS Delivers"), não é o dado
exato do ativo específico que gerou o alerta. Não temos como ligar 1:1 um
produto raspado com um ativo do banco, porque o scraping é uma varredura
geral do site do fabricante, não filtrada pelos 34 motores da Sprint 2.
"""

import glob
import json
import os
import re

base_dir = os.path.dirname(os.path.abspath(__file__))
JSON_DIR = os.path.join(base_dir, "..", "data", "json")

# pra cada sensor, lista de padrões de texto que o nome do campo raspado
# pode ter (ignora maiúscula/minúscula)
PADROES_POR_SENSOR = {
    "temperatura": [r"temperat"],
    "tensao": [r"tens[aã]o", r"voltage"],
    "corrente": [r"corrente", r"\bcurrent\b"],
    "rotacao": [r"rota[cç][aã]o", r"\brpm\b"],
    "vibracao": [r"vibra[cç][aã]o", r"vibration"],
}

_NUM_RE = re.compile(r"-?\d+(?:[.,]\d+)?")


def _extrair_numero(texto):
    """Pega o primeiro número do texto (ex: '40°C' vira 40.0). Se não tem
    número (ex: 'F/B'), devolve None."""
    if not isinstance(texto, str):
        return None
    m = _NUM_RE.search(texto.replace(",", "."))
    return float(m.group()) if m else None


def _carregar_produtos():
    """Lê todos os arquivos de data/json/. O JSON da WEG guarda as specs
    direto no arquivo, já o da Menzel/RS guarda dentro de
    "specifications" — essa função lida com os dois formatos."""
    produtos = []
    for path in glob.glob(os.path.join(JSON_DIR, "*.json")):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        specs = data.get("specifications", data) if isinstance(data, dict) else None
        if not isinstance(specs, dict):
            continue
        fonte = data.get("source", "weg")
        nome = data.get("product_name") or os.path.splitext(os.path.basename(path))[0]
        produtos.append((fonte, nome, specs))
    return produtos


def montar_indice():
    """Monta um dict {sensor: [lista de referências]}. É chamado uma vez
    só no início do monitor_eventos, não pra cada TAG, senão ficaria lendo
    o disco toda hora à toa."""
    indice = {sensor: [] for sensor in PADROES_POR_SENSOR}
    for fonte, nome_produto, specs in _carregar_produtos():
        for campo, valor in specs.items():
            if not isinstance(campo, str):
                continue
            for sensor, padroes in PADROES_POR_SENSOR.items():
                if any(re.search(p, campo, re.IGNORECASE) for p in padroes):
                    valor_texto = valor if isinstance(valor, str) else json.dumps(valor, ensure_ascii=False)
                    indice[sensor].append({
                        "fonte": fonte,
                        "produto": nome_produto,
                        "campo": campo,
                        "valor": valor_texto,
                        "numero": _extrair_numero(valor_texto),
                    })
    return indice


def contexto_para_sensor(indice, sensor, limite=3):
    """Devolve um texto com até `limite` referências pra colar na
    sugestão de ação, ou None se não achou nada. Referências com número
    vêm primeiro (dá pra comparar com a leitura), o resto vem depois."""
    referencias = indice.get(sensor, [])
    if not referencias:
        return None

    com_numero = [r for r in referencias if r["numero"] is not None]
    sem_numero = [r for r in referencias if r["numero"] is None]
    ordenadas = com_numero + sem_numero

    trechos = [f"{r['produto']} ({r['fonte']}): {r['campo']} = {r['valor']}" for r in ordenadas[:limite]]
    return "Contexto técnico (catálogos raspados) — " + "; ".join(trechos)
