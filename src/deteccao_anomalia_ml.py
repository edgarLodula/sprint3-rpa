"""
deteccao_anomalia_ml.py
========================
Camada de ML do Pilar 2. O motor de regras (regras_alerta.py) só enxerga
um sensor de cada vez contra um limite fixo — não pega o caso em que
nenhum sensor isolado estourou o limite, mas a combinação das 5 leituras
foge do padrão histórico do ativo (ex: temperatura levemente alta +
corrente levemente alta ao mesmo tempo).

Esse módulo treina um IsolationForest (não supervisionado, porque não
existe rótulo de falha real nesse projeto — ninguém marcou "isso aqui foi
uma falha") em cima do histórico de leituras já gravado no banco, e usa
esse modelo pra sinalizar leituras multivariadas fora do padrão. Ele roda
lado a lado com o motor de regras, não no lugar dele: as regras continuam
responsáveis pela severidade/sugestão de ação por sensor, e o ML cobre o
caso que as regras não enxergam sozinhas.

Se não tiver leitura histórica suficiente (banco novo, poucos dados), o
modelo simplesmente não treina e o monitor_eventos segue só com as regras
— não é um requisito rígido, é um reforço.
"""

from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

SENSORES = ["temperatura", "vibracao", "corrente", "tensao", "rotacao"]
MIN_AMOSTRAS = 30


def _linha_valida(leitura):
    return all(leitura.get(s) is not None for s in SENSORES)


def _para_vetor(leitura):
    return [leitura[s] for s in SENSORES]


def treinar(leituras: list[dict]):
    """Recebe o histórico de leituras (dicts com os 5 sensores) e devolve
    um (scaler, modelo) treinado, ou None se não tiver amostra suficiente
    pra treinar algo confiável."""
    validas = [l for l in leituras if _linha_valida(l)]
    if len(validas) < MIN_AMOSTRAS:
        return None

    X = [_para_vetor(l) for l in validas]
    scaler = StandardScaler().fit(X)
    X_norm = scaler.transform(X)

    modelo = IsolationForest(n_estimators=200, contamination="auto", random_state=42)
    modelo.fit(X_norm)
    return (scaler, modelo)


def prever(modelo_treinado, leitura: dict):
    """Recebe o (scaler, modelo) de treinar() e uma leitura atual. Devolve
    {"anomalia": bool, "score": float} (score menor = mais anômalo) ou
    None se não dá pra avaliar (modelo não treinado ou leitura incompleta)."""
    if modelo_treinado is None or not _linha_valida(leitura):
        return None

    scaler, modelo = modelo_treinado
    x = scaler.transform([_para_vetor(leitura)])
    score = float(modelo.decision_function(x)[0])
    anomalia = bool(modelo.predict(x)[0] == -1)
    return {"anomalia": anomalia, "score": score}
