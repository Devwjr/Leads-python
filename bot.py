import re
import time
import random
import requests
import pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime
from playwright.sync_api import sync_playwright

MAX_LEADS_DIA = 3000
INTERVALO_BUSCA = 30

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
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
    telefones = [re.sub(r"\s+", " ", t.strip()) for t in telefones]
    telefones = [t for t in telefones if 10 <= len(re.sub(r"\D", "", t)) <= 11]
    telefones = [re.sub(r"\D", "", t) for t in telefones]
    telefones = ["(" + t[:2] + ") " + t[2:6] + "-" + t[6:] if len(t) == 10 else ("(" + t[:2] + ") " + t[2:7] + "-" + t[7:] if len(t) == 11 else "") for t in telefones]
    telefones = [t for t in telefones if t]

    return list(set(emails)), list(set(telefones))

def buscar_sites_google(busca):
    links = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=['--disable-blink-features=AutomationControlled', '--disable-dev-shm-usage', '--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu'])
            context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            page = context.new_page()
            
            page.goto("https://www.google.com", timeout=15000)
            page.wait_for_timeout(1500)
            
            try:
                page.click('button:has-text("Aceitar")', timeout=2000)
            except:
                pass

            url = f"https://www.google.com/search?q={busca}&num=50&hl=pt-BR&gl=br"
            page.goto(url, timeout=15000)
            page.wait_for_timeout(2000)

            html = page.content()
            soup = BeautifulSoup(html, "html.parser")

            for a in soup.select("a"):
                href = a.get("href", "")
                if href.startswith("http") and "google" not in href and "youtube" not in href and "instagram" not in href and "facebook" not in href and "linkedin" not in href:
                    if "/url?" not in href:
                        links.append(href)

            browser.close()
    except Exception as e:
        print(f"Erro na busca: {e}")

    return list(set(links))[:30]

def carregar_excel(nome_arquivo):
    try:
        df = pd.read_excel(nome_arquivo, engine="openpyxl")
    except:
        df = pd.DataFrame(columns=["empresa", "email", "telefone", "site", "cidade", "nicho"])
    return df

def salvar_excel(df, nome_arquivo):
    df.to_excel(nome_arquivo, index=False)

def main():
    print("=" * 50)
    print("BOT DE BUSCA DE LEADS - RODANDO 24H")
    print(f"Meta: {MAX_LEADS_DIA} leads/dia")
    print("=" * 50)
    
    leads_coletados_dia = 0
    
    ciclo = 0
    while True:
        ciclo += 1
        print(f"\n=== CICLO {ciclo} - {datetime.now().strftime('%H:%M:%S')} ===")
        
        if leads_coletados_dia >= MAX_LEADS_DIA:
            print(f"Meta diária atingida ({MAX_LEADS_DIA} leads). Aguardando novo dia...")
            time.sleep(3600)
            leads_coletados_dia = 0
            continue
        
        print("\nBuscando novos leads...")
        df = carregar_excel("leads.xlsx")
        emails_existentes = set(df["email"].str.lower().dropna().values)
        
        try:
            nicho = random.choice(nichos)
            cidade = random.choice(cidades)
            busca = f"{nicho} {cidade}"
            print(f"Buscando: {busca}")
            
            sites = buscar_sites_google(busca)
            print(f"Encontrados {len(sites)} sites")
            
            novos_leads = 0
            for site in sites:
                if leads_coletados_dia >= MAX_LEADS_DIA:
                    break
                
                try:
                    emails, telefones = extrair_emails_e_telefones(site)
                except:
                    continue
                
                for email in emails:
                    email_lower = email.lower()
                    if email_lower in emails_existentes:
                        continue
                    
                    telefone = telefones[0] if telefones else ""
                    linha = pd.DataFrame([{
                        "empresa": "",
                        "email": email,
                        "telefone": telefone,
                        "site": site,
                        "cidade": cidade,
                        "nicho": nicho
                    }])
                    df = pd.concat([df, linha], ignore_index=True)
                    emails_existentes.add(email_lower)
                    leads_coletados_dia += 1
                    novos_leads += 1
                    print(f"Novo lead: {email} | {nicho} | {cidade}")
                    
                    if leads_coletados_dia % 50 == 0:
                        salvar_excel(df, "leads.xlsx")
                        print(f"Salvando... ({leads_coletados_dia}/{MAX_LEADS_DIA})")
                
                time.sleep(random.randint(1, 3))
            
            salvar_excel(df, "leads.xlsx")
            
        except Exception as e:
            print(f"Erro na busca: {e}")
            time.sleep(10)
        
        print(f"\n[STATUS] Leads coletados hoje: {leads_coletados_dia}/{MAX_LEADS_DIA}")
        
        time.sleep(INTERVALO_BUSCA)

if __name__ == "__main__":
    main()
