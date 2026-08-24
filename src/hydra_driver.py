"""
hydra_driver.py
================
Pool de proxies com failover pra raspagem com Selenium.

Quando `driver.get(url)` cai numa página de bloqueio (Acesso Negado /
rate-limit / captcha), o robô não quebra: ele troca de proxy/IP sozinho e
tenta a mesma URL de novo.

Usado por src/weg_page.py, src/menzel_page.py e src/rsdelivers_page.py.
"""

import random
import time
import logging
from itertools import cycle

# o undetected_chromedriver ainda usa o `distutils`, que foi tirado do
# Python 3.12+. o pacote `setuptools` (tá no requirements.txt) devolve
# esse módulo. sem ele o import abaixo quebra.
import undetected_chromedriver as uc
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("hydra_pool")


# ---------------------------------------------------------------------------
# POOL DE PROXIES
# ---------------------------------------------------------------------------
# formato: "http://usuario:senha@host:porta". proxy grátis geralmente não
# tem usuário/senha. deixa vazio pra rodar sem proxy nenhum.
PROXY_POOL = [
    # "http://user:pass@proxy1.provedor.com:8000",
    # "http://user:pass@proxy2.provedor.com:8000",
]


class ProxyPool:
    """Fila de proxies. Quando um proxy é bloqueado, marca ele como morto
    e não usa mais na mesma execução."""

    def __init__(self, proxies: list[str]):
        if not proxies:
            log.warning("PROXY_POOL vazio — rodando SEM proxy (seu IP real).")
        self._alive = list(proxies)
        self._cycle = cycle(self._alive) if self._alive else None
        self._dead = set()

    def get(self) -> str | None:
        if not self._cycle:
            return None
        for _ in range(len(self._alive)):
            proxy = next(self._cycle)
            if proxy not in self._dead:
                return proxy
        raise RuntimeError("Pool de proxies esgotado — todas as cabeças da Hydra morreram.")

    def mark_dead(self, proxy: str | None):
        if proxy and proxy not in self._dead:
            log.warning("Proxy bloqueado, removendo do pool: %s", proxy)
            self._dead.add(proxy)


# ---------------------------------------------------------------------------
# CRIAÇÃO DO DRIVER
# ---------------------------------------------------------------------------
# o bloqueio da WEG acontece logo na primeira tentativa e só quando usa
# Selenium (no Chrome normal, sem automação, funciona liso). ou seja, não é
# bloqueio por IP, é o site detectando que é um robô. por isso usamos
# undetected_chromedriver em vez do Chrome normal do Selenium, que esconde
# essas marcas de automação.
#
# mesmo assim deixamos o pool de proxy pronto, porque se um dia o bloqueio
# virar por volume de requisição, a troca de IP ainda ajuda.

def build_driver(proxy: str | None) -> uc.Chrome:
    options = uc.ChromeOptions()

    if proxy:
        proxy_sem_esquema = proxy.split("://")[-1]
        options.add_argument(f"--proxy-server={proxy_sem_esquema}")

    # version_main trava a versão do chromedriver pra bater com o Chrome
    # instalado na máquina. sem isso o uc às vezes baixa uma versão mais
    # nova que não bate com o Chrome local e dá erro pra abrir o navegador.
    # se o Chrome atualizar, ajusta esse número (ver em chrome://version).
    return uc.Chrome(options=options, version_main=151)


# ---------------------------------------------------------------------------
# HydraDriver — troca de IP sozinho quando toma "Acesso Negado"
# ---------------------------------------------------------------------------

class HydraDriver:
    """
    Se comporta como um driver do Chrome normal (delega find_elements,
    title, page_source etc pro driver de verdade), mas o método .get(url)
    percebe "Acesso Negado" e se resolve sozinho:
      1. marca o proxy atual como morto;
      2. fecha o Chrome atual e abre outro com o próximo proxy;
      3. tenta acessar a mesma url de novo.
    """

    TERMOS_DE_BLOQUEIO = (
        "access denied", "acesso negado", "blocked", "captcha", "403 forbidden",
    )

    def __init__(self, pool: ProxyPool, max_tentativas: int = 5):
        self.pool = pool
        self.max_tentativas = max_tentativas
        self._driver = None
        self._proxy_atual = None
        self._abrir_novo_driver()

    def _abrir_novo_driver(self):
        proxy = self.pool.get()
        self._driver = build_driver(proxy)
        self._proxy_atual = proxy
        log.info("Driver aberto com proxy=%s", proxy)

    def _reabrir_apos_falha(self):
        """Fecha o driver atual (se ainda der pra fechar) e abre outro.
        Usado tanto quando toma "Acesso Negado" quanto quando o Chrome
        crasha de vez — nesse segundo caso o quit() também pode falhar,
        por isso tá dentro de um try/except."""
        try:
            self._driver.quit()
        except Exception:
            pass
        self._abrir_novo_driver()

    def _pagina_negada(self) -> bool:
        # se nem o título dá pra ler, a sessão do Chrome já morreu.
        # trata isso igual bloqueio pra forçar reabrir o driver.
        try:
            titulo = (self._driver.title or "").lower()
        except Exception as e:
            log.warning("Sessão parece morta ao ler título: %s", e)
            return True

        # usa o texto que aparece na tela (body.text), não o html cru.
        # o html cru quase sempre tem um script de recaptcha em algum
        # canto, mesmo quando não tem bloqueio nenhum, e isso tava dando
        # falso positivo.
        try:
            corpo = self._driver.find_element(By.TAG_NAME, "body").text.lower()
        except Exception:
            corpo = ""

        bloqueado = any(termo in titulo or termo in corpo for termo in self.TERMOS_DE_BLOQUEIO)

        log.info("Título: %r | bloqueado=%s | trecho do corpo: %r",
                  self._driver.title, bloqueado, corpo[:150])

        return bloqueado

    def get(self, url: str):
        for tentativa in range(1, self.max_tentativas + 1):
            try:
                self._driver.get(url)
            except WebDriverException as e:
                # aqui o Chrome crashou de vez (diferente do "Acesso
                # Negado", que carrega a página normal só que bloqueada)
                print(f"[HYDRA] Sessão do Chrome morreu em {url} "
                      f"(tentativa {tentativa}/{self.max_tentativas}): {e}. Reabrindo...")
                self._reabrir_apos_falha()
                time.sleep(random.uniform(1.0, 3.0))
                continue

            if not self._pagina_negada():
                return  # deu certo, segue com o driver atual aberto

            print(f"[HYDRA] Acesso negado em {url} (proxy={self._proxy_atual}, "
                  f"tentativa {tentativa}/{self.max_tentativas}). Trocando de IP...")
            self.pool.mark_dead(self._proxy_atual)
            self._reabrir_apos_falha()
            time.sleep(random.uniform(1.0, 3.0))

        raise RuntimeError(f"Pool de proxies esgotado tentando acessar: {url}")

    def __getattr__(self, nome):
        return getattr(self._driver, nome)

    def quit(self):
        self._driver.quit()
