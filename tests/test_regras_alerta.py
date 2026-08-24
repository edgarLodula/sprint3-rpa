import unittest

from src.regras_alerta import avaliar_leitura, severidade_geral


class TestAvaliarLeitura(unittest.TestCase):
    def test_leitura_normal_nao_gera_desvio(self):
        leitura = {"temperatura": 60, "vibracao": 3, "corrente": 15, "tensao": 220, "rotacao": 1490}
        desvios = avaliar_leitura(leitura)
        self.assertEqual(desvios, [])

    def test_temperatura_acima_do_limite_gera_alerta(self):
        leitura = {"temperatura": 88, "vibracao": 3, "corrente": 15, "tensao": 220, "rotacao": 1490}
        desvios = avaliar_leitura(leitura)
        self.assertEqual(len(desvios), 1)
        self.assertEqual(desvios[0]["sensor"], "temperatura")
        self.assertEqual(desvios[0]["severidade"], "alerta")

    def test_temperatura_bem_acima_gera_critico_nao_os_dois(self):
        leitura = {"temperatura": 95, "vibracao": 3, "corrente": 15, "tensao": 220, "rotacao": 1490}
        desvios = avaliar_leitura(leitura)
        self.assertEqual(len(desvios), 1)
        self.assertEqual(desvios[0]["severidade"], "critico")

    def test_tensao_baixa_tambem_conta_como_desvio(self):
        leitura = {"temperatura": 60, "vibracao": 3, "corrente": 15, "tensao": 210, "rotacao": 1490}
        desvios = avaliar_leitura(leitura)
        self.assertEqual(len(desvios), 1)
        self.assertEqual(desvios[0]["sensor"], "tensao")

    def test_varios_sensores_ruins_ao_mesmo_tempo(self):
        leitura = {"temperatura": 95, "vibracao": 12, "corrente": 30, "tensao": 230, "rotacao": 1440}
        desvios = avaliar_leitura(leitura)
        sensores = {d["sensor"] for d in desvios}
        self.assertEqual(sensores, {"temperatura", "vibracao", "corrente", "tensao", "rotacao"})

    def test_sensor_ausente_na_leitura_e_ignorado(self):
        leitura = {"temperatura": 95}
        desvios = avaliar_leitura(leitura)
        self.assertEqual(len(desvios), 1)
        self.assertEqual(desvios[0]["sensor"], "temperatura")


class TestSeveridadeGeral(unittest.TestCase):
    def test_sem_desvios_e_normal(self):
        self.assertEqual(severidade_geral([]), "normal")

    def test_pega_a_pior_severidade(self):
        desvios = [{"severidade": "alerta"}, {"severidade": "critico"}, {"severidade": "alerta"}]
        self.assertEqual(severidade_geral(desvios), "critico")


if __name__ == "__main__":
    unittest.main()
