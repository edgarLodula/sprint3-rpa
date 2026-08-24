"""
regras_alerta.py
=================
Motor de regras do Pilar 2. Não mexe com banco nem Selenium, só recebe uma
leitura (dict com os 5 sensores) e devolve os desvios encontrados.

Os limites (LIMITES abaixo) são baseados na mesma regra que a sprint2-RPA
já usava pra gerar os dados sintéticos (temperatura > 85 ou vibração > 10 =
"alerta"), só que agora com um nível a mais ("critico") e cobrindo os
outros 3 sensores também. Como não temos um dataset de falha real pra
calibrar isso direito, os valores são um chute razoável — dá pra ajustar
fácil aqui se precisar.
"""

LIMITES = {
    "temperatura": {"alerta": (">", 85), "critico": (">", 92)},
    "vibracao":    {"alerta": (">", 10), "critico": (">", 11.5)},
    "corrente":    {"alerta": (">", 26), "critico": (">", 29)},
    "tensao_alta": {"alerta": (">", 225), "critico": (">", 227), "sensor": "tensao"},
    "tensao_baixa": {"alerta": ("<", 215), "critico": ("<", 213), "sensor": "tensao"},
    "rotacao":     {"alerta": ("<", 1465), "critico": ("<", 1455)},
}

SUGESTAO_ACAO = {
    "temperatura": "Verificar sistema de ventilação/refrigeração e carga aplicada ao motor.",
    "vibracao": "Inspecionar alinhamento do eixo, balanceamento e estado dos rolamentos.",
    "corrente": "Verificar carga mecânica excessiva ou desequilíbrio de fase.",
    "tensao": "Verificar qualidade da alimentação elétrica (quedas/picos de tensão).",
    "rotacao": "Verificar escorregamento do rotor, carga no eixo ou falha de acionamento.",
}

SEVERIDADE_ORDEM = {"normal": 0, "alerta": 1, "critico": 2}


def _viola(valor, operador, limite):
    if valor is None:
        return False
    return valor > limite if operador == ">" else valor < limite


def avaliar_leitura(leitura: dict) -> list[dict]:
    """Recebe uma leitura (dict com temperatura, vibracao, corrente,
    tensao, rotacao) e devolve a lista de desvios encontrados, cada um
    já com a pior severidade que bateu naquele sensor."""
    desvios = []

    for regra_nome, regra in LIMITES.items():
        sensor = regra.get("sensor", regra_nome)
        valor = leitura.get(sensor)
        if valor is None:
            continue

        severidade_atingida = None
        limite_atingido = None
        for severidade in ("critico", "alerta"):
            if severidade not in regra:
                continue
            operador, limite = regra[severidade]
            if _viola(valor, operador, limite):
                severidade_atingida = severidade
                limite_atingido = limite
                break  # checa critico antes de alerta, então já para no pior caso

        if severidade_atingida:
            desvios.append({
                "sensor": sensor,
                "valor_medido": valor,
                "limite_violado": limite_atingido,
                "severidade": severidade_atingida,
                "mensagem": f"{sensor} = {valor} ultrapassou limite de {severidade_atingida} ({limite_atingido})",
                "sugestao_acao": SUGESTAO_ACAO.get(sensor, "Verificar manualmente."),
            })

    return desvios


def severidade_geral(desvios: list[dict]) -> str:
    """Devolve a pior severidade entre os desvios, ou 'normal' se a lista
    estiver vazia."""
    if not desvios:
        return "normal"
    return max((d["severidade"] for d in desvios), key=lambda s: SEVERIDADE_ORDEM[s])
