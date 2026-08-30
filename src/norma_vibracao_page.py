"""
norma_vibracao_page.py
========================
Scraper do Pilar 1 pra uma tabela normativa (não é catálogo de fabricante,
é a própria referência técnica que faltava): a ISO 10816-3 define zonas de
severidade de vibração (A/B/C/D, em mm/s RMS) por classe de máquina. Isso
fecha o único sensor do motor de regras (regras_alerta.py) que não tinha
nenhuma referência raspada em contexto_tecnico.py — os outros 4 sensores já
vinham de campo de catálogo (WEG/Menzel/RS Delivers), vibração não.

A tabela é HTML estático (sem JS pesado), então usa requests + BeautifulSoup
em vez de Selenium — mais simples e mais estável que abrir Chrome pra isso.
"""

import json
import os

import requests
from bs4 import BeautifulSoup

URL = "https://www.fabrico.io/blog/iso-10816-3-vibration-severity/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; DigitalTwinRPA/1.0)"}

base_dir = os.path.dirname(os.path.abspath(__file__))
JSON_DIR = os.path.join(base_dir, "..", "data", "json")
OUTPUT_PATH = os.path.join(JSON_DIR, "norma_iso_10816-3_vibracao.json")


def _extrair_tabela(html):
    """Acha a tabela de zonas A/B/C/D e devolve uma lista de linhas
    (classe da máquina + os 3 limites). Devolve [] se a página mudou de
    estrutura e não achar a tabela esperada."""
    soup = BeautifulSoup(html, "html.parser")
    tabela = soup.find("table")
    if tabela is None:
        return []

    linhas = []
    for tr in tabela.find_all("tr")[1:]:  # pula o cabeçalho
        celulas = [c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
        if len(celulas) == 4:
            linhas.append(celulas)
    return linhas


def run():
    """Baixa a página, extrai a tabela e salva em data/json/ no mesmo
    formato usado pelos outros scrapers (source/product_name/url/
    specifications), pra contexto_tecnico.py conseguir ler igual aos
    demais. Se a página estiver fora do ar ou mudar de estrutura, não
    derruba o programa — só avisa e sai."""
    try:
        resposta = requests.get(URL, headers=HEADERS, timeout=15)
        resposta.raise_for_status()
    except Exception as e:
        print(f"[NORMA VIBRACAO] falha ao acessar a fonte: {e}")
        return

    linhas = _extrair_tabela(resposta.text)
    if not linhas:
        print("[NORMA VIBRACAO] tabela não encontrada na página (estrutura pode ter mudado).")
        return

    specifications = {}
    for classe_maquina, limite_ab, limite_bc, limite_cd in linhas:
        specifications[f"Vibração - {classe_maquina} - limite Zona A/B"] = f"{limite_ab} mm/s"
        specifications[f"Vibração - {classe_maquina} - limite Zona B/C"] = f"{limite_bc} mm/s"
        specifications[f"Vibração - {classe_maquina} - limite Zona C/D"] = f"{limite_cd} mm/s"

    dados = {
        "source": "norma_iso_10816-3",
        "product_name": "ISO 10816-3 - Zonas de severidade de vibração (RMS, mm/s)",
        "url": URL,
        "specifications": specifications,
    }

    os.makedirs(JSON_DIR, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=4)

    print(f"[NORMA VIBRACAO] {len(linhas)} classes de máquina extraídas -> {OUTPUT_PATH}")


if __name__ == "__main__":
    run()
