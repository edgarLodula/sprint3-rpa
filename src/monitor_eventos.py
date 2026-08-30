"""
monitor_eventos.py
===================
Pilar 2 — motor de eventos: pra cada TAG, pega a leitura de sensor mais
recente, roda o motor de regras (regras_alerta.py) e, se tiver desvio,
salva em `evento_alerta` e atualiza o `tag.status` ("normal" / "alerta" /
"critico"). Essa é a mesma coluna que a interface da sprint2-RPA já
mostra, então o dashboard atualiza sozinho sem mexer no frontend.

Cada evento também leva um `contexto_tecnico`, que vem dos JSONs raspados
pelo Pilar 1 (ver contexto_tecnico.py), e uma checagem por um modelo de ML
(IsolationForest, ver deteccao_anomalia_ml.py) treinado no histórico de
leituras do próprio banco: além dos limites fixos por sensor, o modelo
pega combinações de leituras fora do padrão que nenhum limite isolado
capturaria sozinho.
"""

from pathlib import Path

from src.db import get_connection
from src.regras_alerta import avaliar_leitura, severidade_geral
from src.contexto_tecnico import montar_indice, contexto_para_sensor
from src.deteccao_anomalia_ml import treinar as treinar_modelo_ml, prever as prever_ml

INIT_SQL_PATH = Path(__file__).resolve().parent.parent / "db" / "init_eventos.sql"


def garantir_tabela_eventos(conn):
    """Cria a tabela evento_alerta se ela ainda não existir. Pode rodar
    isso várias vezes que não dá problema."""
    with open(INIT_SQL_PATH, "r", encoding="utf-8") as f:
        sql = f.read()
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()


def _ultima_leitura_por_tag(cur):
    cur.execute("""
        SELECT DISTINCT ON (tag_id)
            id, tag_id, timestamp, temperatura, vibracao, corrente, tensao, rotacao
        FROM leitura_sensor
        ORDER BY tag_id, timestamp DESC;
    """)
    return cur.fetchall()


def _historico_leituras(cur, limite=2000):
    """Amostra do histórico de leituras (todas as TAGs juntas) pra treinar
    o modelo de ML. Não precisa ser todo o histórico — só o suficiente pra
    o IsolationForest aprender a faixa normal de operação."""
    cur.execute("""
        SELECT temperatura, vibracao, corrente, tensao, rotacao
        FROM leitura_sensor
        ORDER BY timestamp DESC
        LIMIT %s;
    """, (limite,))
    return cur.fetchall()


def _preparar_modelo_ml(cur):
    """Treina o modelo de ML em cima do histórico do banco. Se der
    qualquer problema (poucas leituras, erro inesperado), devolve None e
    o monitor segue só com o motor de regras — o ML é um reforço, não uma
    dependência dura."""
    try:
        historico = _historico_leituras(cur)
        return treinar_modelo_ml(historico)
    except Exception as e:
        print(f"[ML] não foi possível treinar o modelo, seguindo só com as regras: {e}")
        return None


def verificar_anomalias():
    """Roda o motor de regras na leitura mais recente de cada TAG. Se der
    erro numa TAG, não para as outras — segue igual o rpa_cadastro.py da
    sprint2 já fazia."""
    conn = get_connection()
    garantir_tabela_eventos(conn)
    cur = conn.cursor()

    indice_contexto = montar_indice()
    modelo_ml = _preparar_modelo_ml(cur)
    if modelo_ml is None:
        print("[ML] histórico insuficiente pra treinar o modelo nesta rodada — usando só o motor de regras.")

    cur.execute("SELECT id, status FROM tag;")
    status_atual_por_tag = {row["id"]: row["status"] for row in cur.fetchall()}

    leituras = _ultima_leitura_por_tag(cur)

    eventos_gravados = 0
    tags_atualizadas = 0
    erros = 0

    for leitura in leituras:
        tag_id = leitura["tag_id"]
        try:
            desvios = avaliar_leitura(leitura)
            resultado_ml = prever_ml(modelo_ml, leitura)

            # o motor de regras não enxerga combinação de sensores, só um
            # de cada vez — se nenhum estourou limite individual mas o ML
            # acha o conjunto anômalo, isso vira um desvio à parte
            if resultado_ml and resultado_ml["anomalia"] and not desvios:
                desvios.append({
                    "sensor": "multivariado",
                    "valor_medido": None,
                    "limite_violado": None,
                    "severidade": "alerta",
                    "mensagem": (
                        f"Modelo de ML (IsolationForest) detectou padrão multivariado "
                        f"fora do histórico do ativo (score={resultado_ml['score']:.3f}), "
                        f"mesmo sem nenhum sensor isolado estourar limite fixo."
                    ),
                    "sugestao_acao": "Investigar condição operacional geral do ativo — "
                                      "combinação de leituras foge do padrão histórico aprendido.",
                })

            novo_status = severidade_geral(desvios)
            status_anterior = status_atual_por_tag.get(tag_id, "normal")

            for desvio in desvios:
                contexto = contexto_para_sensor(indice_contexto, desvio["sensor"])

                cur.execute("""
                    INSERT INTO evento_alerta
                        (tag_id, leitura_id, sensor, valor_medido, limite_violado,
                         severidade, mensagem, sugestao_acao, contexto_tecnico,
                         status_anterior, status_novo, deteccao_ml, ml_score)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """, (
                    tag_id, leitura["id"], desvio["sensor"], desvio["valor_medido"],
                    desvio["limite_violado"], desvio["severidade"], desvio["mensagem"],
                    desvio["sugestao_acao"], contexto, status_anterior, novo_status,
                    resultado_ml["anomalia"] if resultado_ml else None,
                    resultado_ml["score"] if resultado_ml else None,
                ))
                eventos_gravados += 1

            if novo_status != status_anterior:
                cur.execute("UPDATE tag SET status = %s, updated_at = NOW() WHERE id = %s;",
                             (novo_status, tag_id))
                tags_atualizadas += 1
                print(f"[STATUS] TAG {tag_id}: {status_anterior} -> {novo_status}")

            conn.commit()

        except Exception as e:
            conn.rollback()
            cur = conn.cursor()
            erros += 1
            print(f"[ERRO] TAG {tag_id}: {e}")

    conn.close()
    print(f"Eventos gravados: {eventos_gravados} | TAGs com status atualizado: {tags_atualizadas} | Erros: {erros}")
    return {"eventos_gravados": eventos_gravados, "tags_atualizadas": tags_atualizadas, "erros": erros}
