#!/usr/bin/env python3
import re
import sys
import time
import json
import random
import asyncio
import argparse
import logging
from pathlib import Path

import aiohttp
import pandas as pd
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout


log = logging.getLogger(__name__)


def setup_logging(log_file: str = "bot.log"):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def carregar_config(caminho: str = "config.json") -> dict:
    padrao = {
        "meta_leads": 1000,
        "intervalo_busca": 30,
        "arquivo_excel": "leads.xlsx",
        "arquivo_log": "bot.log",
        "timeout": 10,
        "max_sites_por_busca": 20,
        "concorrencia": 5,
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
    for t in telefones_raw:
        t = re.sub(r"\D", "", t)
        if len(t) == 10:
            telefones.append(f"({t[:2]}) {t[2:6]}-{t[6:]}")
        elif len(t) == 11:
            telefones.append(f"({t[:2]}) {t[2:7]}-{t[7:]}")
    return emails, list(set(telefones))


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


def buscar_sites_google(
    busca: str, max_sites: int, user_agents: list[str]
) -> list[str]:
    links: list[str] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )
            context = browser.new_context(
                user_agent=random.choice(user_agents),
                viewport={"width": 1920, "height": 1080},
                locale="pt-BR",
                timezone_id="America/Sao_Paulo",
            )
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            """)
            page = context.new_page()
            url = f"https://www.google.com/search?q={busca}&num=30&hl=pt-BR"
            page.goto(url, timeout=15000)
            page.wait_for_timeout(1000)

            for a in page.locator("a[href^='http']").all():
                href = a.get_attribute("href") or ""
                if "google" not in href and "youtube" not in href:
                    links.append(href.split("#")[0])

            browser.close()
    except PlaywrightTimeout:
        log.warning("Timeout ao buscar: %s", busca)
    except Exception as e:
        log.error("Erro ao buscar %s: %s", busca, e)
    return list(set(links))[:max_sites]


def carregar_excel(arquivo: str) -> pd.DataFrame:
    path = Path(arquivo)
    if path.exists():
        return pd.read_excel(path)
    return pd.DataFrame(columns=["empresa", "email", "telefone", "cidade", "nicho"])


def salvar_excel(df: pd.DataFrame, arquivo: str):
    temp = Path(arquivo + ".tmp")
    final = Path(arquivo)
    df.to_excel(temp, index=False)
    temp.replace(final)
    log.info("Salvo %s leads em %s", len(df), arquivo)


async def processar_sites(
    sites: list[str],
    cidade: str,
    nicho: str,
    emails_existentes: set[str],
    meta_leads: int,
    config: dict,
) -> list[dict]:
    novos_leads: list[dict] = []
    semaforo = asyncio.Semaphore(config["concorrencia"])

    async with aiohttp.ClientSession() as session:

        async def processar(site: str):
            async with semaforo:
                empresa, emails, telefones = await extrair_dados_site(
                    session,
                    site,
                    config["user_agents"],
                    config["proxies"],
                    config["timeout"],
                    config.get("allowed_domains"),
                )
            if not emails:
                return
            telefone = telefones[0] if telefones else ""
            for email in emails:
                email_lower = email.lower()
                if email_lower in emails_existentes:
                    continue
                novos_leads.append({
                    "empresa": empresa,
                    "email": email,
                    "telefone": telefone,
                    "cidade": cidade,
                    "nicho": nicho,
                })
                emails_existentes.add(email_lower)

        tarefas = [asyncio.create_task(processar(site)) for site in sites]
        await asyncio.gather(*tarefas)

    return novos_leads


def main():
    args = parse_args()
    config = merge_config(args)
    setup_logging(config["arquivo_log"])

    if args.limpar:
        dominios = config.get("allowed_domains", [])
        df = carregar_excel(config["arquivo_excel"])
        antes = len(df)
        df = df[df["email"].apply(lambda e: email_em_dominios_permintidos(str(e), dominios))]
        removidos = antes - len(df)
        salvar_excel(df, config["arquivo_excel"])
        log.info("Limpeza: %s leads removidos, %s restantes", removidos, len(df))
        return

    if args.enviar:
        import disparo
        disparo.disparar(config, args.limite, args.forcar)
        return

    log.info("=" * 50)
    log.info("BOT DE LEADS - META: %s", config["meta_leads"])
    log.info("=" * 50)

    nichos = carregar_lista("nichos.txt")
    cidades = carregar_lista("cidades.txt")
    if not nichos or not cidades:
        log.error("nichos.txt ou cidades.txt vazios ou ausentes")
        return

    df = carregar_excel(config["arquivo_excel"])
    emails_existentes: set[str] = set(df["email"].str.lower().dropna().values)
    total_leads = len(df)
    ultimo_salvamento = total_leads

    ciclo = 0
    while total_leads < config["meta_leads"]:
        ciclo += 1
        log.info("--- CICLO %s ---", ciclo)

        nicho = random.choice(nichos)
        cidade = random.choice(cidades)
        busca = f"{nicho} {cidade}"
        log.info("Buscando: %s", busca)

        sites = buscar_sites_google(
            busca, config["max_sites_por_busca"], config["user_agents"]
        )
        if not sites:
            log.info("Nenhum site encontrado, aguardando...")
            time.sleep(config["intervalo_busca"])
            continue

        novos_leads = asyncio.run(
            processar_sites(
                sites, cidade, nicho, emails_existentes, config["meta_leads"], config
            )
        )

        if novos_leads:
            idx = total_leads
            for lead in novos_leads:
                idx += 1
                log.info("[%s/%s] %s", idx, config["meta_leads"], lead["email"])

            df = pd.concat([df, pd.DataFrame(novos_leads)], ignore_index=True)
            total_leads += len(novos_leads)

        if total_leads - ultimo_salvamento >= 50 or total_leads >= config["meta_leads"]:
            salvar_excel(df, config["arquivo_excel"])
            ultimo_salvamento = total_leads

        log.info("--- CICLO %s: +%s leads (total: %s) ---", ciclo, len(novos_leads), total_leads)
        time.sleep(config["intervalo_busca"])

    salvar_excel(df, config["arquivo_excel"])
    log.info("Script encerrado. Total: %s leads", total_leads)


if __name__ == "__main__":
    main()
