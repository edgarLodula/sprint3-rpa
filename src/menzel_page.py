"""
menzel_page.py
===============
Scraper do catálogo da MENZEL Motors (menzel-motors.com). Segue a mesma
ideia do scraper WEG (src/weg_page.py): cada um usa seu próprio
HydraDriver, erro num produto não derruba o catálogo inteiro, e salva HTML
em data/debug quando não acha o que precisa.

Esse site não tem proteção contra bot igual a WEG, dá até pra acessar com
curl simples. O ponto chato aqui é achar a lista certa de especificações:
a página tem várias <ul class="o-content-list--unordered">, não só uma —
tem também a lista de tensão nominal (só 2 itens) e listas de aplicação.
Por isso a gente escolhe a lista com mais itens que têm <strong> (ver
_achar_lista_specs). E tem produto (ex: slip-ring-motor/ic01) que nem tem
essa lista de specs, aí só salva vazio mesmo.
"""

import json
import os
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By

try:
    from src.hydra_driver import ProxyPool, HydraDriver, PROXY_POOL
    from src.scraping_utils import esperar_qualquer, salvar_html_debug, nome_arquivo_seguro
except ImportError:
    from hydra_driver import ProxyPool, HydraDriver, PROXY_POOL
    from scraping_utils import esperar_qualquer, salvar_html_debug, nome_arquivo_seguro


pool = ProxyPool(PROXY_POOL)
driver = HydraDriver(pool)
base_dir = os.path.dirname(os.path.abspath(__file__))
folder = os.path.join(base_dir, "..", "data", "json")

CATALOGO_URL = "https://www.menzel-motors.com/catalogue/"
PRODUCT_INFO_SELECTOR = "a.o-button--tertiary.o-button--small"
SPECS_MIN_ITENS = 3  # abaixo disso é provavelmente a lista de tensão (2 itens), não as specs


def get_product_links():
    """Acessa o catálogo e devolve as URLs (absolutas, sem duplicata, ordem
    preservada) dos links cujo texto é exatamente 'Product info'."""
    driver.get(CATALOGO_URL)
    esperar_qualquer(driver, PRODUCT_INFO_SELECTOR)

    candidatos = driver.find_elements(By.CSS_SELECTOR, PRODUCT_INFO_SELECTOR)
    urls = []
    for a in candidatos:
        # a.text vem vazio porque esses links ficam numa tabela escondida
        # via CSS. textContent funciona mesmo o elemento estando escondido.
        texto = (a.get_attribute("textContent") or "").strip()
        if texto != "Product info":
            continue
        href = a.get_attribute("href")
        if href:
            urls.append(urljoin(CATALOGO_URL, href))

    return list(dict.fromkeys(urls))  # remove duplicata, preserva ordem


def _achar_lista_specs(soup):
    """A página tem várias <ul class="o-content-list--unordered">. Essa
    função escolhe a que parece ser a de especificações: a que tem mais
    <li> com <strong> dentro, com um mínimo de itens (SPECS_MIN_ITENS) pra
    não confundir com a lista pequena de tensão nominal."""
    melhor, melhor_score = None, 0
    for ul in soup.find_all("ul", class_="o-content-list--unordered"):
        itens = ul.find_all("li", recursive=False)
        com_strong = sum(1 for li in itens if li.find("strong"))
        if com_strong >= SPECS_MIN_ITENS and com_strong > melhor_score:
            melhor, melhor_score = ul, com_strong
    return melhor


def parse_specifications(soup):
    """Pega as specs da lista encontrada. Tem dois formatos de <li>: um com
    chave e valor ("<strong>Chave:</strong> valor"), que vira entrada no
    dict; outro só com um texto em negrito, sem valor, que vai pra
    `features`. Se a mesma chave aparecer duas vezes, vira uma lista em vez
    de sobrescrever o valor anterior."""
    especificacoes = {}
    features = []

    lista = _achar_lista_specs(soup)
    if lista is None:
        return especificacoes, features

    for li in lista.find_all("li", recursive=False):
        strong = li.find("strong")
        if strong is None:
            texto = li.get_text(" ", strip=True)
            if texto:
                features.append(texto)
            continue

        texto_strong = strong.get_text(strip=True)
        chave = texto_strong.rstrip(":").strip()

        valor = li.get_text(" ", strip=True)
        if valor.startswith(texto_strong):
            valor = valor[len(texto_strong):]
        valor = " ".join(valor.lstrip(": ").split())  # tira espaço/&nbsp; extra, sem mudar o conteúdo

        if not valor:
            # não tem valor depois do <strong>, então é um bullet tipo
            # "For grid and inverter operation" — vai pra features
            features.append(chave)
            continue

        if chave in especificacoes:
            existente = especificacoes[chave]
            especificacoes[chave] = existente + [valor] if isinstance(existente, list) else [existente, valor]
        else:
            especificacoes[chave] = valor

    return especificacoes, features


def extract_product(url):
    """Acessa um produto Menzel e devolve o dict pronto pra virar JSON, ou
    None se der erro (erro já foi logado/debugado)."""
    try:
        driver.get(url)
        esperar_qualquer(driver, "h1")

        soup = BeautifulSoup(driver.page_source, "html.parser")

        h1 = soup.find("h1")
        product_name = h1.get_text(strip=True) if h1 else None

        specifications, features = parse_specifications(soup)

        if not specifications and not features:
            print(f"[MENZEL] nenhuma especificação encontrada em {url}")
            salvar_html_debug(driver, base_dir, url, "menzel_sem_specs")

        return {
            "source": "menzel",
            "product_name": product_name,
            "url": url,
            "specifications": specifications,
            "features": features,
        }

    except Exception as e:
        print(f"[MENZEL] Erro em {url}: {e}")
        salvar_html_debug(driver, base_dir, url, "menzel_erro")
        return None


def save_product_json(produto):
    os.makedirs(folder, exist_ok=True)
    base_nome = produto.get("product_name") or produto["url"]
    nome_arquivo = f"menzel_{nome_arquivo_seguro(base_nome)}.json"
    path = os.path.join(folder, nome_arquivo)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(produto, f, ensure_ascii=False, indent=4)
    print(f"[MENZEL] JSON salvo: {path}")
    return path


def run(max_products=None):
    salvos, total = 0, 0
    try:
        print("[MENZEL] Coletando catálogo...")
        urls = get_product_links()
        if max_products:
            urls = urls[:max_products]
        total = len(urls)
        print(f"[MENZEL] {total} URLs únicas encontradas.")

        for i, url in enumerate(urls, start=1):
            print(f"[MENZEL] [{i}/{total}] {url}")
            produto = extract_product(url)
            if produto is None:
                continue
            print(f"[MENZEL] {len(produto['specifications'])} especificações encontradas.")
            save_product_json(produto)
            salvos += 1

    except Exception as e:
        print(f"[MENZEL] Erro fatal no catálogo: {e}")
    finally:
        driver.quit()

    print(f"[MENZEL] Concluído: {salvos}/{total} produtos salvos.")
    return salvos


if __name__ == "__main__":
    run()
