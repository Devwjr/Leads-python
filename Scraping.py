import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
import threading
import time
import pandas as pd
import re
import random

class BarbeariaLeadFinderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Auto Lead Finder - Busca Automática de Clientes")
        self.root.geometry("800x700")
        self.root.configure(bg='#f0f0f0')
        
        self.leads = []
        self.driver = None
        self.is_running = False
        
        self.setup_ui()
    
    def setup_ui(self):
        
        # Título
        title_frame = tk.Frame(self.root, bg='#2c3e50', height=80)
        title_frame.pack(fill=tk.X, padx=10, pady=10)
        title_frame.pack_propagate(False)
        
        title_label = tk.Label(
            title_frame, 
            text="Auto Lead Finder", 
            font=('Arial', 20, 'bold'),
            fg='white',
            bg='#2c3e50'
        )
        title_label.pack(expand=True)
        
        # Frame de configuração
        config_frame = tk.LabelFrame(
            self.root, 
            text="🔧 Configurações da Busca",
            font=('Arial', 12, 'bold'),
            bg='#f0f0f0',
            padx=15,
            pady=15
        )
        config_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Nicho
        tk.Label(config_frame, text="Nicho:", bg='#f0f0f0', font=('Arial', 10)).grid(row=0, column=0, sticky='w', pady=5)
        self.nicho_var = tk.StringVar(value="barbearia")
        nicho_combo = ttk.Combobox(config_frame, textvariable=self.nicho_var, width=30)
        nicho_combo['values'] = (
            'barbearia', 'salão de beleza', 'academia', 'restaurante', 
            'loja de roupas', 'construtoras', 'clínicas', 'advogados',
            'dentistas', 'mecânicas', 'hotéis', 'escolas'
        )
        nicho_combo.grid(row=0, column=1, padx=5, pady=5)
        
        # Cidade
        tk.Label(config_frame, text="Cidade:", bg='#f0f0f0', font=('Arial', 10)).grid(row=1, column=0, sticky='w', pady=5)
        self.cidade_var = tk.StringVar(value="Rio de Janeiro")
        cidade_combo = ttk.Combobox(config_frame, textvariable=self.cidade_var, width=30)
        cidade_combo['values'] = (
            'Rio de Janeiro', 'São Paulo', 'Belo Horizonte', 'Brasília',
            'Salvador', 'Fortaleza', 'Recife', 'Porto Alegre',
            'Curitiba', 'Belém', 'Manaus', 'Goiânia'
        )
        cidade_combo.grid(row=1, column=1, padx=5, pady=5)
        
        # Quantidade de leads
        tk.Label(config_frame, text="Máx. Leads:", bg='#f0f0f0', font=('Arial', 10)).grid(row=2, column=0, sticky='w', pady=5)
        self.max_leads_var = tk.StringVar(value="10")
        ttk.Spinbox(config_frame, from_=1, to=50, textvariable=self.max_leads_var, width=28).grid(row=2, column=1, padx=5, pady=5)
        
        # Frame de ações
        action_frame = tk.LabelFrame(
            self.root, 
            text=" Ações",
            font=('Arial', 12, 'bold'),
            bg='#f0f0f0',
            padx=15,
            pady=15
        )
        action_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Botões de ação
        self.buscar_btn = tk.Button(
            action_frame,
            text=" Buscar Leads",
            command=self.iniciar_busca,
            bg='#3498db',
            fg='white',
            font=('Arial', 11, 'bold'),
            width=15,
            height=2
        )
        self.buscar_btn.grid(row=0, column=0, padx=5, pady=5)
        
        self.salvar_btn = tk.Button(
            action_frame,
            text="Salvar Excel",
            command=self.salvar_leads,
            bg='#27ae60',
            fg='white',
            font=('Arial', 11, 'bold'),
            width=15,
            height=2,
            state='disabled'
        )
        self.salvar_btn.grid(row=0, column=1, padx=5, pady=5)
        
        self.whatsapp_btn = tk.Button(
            action_frame,
            text="📱 Enviar WhatsApp",
            command=self.enviar_whatsapp,
            bg='#25d366',
            fg='white',
            font=('Arial', 11, 'bold'),
            width=15,
            height=2,
            state='disabled'
        )
        self.whatsapp_btn.grid(row=0, column=2, padx=5, pady=5)
        
        self.parar_btn = tk.Button(
            action_frame,
            text=" Parar",
            command=self.parar_execucao,
            bg='#e74c3c',
            fg='white',
            font=('Arial', 11, 'bold'),
            width=15,
            height=2,
            state='disabled'
        )
        self.parar_btn.grid(row=0, column=3, padx=5, pady=5)
        
        # Frame de mensagem personalizada
        msg_frame = tk.LabelFrame(
            self.root, 
            text=" Mensagem para WhatsApp",
            font=('Arial', 12, 'bold'),
            bg='#f0f0f0',
            padx=15,
            pady=15
        )
        msg_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.mensagem_text = scrolledtext.ScrolledText(
            msg_frame, 
            height=4,
            font=('Arial', 10),
            wrap=tk.WORD
        )
        self.mensagem_text.pack(fill=tk.X)
        self.mensagem_text.insert('1.0', """Olá! Encontrei seu estabelecimento aqui no {cidade} e gostaria de conversar sobre uma parceria.

Aguardo seu retorno! """)
        
        tk.Label(msg_frame, text="Variáveis disponíveis: {nome}, {cidade}, {nicho}", 
                bg='#f0f0f0', font=('Arial', 9), fg='#666').pack(anchor='w')
        
        # Frame de logs
        log_frame = tk.LabelFrame(
            self.root, 
            text="Logs e Resultados",
            font=('Arial', 12, 'bold'),
            bg='#f0f0f0',
            padx=15,
            pady=15
        )
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(
            log_frame, 
            height=15,
            font=('Consolas', 9),
            wrap=tk.WORD,
            state='disabled'
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # Status bar
        self.status_var = tk.StringVar(value="Pronto para iniciar...")
        status_bar = tk.Label(
            self.root, 
            textvariable=self.status_var,
            relief=tk.SUNKEN,
            anchor=tk.W,
            font=('Arial', 9),
            bg='#34495e',
            fg='white'
        )
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)
    
    def log(self, mensagem):
        """Adiciona mensagem aos logs"""
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, f"{time.strftime('%H:%M:%S')} - {mensagem}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')
        self.root.update()
    
    def atualizar_status(self, mensagem):
        """Atualiza a barra de status"""
        self.status_var.set(mensagem)
        self.root.update()
    
    def toggle_buttons(self, buscar_state, outros_state):
        """Controla estado dos botões"""
        states = {'normal': 'normal', 'disabled': 'disabled'}
        self.buscar_btn.config(state=states[buscar_state])
        self.salvar_btn.config(state=states[outros_state])
        self.whatsapp_btn.config(state=states[outros_state])
        self.parar_btn.config(state=states[buscar_state])
    
    def iniciar_busca(self):
        """Inicia a busca em thread separada"""
        if self.is_running:
            return
        
        self.is_running = True
        self.toggle_buttons('disabled', 'disabled')
        self.leads = []
        self.log_text.config(state='normal')
        self.log_text.delete('1.0', tk.END)
        self.log_text.config(state='disabled')
        
        thread = threading.Thread(target=self.executar_busca)
        thread.daemon = True
        thread.start()
    
    def executar_busca(self):
        """Executa a busca de leads"""
        try:
            self.log(" Iniciando busca automática...")
            self.atualizar_status("Configurando navegador...")
            
            # Configurar Firefox
            firefox_options = Options()
            firefox_options.add_argument("--width=1200")
            firefox_options.add_argument("--height=800")
            self.driver = webdriver.Firefox(options=firefox_options)
            
            self.log("Navegador iniciado - Buscando no Google Maps...")
            self.atualizar_status("Buscando no Google Maps...")
            
            # Construir query de busca
            nicho = self.nicho_var.get()
            cidade = self.cidade_var.get()
            query = f"{nicho} {cidade}"
            max_leads = int(self.max_leads_var.get())
            
            self.log(f"Buscando: {query} (Máx: {max_leads} leads)")
            
            # Navegar para Google Maps
            self.driver.get("https://www.google.com/maps")
            time.sleep(3)
            
            # Realizar busca
            search_box = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "searchboxinput"))
            )
            search_box.clear()
            search_box.send_keys(query)
            search_box.send_keys(Keys.RETURN)
            time.sleep(5)
            
            self.log("Coletando resultados...")
            self.coletar_resultados_maps(max_leads)
            
            self.log(f"Busca concluída! {len(self.leads)} leads encontrados")
            self.atualizar_status(f"Busca concluída - {len(self.leads)} leads encontrados")
            
            # Habilitar botões
            self.toggle_buttons('normal', 'normal')
            
        except Exception as e:
            self.log(f"Erro na busca: {str(e)}")
            self.atualizar_status("Erro na busca")
            messagebox.showerror("Erro", f"Ocorreu um erro durante a busca:\n{str(e)}")
        
        finally:
            self.is_running = False
            self.toggle_buttons('normal', 'normal' if len(self.leads) > 0 else 'disabled')
    
    def coletar_resultados_maps(self, max_leads):
        """Coleta resultados do Google Maps"""
        try:
            # Rolar para carregar resultados
            for i in range(3):
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
                self.log(f"Carregando mais resultados... ({i+1}/3)")
            
            time.sleep(3)
            
            # Encontrar resultados
            places = self.driver.find_elements(By.CSS_SELECTOR, "div[role='article']")[:max_leads]
            self.log(f" Encontrados {len(places)} estabelecimentos")
            
            for i, place in enumerate(places):
                if not self.is_running:
                    break
                    
                try:
                    self.log(f"🔍 Processando {i+1}/{len(places)}...")
                    self.atualizar_status(f"Processando lead {i+1}/{len(places)}")
                    
                    place.click()
                    time.sleep(3)
                    
                    lead_info = self.extrair_detalhes_lead()
                    if lead_info:
                        self.leads.append(lead_info)
                        self.log(f" {lead_info['nome']}")
                    
                    # Fechar painel de detalhes
                    self.fechar_painel_detalhes()
                    
                except Exception as e:
                    self.log(f"Erro no lead {i+1}: {str(e)}")
                    continue
                    
        except Exception as e:
            self.log(f" Erro ao coletar resultados: {str(e)}")
            raise
    
    def extrair_detalhes_lead(self):
        """Extrai detalhes do lead"""
        try:
            # Aguardar carregamento
            time.sleep(3)
            
            # Extrair informações básicas
            nome = self.obter_texto_elemento('h1')
            endereco = self.obter_texto_elemento("button[data-item-id='address']")
            telefone = self.obter_texto_elemento("button[data-item-id='phone']")
            website = self.obter_website()
            
            # Buscar WhatsApp
            whatsapp = self.formatar_whatsapp(telefone)
            
            return {
                'nome': nome,
                'endereco': endereco,
                'telefone': telefone,
                'whatsapp': whatsapp,
                'website': website,
                'nicho': self.nicho_var.get(),
                'cidade': self.cidade_var.get(),
                'data_coleta': pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
            }
            
        except Exception as e:
            self.log(f"Erro nos detalhes: {str(e)}")
            return None
    
    def obter_texto_elemento(self, seletor):
        """Obtém texto de elemento se existir"""
        try:
            elemento = self.driver.find_element(By.CSS_SELECTOR, seletor)
            return elemento.text.strip()
        except:
            return ""
    
    def obter_website(self):
        """Obtém website do estabelecimento"""
        try:
            website_btn = self.driver.find_element(By.CSS_SELECTOR, "a[data-item-id='authority']")
            return website_btn.get_attribute('href')
        except:
            return ""
    
    def formatar_whatsapp(self, telefone):
        """Formata número para WhatsApp"""
        if not telefone:
            return ""
        
        numero_limpo = re.sub(r'\D', '', telefone)
        if len(numero_limpo) >= 10:
            return f"https://wa.me/55{numero_limpo}"
        
        return ""
    
    def fechar_painel_detalhes(self):
        """Fecha painel de detalhes"""
        try:
            close_btn = self.driver.find_element(By.CSS_SELECTOR, "button[aria-label*='Fechar']")
            close_btn.click()
            time.sleep(2)
        except:
            pass
    
    def salvar_leads(self):
        """Salva leads em Excel"""
        if not self.leads:
            messagebox.showwarning("Aviso", "Nenhum lead para salvar!")
            return
        
        try:
            filename = f"leads_{self.nicho_var.get()}_{self.cidade_var.get()}.xlsx"
            df = pd.DataFrame(self.leads)
            df.to_excel(filename, index=False)
            self.log(f"Leads salvos em: {filename}")
            messagebox.showinfo("Sucesso", f"Leads salvos em {filename}")
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao salvar: {str(e)}")
    
    def enviar_whatsapp(self):
        """Envia mensagens via WhatsApp"""
        if not self.leads:
            messagebox.showwarning("Aviso", "Nenhum lead para contatar!")
            return
        
        leads_com_whatsapp = [lead for lead in self.leads if lead['whatsapp']]
        if not leads_com_whatsapp:
            messagebox.showwarning("Aviso", "Nenhum lead com WhatsApp encontrado!")
            return
        
        # Confirmar envio
        confirmar = messagebox.askyesno(
            "Confirmar", 
            f"Enviar mensagem para {len(leads_com_whatsapp)} leads?\n\nO WhatsApp Web será aberto."
        )
        
        if not confirmar:
            return
        
        # Executar em thread separada
        thread = threading.Thread(target=self.executar_envio_whatsapp)
        thread.daemon = True
        thread.start()
    
    def executar_envio_whatsapp(self):
        """Executa o envio de mensagens no WhatsApp"""
        try:
            self.toggle_buttons('disabled', 'disabled')
            self.is_running = True
            
            leads_com_whatsapp = [lead for lead in self.leads if lead['whatsapp']]
            mensagem = self.mensagem_text.get('1.0', tk.END).strip()
            
            self.log("Iniciando envio de mensagens...")
            
            for i, lead in enumerate(leads_com_whatsapp):
                if not self.is_running:
                    break
                
                try:
                    self.log(f"Enviando para {i+1}/{len(leads_com_whatsapp)}: {lead['nome']}")
                    self.atualizar_status(f"Enviando {i+1}/{len(leads_com_whatsapp)}")
                    
                    
                    msg_personalizada = mensagem.replace('{nome}', lead['nome'])\
                                               .replace('{cidade}', lead['cidade'])\
                                               .replace('{nicho}', lead['nicho'])
                    
                    
                    self.driver.get(lead['whatsapp'])
                    time.sleep(10)
                    
                    # Enviar mensagem
                    caixa_msg = WebDriverWait(self.driver, 15).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "div[title='Caixa de texto de mensagem']"))
                    )
                    
                    caixa_msg.send_keys(msg_personalizada)
                    time.sleep(2)
                    caixa_msg.send_keys(Keys.ENTER)
                    time.sleep(5)
                    
                    self.log(f"Mensagem enviada para {lead['nome']}")
                    
                    # Intervalo aleatório entre mensagens
                    if i < len(leads_com_whatsapp) - 1:
                        intervalo = random.randint(15, 30)
                        self.log(f"⏳ Aguardando {intervalo} segundos...")
                        time.sleep(intervalo)
                        
                except Exception as e:
                    self.log(f"Erro ao enviar para {lead['nome']}: {str(e)}")
                    continue
            
            self.log(" Envio de mensagens concluído!")
            self.atualizar_status("Envio concluído")
            
        except Exception as e:
            self.log(f" Erro no envio: {str(e)}")
            messagebox.showerror("Erro", f"Erro durante o envio:\n{str(e)}")
        
        finally:
            self.is_running = False
            self.toggle_buttons('normal', 'normal')
    
    def parar_execucao(self):
        """Para a execução atual"""
        self.is_running = False
        self.log(" Parando execução...")
        self.atualizar_status("Parando...")
        
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass

def main():
    root = tk.Tk()
    app = BarbeariaLeadFinderGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
