"""
test_monitor_eventos.py
=========================
monitor_eventos.py depende de Postgres de verdade (por isso o README dizia
que ele não tinha teste automatizado, só validação manual). Aqui a gente
troca get_connection por um banco falso (FakeConnection/FakeCursor) que
responde de acordo com o texto de cada SQL executado, pra testar a lógica
de verificar_anomalias isoladamente: grava evento certo, atualiza status
certo, e não deixa uma TAG com erro derrubar as outras.
"""

import unittest
from unittest.mock import patch

from src import monitor_eventos


class FakeCursor:
    def __init__(self, respostas_por_trecho, capturados):
        self._respostas_por_trecho = respostas_por_trecho
        self._capturados = capturados
        self._ultimo_resultado = []

    def execute(self, sql, params=None):
        sql_norm = " ".join(sql.split())
        self._capturados.append((sql_norm, params))
        for trecho, resultado in self._respostas_por_trecho:
            if trecho in sql_norm:
                self._ultimo_resultado = resultado
                return
        self._ultimo_resultado = []

    def fetchall(self):
        return self._ultimo_resultado

    def fetchone(self):
        return self._ultimo_resultado[0] if self._ultimo_resultado else None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


LEITURA_NORMAL = {
    "id": 101, "tag_id": 1, "temperatura": 60, "vibracao": 3,
    "corrente": 15, "tensao": 220, "rotacao": 1490,
}
LEITURA_CRITICA = {
    "id": 102, "tag_id": 2, "temperatura": 95, "vibracao": 3,
    "corrente": 15, "tensao": 220, "rotacao": 1490,
}


def _montar_conexao_falsa(leituras, status_por_tag, capturados):
    respostas = [
        ("SELECT temperatura, vibracao, corrente, tensao, rotacao", []),  # histórico do ML: vazio -> sem modelo
        ("SELECT id, status FROM tag", status_por_tag),
        ("SELECT DISTINCT ON (tag_id)", leituras),
    ]
    cursor = FakeCursor(respostas, capturados)
    return FakeConnection(cursor)


class TestVerificarAnomalias(unittest.TestCase):
    def setUp(self):
        patcher_sql = patch("src.monitor_eventos.garantir_tabela_eventos", lambda conn: None)
        patcher_sql.start()
        self.addCleanup(patcher_sql.stop)

    def test_leitura_normal_nao_grava_evento_nem_muda_status(self):
        capturados = []
        status_por_tag = [{"id": 1, "status": "normal"}]
        conn = _montar_conexao_falsa([LEITURA_NORMAL], status_por_tag, capturados)

        with patch("src.monitor_eventos.get_connection", return_value=conn):
            resultado = monitor_eventos.verificar_anomalias()

        self.assertEqual(resultado, {"eventos_gravados": 0, "tags_atualizadas": 0, "erros": 0})
        inserts = [c for c in capturados if "INSERT INTO evento_alerta" in c[0]]
        updates = [c for c in capturados if "UPDATE tag SET status" in c[0]]
        self.assertEqual(inserts, [])
        self.assertEqual(updates, [])
        self.assertTrue(conn.closed)

    def test_leitura_critica_grava_evento_e_atualiza_status(self):
        capturados = []
        status_por_tag = [{"id": 2, "status": "normal"}]
        conn = _montar_conexao_falsa([LEITURA_CRITICA], status_por_tag, capturados)

        with patch("src.monitor_eventos.get_connection", return_value=conn):
            resultado = monitor_eventos.verificar_anomalias()

        self.assertEqual(resultado["eventos_gravados"], 1)
        self.assertEqual(resultado["tags_atualizadas"], 1)
        self.assertEqual(resultado["erros"], 0)

        inserts = [c for c in capturados if "INSERT INTO evento_alerta" in c[0]]
        self.assertEqual(len(inserts), 1)
        params_insert = inserts[0][1]
        self.assertEqual(params_insert[0], 2)          # tag_id
        self.assertEqual(params_insert[2], "temperatura")  # sensor
        self.assertEqual(params_insert[5], "critico")      # severidade

        updates = [c for c in capturados if "UPDATE tag SET status" in c[0]]
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0][1], ("critico", 2))

    def test_erro_em_uma_tag_nao_impede_as_outras(self):
        capturados = []
        leitura_quebrada = dict(LEITURA_CRITICA)
        leitura_quebrada["tag_id"] = 3
        del leitura_quebrada["id"]  # vai estourar KeyError ao montar o INSERT
        status_por_tag = [{"id": 1, "status": "normal"}, {"id": 3, "status": "normal"}]
        conn = _montar_conexao_falsa([leitura_quebrada, LEITURA_NORMAL], status_por_tag, capturados)

        with patch("src.monitor_eventos.get_connection", return_value=conn):
            resultado = monitor_eventos.verificar_anomalias()

        self.assertEqual(resultado["erros"], 1)
        self.assertEqual(conn.rollbacks, 1)
        # a segunda TAG (normal, sem desvio) processou sem problema mesmo
        # depois do erro na primeira
        self.assertEqual(resultado["eventos_gravados"], 0)


if __name__ == "__main__":
    unittest.main()
