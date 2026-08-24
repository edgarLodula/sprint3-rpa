"""
scraping_utils.py
==================
Funções pequenas usadas tanto no menzel_page.py quanto no rsdelivers_page.py,
pra não repetir código. O weg_page.py não usa isso, ele já tinha essas
mesmas funções antes e não precisava mexer nele.
"""

import os
import re

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def esperar_qualquer(driver, css_selector, timeout=10):
    """Espera até `timeout`s um elemento com esse seletor aparecer na
    página. Não dá erro se não aparecer, só continua depois do tempo."""
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, css_selector))
        )
    except Exception:
        pass


def salvar_html_debug(driver, base_dir, url, prefixo, html=None):
    """Salva o HTML em data/debug/ pra dar uma olhada depois, quando o
    crawler não acha o que precisava."""
    try:
        conteudo = html if html is not None else driver.page_source
        debug_dir = os.path.join(base_dir, "..", "data", "debug")
        os.makedirs(debug_dir, exist_ok=True)
        nome = re.sub(r'[^a-zA-Z0-9]+', '_', url)[-80:]
        path = os.path.join(debug_dir, f"{prefixo}_{nome}.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(conteudo)
        print(f"[DEBUG] HTML salvo em {path}")
    except Exception as e:
        print(f"[DEBUG] falhou ao salvar HTML: {e}")


def nome_arquivo_seguro(texto, limite=120):
    """Deixa o texto seguro pra usar como nome de arquivo no Windows
    (tira / \\ : ? * e outros caracteres que dão problema)."""
    limpo = re.sub(r'[^a-zA-Z0-9._-]+', '_', texto).strip('_')
    return limpo[:limite] or "produto"
