"""
rsdelivers_page.py
====================
Scraper de produtos da RS Delivers (int.rsdelivers.com), busca por
"motores". Segue a mesma ideia do scraper WEG: HydraDriver próprio, erro
num produto não derruba o catálogo, HTML de debug salvo quando algo dá
errado.

Três coisas importantes sobre esse site:

1. As especificações do produto vêm de um bloco JSON-LD (aquele
   <script type="application/ld+json"> que os sites usam pra SEO). É bem
   mais estável que ficar pegando classe CSS gerada automaticamente
   (tipo "...module-scss-module__SKXDoW__spec", que muda toda hora que o
   site é atualizado). Por isso o JSON-LD é a forma principal de pegar os
   dados, e o parsing por classe CSS só é usado como fallback se o
   produto não tiver JSON-LD.

2. A paginação pelo link (tipo "...#po=20") não funciona sozinha — testei
   e o site não troca os produtos só de mudar isso na URL. Só funciona
   clicando de verdade no botão "Next".

3. Tem um banner de cookies que atrapalha o clique no botão "Next" se não
   for fechado antes.
"""

import json
import os
from urllib.parse import urlsplit, urlunsplit

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

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

SEARCH_URL = "https://int.rsdelivers.com/productlist/search?query=motores"
PRODUCT_LINK_SELECTOR = 'a[href*="/product/"]'
NEXT_BUTTON_SELECTOR = 'button[class*="next-button"]'
COOKIE_BANNER_ACCEPT_ID = "ensCloseBanner"

# fallback (só usado se o produto não tiver JSON-LD): a classe tem um
# hash que muda, então usamos [class*=] pra pegar mesmo assim
FALLBACK_SPEC_ROW_SELECTOR = '[class*="__spec"]'
FALLBACK_LABEL_SELECTOR = '[class*="__label"]'
FALLBACK_VALUE_SELECTOR = '[class*="__value"]'


def _limpar_url(url):
    """Remove query string (ex: ?backToResults=1) pra dedup e nome de
    arquivo consistentes."""
    partes = urlsplit(url)
    return urlunsplit((partes.scheme, partes.netloc, partes.path, "", ""))


def _fechar_banner_cookies():
    try:
        botao = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.ID, COOKIE_BANNER_ACCEPT_ID))
        )
        botao.click()
        print("[RS] Banner de cookies fechado.")
    except Exception:
        pass  # se o banner não aparecer (já foi aceito antes) tudo bem


def _coletar_links_da_pagina():
    elementos = driver.find_elements(By.CSS_SELECTOR, PRODUCT_LINK_SELECTOR)
    urls = []
    for el in elementos:
        href = el.get_attribute("href")
        if href and "/product/" in href:
            urls.append(_limpar_url(href))
    return list(dict.fromkeys(urls))


def _ir_para_proxima_pagina(primeiro_produto_atual):
    """Clica no botão 'Next' e espera a lista de produtos mudar de verdade
    (o clique sozinho não garante nada, o conteúdo é trocado depois via
    JS). Devolve False se não tinha mais próxima página ou se o clique
    falhou."""
    try:
        botao = driver.find_element(By.CSS_SELECTOR, NEXT_BUTTON_SELECTOR)
    except Exception:
        return False

    if botao.get_attribute("aria-disabled") == "true":
        return False

    try:
        botao.click()
        WebDriverWait(driver, 15).until(
            lambda d: _coletar_links_da_pagina() and _coletar_links_da_pagina()[0] != primeiro_produto_atual
        )
        return True
    except Exception as e:
        print(f"[RS] Falha ao avançar de página: {e}")
        return False


def coletar_urls_com_paginacao(max_paginas=5):
    """Acessa a busca, fecha o banner de cookies, e vai clicando em 'Next'
    até `max_paginas` ou até não haver mais próxima página. Preserva a
    ordem, remove URLs duplicadas."""
    todas_urls = []
    vistas = set()

    driver.get(SEARCH_URL)
    esperar_qualquer(driver, PRODUCT_LINK_SELECTOR, timeout=15)
    _fechar_banner_cookies()

    for pagina in range(max_paginas):
        print(f"[RS] Página {pagina + 1} (offset {pagina * 20})...")
        encontrados = _coletar_links_da_pagina()
        novos = [u for u in encontrados if u not in vistas]
        print(f"[RS] {len(encontrados)} produtos encontrados ({len(novos)} novos).")

        for u in novos:
            vistas.add(u)
            todas_urls.append(u)

        if not encontrados:
            print("[RS] Nenhum produto na página — encerrando paginação.")
            break

        if pagina + 1 >= max_paginas:
            break

        avancou = _ir_para_proxima_pagina(encontrados[0])
        if not avancou:
            print("[RS] Sem próxima página — encerrando paginação.")
            break

    return todas_urls


def _extrair_via_jsonld(soup):
    """Pega as specs do bloco JSON-LD (`additionalProperty` vira
    `specifications`). Esse mesmo bloco também traz sku, categoria, marca
    e imagem do produto, então aproveita e pega tudo junto."""
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(script.string)
        except Exception:
            continue
        if data.get("@type") != "Product":
            continue

        specifications = {}
        for prop in data.get("additionalProperty", []):
            nome = prop.get("name")
            valor = prop.get("value")
            if nome and valor is not None:
                specifications[nome] = valor

        marca = data.get("brand")
        if isinstance(marca, dict):
            marca = marca.get("name")

        imagem = data.get("image")
        if isinstance(imagem, list):
            imagem = imagem[0] if imagem else None

        return {
            "product_name": data.get("name"),
            "specifications": specifications,
            "sku": data.get("sku"),
            "product_id": data.get("productID"),
            "category": data.get("category"),
            "brand": marca,
            "image": imagem,
        }
    return None


def _extrair_via_dom(soup):
    """Fallback: pega os pares label/valor pelo HTML direto. Só é usado se
    o produto não tiver o bloco JSON-LD."""
    specifications = {}
    for bloco in soup.select(FALLBACK_SPEC_ROW_SELECTOR):
        label = bloco.select_one(FALLBACK_LABEL_SELECTOR)
        valor = bloco.select_one(FALLBACK_VALUE_SELECTOR)
        if label and valor:
            chave = label.get_text(strip=True)
            texto_valor = valor.get_text(strip=True)
            if chave and texto_valor:
                specifications[chave] = texto_valor
    return specifications


def extract_product(url):
    """Acessa um produto RS e devolve o dict pronto pra virar JSON, ou None
    se der erro (erro já foi logado/debugado)."""
    try:
        driver.get(url)
        esperar_qualquer(driver, "h1", timeout=15)

        soup = BeautifulSoup(driver.page_source, "html.parser")

        via_jsonld = _extrair_via_jsonld(soup)
        metadados = {}
        if via_jsonld and via_jsonld["specifications"]:
            product_name = via_jsonld["product_name"]
            specifications = via_jsonld["specifications"]
            metadados = {
                "sku": via_jsonld.get("sku"),
                "product_id": via_jsonld.get("product_id"),
                "category": via_jsonld.get("category"),
                "brand": via_jsonld.get("brand"),
                "image": via_jsonld.get("image"),
            }
        else:
            h1 = soup.find("h1")
            product_name = h1.get_text(strip=True) if h1 else None
            specifications = _extrair_via_dom(soup)

        if not product_name:
            h1 = soup.find("h1")
            product_name = h1.get_text(strip=True) if h1 else None

        if not specifications:
            print(f"[RS] nenhuma especificação encontrada em {url}")
            salvar_html_debug(driver, base_dir, url, "rs_sem_specs")

        produto = {
            "source": "rs_delivers",
            "product_name": product_name,
            "url": url,
            "specifications": specifications,
        }
        # só adiciona sku/categoria/marca/imagem se vieram do JSON-LD e
        # tem valor mesmo, senão o JSON fica cheio de campo None à toa
        produto.update({k: v for k, v in metadados.items() if v})
        return produto

    except Exception as e:
        print(f"[RS] Erro em {url}: {e}")
        salvar_html_debug(driver, base_dir, url, "rs_erro")
        return None


def save_product_json(produto):
    os.makedirs(folder, exist_ok=True)
    base_nome = produto.get("product_name") or produto["url"]
    nome_arquivo = f"rsdelivers_{nome_arquivo_seguro(base_nome)}.json"
    path = os.path.join(folder, nome_arquivo)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(produto, f, ensure_ascii=False, indent=4)
    print(f"[RS] JSON salvo: {path}")
    return path


def run(max_paginas=5, max_products=None):
    salvos, total = 0, 0
    try:
        urls = coletar_urls_com_paginacao(max_paginas=max_paginas)
        if max_products:
            urls = urls[:max_products]
        total = len(urls)
        print(f"[RS] {total} URLs únicas encontradas.")

        for i, url in enumerate(urls, start=1):
            print(f"[RS] [{i}/{total}] {url}")
            produto = extract_product(url)
            if produto is None:
                continue
            print(f"[RS] {len(produto['specifications'])} especificações encontradas.")
            save_product_json(produto)
            salvos += 1

    except Exception as e:
        print(f"[RS] Erro fatal no catálogo: {e}")
    finally:
        driver.quit()

    print(f"[RS] Concluído: {salvos}/{total} produtos salvos.")
    return salvos


if __name__ == "__main__":
    run()
