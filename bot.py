import re
import time
import random
import requests
import pandas as pd
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

META_LEADS = 1000
INTERVALO_BUSCA = 30

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

def extrair_emails_e_telefones(url):
    try:
        r = requests.get(url, timeout=10, headers=HEADERS)
    except:
        return [], []

    emails = re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", r.text)

    telefones = re.findall(r"(?:\+?55)?\s*(?:\(?\d{2}\)?)\s*(?:9?\d{4}[-.\s]?\d{4})", r.text)
    telefones = [re.sub(r"\D", "", t) for t in telefones]

    telefones_formatados = []
    for t in telefones:
        if len(t) == 10:
            telefones_formatados.append(f"({t[:2]}) {t[2:6]}-{t[6:]}")
        elif len(t) == 11:
            telefones_formatados.append(f"({t[:2]}) {t[2:7]}-{t[7:]}")

    return list(set(emails)), list(set(telefones_formatados))


def buscar_sites_google(busca):
    links = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            url = f"https://www.google.com/search?q={busca}&num=30&hl=pt-BR"
            page.goto(url, timeout=15000)
            page.wait_for_timeout(2000)

            soup = BeautifulSoup(page.content(), "html.parser")

            for a in soup.select("a"):
                href = a.get("href", "")
                if href.startswith("http") and "google" not in href:
                    links.append(href)

            browser.close()
    except Exception as e:
        print(f"Erro na busca: {e}")

    return list(set(links))[:20]


def carregar_excel(nome_arquivo):
    try:
        return pd.read_excel(nome_arquivo)
    except:
        return pd.DataFrame(columns=["empresa", "email", "telefone", "cidade", "nicho"])


def salvar_excel(df, nome_arquivo):
    df.to_excel(nome_arquivo, index=False)


def main():
    print("=" * 50)
    print(f"BOT DE LEADS - META: {META_LEADS}")
    print("=" * 50)

    df = carregar_excel("leads.xlsx")
    emails_existentes = set(df["email"].str.lower().dropna().values)

    total_leads = len(df)

    ciclo = 0
    while total_leads < META_LEADS:
        ciclo += 1
        print(f"\n=== CICLO {ciclo} ===")

        nicho = random.choice(nichos)
        cidade = random.choice(cidades)
        busca = f"{nicho} {cidade}"

        print(f"Buscando: {busca}")

        sites = buscar_sites_google(busca)

        for site in sites:
            if total_leads >= META_LEADS:
                break

            emails, telefones = extrair_emails_e_telefones(site)

            for email in emails:
                email_lower = email.lower()
                if email_lower in emails_existentes:
                    continue

                telefone = telefones[0] if telefones else ""

                nova_linha = pd.DataFrame([{
                    "empresa": "",
                    "email": email,
                    "telefone": telefone,
                    "cidade": cidade,
                    "nicho": nicho
                }])

                df = pd.concat([df, nova_linha], ignore_index=True)

                emails_existentes.add(email_lower)
                total_leads += 1

                print(f"[{total_leads}/{META_LEADS}] {email}")

                if total_leads % 50 == 0:
                    salvar_excel(df, "leads.xlsx")
                    print("Salvo parcial...")

            time.sleep(random.randint(1, 2))

        time.sleep(INTERVALO_BUSCA)

    salvar_excel(df, "leads.xlsx")
    print("\Script encerrado.")


if __name__ == "__main__":
    main()