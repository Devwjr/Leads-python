import re
import time
import random
import asyncio
import argparse
import logging
import concurrent.futures
from pathlib import Path

import aiohttp
import primp
import requests
import pandas as pd
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

META_LEADS = 1000
INTERVALO_BUSCA = 30

log = logging.getLogger(__name__)
logging.getLogger("primp").setLevel(logging.WARNING)

_BROWSER = None
_PLAYWRIGHT = None

HEADERS = {
    "User-Agent": "Mozilla/5.0",
}

def carregar_lista(arquivo):
    try:
        with open(arquivo) as f:
            return [l.strip() for l in f.readlines() if l.strip()]
    except:
        return []

nichos = carregar_lista("nichos.txt")
cidades = carregar_lista("cidades.txt")

def extrair_contatos(url):
    try:
        r = requests.get(url, timeout=10, headers=HEADERS)
        html = r.text
    except:
        return [], []

    emails = re.findall(
        r"[a-zA-Z0-9_.+-]+@(gmail\.com|outlook\.com|hotmail\.com|yahoo\.com|[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)",
        html
    )
    emails = re.findall(
        r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
        html
    )

    telefones_raw = re.findall(
        r"(?:\+?55\s*)?(?:\(?\d{2}\)?\s*)?(9\d{4}[-.\s]?\d{4})",
        html
    )

    return list(set(emails)), []


def carregar_config(caminho: str = "config.json") -> dict:
    padrao = {
        "meta_leads": 1000,
        "intervalo_busca": 15,
        "arquivo_excel": "leads.xlsx",
        "arquivo_log": "bot.log",
        "timeout": 5,
        "max_sites_por_busca": 40,
        "concorrencia": 15,
        "buscas_por_ciclo": 3,
        "user_agents": [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        ],
        "proxies": [],
        "allowed_domains": [],
    }
    path = Path(caminho)
    if path.exists():
        with open(path, encoding="utf-8") as f:
            loaded = json.load(f)
            padrao.update(loaded)
    return padrao


def parse_args():
    parser = argparse.ArgumentParser(description="Bot de captura de leads")
    parser.add_argument("--meta", type=int, help="Meta de leads")
    parser.add_argument("--intervalo", type=int, help="Intervalo entre buscas (segundos)")
    parser.add_argument("--excel", help="Arquivo Excel de saída")
    parser.add_argument("--config", default="config.json", help="Arquivo de configuração")
    parser.add_argument("--concorrencia", type=int, help="Sites paralelos por ciclo")
    parser.add_argument("--enviar", action="store_true", help="Dispara emails para leads pendentes")
    parser.add_argument("--limite", type=int, help="Limite de envios no disparo")
    parser.add_argument("--forcar", action="store_true", help="Ignora warm-up no disparo")
    parser.add_argument("--limpar", action="store_true", help="Remove leads com dominios nao permitidos")
    return parser.parse_args()


def merge_config(args) -> dict:
    config = carregar_config(args.config)
    if args.meta:
        config["meta_leads"] = args.meta
    if args.intervalo:
        config["intervalo_busca"] = args.intervalo
    if args.excel:
        config["arquivo_excel"] = args.excel
    if args.concorrencia:
        config["concorrencia"] = args.concorrencia
    return config


def carregar_lista(arquivo: str) -> list[str]:
    path = Path(arquivo)
    if not path.exists():
        log.warning("Arquivo %s nao encontrado", arquivo)
        return []
    return [l.strip() for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def validar_email(email: str) -> bool:
    if not re.match(r"^[a-zA-Z0-9_.+-]+@(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}$", email):
        return False
    _, dominio = email.rsplit("@", 1)
    partes = dominio.rsplit(".", 1)
    if len(partes) != 2:
        return False
    tld = partes[1]
    if tld.lower() in {"png", "jpg", "jpeg", "gif", "webp", "svg", "ico", "bmp", "tiff", "tif", "avif", "heic", "heif", "json", "css", "js", "xml", "woff", "woff2", "ttf", "otf", "eot", "mp4", "mp3", "pdf", "zip", "gz", "rar"}:
        return False
    if not re.search(r"[a-zA-Z]", partes[0]):
        return False
    return True


def email_em_dominios_permintidos(email: str, dominios: list[str]) -> bool:
    if not dominios:
        return True
    _, dominio = email.rsplit("@", 1)
    return dominio.lower() in dominios


def extrair_nome_empresa(soup: BeautifulSoup) -> str:
    for tag in soup.find_all(["title", "h1", "h2"]):
        texto = tag.get_text(strip=True)
        if texto and len(texto) < 120:
            return texto.split(" | ")[0].split(" - ")[0].strip()
    return ""


def extrair_emails_e_telefones(texto: str, allowed_domains: list[str] | None = None) -> tuple[list[str], list[str]]:
    emails = list(set(
        m.lower()
        for m in re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-]{2,}", texto)
        if validar_email(m) and email_em_dominios_permintidos(m, allowed_domains or [])
    ))
    telefones_raw = re.findall(r"(?:\+?55)?\s*(?:\(?\d{2}\)?)\s*(?:9?\d{4}[-.\s]?\d{4})", texto)
    telefones = []
    for raw in telefones_raw:
        nums = re.sub(r"\D", "", raw)
        if len(nums) >= 10:
            nums = nums[-10:] if len(nums) > 10 else nums
            ddd, num = nums[:2], nums[2:]
            if 8 <= len(num) <= 9:
                if len(num) == 9:
                    telefones.append(f"({ddd}) {num[:5]}-{num[5:]}")
                else:
                    telefones.append(f"({ddd}) 9{num[:4]}-{num[4:]}")
    return emails, telefones


async def extrair_dados_site(
    session: aiohttp.ClientSession,
    site: str,
    user_agents: list[str],
    proxies: list[str],
    timeout: int,
    allowed_domains: list[str] | None = None,
) -> tuple[str, list[str], list[str]]:
    headers = {"User-Agent": random.choice(user_agents)}
    proxy = random.choice(proxies) if proxies else None
    try:
        async with session.get(
            site,
            timeout=aiohttp.ClientTimeout(total=timeout),
            headers=headers,
            proxy=proxy,
        ) as resp:
            if resp.status != 200:
                return "", [], []
            texto = await resp.text()
    except Exception:
        return "", [], []

    soup = BeautifulSoup(texto, "html.parser")
    empresa = extrair_nome_empresa(soup)
    emails, telefones = extrair_emails_e_telefones(texto, allowed_domains)
    return empresa, emails, telefones


def buscar_sites_duckduckgo(busca: str, max_sites: int, user_agents: list[str]) -> list[str]:
    links: list[str] = []
    ua = random.choice(user_agents)
    try:
        client = primp.Client(
            headers={
                "User-Agent": ua,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": "https://html.duckduckgo.com",
                "Referer": "https://html.duckduckgo.com/",
            },
            follow_redirects=True,
        )
        client.get("https://html.duckduckgo.com/")
        resp = client.post(
            "https://html.duckduckgo.com/html/",
            data={"q": busca},
        )
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if href.startswith("http") and "duckduckgo" not in href:
                    links.append(href)
        elif resp.status_code == 202:
            log.warning("DuckDuckGo rate limit (202)")
    except Exception as e:
        log.error("Erro DuckDuckGo [%s]: %s", busca, e)
    return list(dict.fromkeys(links))[:max_sites]


def buscar_sites_bing(busca: str, max_sites: int, user_agents: list[str]) -> list[str]:
    links: list[str] = []
    ua = random.choice(user_agents)
    try:
        client = primp.Client(
            headers={
                "User-Agent": ua,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            },
            follow_redirects=True,
        )
        resp = client.get(
            "https://www.bing.com/search",
            params={"q": busca, "count": str(max_sites), "setlang": "pt-br"},
        )
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.select("li.b_algo h2 a"):
                href = a.get("href")
                if href and href.startswith("http"):
                    links.append(href)
            for a in soup.select("a[href^='http']"):
                href = a["href"]
                parent_classes = a.parent.get("class", []) if a.parent else []
                if "b_algo" in str(parent_classes) or a.find_parent("li", class_="b_algo"):
                    if href.startswith("http") and href not in links:
                        links.append(href)
    except Exception as e:
        log.error("Erro Bing [%s]: %s", busca, e)

    links = list(dict.fromkeys(links))
    seen = set()
    resultado = []
    for link in links:
        if link not in seen:
            seen.add(link)
            resultado.append(link)
    return resultado[:max_sites]


def buscar_sites_google(busca: str, max_sites: int, user_agents: list[str]) -> list[str]:
    global _BROWSER, _PLAYWRIGHT
    links: list[str] = []
    for tentativa in range(3):
        try:
            if _PLAYWRIGHT is None:
                _PLAYWRIGHT = sync_playwright()
                _PLAYWRIGHT.start()
            if _BROWSER is None:
                _BROWSER = _PLAYWRIGHT.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
                )
            context = _BROWSER.new_context(
                user_agent=random.choice(user_agents),
                locale="pt-BR",
            )
            page = context.new_page()
            try:
                page.goto(
                    f"https://www.google.com/search?q={busca}&hl=pt-BR",
                    timeout=15000,
                    wait_until="domcontentloaded",
                )
                page.wait_for_timeout(2000)
                for a in page.query_selector_all("a[href]"):
                    href = a.get_attribute("href")
                    if href and href.startswith("http") and "google.com" not in href:
                        links.append(href)
            except Exception as e:
                log.debug("Erro Google page [%s]: %s", busca, e)
            finally:
                try:
                    context.close()
                except Exception:
                    pass
            break
        except Exception as e:
            log.debug("Erro Google [%s] (tentativa %s): %s", busca, tentativa + 1, e)
            if _BROWSER:
                try:
                    _BROWSER.close()
                except Exception:
                    pass
                _BROWSER = None
            if _PLAYWRIGHT:
                try:
                    _PLAYWRIGHT.stop()
                except Exception:
                    pass
                _PLAYWRIGHT = None
            time.sleep(2)
    return list(dict.fromkeys(links))[:max_sites]


def buscar_sites(busca: str, max_sites: int, config: dict) -> list[str]:
    motores = []
    if config.get("usar_duckduckgo", True):
        motores.append(("duckduckgo", buscar_sites_duckduckgo))
    if config.get("usar_bing", True):
        motores.append(("bing", buscar_sites_bing))
    if config.get("usar_google", True):
        motores.append(("google", buscar_sites_google))

    if not motores:
        motores = [("duckduckgo", buscar_sites_duckduckgo)]

    todos_links: list[str] = []
    for nome, func in motores:
        try:
            links = func(busca, max_sites, config["user_agents"])
            if links:
                log.info("  %s: %s sites", nome, len(links))
                todos_links.extend(links)
        except Exception as e:
            log.error("Erro no motor %s: %s", nome, e)

    return list(dict.fromkeys(todos_links))[:max_sites]


def fechar_browser():
    global _BROWSER, _PLAYWRIGHT
    if _BROWSER:
        try:
            _BROWSER.close()
        except Exception:
            pass
        _BROWSER = None
    if _PLAYWRIGHT:
        try:
            _PLAYWRIGHT.stop()
        except Exception:
            pass
        _PLAYWRIGHT = None


def carregar_excel(nome_arquivo):
    try:
        return pd.read_excel(nome_arquivo)
    except:
        return pd.DataFrame(columns=["empresa", "email", "telefone", "cidade", "nicho"])


def salvar_excel(df, nome_arquivo):
    df.to_excel(nome_arquivo, index=False)


def executar_busca(
    nicho: str,
    cidade: str,
    max_sites: int,
    config: dict,
) -> list[str]:
    busca = f"{nicho} {cidade}"
    return buscar_sites(busca, max_sites, config)


def main():
    import atexit
    atexit.register(fechar_browser)

    args = parse_args()
    config = merge_config(args)
    setup_logging(config["arquivo_log"])

    df = carregar_excel("leads.xlsx")

    emails_existentes = set(df["email"].dropna().str.lower().values)
    telefones_existentes = set(df["telefone"].dropna().values)

    total_leads = len(df)

    buscas_por_ciclo = config.get("buscas_por_ciclo", 3)
    max_sites = config["max_sites_por_busca"]

    ciclo = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=buscas_por_ciclo) as executor:
        while total_leads < config["meta_leads"]:
            ciclo += 1
            log.info("--- CICLO %s: %s buscas paralelas ---", ciclo, buscas_por_ciclo)

            pares = []
            for _ in range(buscas_por_ciclo):
                nicho = random.choice(nichos)
                cidade = random.choice(cidades)
                pares.append((nicho, cidade, max_sites, config))

            futuros = [
                executor.submit(executar_busca, n, c, m, cfg)
                for n, c, m, cfg in pares
            ]
            todas_sites: list[str] = []
            for futuro in concurrent.futures.as_completed(futuros):
                try:
                    sites = futuro.result()
                    todas_sites.extend(sites)
                except Exception as e:
                    log.error("Erro em busca paralela: %s", e)

            todas_sites = list(dict.fromkeys(todas_sites))
            log.info("Total sites unicos: %s", len(todas_sites))

            if not todas_sites:
                log.info("Nenhum site encontrado, aguardando %ss...", config["intervalo_busca"])
                time.sleep(config["intervalo_busca"])
                continue

            novos_leads = asyncio.run(
                processar_sites(
                    todas_sites, pares[0][1], pares[0][0],
                    emails_existentes, config["meta_leads"], config,
                )
            )

            if novos_leads:
                idx = total_leads
                for lead in novos_leads:
                    idx += 1
                    log.info("[%s/%s] %s", idx, config["meta_leads"], lead["email"])

                df = pd.concat([df, pd.DataFrame(novos_leads)], ignore_index=True)
                total_leads += len(novos_leads)

            if novos_leads:
                salvar_excel(df, config["arquivo_excel"])
                ultimo_salvamento = total_leads

            log.info("--- CICLO %s: +%s leads (total: %s) ---", ciclo, len(novos_leads), total_leads)
            if total_leads >= config["meta_leads"]:
                break
            time.sleep(config["intervalo_busca"])


if __name__ == "__main__":
    main()