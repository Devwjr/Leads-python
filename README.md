# LeadBot - Captura de Leads via Google

Bot Python que automatiza a busca de leads (e-mails e telefones) no Google, extraindo contatos de sites de empresas e salvando tudo em uma planilha Excel.

## Funcionalidades

- Busca aleatória combinando nichos e cidades (ex: "dentista sao paulo contato whatsapp email")
- Utiliza **Playwright** para navegar no Google e obter resultados de busca
- Utiliza **requests + BeautifulSoup** para extrair e-mails e telefones dos sites encontrados
- Deduplica leads automaticamente (evita repetir e-mail ou telefone já salvos)
- Salva progresso parcial a cada 50 leads encontrados
- Meta padrão: **1.000 leads**

## Requisitos

- Python 3.8 ou superior
- Navegador Chromium (instalado automaticamente pelo Playwright)

## Instalação

```bash
# Clone o repositório
git clone <url-do-repositorio>
cd leadbot

# Instale as dependências
pip install -r requirements.txt

# Instale os navegadores do Playwright
playwright install chromium
```

## Configuração

### nichos.txt
Lista de nichos/segmentos para buscar. Um por linha. Exemplo:

```
dentista
advogado
restaurante
academia
```

### cidades.txt
Lista de cidades para buscar. Um por linha. Exemplo:

```
sao paulo
rio de janeiro
belo horizonte
```

## Como Executar

```bash
python bot.py
```

O bot vai:
1. Carregar nichos.txt e cidades.txt
2. Escolher combinações aleatórias e buscar no Google
3. Visitar cada site encontrado e extrair contatos
4. Salvar os leads em **leads.xlsx**

Pressione **Ctrl+C** a qualquer momento para interromper (os dados já coletados estarão salvos).

## Estrutura do Projeto

```
leadbot/
├── bot.py            # Script principal
├── nichos.txt        # Lista de nichos
├── cidades.txt       # Lista de cidades
├── leads.xlsx        # Planilha gerada com os leads
├── requirements.txt  # Dependências do projeto
└── README.md         # Este arquivo
```

## Meta de Leads

Por padrão o bot busca **1.000 leads**. Para alterar, edite a variável `META_LEADS` no início do `bot.py`:

```python
META_LEADS = 1000
```

## Formato da Planilha

| Coluna     | Descrição                     |
|------------|-------------------------------|
| empresa    | Nome da empresa (em branco)   |
| email      | E-mail encontrado             |
| telefone   | Telefone formatado (DDD)      |
| cidade     | Cidade usada na busca         |
| nicho      | Nicho usado na busca          |

## Aviso Legal

Este bot é fornecido apenas para fins educacionais. Respeite os termos de serviço dos sites visitados e as leis de proteção de dados aplicáveis (LGPD, GDPR, etc.). O uso comercial indevido é de responsabilidade do usuário.