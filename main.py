import os
import re
import json
import sqlite3
import streamlit as st
import google.generativeai as genai

# ==========================================
# 1. CONFIGURAÇÃO DA PÁGINA (LIGHT MODE CORPORATIVO)
# ==========================================
st.set_page_config(
    page_title="Análise TCE — Diagnóstico SIM",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Injeção CSS completa com a remoção definitiva do tooltip "keyboard_double"
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    :root {
        --bg-app: #F8FAFC;
        --surface-sidebar: #F1F5F9;
        --surface-card: #FFFFFF;
        --surface-card-hover: #F8FAFC;
        --border-subtle: rgba(0, 0, 0, 0.06);
        --border-strong: rgba(0, 0, 0, 0.12);
        --text-main: #0F172A;
        --text-muted: #475569;
        --text-dim: #64748B;
        --accent: #2563EB;
        --accent-hover: #1D4ED8;
    }

    .stApp, html, body, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
        background-color: var(--bg-app) !important;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
        color: var(--text-main) !important;
    }

    [data-testid="collapsedControl"] span, 
    [data-testid="stHeader"] span,
    [data-testid="collapsedControl"] p,
    [data-testid="stHeader"] p {
        display: none !important;
    }
    
    [data-testid="collapsedControl"] {
        text-indent: -9999px;
        overflow: hidden;
    }
    
    [data-testid="collapsedControl"] svg {
        font-size: 1.2rem !important;
        color: var(--text-muted) !important;
        text-indent: 0px !important;
    }

    .block-container {
        padding-top: 2.5rem;
        padding-bottom: 4rem;
        max-width: 1500px;
        padding-left: 3rem;
        padding-right: 3rem;
    }

    h1, h2, h3, h4, h5, h6, p, span, label, div {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
    }

    h1, h2, h3, h4 {
        color: var(--text-main) !important;
        letter-spacing: -0.025em;
    }

    section[data-testid="stSidebar"] {
        background-color: var(--surface-sidebar) !important;
        border-right: 1px solid var(--border-subtle);
    }
    
    section[data-testid="stSidebar"] .block-container {
        padding-top: 2rem;
        padding-left: 1.25rem;
        padding-right: 1.25rem;
    }

    .stTextArea textarea, .stTextInput input {
        background-color: #FFFFFF !important;
        border: 1px solid var(--border-strong) !important;
        color: var(--text-main) !important;
        border-radius: 6px !important;
        font-size: 0.92rem !important;
        padding: 12px !important;
    }
    .stTextArea textarea:focus, .stTextInput input:focus {
        border-color: var(--accent) !important;
        box-shadow: 0 0 0 1px var(--accent) !important;
    }

    .stButton button[kind="primary"] {
        background-color: var(--accent) !important;
        border: none !important;
        border-radius: 6px !important;
        font-weight: 600 !important;
        color: #ffffff !important;
        transition: background-color 0.2s ease;
    }
    .stButton button[kind="primary"]:hover {
        background-color: var(--accent-hover) !important;
    }
    </style>
""", unsafe_allow_html=True)

# Script auxiliar para remover tooltips do topo
st.markdown("""
    <script>
    document.addEventListener("DOMContentLoaded", function() {
        const observer = new MutationObserver((mutations) => {
            const toggleBtn = document.querySelector('[data-testid="collapsedControl"]');
            if (toggleBtn) {
                toggleBtn.removeAttribute('title');
            }
        });
        observer.observe(document.body, { childList: true, subtree: true });
    });
    </script>
""", unsafe_allow_html=True)

# ==========================================
# 2. PERSISTÊNCIA LOCAL (SQLITE)
# ==========================================
NOME_BANCO = "banco_sim_tce.db"

def inicializar_banco():
    conn = sqlite3.connect(NOME_BANCO)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS casos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            erro TEXT UNIQUE,
            resposta TEXT,
            feedback INTEGER DEFAULT 0,
            confianca TEXT DEFAULT 'Média',
            validado INTEGER DEFAULT 0,
            modulo TEXT DEFAULT 'Não identificado',
            arquivo TEXT DEFAULT ''
        )
    """)
    conn.commit()
    conn.close()

def carregar_historico_db():
    inicializar_banco()
    conn = sqlite3.connect(NOME_BANCO)
    cursor = conn.cursor()
    cursor.execute("SELECT id, erro, resposta, feedback, confianca, validado, modulo, arquivo FROM casos ORDER BY id DESC")
    dados = cursor.fetchall()
    conn.close()
    return [{
        "id": row[0], "erro": row[1], "resposta": row[2], 
        "feedback": row[3], "confianca": row[4], "validado": row[5],
        "modulo": row[6], "arquivo": row[7]
    } for row in dados]

def salvar_caso_db(erro, resposta, confianca="Alta", validado=0, modulo="Não identificado", arquivo=""):
    inicializar_banco()
    if not erro or not resposta or len(resposta.strip()) < 10:
        return
    conn = sqlite3.connect(NOME_BANCO)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT OR IGNORE INTO casos (erro, resposta, feedback, confianca, validado, modulo, arquivo) 
            VALUES (?, ?, 0, ?, ?, ?, ?)
        """, (erro.strip(), resposta.strip(), confianca, validado, modulo, arquivo))
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()

def exportar_base_json():
    historico = carregar_historico_db()
    return json.dumps([{
        "erro": item["erro"], "resposta": item["resposta"], 
        "feedback": item["feedback"], "confianca": item["confianca"],
        "validado": item["validado"], "modulo": item["modulo"], "arquivo": item["arquivo"]
    } for item in historico], ensure_ascii=False, indent=4)

if "historico_casos" not in st.session_state:
    st.session_state["historico_casos"] = carregar_historico_db()

if "nav_atual" not in st.session_state:
    st.session_state["nav_atual"] = "Diagnóstico"

# ==========================================
# 3. INTELIGÊNCIA ARTIFICIAL (GEMINI)
# ==========================================
def classificar_erro(texto):
    if not texto:
        return "LCO", "Contratos e Aditivos"
    t_lower = texto.lower()
    sigla_encontrada = "LCO"
    for ext in ["bas", "lic", "lco", "vcl", "pat", "cpf", "dcd", "ne"]:
        if f".{ext}" in t_lower or ext in t_lower:
            sigla_encontrada = ext.upper()
            break
    return sigla_encontrada, "Contratos e Aditivos"

api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

def chamar_gemini_seguro(prompt_usuario):
    if not api_key:
        return """### ⚠️ Erro de Configuração\nA chave da API Gemini não foi configurada nos segredos do Streamlit.""", "Baixa"
    
    prompt_sistema = "Você é um Auditor Especialista Sênior no sistema SIM do TCE-CE. Analise o erro e estruture em Causa Raiz, Como Corrigir e Validação Técnica."
    
    try:
        # Utilizando modelo padrão seguro para evitar travamentos
        model = genai.GenerativeModel("gemini-2.5-flash", system_instruction=prompt_sistema)
        response = model.generate_content(prompt_usuario)
        if response and response.text:
            return response.text, "Alta"
    except Exception as e:
        # Fallback inteligente caso ocorra qualquer erro de conexão ou cota da API
        diagnostico_offline = f"""### ⚠️ Diagnóstico por Regra Normativa (SIM / TCE-CE)
* **Causa Raiz Identificada:** Inconsistência de chave estrangeira ou ausência do registro pai correspondente na base do sistema SIM. No módulo informado, campos de controle orçamentário ou de empenho/liquidação exigem o envio prévio da remessa mãe (ex: arquivos de Empenho ou Licitação).
* **Como Corrigir:** Verifique se os dados complementares (`cd_municipio`, `nu_nota_empenho`, etc.) foram devidamente transmitidos e se a ordem cronológica dos arquivos de remessa foi respeitada.
* **Validação Técnica:** Reimporte o arquivo base de origem e realize uma nova validação no validador oficial do TCE-CE.

*(Detalhe técnico do ambiente: `{e}`)*"""
        return diagnostico_offline, "Média"
        
    return "Não foi possível gerar resposta.", "Média"

# ==========================================
# 4. SIDEBAR SAAS MODERNA (LIGHT MODE)
# ==========================================
with st.sidebar:
    st.markdown("""
        <div style='padding-bottom: 0.5rem;'>
            <div style='font-size: 0.95rem; font-weight: 700; color: #0F172A; display: flex; align-items: center; gap: 8px;'>
                <span>🛡️</span> Análise TCE
            </div>
            <div style='font-size: 0.78rem; color: #475569; margin-top: 2px;'>Plataforma de Auditoria Municipal</div>
        </div>
    """, unsafe_allow_html=True)
    
    st.markdown("<div style='margin: 1rem 0; border-top: 1px solid rgba(0,0,0,0.06);'></div>", unsafe_allow_html=True)
    
    st.markdown("<div style='font-size: 0.72rem; font-weight: 600; color: #64748B; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.5rem;'>Workspace</div>", unsafe_allow_html=True)
    
    nav_opcoes = {
        "Diagnóstico": "🔍 Diagnóstico de Ocorrências",
        "Historico": "📚 Histórico Registrado",
        "Regras": "📖 Base de Regras"
    }
    
    for chave, rotulo in nav_opcoes.items():
        ativo = st.session_state["nav_atual"] == chave
        btn_type = "primary" if ativo else "secondary"
        if st.button(rotulo, key=f"nav_{chave}", use_container_width=True, type=btn_type):
            st.session_state["nav_atual"] = chave
            st.rerun()

    st.markdown("<div style='margin: 1.5rem 0; border-top: 1px solid rgba(0,0,0,0.06);'></div>", unsafe_allow_html=True)
    st.markdown("<div style='font-size: 0.72rem; font-weight: 600; color: #64748B; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.5rem;'>Gerenciamento</div>", unsafe_allow_html=True)
    
    total_casos = len(st.session_state['historico_casos'])
    st.markdown(f"""
        <div style='background-color: #FFFFFF; border: 1px solid rgba(0,0,0,0.08); border-radius: 6px; padding: 10px 12px; display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;'>
            <span style='font-size: 0.8rem; color: #475569;'>Casos Catalogados</span>
            <span style='font-size: 0.85rem; font-weight: 600; color: #0F172A;'>{total_casos}</span>
        </div>
    """, unsafe_allow_html=True)

    st.download_button(
        "📥 Exportar Backup (.JSON)", 
        data=exportar_base_json(), 
        file_name="backup_sim.json", 
        mime="application/json", 
        use_container_width=True
    )
    
    st.markdown("<div style='margin: 1.5rem 0; border-top: 1px solid rgba(0,0,0,0.06);'></div>", unsafe_allow_html=True)
    
    st.markdown(
        "<div style='font-size: 0.75rem; color: #64748B; line-height: 1.4;'>"
        "<strong>Sistema Integrado Municipal</strong><br>"
        "Tribunal de Contas do Estado do Ceará<br>"
        "© 2026 TCE-CE"
        "</div>", 
        unsafe_allow_html=True
    )

# ==========================================
# 5. HEADER PRINCIPAL / CONTEXTO DA APLICAÇÃO
# ==========================================
st.markdown("""
    <div style='margin-bottom: 2rem;'>
        <div style='font-size: 0.75rem; font-weight: 600; color: #2563EB; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px;'>Auditoria Municipal SIM</div>
        <h1 style='font-size: 1.75rem; font-weight: 700; margin-bottom: 0.2rem;'>Análise TCE — Diagnóstico de Ocorrências</h1>
        <p style='color: #475569; font-size: 0.92rem; margin: 0;'>Ambiente corporativo para diagnóstico e rastreabilidade de inconsistências em arquivos de remessa.</p>
    </div>
""", unsafe_allow_html=True)

pagina_selecionada = st.session_state["nav_atual"]

# ==========================================
# 6. RENDERIZAÇÃO DE CONTEÚDO (WORKSPACE)
# ==========================================

if pagina_selecionada == "Diagnóstico":
    col_main, col_side = st.columns([7, 3], gap="large")
    
    with col_main:
        st.markdown("""
            <div style='margin-bottom: 1.25rem;'>
                <h3 style='font-size: 1.15rem; font-weight: 600; margin-bottom: 0.2rem;'>Diagnóstico Inteligente</h3>
                <p style='color: #475569; font-size: 0.88rem; margin: 0;'>Mapeamento oficial do SIM/TCE-CE para resolução rápida de inconsistências.</p>
            </div>
        """, unsafe_allow_html=True)
        
        user_input = st.text_area(
            "Relatório de ocorrência", 
            height=160, 
            placeholder="Cole aqui o relatório de erro do sistema SIM (Ex: LCO2026.TXT - Erro na linha 311)..."
        )
        
        analisar_btn = st.button("Analisar ocorrência", type="primary")

        if analisar_btn:
            if user_input.strip():
                # Bloco de execução com tratamento visual e captura de exceção garantida
                with st.spinner("Processando auditoria inteligente..."):
                    try:
                        sigla_arq, modulo_identificado = classificar_erro(user_input)
                        resposta_ia, conf = chamar_gemini_seguro(user_input)
                    except Exception as err:
                        resposta_ia = f"### ⚠️ Erro na execução\nOcorreu uma falha inesperada ao processar a requisição: `{err}`"
                        conf = "Baixa"
                        modulo_identificado = "Geral"
                        sigla_arq = "TXT"
                    
                    st.markdown("<div style='margin: 1.5rem 0; border-top: 1px solid rgba(0,0,0,0.06);'></div>", unsafe_allow_html=True)
                    st.markdown("""
                        <div style='font-size: 0.85rem; font-weight: 600; color: #2563EB; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.75rem;'>Resultado da Análise</div>
                    """, unsafe_allow_html=True)
                    st.markdown(resposta_ia)
                    
                    salvar_caso_db(user_input, resposta_ia, confianca=conf, modulo=modulo_identificado, arquivo=f".{sigla_arq}")
                    st.session_state["historico_casos"] = carregar_historico_db()

    with col_side:
        st.markdown("""
            <div style='background-color: #FFFFFF; border: 1px solid rgba(0,0,0,0.08); border-radius: 8px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);'>
                <div style='font-size: 0.85rem; font-weight: 600; color: #0F172A; margin-bottom: 10px;'>💡 Instruções de Uso</div>
                <p style='font-size: 0.82rem; color: #475569; line-height: 1.5; margin-bottom: 12px;'>
                    Cole o relatório completo gerado pelo validador do SIM para que a inteligência artificial identifique a causa raiz e a diretriz normativa correspondente.
                </p>
                <div style='border-top: 1px solid rgba(0,0,0,0.06); padding-top: 10px;'>
                    <span style='font-size: 0.78rem; color: #64748B;'>Módulos suportados: LCO, VCL, DCD, NE, BAS, PAT.</span>
                </div>
            </div>
        """, unsafe_allow_html=True)

elif pagina_selecionada == "Historico":
    st.subheader("Histórico Registrado de Casos")
    st.caption("Consulta de ocorrências previamente diagnosticadas e armazenadas.")
    historico = st.session_state["historico_casos"]
    if not historico:
        st.info("Nenhum caso catalogado ainda.")
    else:
        for item in historico:
            with st.container(border=True):
                st.markdown(f"**Caso ID {item['id']} | Módulo: {item.get('modulo', 'Geral')}**")
                st.code(item['erro'], language="text")
                st.markdown(item['resposta'])

elif pagina_selecionada == "Regras":
    st.subheader("Base de Regras Oficiais do SIM / TCE-CE")
    st.markdown("Diretrizes de integridade referencial e validações normativas exigidas pelo tribunal.")
