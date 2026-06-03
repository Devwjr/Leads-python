#!/usr/bin/env python3
import json
import time
import random
import smtplib
import argparse
import logging
from pathlib import Path
from datetime import datetime, date
from email.mime.text import MIMEText
from email.utils import formataddr

import pandas as pd


log = logging.getLogger(__name__)
ARQUIVO_WARMUP = Path("warmup.json")


def setup_logging(log_file: str = "disparo.log"):
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
        "email": {
            "smtp_host": "",
            "smtp_port": 587,
            "smtp_user": "",
            "smtp_pass": "",
            "from_name": "Seu Nome",
            "from_email": "seu@email.com",
            "daily_limit": 50,
            "warmup_days": 14,
            "warmup_start": 10,
            "intervalo_min": 60,
            "assunto": "Parceria - [nicho] em [cidade]",
            "template": "Ol\u00e1, tudo bem?\n\nVi que voc\u00ea trabalha com [nicho] em [cidade] e gostaria de propor uma parceria.\n\nPodemos conversar?\n\nAtenciosamente,\nSeu Nome",
        },
        "arquivo_excel": "leads.xlsx",
    }
    path = Path(caminho)
    if path.exists():
        with open(path, encoding="utf-8") as f:
            loaded = json.load(f)
            padrao.update(loaded)
    return padrao


def parse_args():
    parser = argparse.ArgumentParser(description="Disparo de emails para leads")
    parser.add_argument("--config", default="config.json", help="Arquivo de configuracao")
    parser.add_argument("--limite", type=int, help="Sobrescreve daily_limit")
    parser.add_argument("--forcar", action="store_true", help="Ignora warm-up e limite diario")
    parser.add_argument("--teste", action="store_true", help="Envia apenas 1 email de teste")
    return parser.parse_args()


def carregar_excel(arquivo: str) -> pd.DataFrame:
    cols = ["empresa", "email", "telefone", "cidade", "nicho", "status", "enviado_em"]
    path = Path(arquivo)
    if path.exists():
        df = pd.read_excel(arquivo)
        for col in cols:
            if col not in df.columns:
                df[col] = ""
        return df
    return pd.DataFrame(columns=cols)


def salvar_excel(df: pd.DataFrame, arquivo: str):
    temp = Path(arquivo + ".tmp")
    final = Path(arquivo)
    df.to_excel(temp, index=False)
    temp.replace(final)
    log.info("Planilha salva: %s", arquivo)


def compor_email(lead: dict, cfg: dict) -> tuple[str, str]:
    email_cfg = cfg["email"]
    substituicoes = {
        "[nome_empresa]": lead.get("empresa", ""),
        "[nicho]": lead.get("nicho", ""),
        "[cidade]": lead.get("cidade", ""),
        "[email]": lead.get("email", ""),
    }
    assunto = email_cfg["assunto"]
    corpo = email_cfg["template"]
    for chave, valor in substituicoes.items():
        assunto = assunto.replace(chave, valor)
        corpo = corpo.replace(chave, valor)
    return assunto, corpo


def ler_warmup() -> dict:
    if ARQUIVO_WARMUP.exists():
        return json.loads(ARQUIVO_WARMUP.read_text())
    return {}


def salvar_warmup(dados: dict):
    ARQUIVO_WARMUP.write_text(json.dumps(dados, indent=2, ensure_ascii=False))


def max_hoje(cfg: dict) -> int:
    email_cfg = cfg["email"]
    warmup = ler_warmup()

    primeira_data = warmup.get("primeiro_envio")
    if not primeira_data:
        return email_cfg["warmup_start"]

    dias = (date.today() - date.fromisoformat(primeira_data)).days
    if dias >= email_cfg["warmup_days"]:
        return email_cfg["daily_limit"]

    inclinacao = (email_cfg["daily_limit"] - email_cfg["warmup_start"]) / email_cfg["warmup_days"]
    return int(email_cfg["warmup_start"] + inclinacao * dias)


def contar_enviados_hoje(df: pd.DataFrame) -> int:
    hoje = date.today().isoformat()
    if "enviado_em" not in df.columns:
        return 0
    enviados = df["enviado_em"].dropna().astype(str)
    return int(enviados.str.startswith(hoje).sum())


def filtrar_pendentes(df: pd.DataFrame) -> list[dict]:
    if "status" not in df.columns or df.empty:
        return []
    pendentes = df[df["status"].isin(["", "pendente", None]) | df["status"].isna()]
    return pendentes.to_dict("records")


def enviar(smtp, cfg: dict, lead: dict) -> str:
    email_cfg = cfg["email"]
    assunto, corpo = compor_email(lead, cfg)

    msg = MIMEText(corpo, "plain", "utf-8")
    msg["Subject"] = assunto
    msg["From"] = formataddr((email_cfg["from_name"], email_cfg["from_email"]))
    msg["To"] = lead["email"]

    try:
        smtp.sendmail(email_cfg["from_email"], [lead["email"]], msg.as_string())
        return "enviado"
    except smtplib.SMTPRecipientsRefused as e:
        log.warning("Bounce: %s -> %s", lead["email"], e)
        return "bounce"
    except smtplib.SMTPSenderRefused as e:
        log.warning("Remetente recusado: %s", e)
        return "erro"
    except smtplib.SMTPDataError as e:
        log.warning("Erro SMTP: %s", e)
        return "erro"
    except smtplib.SMTPException as e:
        log.warning("Erro SMTP generico: %s", e)
        return "erro"


def disparar(config: dict, limite: int | None = None, forcar: bool = False):
    email_cfg = config["email"]

    if not email_cfg["smtp_host"] or not email_cfg["smtp_user"]:
        log.error("Configure smtp_host e smtp_user no config.json (sessao email)")
        return

    df = carregar_excel(config["arquivo_excel"])
    pendentes = filtrar_pendentes(df)

    if not pendentes:
        log.info("Nenhum lead pendente para enviar.")
        return

    if forcar:
        maximo = len(pendentes)
    elif limite is not None:
        maximo = limite
    else:
        maximo = max_hoje(config)
        ja_enviados = contar_enviados_hoje(df)
        maximo = max(0, maximo - ja_enviados)

    log.info("Leads pendentes: %s | Limite hoje: %s", len(pendentes), maximo)

    if maximo <= 0:
        log.info("Limite diario ja atingido.")
        return

    random.shuffle(pendentes)
    leads_hoje = pendentes[:maximo]

    warmup = ler_warmup()
    if "primeiro_envio" not in warmup:
        warmup["primeiro_envio"] = date.today().isoformat()
    warmup["ultimo_envio"] = datetime.now().isoformat()
    salvar_warmup(warmup)

    log.info("Conectando ao SMTP %s:%s...", email_cfg["smtp_host"], email_cfg["smtp_port"])
    try:
        server = smtplib.SMTP(email_cfg["smtp_host"], email_cfg["smtp_port"], timeout=15)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(email_cfg["smtp_user"], email_cfg["smtp_pass"])
    except smtplib.SMTPException as e:
        log.error("Falha ao conectar SMTP: %s", e)
        return

    enviados = 0
    for i, lead in enumerate(leads_hoje, 1):
        status = enviar(server, config, lead)
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        mask = df["email"].str.lower() == lead["email"].lower()
        df.loc[mask, "status"] = status
        df.loc[mask, "enviado_em"] = agora

        if status == "enviado":
            enviados += 1
            log.info("[%s/%s] Enviado -> %s (%s - %s)", i, len(leads_hoje), lead["email"], lead.get("nicho", ""), lead.get("cidade", ""))
        elif status == "bounce":
            log.info("[%s/%s] BOUNCE -> %s", i, len(leads_hoje), lead["email"])
        else:
            log.info("[%s/%s] ERRO -> %s", i, len(leads_hoje), lead["email"])

        if i % 10 == 0:
            salvar_excel(df, config["arquivo_excel"])

        if i < len(leads_hoje):
            intervalo = email_cfg["intervalo_min"] * 60
            if not forcar:
                jitter = random.uniform(0.8, 1.2)
                time.sleep(intervalo * jitter)

    server.quit()
    salvar_excel(df, config["arquivo_excel"])
    log.info("Disparo concluido: %s enviados de %s tentativas", enviados, len(leads_hoje))


def main():
    args = parse_args()
    config = carregar_config(args.config)
    setup_logging(config.get("arquivo_log", "disparo.log"))
    disparar(config, args.limite, args.forcar)


if __name__ == "__main__":
    main()
