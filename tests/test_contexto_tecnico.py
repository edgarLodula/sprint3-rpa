import unittest

from src.contexto_tecnico import _extrair_numero, contexto_para_sensor, PADROES_POR_SENSOR


class TestExtrairNumero(unittest.TestCase):
    def test_pega_numero_de_texto_com_unidade(self):
        self.assertEqual(_extrair_numero("40°C"), 40.0)

    def test_pega_numero_com_virgula_decimal(self):
        self.assertEqual(_extrair_numero("12,5A"), 12.5)

    def test_texto_sem_numero_devolve_none(self):
        self.assertIsNone(_extrair_numero("F/B"))

    def test_valor_nao_string_devolve_none(self):
        self.assertIsNone(_extrair_numero(["não", "é", "texto"]))


class TestContextoParaSensor(unittest.TestCase):
    def test_sensor_sem_referencia_devolve_none(self):
        indice = {sensor: [] for sensor in PADROES_POR_SENSOR}
        self.assertIsNone(contexto_para_sensor(indice, "vibracao"))

    def test_referencias_com_numero_vem_primeiro(self):
        indice = {
            "temperatura": [
                {"fonte": "menzel", "produto": "SemNumero", "campo": "Thermal utilization", "valor": "F/B", "numero": None},
                {"fonte": "rs_delivers", "produto": "ComNumero", "campo": "Max Temp", "valor": "40°C", "numero": 40.0},
            ]
        }
        texto = contexto_para_sensor(indice, "temperatura")
        # a referência com número (ComNumero) precisa vir antes da sem número (SemNumero)
        self.assertLess(texto.index("ComNumero"), texto.index("SemNumero"))

    def test_respeita_o_limite_de_referencias(self):
        indice = {
            "tensao": [
                {"fonte": "weg", "produto": f"produto{i}", "campo": "Tensão", "valor": "220V", "numero": 220.0}
                for i in range(10)
            ]
        }
        texto = contexto_para_sensor(indice, "tensao", limite=2)
        self.assertEqual(texto.count("weg"), 2)


if __name__ == "__main__":
    unittest.main()
