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

    telefones = []

    for numero_match in telefones_raw:
        numero = re.sub(r"\D", "", numero_match)

        possiveis = re.findall(
            r"(?:\+?55)?\s*(\d{2})\s*(" + numero + r")",
            html
        )

        if not possiveis:
            continue

        ddd = possiveis[0][0]

        if not numero.startswith("9") or len(numero) != 9:
            continue

        telefone_formatado = f"({ddd}) {numero[:5]}-{numero[5:]}"
        telefones.append(telefone_formatado)

    return list(set(emails)), list(set(telefones))


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
    print(f"BOT DE LEADS (WHATSAPP + EMAIL) - META: {META_LEADS}")
    print("=" * 50)

    df = carregar_excel("leads.xlsx")

    emails_existentes = set(df["email"].dropna().str.lower().values)
    telefones_existentes = set(df["telefone"].dropna().values)

    total_leads = len(df)

    ciclo = 0
    while total_leads < META_LEADS:
        ciclo += 1
        print(f"\n=== CICLO {ciclo} ===")

        nicho = random.choice(nichos)
        cidade = random.choice(cidades)
        busca = f"{nicho} {cidade} contato whatsapp email gmail"

        print(f"Buscando: {busca}")

        sites = buscar_sites_google(busca)

        for site in sites:
            if total_leads >= META_LEADS:
                break

            emails, telefones = extrair_contatos(site)

            for i in range(max(len(emails), len(telefones))):
                email = emails[i] if i < len(emails) else ""
                telefone = telefones[i] if i < len(telefones) else ""

                if email and email.lower() in emails_existentes:
                    continue

                if telefone and telefone in telefones_existentes:
                    continue

                nova_linha = pd.DataFrame([{
                    "empresa": "",
                    "email": email,
                    "telefone": telefone,
                    "cidade": cidade,
                    "nicho": nicho
                }])

                df = pd.concat([df, nova_linha], ignore_index=True)

                if email:
                    emails_existentes.add(email.lower())
                if telefone:
                    telefones_existentes.add(telefone)

                total_leads += 1

                print(f"[{total_leads}/{META_LEADS}] {email} | {telefone}")

                if total_leads % 50 == 0:
                    salvar_excel(df, "leads.xlsx")
                    print("Salvo parcial...")

            time.sleep(random.randint(1, 2))

        time.sleep(INTERVALO_BUSCA)

    salvar_excel(df, "leads.xlsx")
    print("\nScript encerrado.")


if __name__ == "__main__":
    main()