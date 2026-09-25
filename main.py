import os
import json
import streamlit as st
import google.generativeai as genai
import pandas as pd

# Importações dos seus serviços e módulos personalizados
from services.tce_api import TCEApiClient
from storage.storage_service import StorageService
from services.error_validation_service import ErrorValidationService

# ==========================================
# 1. CONFIGURAÇÃO DA PÁGINA E CSS
# ==========================================
st.set_page_config(
    page_title="Assistente SIM — TCE-CE",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    :root {
        --bg-app: #F8FAFC;
        --sidebar-bg: #FFFFFF;
        --surface-card: #FFFFFF;
        --surface-hover: #F1F5F9;
        --border-subtle: #E2E8F0;
        --border-strong: #CBD5E1;
        --text-main: #0F172A;
        --text-muted: #475569;
        --accent: #2563EB;
        --accent-hover: #1D4ED8;
    }

    .stApp {
        background-color: var(--bg-app);
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        color: var(--text-main);
    }

    .block-container {
        padding-top: 2.5rem;
        padding-bottom: 7rem;
        max-width: 950px;
        margin: 0 auto;
    }

    section[data-testid="stSidebar"] {
        background-color: var(--sidebar-bg);
        border-right: 1px solid var(--border-subtle);
    }
    
    [data-testid="stChatInput"] textarea {
        background-color: #FFFFFF;
        color: var(--text-main);
        border: 1px solid var(--border-strong);
        border-radius: 12px;
        font-size: 0.95rem;
        padding: 0.85rem 1rem;
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        border-bottom: 1px solid var(--border-subtle);
        padding-bottom: 0.5rem;
    }

    .stTabs [data-baseweb="tab"] {
        background-color: var(--surface-card);
        border: 1px solid var(--border-subtle);
        border-radius: 8px;
        color: var(--text-muted);
        padding: 0.5rem 1rem;
        font-weight: 500;
    }

    .stTabs [aria-selected="true"] {
        background-color: var(--surface-hover);
        color: var(--accent);
        border-color: var(--border-strong);
    }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. INICIALIZAÇÃO DOS SERVIÇOS
# ==========================================
@st.cache_resource
def carregar_servicos():
    try:
        tce_api = TCEApiClient()
        storage = StorageService()
        validador = ErrorValidationService()
        return tce_api, storage, validador
    except Exception:
        return None, None, None

tce_api, storage_service, error_validator = carregar_servicos()

# ==========================================
# 3. CONFIGURAÇÃO DA API GEMINI
# ==========================================
api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

def consultar_assistente_gemini(historico_conversas, ultima_mensagem):
    if not api_key:
        return "### ⚠️ Configuração Pendente\nA chave da API Gemini não foi configurada."
    
    prompt_sistema = """Você é um assistente técnico sênior especializado no SIM — Sistema de Informações Municipais do TCE-CE, com base no Manual do SIM 2026.
Ajude técnicos e operadores a diagnosticar erros, inconsistências e divergências de remessa de arquivos do SIM a partir das linhas e arquivos informados.
Estruture a resposta claramente em: 
1. **O que significa a divergência**
2. **Onde está o problema (Linhas afetadas)**
3. **Provável causa raiz**
4. **Como corrigir**
5. **Fundamentação (Manual do SIM 2026)**"""

    contents = [{"role": ("user" if m["role"] == "user" else "model"), "parts": [m["content"]]} for m in historico_conversas]
    contents.append({"role": "user", "parts": [ultima_mensagem]})
    
    try:
        model = genai.GenerativeModel("gemini-3.6-flash", system_instruction=prompt_sistema)
        response = model.generate_content(contents)
        if response and response.text:
            return response.text
    except Exception as e:
        return f"Erro ao processar a solicitação com a IA: {e}"
    return "Não foi possível gerar resposta."

# ==========================================
# 4. GERENCIAMENTO DE ESTADO
# ==========================================
if "mensagens" not in st.session_state:
    st.session_state["mensagens"] = []
if "nav_atual" not in st.session_state:
    st.session_state["nav_atual"] = "Assistente"

# Estados para o fluxo em etapas da Verificação de Erros
if "etapa_verificacao" not in st.session_state:
    st.session_state["etapa_verificacao"] = 1  # 1: Linhas, 2: Arquivo, 3: Resultado
if "linhas_erro" not in st.session_state:
    st.session_state["linhas_erro"] = ""
if "conteudo_arquivo_verificacao" not in st.session_state:
    st.session_state["conteudo_arquivo_verificacao"] = ""
if "resultado_diagnostico" not in st.session_state:
    st.session_state["resultado_diagnostico"] = ""

# ==========================================
# 5. SIDEBAR DE NAVEGAÇÃO
# ==========================================
with st.sidebar:
    st.markdown("### 🛡️ Assistente SIM\n*TCE-CE • Manual 2026*")
    if st.button("＋ Nova análise", use_container_width=True, type="primary"):
        st.session_state["mensagens"] = []
        st.session_state["nav_atual"] = "Assistente"
        st.session_state["etapa_verificacao"] = 1
        st.session_state["linhas_erro"] = ""
        st.session_state["conteudo_arquivo_verificacao"] = ""
        st.session_state["resultado_diagnostico"] = ""
        st.rerun()
        
    st.markdown("---")
    
    nav_opcoes = {
        "Assistente": "💬 Assistente de Chat",
        "Verificador": "🔍 Verificador de Erros (Arquivos SIM)",
        "Historico": "📁 Histórico / Armazenamento"
    }
    
    for chave, rotulo in nav_opcoes.items():
        ativo = st.session_state["nav_atual"] == chave
        if st.button(rotulo, key=f"nav_{chave}", use_container_width=True, type="primary" if ativo else "secondary"):
            st.session_state["nav_atual"] = chave
            st.rerun()

# ==========================================
# 6. TELAS DA APLICAÇÃO
# ==========================================
pagina = st.session_state["nav_atual"]

if pagina == "Assistente":
    st.markdown("## 💬 Assistente SIM — Chat Técnico")
    for msg in st.session_state["mensagens"]:
        with st.chat_message("user" if msg["role"] == "user" else "assistant", avatar="👤" if msg["role"] == "user" else "🛡️"):
            st.markdown(msg["content"])
            
    if prompt := st.chat_input("Digite sua dúvida ou ocorrência do SIM..."):
        st.session_state["mensagens"].append({"role": "user", "content": prompt})
        with st.chat_message("user", avatar="👤"):
            st.markdown(prompt)
        with st.chat_message("assistant", avatar="🛡️"):
            with st.spinner("Analisando..."):
                resposta = consultar_assistente_gemini(st.session_state["mensagens"][:-1], prompt)
                st.markdown(resposta)
        st.session_state["mensagens"].append({"role": "assistant", "content": resposta})

elif pagina == "Verificador":
    st.markdown("### 🔍 Análise de divergências")
    
    # Barra de Progresso / Indicador Visual de Etapas
    etapa = st.session_state["etapa_verificacao"]
    
    col_ind1, col_ind2, col_ind3 = st.columns(3)
    with col_ind1:
        st.markdown(f"**{'🟢' if etapa >= 1 else '⚪'} 1. Linhas**")
    with col_ind2:
        st.markdown(f"**{'🟢' if etapa >= 2 else '⚪'} 2. Arquivo**")
    with col_ind3:
        st.markdown(f"**{'🟢' if etapa >= 3 else '⚪'} 3. Resultado**")
    
    st.markdown("---")

    # ETAPA 1: DEFINIR LINHAS COM ERRO
    if etapa == 1:
        st.markdown("#### Defina as linhas com erro para iniciar")
        st.session_state["linhas_erro"] = st.text_area(
            "Linhas com erro",
            value=st.session_state["linhas_erro"],
            placeholder="Ex.: 113, 150, 201-205",
            height=120,
            label_visibility="collapsed"
        )
        
        col_esp, col_btn = st.columns([4, 1])
        with col_btn:
            if st.button("Avançar para upload", type="primary", use_container_width=True):
                if st.session_state["linhas_erro"].strip():
                    st.session_state["etapa_verificacao"] = 2
                    st.rerun()
                else:
                    st.warning("Por favor, informe ao menos uma linha ou intervalo com erro.")

    # ETAPA 2: UPLOAD OU COLETA DO ARQUIVO / RELATÓRIO
    elif etapa == 2:
        st.markdown("#### Envie o arquivo ou cole os dados do log do SIM")
        st.markdown(f"*Linhas com erro informadas na etapa anterior:* `{st.session_state['linhas_erro']}`")
        
        arquivo_enviado = st.file_uploader("Enviar arquivo de log ou remessa do SIM", type=["txt", "csv", "json", "rem"])
        log_input = st.text_area("Ou cole o conteúdo do arquivo/relatório de erros:", value=st.session_state["conteudo_arquivo_verificacao"], height=150)
        
        col_voltar, col_avancar = st.columns([1, 1])
        with col_voltar:
            if st.button("⬅️ Voltar", use_container_width=True):
                st.session_state["etapa_verificacao"] = 1
                st.rerun()
        with col_avancar:
            if st.button("Analisar divergências ➔", type="primary", use_container_width=True):
                texto_analise = ""
                if arquivo_enviado is not None:
                    texto_analise = str(arquivo_enviado.read(), "utf-8", errors="ignore")
                elif log_input.strip():
                    texto_analise = log_input
                
                if texto_analise:
                    st.session_state["conteudo_arquivo_verificacao"] = texto_analise
                    with st.spinner("Cruzando linhas afetadas com o Manual do SIM 2026..."):
                        prompt_auditoria = (
                            f"O operador reportou erros nas seguintes linhas: {st.session_state['linhas_erro']}.\n"
                            f"Abaixo está o conteúdo/relatório do arquivo do SIM enviado:\n\n{texto_analise}\n\n"
                            "Por favor, apresente o resultado detalhado do que está divergente nestas linhas específicas e como corrigir."
                        )
                        st.session_state["resultado_diagnostico"] = consultar_assistente_gemini([], prompt_auditoria)
                        st.session_state["etapa_verificacao"] = 3
                        st.rerun()
                else:
                    st.warning("Envie um arquivo ou cole o conteúdo do log para prosseguir.")

    # ETAPA 3: RESULTADO DAS DIVERGÊNCIAS
    elif etapa == 3:
        st.markdown("#### Resultado da Análise de Divergências")
        st.markdown(f"**Linhas analisadas:** `{st.session_state['linhas_erro']}`")
        
        st.markdown("---")
        st.markdown(st.session_state["resultado_diagnostico"])
        st.markdown("---")
        
        col_recomecar, _ = st.columns([1, 2])
        with col_recomecar:
            if st.button("🔄 Nova Verificação", type="primary", use_container_width=True):
                st.session_state["etapa_verificacao"] = 1
                st.session_state["linhas_erro"] = ""
                st.session_state["conteudo_arquivo_verificacao"] = ""
                st.session_state["resultado_diagnostico"] = ""
                st.rerun()

elif pagina == "Historico":
    st.markdown("## 📁 Histórico e Armazenamento")
    st.markdown("Gerenciamento de análises e arquivos salvos através do `StorageService`.")
    if storage_service:
        st.success("Serviço de armazenamento conectado com sucesso.")
    else:
        st.info("Nenhum armazenamento persistente configurado ou serviço indisponível no momento.")
