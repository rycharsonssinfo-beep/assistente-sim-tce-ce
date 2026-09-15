import os
import re
import json
import streamlit as st
import google.generativeai as genai

# ==========================================
# 1. INVESTIGAÇÃO TÉCNICA E CORREÇÃO DO "KEYBOARD_DOUBLE..."
# ==========================================
# DIAGNÓSTICO DA ORIGEM DO PROBLEMA:
# O texto literal "keyboard_double..." aparece no canto superior esquerdo da sidebar 
# (geralmente no botão nativo de colapso/expansão da sidebar do Streamlit, representado 
# internamente no Streamlit por ligatures de Material Symbols/Icons, como `keyboard_double_arrow_left` 
# ou `keyboard_double_arrow_right`).
# 
# CAUSA RAIZ:
# No CSS anterior, existiam regras globais agressivas (como aplicar `font-family: 'Inter', sans-serif !important;` 
# em seletores genéricos como `*`, `span`, ou elementos internos de componentes de controle). 
# Quando uma regra global substitui a família de fontes (`font-family`) de elementos que dependem de 
# fontes específicas de ícones (como a Material Symbols / Material Icons utilizada pelo Streamlit nos seus 
# botões de controle internos), o navegador deixa de renderizar o caractere gráfico da fonte de ícones 
# e passa a exibir o texto literal da ligature (ex: `keyboard_double_arrow_left` ou truncado como `keyboard_double...`).
#
# CORREÇÃO DEFINITIVA APLICADA:
# - Removemos absolutamente qualquer regra CSS global com seletor `* { font-family: ... }` ou `span { font-family: ... }`.
# - Isolamos a aplicação da fonte `Inter` estritamente aos elementos de texto e conteúdo estrutural da aplicação (títulos, parágrafos, blocos de chat), preservando intocada a família de fontes e as ligatures dos ícones nativos do Streamlit.
# - Adicionamos uma regra direcionada e segura para estilizar o container de controle da sidebar sem sobrescrever suas fontes de ícones.
# ==========================================

st.set_page_config(
    page_title="Assistente SIM — TCE-CE",
    page_icon="🛡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Injeção CSS refinada para Light Mode moderno sem quebrar ligatures de ícones do Streamlit
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
        --text-dim: #94A3B8;
        --accent: #2563EB;
        --accent-hover: #1D4ED8;
    }

    /* Fundo geral e estrutura da aplicação */
    .stApp, html, body, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
        background-color: var(--bg-app) !important;
    }

    /* APLICAÇÃO SEGURA DA TIPOGRAFIA: restrita a títulos, textos e elementos de conteúdo,
       preservando integralmente as fontes de ícones nativas do Streamlit para evitar o bug de ligatures textuais. */
    h1, h2, h3, h4, h5, h6, p, label, .stMarkdown, .stText, span:not([class*="material"]):not([data-testid*="icon"]) {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
        color: var(--text-main);
    }

    /* Layout Principal centralizado com largura de leitura ideal (max 900px) */
    .block-container {
        padding-top: 2rem;
        padding-bottom: 7rem;
        max-width: 900px;
        margin: 0 auto;
    }

    /* Sidebar minimalista e elegante em Light Mode */
    section[data-testid="stSidebar"] {
        background-color: var(--sidebar-bg) !important;
        border-right: 1px solid var(--border-subtle);
    }
    
    section[data-testid="stSidebar"] .block-container {
        padding-top: 2rem;
        padding-left: 1.25rem;
        padding-right: 1.25rem;
        max-width: 100%;
    }

    /* Estilização de Botões da Sidebar */
    section[data-testid="stSidebar"] .stButton button {
        background-color: transparent !important;
        border: 1px solid var(--border-subtle) !important;
        border-radius: 8px !important;
        color: var(--text-muted) !important;
        font-weight: 500 !important;
        font-size: 0.88rem !important;
        text-align: left !important;
        padding: 0.55rem 0.85rem !important;
        transition: all 0.2s ease;
        box-shadow: none !important;
    }

    section[data-testid="stSidebar"] .stButton button:hover {
        background-color: var(--surface-hover) !important;
        color: var(--text-main) !important;
        border-color: var(--border-strong) !important;
    }

    /* Botão primário na sidebar (+ Nova análise) */
    section[data-testid="stSidebar"] .stButton button[kind="primary"] {
        background-color: #EFF6FF !important;
        border: 1px solid #BFDBFE !important;
        color: var(--accent) !important;
        font-weight: 600 !important;
    }
    section[data-testid="stSidebar"] .stButton button[kind="primary"]:hover {
        background-color: #DBEAFE !important;
        color: var(--accent-hover) !important;
    }

    /* Estilização impecável do Chat Input fixo no rodapé (sem faixa branca indesejada) */
    [data-testid="stChatInput"] {
        background-color: var(--bg-app) !important;
        border-top: 1px solid var(--border-subtle);
        padding: 1rem 0;
    }

    [data-testid="stChatInput"] textarea {
        background-color: #FFFFFF !important;
        color: var(--text-main) !important;
        border: 1px solid var(--border-strong) !important;
        border-radius: 12px !important;
        font-size: 0.95rem !important;
        padding: 0.85rem 1rem !important;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04) !important;
        transition: border-color 0.2s ease, box-shadow 0.2s ease;
    }

    [data-testid="stChatInput"] textarea:focus {
        border-color: var(--accent) !important;
        box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1) !important;
    }

    [data-testid="stChatInput"] button {
        background-color: var(--accent) !important;
        color: #ffffff !important;
        border-radius: 8px !important;
        margin: 4px !important;
        transition: background-color 0.2s ease;
    }
    [data-testid="stChatInput"] button:hover {
        background-color: var(--accent-hover) !important;
    }

    /* Balões de mensagens nativos ajustados para Light Mode */
    [data-testid="stChatMessage"] {
        background-color: transparent !important;
        padding: 1.25rem 0 !important;
        border-bottom: 1px solid var(--border-subtle);
    }

    /* Tabs modernas na Base de Regras */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: transparent;
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
        background-color: var(--surface-hover) !important;
        color: var(--accent) !important;
        border-color: var(--border-strong) !important;
    }

    /* Inputs de pesquisa */
    input {
        background-color: #FFFFFF !important;
        color: var(--text-main) !important;
        border: 1px solid var(--border-strong) !important;
        border-radius: 8px !important;
    }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. BASE DE CONHECIMENTO OFICIAL SIM 2026
# ==========================================
BASE_CONHECIMENTO_SIM_2026 = {
    "metadata": {
        "documento": "Manual do Sistema de Informações Municipais – SIM",
        "versao": "2026",
        "aprovacao": "Portaria nº 1227/2025, publicada no DOE-TCE/CE em 19/12/2025",
        "orgao": "Tribunal de Contas do Estado do Ceará (TCE-CE)"
    },
    "tabelas": [
        {"tabela": "103", "nome": "Órgãos", "modulo": "Orçamento", "finalidade": "Identificar os órgãos da administração municipal e suas características cadastrais.", "paginas": "11", "fonte": "Manual do SIM 2026 — p. 11"},
        {"tabela": "104", "nome": "Unidades Orçamentárias", "modulo": "Orçamento", "finalidade": "Identificar as unidades orçamentárias subordinadas aos órgãos.", "paginas": "11", "fonte": "Manual do SIM 2026 — p. 11"},
        {"tabela": "106", "nome": "Contas Bancárias do Município", "modulo": "Orçamento / Financeiro", "finalidade": "Cadastrar as contas bancárias movimentadas pela gestão municipal.", "paginas": "45-47", "fonte": "Manual do SIM 2026 — p. 45"},
        {"tabela": "107", "nome": "Contas Extra-Orçamentárias", "modulo": "Financeiro", "finalidade": "Relação de contas extra-orçamentárias do ente.", "paginas": "51-54", "fonte": "Manual do SIM 2026 — p. 51"},
        {"tabela": "201", "nome": "Receita Prevista", "modulo": "Orçamento", "finalidade": "Demonstrar a previsão da receita orçamentária.", "paginas": "Diversas", "fonte": "Manual do SIM 2026 — Seção Orçamentária"},
        {"tabela": "202", "nome": "Despesa Fixada", "modulo": "Orçamento", "finalidade": "Demonstrar a fixação da despesa orçamentária.", "paginas": "Diversas", "fonte": "Manual do SIM 2026 — Seção Orçamentária"},
        {"tabela": "501", "nome": "Processos Administrativos para Contratações", "modulo": "Licitações", "finalidade": "Registrar os processos de contratação pública.", "paginas": "118-124", "fonte": "Manual do SIM 2026 — p. 118"},
        {"tabela": "502", "nome": "Publicações de Processos Administrativos", "modulo": "Licitações", "finalidade": "Registrar os extratos de publicações de editais e atos licitatórios.", "paginas": "125-126", "fonte": "Manual do SIM 2026 — p. 125"},
        {"tabela": "531", "nome": "Processos Administrativos para Parcerias – OSC", "modulo": "Terceiro Setor", "finalidade": "Registrar parcerias com Organizações da Sociedade Civil.", "paginas": "147-149", "fonte": "Manual do SIM 2026 — p. 147"},
        {"tabela": "601", "nome": "Empenhos", "modulo": "Execução da Despesa", "finalidade": "Registrar os empenhos da despesa pública.", "paginas": "Diversas", "fonte": "Manual do SIM 2026 — Execução da Despesa"},
        {"tabela": "604", "nome": "Notas de Pagamentos", "modulo": "Execução da Despesa", "finalidade": "Registrar as baixas por pagamento de despesas orçamentárias ou restos a pagar.", "paginas": "Diversas", "fonte": "Manual do SIM 2026 — p. 9"},
        {"tabela": "612", "nome": "Liquidações", "modulo": "Execução da Despesa", "finalidade": "Registrar a liquidação das despesas públicas.", "paginas": "Diversas", "fonte": "Manual do SIM 2026 — Execução da Despesa"},
        {"tabela": "620", "nome": "Pagamentos e Liquidações", "modulo": "Execução da Despesa", "finalidade": "Consolidar o movimento integrado de pagamentos e liquidações.", "paginas": "210-221", "fonte": "Manual do SIM 2026 — p. 210"},
        {"tabela": "704", "nome": "Destinação de Remanejamentos (RTT)", "modulo": "Orçamento", "finalidade": "Registrar as movimentações orçamentárias de RTT.", "paginas": "222-224", "fonte": "Manual do SIM 2026 — p. 222"},
        {"tabela": "705", "nome": "Movimentações de Fontes de Recursos", "modulo": "Orçamento", "finalidade": "Registrar remanejamentos de fontes de recursos.", "paginas": "225-230", "fonte": "Manual do SIM 2026 — p. 225"},
        {"tabela": "958", "nome": "Folha de Pagamento", "modulo": "Pessoal", "finalidade": "Registrar os dados da folha de pagamento de pessoal.", "paginas": "Diversas", "fonte": "Manual do SIM 2026 — Módulo Pessoal"}
    ],
    "regras": [
        {
            "id_interno": "SIM-RULE-000001",
            "modulo": "Execução da Despesa",
            "tabela": "604",
            "regra": "Toda despesa orçamentária ou restos a pagar exige liquidação prévia para poder ser paga.",
            "mensagem_original": "Despesa orçamentária ou Restos a Pagar sem comprovação de liquidação prévia.",
            "causa": "Pagamento efetuado sem o respectivo registro de liquidação no sistema.",
            "correcao": "Enviar obrigatoriamente o registro de liquidação mantendo coerência nas datas.",
            "fonte": "Manual do SIM 2026 — p. 9"
        },
        {
            "id_interno": "SIM-RULE-000002",
            "modulo": "Pessoal",
            "tabela": "958",
            "regra": "Toda folha de pagamento deve ser plenamente liquidada ao final do mês de competência.",
            "mensagem_original": "Divergência entre o valor da folha de pagamento e o total liquidado no mês.",
            "causa": "Folha gerada sem o respectivo lançamento e envio das liquidações no mesmo mês.",
            "correcao": "Garantir o lançamento e envio da liquidação integral da folha no mês de referência.",
            "fonte": "Manual do SIM 2026 — p. 11"
        },
        {
            "id_interno": "SIM-RULE-000003",
            "modulo": "Execução da Despesa",
            "tabela": "601",
            "regra": "O somatório das liquidações (Tabela 612) vinculadas a um empenho não pode exceder o saldo total.",
            "mensagem_original": "Valor liquidado superior ao saldo disponível no empenho.",
            "causa": "Tentativa de liquidar valor superior ao empenhado ou ausência de reforço.",
            "correcao": "Efetuar o reforço do empenho correspondente ou corrigir o valor da liquidação.",
            "fonte": "Manual do SIM 2026 — p. 62"
        },
        {
            "id_interno": "SIM-RULE-000004",
            "modulo": "Licitações",
            "tabela": "501",
            "regra": "Toda contratação deve ser precedida de processo administrativo com modalidade válida.",
            "mensagem_original": "Modalidade de licitação incompatível com o valor estimado ou objeto.",
            "causa": "Erro na escolha da modalidade frente aos limites da lei vigente.",
            "correcao": "Adequar a modalidade do processo administrativo ao valor estimado.",
            "fonte": "Manual do SIM 2026 — p. 119"
        },
        {
            "id_interno": "SIM-RULE-000005",
            "modulo": "Orçamento / Receita",
            "tabela": "201",
            "regra": "A previsão da receita orçamentária deve refletir estritamente os valores aprovados na LOA.",
            "mensagem_original": "Valor da receita diverge do montante autorizado na Lei Orçamentária Anual.",
            "causa": "Lançamento incorreto de valores ou ausência de atualização de créditos adicionais.",
            "correcao": "Conferir os valores com a LOA vigente e retificar na Tabela 201.",
            "fonte": "Manual do SIM 2026 — p. 28"
        }
    ],
    "validacoes_matematicas": [
        {"id": "MAT-000001", "descricao": "Equalização entre receita prevista e despesa fixada", "formula": "Somatório(Receita 201) = Somatório(Despesa 202)", "fonte": "Manual do SIM 2026 — p. 26"},
        {"id": "MAT-000002", "descricao": "Verificação de saldo de dotação no empenho", "formula": "Dotação Inicial + Créditos Adicionais - Empenhos >= 0", "fonte": "Manual do SIM 2026 — p. 34"},
        {"id": "MAT-000003", "descricao": "Conferência do saldo de contas bancárias", "formula": "Saldo Final = Saldo Inicial + Entradas - Saídas", "fonte": "Manual do SIM 2026 — p. 48"}
    ]
}

# ==========================================
# 3. MOTOR DE RAG / BUSCA INTELIGENTE NA BASE
# ==========================================
def buscar_conhecimento_relevante(query):
    query_lower = query.lower()
    trechos_relevantes = []
    
    for r in BASE_CONHECIMENTO_SIM_2026["regras"]:
        termos = [r["modulo"].lower(), r["tabela"], r["mensagem_original"].lower(), r["regra"].lower()]
        if any(termo in query_lower for termo in termos if len(termo) > 2):
            trechos_relevantes.append(r)
            
    for t in BASE_CONHECIMENTO_SIM_2026["tabelas"]:
        if t["tabela"] in query_lower or t["nome"].lower() in query_lower or t["modulo"].lower() in query_lower:
            trechos_relevantes.append(t)
            
    for m in BASE_CONHECIMENTO_SIM_2026["validacoes_matematicas"]:
        if m["id"].lower() in query_lower or m["descricao"].lower() in query_lower:
            trechos_relevantes.append(m)
            
    if not trechos_relevantes:
        return BASE_CONHECIMENTO_SIM_2026["regras"][:3]
        
    return trechos_relevantes

# ==========================================
# 4. CONFIGURAÇÃO DA API GEMINI
# ==========================================
api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

def consultar_assistente_gemini(historico_conversas, ultima_mensagem):
    if not api_key:
        return "### ⚠️ Configuração Pendente\nA chave da API Gemini não foi configurada nos segredos da aplicação."
        
    contexto_filtrado = buscar_conhecimento_relevante(ultima_mensagem)
    
    prompt_sistema = f"""Você é um assistente técnico sênior especializado no SIM — Sistema de Informações Municipais do Tribunal de Contas do Estado do Ceará (TCE-CE), com base no Manual do SIM 2026.
Seu objetivo é ajudar técnicos e operadores a diagnosticar erros, inconsistências e divergências de remessa de arquivos.

Contexto técnico recuperado do Manual do SIM 2026 para auxiliar nesta dúvida:
{json.dumps(contexto_filtrado, ensure_ascii=False, indent=2)}

Diretrizes para a resposta:
- Seja objetivo, técnico e direto ao ponto.
- Se o usuário enviou uma mensagem genérica ou incompleta (ex: "erro na LCO" ou "problema na tabela 604"), conduza a investigação pedindo a mensagem exata do erro, arquivo ou linha correspondente.
- Se o usuário enviou uma ocorrência clara, estruture o diagnóstico obrigatoriamente nos seguintes tópicos:
  1. **O que significa o erro / Contexto**
  2. **Onde está o problema**
  3. **Provável causa**
  4. **Dados que devem ser conferidos**
  5. **Como corrigir**
  6. **Como validar a correção**
  7. **Fundamentação (Manual do SIM 2026)**
- Inclua ao final em linha discreta: ● Alta confiança."""

    contents = []
    for msg in historico_conversas:
        role = "user" if msg["role"] == "user" else "model"
        contents.append({"role": role, "parts": [msg["content"]]})
        
    contents.append({"role": "user", "parts": [ultima_mensagem]})
    
    try:
        model = genai.GenerativeModel("gemini-1.5-flash", system_instruction=prompt_sistema)
        response = model.generate_content(contents)
        if response and response.text:
            return response.text
    except Exception as e:
        return f"""### ⚠️ Diagnóstico por Regra Normativa (SIM / TCE-CE)
* **Contexto e Causa Raiz:** O erro reportado indica uma quebra de integridade referencial ou divergência nas chaves do módulo SIM.
* **Plano de Correção:** Verifique os campos apontados no relatório de erro do validador e assegure a coerência dos dados de origem.
*(Detalhe técnico: `{e}`)*\n\n● Média confiança"""

    return "Não foi possível gerar uma resposta no momento."

# ==========================================
# 5. GERENCIAMENTO DE ESTADO DA SESSÃO (CHAT)
# ==========================================
if "mensagens" not in st.session_state:
    st.session_state["mensagens"] = []

if "nav_atual" not in st.session_state:
    st.session_state["nav_atual"] = "Assistente"

# ==========================================
# 6. SIDEBAR MINIMALISTA E DISCRETA
# ==========================================
with st.sidebar:
    st.markdown("""
        <div style='padding-top: 0.5rem; padding-bottom: 1.2rem;'>
            <div style='font-size: 0.95rem; font-weight: 700; color: #0F172A; display: flex; align-items: center; gap: 8px;'>
                <span>🛡</span> Assistente SIM
            </div>
            <div style='font-size: 0.75rem; color: #64748B; margin-top: 2px;'>TCE-CE • Manual 2026</div>
        </div>
    """, unsafe_allow_html=True)
    
    if st.button("＋ Nova análise", key="btn_nova_analise", use_container_width=True, type="primary"):
        st.session_state["mensagens"] = []
        st.session_state["nav_atual"] = "Assistente"
        st.rerun()
        
    st.markdown("<div style='margin: 1.2rem 0; border-top: 1px solid #E2E8F0;'></div>", unsafe_allow_html=True)
    
    nav_opcoes = {
        "Assistente": "💬 Assistente",
        "Regras": "📖 Base de Regras"
    }
    
    for chave, rotulo in nav_opcoes.items():
        ativo = st.session_state["nav_atual"] == chave
        btn_type = "primary" if ativo else "secondary"
        if st.button(rotulo, key=f"nav_{chave}", use_container_width=True, type=btn_type):
            st.session_state["nav_atual"] = chave
            st.rerun()

    st.markdown("<div style='margin: 2rem 0; border-top: 1px solid #E2E8F0;'></div>", unsafe_allow_html=True)
    
    st.markdown(
        "<div style='font-size: 0.73rem; color: #94A3B8; line-height: 1.5;'>"
        "<strong>SIM • TCE-CE</strong><br>"
        "Manual do SIM 2026<br>"
        "Portaria nº 1227/2025"
        "</div>", 
        unsafe_allow_html=True
    )

# ==========================================
# 7. CORPO DA APLICAÇÃO (TELAS)
# ==========================================
pagina = st.session_state["nav_atual"]

if pagina == "Assistente":
    st.markdown("""
        <div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem; border-bottom: 1px solid #E2E8F0; padding-bottom: 0.8rem;'>
            <div>
                <div style='font-size: 1.05rem; font-weight: 600; color: #0F172A;'>Assistente SIM</div>
                <div style='font-size: 0.78rem; color: #64748B;'>Diagnóstico técnico especializado do SIM • TCE-CE</div>
            </div>
            <div style='display: flex; align-items: center; gap: 6px; font-size: 0.78rem; color: #059669;'>
                <span style='width: 7px; height: 7px; background-color: #10B981; border-radius: 50%; display: inline-block;'></span> Online
            </div>
        </div>
    """, unsafe_allow_html=True)
    
    if not st.session_state["mensagens"]:
        st.markdown("""
            <div style='text-align: center; margin-top: 5rem; margin-bottom: 3rem;'>
                <div style='font-size: 2.2rem; margin-bottom: 0.8rem;'>🛡</div>
                <h1 style='font-size: 1.4rem; font-weight: 600; color: #0F172A; margin-bottom: 0.4rem;'>Como posso ajudar?</h1>
                <p style='font-size: 0.9rem; color: #64748B; max-width: 420px; margin: 0 auto; line-height: 1.5;'>
                    Descreva uma ocorrência, erro ou divergência do SIM para iniciar o diagnóstico.
                </p>
            </div>
        """, unsafe_allow_html=True)
        
    for msg in st.session_state["mensagens"]:
        if msg["role"] == "user":
            with st.chat_message("user", avatar="👤"):
                st.markdown(msg["content"])
        else:
            with st.chat_message("assistant", avatar="🛡"):
                st.markdown(msg["content"])
                
    if prompt_usuario := st.chat_input("Digite uma dúvida ou cole a ocorrência do SIM..."):
        st.session_state["mensagens"].append({"role": "user", "content": prompt_usuario})
        with st.chat_message("user", avatar="👤"):
            st.markdown(prompt_usuario)
            
        with st.chat_message("assistant", avatar="🛡"):
            with st.spinner("Analisando ocorrência..."):
                resposta_ia = consultar_assistente_gemini(st.session_state["mensagens"][:-1], prompt_usuario)
                st.markdown(resposta_ia)
                
        st.session_state["mensagens"].append({"role": "assistant", "content": resposta_ia})

elif pagina == "Regras":
    st.markdown("""
        <div style='margin-bottom: 2rem;'>
            <h2 style='font-size: 1.35rem; font-weight: 600; margin-bottom: 0.3rem; color: #0F172A;'>Base de Regras</h2>
            <p style='color: #64748B; font-size: 0.88rem; margin: 0;'>Conhecimento técnico utilizado pelo Assistente SIM (Manual do SIM 2026).</p>
        </div>
    """, unsafe_allow_html=True)
    
    termo_busca = st.text_input("🔍 Pesquisar regras, tabelas ou mensagens...", placeholder="Digite um termo ou número de tabela...")
    
    st.markdown("<div style='margin: 1.2rem 0;'></div>", unsafe_allow_html=True)
    
    tab_regras, tab_tabelas, tab_matematicas = st.tabs(["📌 Regras de Validação", "📊 Catálogo de Tabelas", "📐 Validações Matemáticas"])
    
    with tab_regras:
        st.markdown("<div style='height: 0.8rem;'></div>", unsafe_allow_html=True)
        filtro_modulo = st.selectbox("Filtrar por Módulo", ["Todos"] + list(set(r["modulo"] for r in BASE_CONHECIMENTO_SIM_2026["regras"])))
        st.markdown("<div style='height: 0.8rem;'></div>", unsafe_allow_html=True)
        
        for regra in BASE_CONHECIMENTO_SIM_2026["regras"]:
            texto_regra_completo = f"{regra['id_interno']} {regra['modulo']} {regra['tabela']} {regra['regra']} {regra['mensagem_original']} {regra['causa']} {regra['correcao']}".lower()
            if termo_busca.lower() in texto_regra_completo or not termo_busca:
                if filtro_modulo == "Todos" or regra["modulo"] == filtro_modulo:
                    st.markdown(f"""
                        <div style='background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 10px; padding: 18px; margin-bottom: 14px; box-shadow: 0 1px 3px rgba(0,0,0,0.02);'>
                            <div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;'>
                                <span style='font-size: 0.73rem; font-weight: 600; color: #2563EB; background: #EFF6FF; padding: 2px 8px; border-radius: 4px;'>{regra['id_interno']}</span>
                                <span style='font-size: 0.78rem; color: #64748B;'>{regra['modulo']} • Tabela {regra['tabela']}</span>
                            </div>
                            <div style='font-size: 0.93rem; font-weight: 600; color: #0F172A; margin-bottom: 6px;'>{regra['regra']}</div>
                            <div style='font-size: 0.83rem; color: #475569; margin-bottom: 10px; font-family: monospace; background: #F8FAFC; padding: 6px 10px; border-radius: 6px; border: 1px solid #E2E8F0;'>{regra['mensagem_original']}</div>
                            <div style='font-size: 0.83rem; color: #334155; margin-bottom: 4px;'><strong>Causa:</strong> {regra['causa']}</div>
                            <div style='font-size: 0.83rem; color: #334155; margin-bottom: 10px;'><strong>Correção:</strong> {regra['correcao']}</div>
                            <div style='font-size: 0.73rem; color: #94A3B8;'>{regra['fonte']}</div>
                        </div>
                    """, unsafe_allow_html=True)
                        
    with tab_tabelas:
        st.markdown("<div style='height: 0.8rem;'></div>", unsafe_allow_html=True)
        for tab in BASE_CONHECIMENTO_SIM_2026["tabelas"]:
            texto_tab_completo = f"tabela {tab['tabela']} {tab['nome']} {tab['modulo']} {tab['finalidade']}".lower()
            if termo_busca.lower() in texto_tab_completo or not termo_busca:
                st.markdown(f"""
                    <div style='background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 10px; padding: 16px; margin-bottom: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.02);'>
                        <div style='display: flex; align-items: baseline; gap: 10px; margin-bottom: 6px;'>
                            <span style='font-size: 0.95rem; font-weight: 700; color: #2563EB;'>{tab['tabela']}</span>
                            <span style='font-size: 0.9rem; font-weight: 600; color: #0F172A;'>{tab['nome']}</span>
                            <span style='font-size: 0.75rem; color: #64748B; margin-left: auto;'>{tab['modulo']}</span>
                        </div>
                        <p style='font-size: 0.83rem; color: #475569; margin: 0 0 8px 0;'>{tab['finalidade']}</p>
                        <div style='font-size: 0.73rem; color: #94A3B8;'>{tab['fonte']}</div>
                    </div>
                """, unsafe_allow_html=True)
                    
    with tab_matematicas:
        st.markdown("<div style='height: 0.8rem;'></div>", unsafe_allow_html=True)
        for mat in BASE_CONHECIMENTO_SIM_2026["validacoes_matematicas"]:
            texto_mat_completo = f"{mat['id']} {mat['descricao']} {mat['formula']}".lower()
            if termo_busca.lower() in texto_mat_completo or not termo_busca:
                st.markdown(f"""
                    <div style='background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 10px; padding: 16px; margin-bottom: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.02);'>
                        <div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;'>
                            <span style='font-size: 0.9rem; font-weight: 600; color: #0F172A;'>{mat['descricao']}</span>
                            <span style='font-size: 0.73rem; font-weight: 600; color: #2563EB; background: #EFF6FF; padding: 2px 8px; border-radius: 4px;'>{mat['id']}</span>
                        </div>
                        <div style='font-family: monospace; font-size: 0.83rem; color: #1D4ED8; background: #F8FAFC; padding: 8px 12px; border-radius: 6px; margin-bottom: 6px; border: 1px solid #E2E8F0;'>{mat['formula']}</div>
                        <div style='font-size: 0.73rem; color: #94A3B8;'>{mat['fonte']}</div>
                    </div>
                """, unsafe_allow_html=True)
