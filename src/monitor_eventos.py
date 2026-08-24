"""
monitor_eventos.py
===================
Pilar 2 — motor de eventos: pra cada TAG, pega a leitura de sensor mais
recente, roda o motor de regras (regras_alerta.py) e, se tiver desvio,
salva em `evento_alerta` e atualiza o `tag.status` ("normal" / "alerta" /
"critico"). Essa é a mesma coluna que a interface da sprint2-RPA já
mostra, então o dashboard atualiza sozinho sem mexer no frontend.

Cada evento também leva um `contexto_tecnico`, que vem dos JSONs raspados
pelo Pilar 1 (ver contexto_tecnico.py).
"""

from pathlib import Path

from src.db import get_connection
from src.regras_alerta import avaliar_leitura, severidade_geral
from src.contexto_tecnico import montar_indice, contexto_para_sensor

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


def verificar_anomalias():
    """Roda o motor de regras na leitura mais recente de cada TAG. Se der
    erro numa TAG, não para as outras — segue igual o rpa_cadastro.py da
    sprint2 já fazia."""
    conn = get_connection()
    garantir_tabela_eventos(conn)
    cur = conn.cursor()

    indice_contexto = montar_indice()

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
            novo_status = severidade_geral(desvios)
            status_anterior = status_atual_por_tag.get(tag_id, "normal")

            for desvio in desvios:
                contexto = contexto_para_sensor(indice_contexto, desvio["sensor"])

                cur.execute("""
                    INSERT INTO evento_alerta
                        (tag_id, leitura_id, sensor, valor_medido, limite_violado,
                         severidade, mensagem, sugestao_acao, contexto_tecnico,
                         status_anterior, status_novo)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """, (
                    tag_id, leitura["id"], desvio["sensor"], desvio["valor_medido"],
                    desvio["limite_violado"], desvio["severidade"], desvio["mensagem"],
                    desvio["sugestao_acao"], contexto, status_anterior, novo_status,
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
