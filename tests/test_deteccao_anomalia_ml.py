import random
import unittest

from src.deteccao_anomalia_ml import treinar, prever, MIN_AMOSTRAS


def _leitura_normal(rng):
    return {
        "temperatura": rng.gauss(70, 3),
        "vibracao": rng.gauss(4, 0.5),
        "corrente": rng.gauss(18, 1),
        "tensao": rng.gauss(220, 2),
        "rotacao": rng.gauss(1480, 5),
    }


class TestTreinar(unittest.TestCase):
    def test_poucas_amostras_nao_treina(self):
        rng = random.Random(42)
        leituras = [_leitura_normal(rng) for _ in range(MIN_AMOSTRAS - 1)]
        self.assertIsNone(treinar(leituras))

    def test_leituras_incompletas_sao_ignoradas_na_contagem(self):
        rng = random.Random(42)
        completas = [_leitura_normal(rng) for _ in range(MIN_AMOSTRAS)]
        incompletas = [{"temperatura": 70} for _ in range(50)]
        self.assertIsNotNone(treinar(completas + incompletas))

    def test_treina_com_amostras_suficientes(self):
        rng = random.Random(42)
        leituras = [_leitura_normal(rng) for _ in range(200)]
        self.assertIsNotNone(treinar(leituras))


class TestPrever(unittest.TestCase):
    def setUp(self):
        rng = random.Random(7)
        self.historico = [_leitura_normal(rng) for _ in range(300)]
        self.modelo = treinar(self.historico)

    def test_modelo_nao_treinado_devolve_none(self):
        self.assertIsNone(prever(None, _leitura_normal(random.Random(1))))

    def test_leitura_incompleta_devolve_none(self):
        self.assertIsNone(prever(self.modelo, {"temperatura": 70}))

    def test_leitura_tipica_nao_e_anomalia(self):
        rng = random.Random(99)
        resultado = prever(self.modelo, _leitura_normal(rng))
        self.assertFalse(resultado["anomalia"])

    def test_combinacao_fora_do_padrao_e_anomalia_mesmo_sem_estourar_limite_isolado(self):
        # nenhum valor aqui estoura o limite fixo do regras_alerta.py sozinho,
        # mas a combinação (temperatura e corrente subindo juntas, fora da
        # correlação normal do histórico) foge do padrão aprendido
        leitura_suspeita = {
            "temperatura": 84,
            "vibracao": 4,
            "corrente": 25,
            "tensao": 220,
            "rotacao": 1480,
        }
        resultado = prever(self.modelo, leitura_suspeita)
        self.assertTrue(resultado["anomalia"])


if __name__ == "__main__":
    unittest.main()
