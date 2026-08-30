
import json
import os
import random
import re
import time
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

try:
    from src.hydra_driver import ProxyPool, HydraDriver, PROXY_POOL
except ImportError:
    from hydra_driver import ProxyPool, HydraDriver, PROXY_POOL


# o HydraDriver troca de proxy sozinho quando a WEG bloqueia o acesso.
# ele delega tudo (get, find_elements, etc) pro driver de verdade por baixo.
pool = ProxyPool(PROXY_POOL)
driver = HydraDriver(pool)
base_dir = os.path.dirname(os.path.abspath(__file__))
folder = os.path.join(base_dir, "..", "data", "json")


def _salvar_html_debug(url, prefixo, html=None):
    """Salva o HTML da página em data/debug pra dar uma olhada depois
    quando o crawler não acha o que precisa. Se `html` não for passado,
    salva a página que está aberta no driver agora."""
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


def _specs_de_html(html):
    # a tabela de specs do produto fica dentro de div.product-info-specs.
    # a página tem várias outras <table>, então não dá pra pegar a primeira.
    soup = BeautifulSoup(html, "html.parser")
    elemento = soup.select_one("div.product-info-specs")
    if elemento is None:
        return None

    table_line_value = [td.get_text(strip=True) for td in elemento.find_all("td")]
    table_line_head = [th.get_text(strip=True) for th in elemento.find_all("th")]
    if not table_line_head or not table_line_value:
        return None

    return dict(zip(table_line_head, table_line_value))


def get_weg_talbe(table_page):
    try:
        driver.get(table_page)
        wait = WebDriverWait(driver, 10)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.product-info-specs")))

        dic = _specs_de_html(driver.page_source)
        if dic is None:
            raise ValueError("Nenhum th/td encontrado em product-info-specs")
    except Exception as e:
        print(f'[TABELA] Error em {table_page}: {e}')
        _salvar_html_debug(table_page, "tabela_falhou")
        return

    # usa o código do produto (da URL) como nome do arquivo, porque o
    # título repete entre produtos parecidos e ia sobrescrever o JSON
    match = re.search(r'/p/([^/?#]+)', table_page)
    nome_arquivo = match.group(1) if match else "produto"

    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{nome_arquivo}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(dic, f, ensure_ascii=False, indent=4)
    print(f"[JSON] {path}")

    # respiro entre produtos pra não parecer um robô martelando o site —
    # delay fixo é detectável, por isso o jitter. Isso ataca direto o
    # bloqueio por volume: antes o crawler ia num produto atrás do outro
    # sem pausa nenhuma entre eles.
    time.sleep(random.uniform(2.5, 6.0))


def _hrefs_diretos(elements):
    """Pega o href de cada <li> agora mesmo, antes de navegar pra próxima
    página. Se esperar, o elemento fica "velho" (stale) e dá erro."""
    urls = []
    for li in elements:
        try:
            href = li.find_element(By.XPATH, './a').get_attribute('href')
        except Exception:
            href = None
        if href:
            urls.append(href)
    return urls


def _codigo_categoria(url):
    """Pega o código da categoria que fica em .../c/<codigo>. Usar só o
    código é mais seguro que comparar a URL inteira, porque a URL pode vir
    com parâmetros a mais (tipo ?h=...)."""
    match = re.search(r'/c/([^/?#]+)', url)
    return match.group(1) if match else None


def _submenu_da_categoria_atual(url):
    """O menu do site (li[data-level]) mostra a árvore de categorias
    inteira em qualquer página, não só as filhas da categoria atual. Por
    isso não dá pra simplesmente pegar todo li[data-level="2"] da página —
    precisa achar o <li> certo (pelo código da categoria) e olhar só os
    filhos dele, senão o crawler acaba entrando em categorias de outros
    produtos tipo tinta e automação."""
    codigo = _codigo_categoria(url)
    if not codigo:
        return []
    try:
        link_atual = driver.find_element(
            By.XPATH, f'//li[@data-level]/a[contains(@href, "/c/{codigo}")]')
        li_atual = link_atual.find_element(By.XPATH, './..')
        return li_atual.find_elements(By.XPATH, './ul/li[@data-level]')
    except Exception:
        return []


FACET_CATEGORIES_SELECTOR = '#productCategories a.xtt-url-categories, #productCategories a.add-hash-to-category-url'


def _submenu_facet(url):
    """Algumas páginas têm subcategorias que não aparecem no menu normal,
    só num filtro (#productCategories). Sem checar isso a gente perdia
    produtos inteiros que só existem atrás desse filtro."""
    try:
        links = driver.find_elements(By.CSS_SELECTOR, FACET_CATEGORIES_SELECTOR)
        urls = [href for href in (l.get_attribute('href') for l in links) if href]
        return list(dict.fromkeys(urls))
    except Exception:
        return []


def _debug_sem_caminho(url):
    """Quando a página não tem nem submenu nem botão de seleção de
    produtos, salva o HTML e lista os li[data-level] encontrados pra
    ajudar a entender o que rolou depois."""
    try:
        candidatos = driver.find_elements(By.CSS_SELECTOR, 'li[data-level]')
        print(f"[DEBUG] {len(candidatos)} li[data-level] encontrados (qualquer class) em {url}")
        for li in candidatos[:20]:
            nivel = li.get_attribute('data-level')
            classe = li.get_attribute('class')
            print(f"[DEBUG]   data-level={nivel!r} class={classe!r}")

        _salvar_html_debug(url, "sem_caminho")
    except Exception as e:
        print(f"[DEBUG] falhou ao coletar diagnóstico: {e}")


def _esperar_qualquer(css_selector, timeout=10):
    """Espera até `timeout`s um elemento aparecer na página antes de
    continuar. Sem isso, o código pode tentar pegar um elemento que ainda
    não carregou e vir vazio."""
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, css_selector))
        )
    except Exception:
        pass


# pra achar os produtos precisa primeiro achar o botão de "modo lista"
# (que tem o link de verdade) e só depois seguir pra listagem final
LAYOUT_LIST_SELECTOR = 'a.xtt-layout-list[data-link]'
FINAL_PRODUCTS_SELECTOR = 'a[target="_self"]'

# o site mostra o botão de "seleção de produtos" de dois jeitos diferentes
# dependendo da página, então cobre os dois
PRODUCTS_SELECTION_SELECTOR = 'li#products-selection > a, a#productsSelection'

_JS_FETCH_XHR = """
const url = arguments[0];
const callback = arguments[arguments.length - 1];
fetch(url, {
    credentials: 'same-origin',
    headers: { 'X-Requested-With': 'XMLHttpRequest' }
})
.then(r => r.text().then(t => callback({status: r.status, body: t})))
.catch(e => callback({status: -1, body: String(e)}));
"""


def _buscar_html_ajax(url, timeout=20):
    """Esse endpoint só devolve o resultado certo quando chamado como ajax
    (com o header X-Requested-With). Chamando direto com driver.get() ele
    devolve uma página de erro. Por isso faz a chamada de dentro do próprio
    navegador, assim aproveita os cookies da sessão que já está aberta."""
    driver.set_script_timeout(timeout)
    try:
        resultado = driver.execute_async_script(_JS_FETCH_XHR, url)
    except Exception as e:
        print(f"[AJAX] falha ao buscar {url}: {e}")
        return None

    if resultado.get("status") != 200:
        print(f"[AJAX] {url} respondeu status {resultado.get('status')}")
        return None

    return resultado.get("body")


def process_page(url, visited):
    """Decide o que fazer olhando a página atual: se a categoria tem
    submenu (filhos no menu), desce por eles; se não tem, procura o botão
    de seleção de produtos e vai até a listagem final."""
    if url in visited:
        return
    visited.add(url)

    try:
        driver.get(url)
        _esperar_qualquer(f'li[data-level], {PRODUCTS_SELECTION_SELECTOR}, {FACET_CATEGORIES_SELECTOR}')

        submenu_items = _submenu_da_categoria_atual(url)

        if submenu_items:
            print(f"[LEVEL] {url}")
            for next_url in _hrefs_diretos(submenu_items):
                try:
                    process_page(next_url, visited)
                except Exception as e:
                    print(f"Erro processando {next_url}: {e}")
            return

        submenu_facet_urls = _submenu_facet(url)

        if submenu_facet_urls:
            print(f"[LEVEL-FACET] {url}")
            for next_url in submenu_facet_urls:
                try:
                    process_page(next_url, visited)
                except Exception as e:
                    print(f"Erro processando {next_url}: {e}")
            return

        # a espera lá em cima já passa rápido pq o menu carrega rápido, mas
        # o botão de produtos pode demorar mais — por isso espera de novo aqui
        _esperar_qualquer(PRODUCTS_SELECTION_SELECTOR)

        products_links = driver.find_elements(By.CSS_SELECTOR, PRODUCTS_SELECTION_SELECTOR)
        products_urls = [href for href in (l.get_attribute("href") for l in products_links) if href]

        if products_urls:
            products_url = products_urls[0]
            print(f"[PRODUCTS SELECTION] {products_url}")
            driver.get(products_url)
            _esperar_qualquer(LAYOUT_LIST_SELECTOR)

            layout_list_items = driver.find_elements(By.CSS_SELECTOR, LAYOUT_LIST_SELECTOR)
            if not layout_list_items:
                print(f"[PRODUCTS SELECTION] sem {LAYOUT_LIST_SELECTOR!r} em {products_url}")
                _salvar_html_debug(products_url, "sem_layout_list")
                return

            data_link = layout_list_items[0].get_attribute("data-link")
            if not data_link:
                print(f"[CACHER] data-link vazio em {products_url}")
                _salvar_html_debug(products_url, "data_link_vazio")
                return

            cacher_url = urljoin(driver.current_url, data_link)
            print(f"[CACHER] {cacher_url}")

            cacher_html = _buscar_html_ajax(cacher_url)
            if not cacher_html:
                print(f"[CACHER] sem resposta válida em {cacher_url}")
                return

            cacher_soup = BeautifulSoup(cacher_html, "html.parser")
            final_urls = []
            for a in cacher_soup.select(FINAL_PRODUCTS_SELECTOR):
                href = a.get("href")
                if href:
                    final_urls.append(urljoin(cacher_url, href))

            final_urls = list(dict.fromkeys(final_urls))
            print(f"[CACHER] {len(final_urls)} produtos encontrados em {cacher_url}")
            if not final_urls:
                _salvar_html_debug(cacher_url, "sem_produtos", html=cacher_html)

            for final_url in final_urls:
                try:
                    print(f"[FINAL] {final_url}")
                    get_weg_talbe(final_url)
                except Exception as e:
                    print(f"Erro processando {final_url}: {e}")
            return

        print(f"[SEM CAMINHO] {url}")
        _debug_sem_caminho(url)

    except Exception as e:
        print(f"Erro processando {url}: {e}")


def pages(url):
    visited = set()
    try:
        process_page(url, visited)
    except Exception as e:
        print("Tipo do erro:", type(e).__name__)
        print("Erro:", repr(e))
    finally:
        driver.quit()


if __name__ == "__main__":
    pages("https://www.weg.net/catalog/weg/BR/pt/Motores-El%C3%A9tricos/c/BR_MT")
