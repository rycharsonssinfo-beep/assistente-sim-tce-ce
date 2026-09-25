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
        --accent: #0F766E;
        --accent-hover: #115E59;
    }

    .stApp {
        background-color: var(--bg-app);
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        color: var(--text-main);
    }

    .block-container {
        padding-top: 2.5rem;
        padding-bottom: 7rem;
        max-width: 1050px;
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
Ajude técnicos a diagnosticar divergências comparando arquivos locais com registros do tribunal."""

    contents = [{"role": ("user" if m["role"] == "user" else "model"), "parts": [m["content"]]} for m in historico_conversas]
    contents.append({"role": "user", "parts": [ultima_mensagem]})
    
    try:
        model = genai.GenerativeModel("gemini-3.6-flash", system_instruction=prompt_sistema)
        response = model.generate_content(contents)
        if response and response.text:
            return response.text
    except Exception as e:
        return f"Erro ao processar com a IA: {e}"
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
if "arquivo_principal" not in st.session_state:
    st.session_state["arquivo_principal"] = None
if "arquivo_secundario" not in st.session_state:
    st.session_state["arquivo_secundario"] = None
if "exibir_apenas_erros" not in st.session_state:
    st.session_state["exibir_apenas_erros"] = True
if "resultado_comparacao" not in st.session_state:
    st.session_state["resultado_comparacao"] = None

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
        st.session_state["arquivo_principal"] = None
        st.session_state["arquivo_secundario"] = None
        st.session_state["resultado_comparacao"] = None
        st.rerun()
        
    st.markdown("---")
    
    nav_opcoes = {
        "Assistente": "💬 Assistente de Chat",
        "Verificador": "🔍 Análise de divergências",
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
    st.markdown("### Processos › **Análise de divergências**")
    
    # Barra de Progresso Visual Estilo Wizard (1. Linhas -> 2. Arquivo -> 3. Resultado)
    etapa = st.session_state["etapa_verificacao"]
    
    col_ind1, col_ind2, col_ind3 = st.columns(3)
    with col_ind1:
        st.markdown(f"**{'🟢' if etapa >= 1 else '⚪'} 1. Linhas**")
    with col_ind2:
        st.markdown(f"**{'🟢' if etapa >= 2 else '⚪'} 2. Arquivo**")
    with col_ind3:
        st.markdown(f"**{'🟢' if etapa >= 3 else '⚪'} 3. Resultado**")
    
    st.markdown("---")

    # ------------------------------------------
    # ETAPA 1: DEFINIR LINHAS COM ERRO
    # ------------------------------------------
    if etapa == 1:
        st.markdown("#### Defina as linhas com erro para iniciar")
        st.session_state["linhas_erro"] = st.text_area(
            "Linhas com erro",
            value=st.session_state["linhas_erro"],
            placeholder="Ex.: 251",
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
                    st.warning("Por favor, informe ao menos uma linha com erro.")

    # ------------------------------------------
    # ETAPA 2: ANEXAR ARQUIVOS E FILTROS
    # ------------------------------------------
    elif etapa == 2:
        st.markdown("#### Anexe os arquivos para validações")
        st.markdown(f"*Linhas com erro informadas:* `{st.session_state['linhas_erro']}`")
        
        col_up1, col_up2 = st.columns(2)
        with col_up1:
            st.session_state["arquivo_principal"] = st.file_uploader("Anexe o arquivo principal (ex: .DCD)")
        with col_up2:
            st.session_state["arquivo_secundario"] = st.file_uploader("Clique ou arraste o arquivo CO (.LCO)")
            
        st.session_state["exibir_apenas_erros"] = st.checkbox(
            "Exibir somente as linhas com erros", 
            value=st.session_state["exibir_apenas_erros"],
            help="O servidor filtrará automaticamente apenas as divergências."
        )
        
        col_voltar, col_avancar = st.columns([1, 1])
        with col_voltar:
            if st.button("Voltar", use_container_width=True):
                st.session_state["etapa_verificacao"] = 1
                st.rerun()
        with col_avancar:
            if st.button("Executar análise", type="primary", use_container_width=True):
                with st.spinner("Comparando dados locais com o histórico do Tribunal..."):
                    # Simulação de estrutura comparativa de divergência idêntica à sua tela
                    st.session_state["resultado_comparacao"] = {
                        "linha": st.session_state["linhas_erro"],
                        "status": "Contrato localizado",
                        "campos": [
                            {"nome": "CONTRATO", "arquivo": "07.12.09.25.001", "historico": "07.12.09.25.001", "divergente": False},
                            {"nome": "CPF GESTOR", "arquivo": "00322594332", "historico": "Cw/SxlO8tmg/z5DtWKatiA==", "divergente": True},
                            {"nome": "ASSINATURA", "arquivo": "02/06/2026", "historico": "02/06/2026", "divergente": False}
                        ]
                    }
                    st.session_state["etapa_verificacao"] = 3
                    st.rerun()

    # ------------------------------------------
    # ETAPA 3: RESULTADO DA ANÁLISE (ESTILO CARTÃO COMPARATIVO)
    # ------------------------------------------
    elif etapa == 3:
        st.markdown("### Resultado da análise")
        st.markdown("Mostrando apenas divergências.")
        
        res = st.session_state["resultado_comparacao"]
        
        if res:
            # Card principal da linha
            with st.container(border=True):
                col_cab1, col_cab2 = st.columns([4, 1])
                with col_cab1:
                    st.markdown(f"#### Linha {res['linha']}")
                with col_cab2:
                    st.markdown(f"🟢 **{res['status']}**")
                
                st.markdown("---")
                
                # Sub-colunas comparando os campos do Arquivo vs Histórico (Tribunal)
                cols = st.columns(len(res['campos']))
                for i, campo in enumerate(res['campos']):
                    with cols[i]:
                        # Estilo visual condicional se houver divergência (fundo avermelhado simulado)
                        borda_cor = "border: 1px solid #EF4444; background-color: #FEF2F2;" if campo['divergente'] else "border: 1px solid #E2E8F0; background-color: #FFFFFF;"
                        
                        st.markdown(f"""
                        <div style="{borda_cor} padding: 10px; border-radius: 8px; margin-bottom: 5px;">
                            <small style="color: #64748B; font-weight: bold;">{campo['nome']}</small><br>
                            <b>Arquivo:</b> <span style="color: {'#DC2626' if campo['divergente'] else '#0F172A'};">{campo['arquivo']}</span><br>
                            <small style="color: #64748B;">Histórico:</small> <span style="font-size: 0.85rem;">{campo['historico']}</span>
                        </div>
                        """, unsafe_allow_html=True)

        st.markdown("---")
        
        col_voltar_res, col_exportar = st.columns([1, 1])
        with col_voltar_res:
            if st.button("⬅️ Nova Análise", use_container_width=True):
                st.session_state["etapa_verificacao"] = 1
                st.session_state["linhas_erro"] = ""
                st.session_state["arquivo_principal"] = None
                st.session_state["arquivo_secundario"] = None
                st.session_state["resultado_comparacao"] = None
                st.rerun()

elif pagina == "Historico":
    st.markdown("## 📁 Histórico e Armazenamento")
    st.markdown("Gerenciamento de análises e arquivos salvos através do `StorageService`.")
    if storage_service:
        st.success("Serviço de armazenamento conectado com sucesso.")
    else:
        st.info("Nenhum armazenamento persistente configurado ou serviço indisponível no momento.")
