import os
import re
import json
import streamlit as st
import google.generativeai as genai

# ==========================================
# 1. CONFIGURAÇÃO DA PÁGINA (LIGHT MODE CORPORATIVO)
# ==========================================
st.set_page_config(
    page_title="Assistente SIM — TCE-CE",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Injeção CSS completa focada em chat limpo e profissional
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    :root {
        --bg-app: #F8FAFC;
        --surface-sidebar: #F1F5F9;
        --surface-card: #FFFFFF;
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
        padding-top: 2rem;
        padding-bottom: 4rem;
        max-width: 1200px;
        padding-left: 2rem;
        padding-right: 2rem;
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
    
    /* Estilo customizado para mensagens de chat */
    .chat-container {
        display: flex;
        flex-direction: column;
        gap: 1rem;
        margin-bottom: 2rem;
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
    
    # Busca nas regras
    for r in BASE_CONHECIMENTO_SIM_2026["regras"]:
        termos = [r["modulo"].lower(), r["tabela"], r["mensagem_original"].lower(), r["regra"].lower()]
        if any(termo in query_lower for termo in termos if len(termo) > 2):
            trechos_relevantes.append(r)
            
    # Busca nas tabelas
    for t in BASE_CONHECIMENTO_SIM_2026["tabelas"]:
        if t["tabela"] in query_lower or t["nome"].lower() in query_lower or t["modulo"].lower() in query_lower:
            trechos_relevantes.append(t)
            
    # Busca em validações matemáticas
    for m in BASE_CONHECIMENTO_SIM_2026["validacoes_matematicas"]:
        if m["id"].lower() in query_lower or m["descricao"].lower() in query_lower:
            trechos_relevantes.append(m)
            
    if not trechos_relevantes:
        # Se não achar correspondência direta, retorna um resumo geral ou as regras principais para manter contexto
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
        return "### ⚠️ Erro de Configuração\nA chave da API Gemini não foi configurada nos segredos do Streamlit."
        
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
- Confiança da resposta: Alta / Média."""

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
*(Detalhe técnico: `{e}`)*"""

    return "Não foi possível gerar uma resposta no momento."

# ==========================================
# 5. GERENCIAMENTO DE ESTADO DA SESSÃO (CHAT)
# ==========================================
if "mensagens" not in st.session_state:
    st.session_state["mensagens"] = []

if "nav_atual" not in st.session_state:
    st.session_state["nav_atual"] = "Assistente"

# ==========================================
# 6. SIDEBAR SIMPLIFICADA (SAAS MODERNA)
# ==========================================
with st.sidebar:
    st.markdown("""
        <div style='padding-bottom: 0.5rem;'>
            <div style='font-size: 0.95rem; font-weight: 700; color: #0F172A; display: flex; align-items: center; gap: 8px;'>
                <span>🛡️</span> Assistente SIM
            </div>
            <div style='font-size: 0.78rem; color: #475569; margin-top: 2px;'>Suporte Técnico Especializado</div>
        </div>
    """, unsafe_allow_html=True)
    
    st.markdown("<div style='margin: 1rem 0; border-top: 1px solid rgba(0,0,0,0.06);'></div>", unsafe_allow_html=True)
    
    if st.button("➕ Nova análise", key="btn_nova_analise", use_container_width=True, type="primary"):
        st.session_state["mensagens"] = []
        st.session_state["nav_atual"] = "Assistente"
        st.rerun()
        
    st.markdown("<div style='margin: 1rem 0; border-top: 1px solid rgba(0,0,0,0.06);'></div>", unsafe_allow_html=True)
    
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

    st.markdown("<div style='margin: 2rem 0; border-top: 1px solid rgba(0,0,0,0.06);'></div>", unsafe_allow_html=True)
    
    st.markdown(
        "<div style='font-size: 0.75rem; color: #64748B; line-height: 1.4;'>"
        "<strong>SIM • TCE-CE</strong><br>"
        "Manual do SIM 2026<br>"
        "© 2026 Tribunal de Contas"
        "</div>", 
        unsafe_allow_html=True
    )

# ==========================================
# 7. CORPO DA APLICAÇÃO (TELAS)
# ==========================================
pagina = st.session_state["nav_atual"]

if pagina == "Assistente":
    st.markdown("""
        <div style='margin-bottom: 1.5rem;'>
            <h2 style='font-size: 1.5rem; font-weight: 700; margin-bottom: 0.2rem;'>Assistente Técnico SIM</h2>
            <p style='color: #475569; font-size: 0.9rem; margin: 0;'>Tire dúvidas, investigue inconsistências e obtenha orientações precisas baseadas no Manual 2026.</p>
        </div>
    """, unsafe_allow_html=True)
    
    # Se o chat estiver vazio, exibe mensagem inicial amigável
    if not st.session_state["mensagens"]:
        st.markdown("""
            <div style='background-color: #FFFFFF; border: 1px solid rgba(0,0,0,0.08); border-radius: 8px; padding: 24px; text-align: center; margin-bottom: 2rem;'>
                <div style='font-size: 1.1rem; font-weight: 600; color: #0F172A; margin-bottom: 8px;'>Como posso ajudar com o SIM?</div>
                <p style='font-size: 0.88rem; color: #475569; max-width: 500px; margin: 0 auto;'>
                    Descreva o erro, cole uma ocorrência ou envie o trecho do relatório para iniciar o diagnóstico técnico.
                </p>
            </div>
        """, unsafe_allow_html=True)
        
    # Exibe o histórico de mensagens da conversa atual
    for msg in st.session_state["mensagens"]:
        if msg["role"] == "user":
            with st.chat_message("user", avatar="👤"):
                st.markdown(msg["content"])
        else:
            with st.chat_message("assistant", avatar="🛡️"):
                st.markdown(msg["content"])
                
    # Entrada do chat
    if prompt_usuario := st.chat_input("Digite sua dúvida ou cole a ocorrência do SIM..."):
        # Adiciona mensagem do usuário
        st.session_state["mensagens"].append({"role": "user", "content": prompt_usuario})
        with st.chat_message("user", avatar="👤"):
            st.markdown(prompt_usuario)
            
        # Gera resposta do assistente
        with st.chat_message("assistant", avatar="🛡️"):
            with st.spinner("Analisando ocorrência..."):
                resposta_ia = consultar_assistente_gemini(st.session_state["mensagens"][:-1], prompt_usuario)
                st.markdown(resposta_ia)
                
        # Adiciona resposta ao histórico
        st.session_state["mensagens"].append({"role": "assistant", "content": resposta_ia})

elif pagina == "Regras":
    st.markdown("""
        <div style='margin-bottom: 1.5rem;'>
            <h2 style='font-size: 1.5rem; font-weight: 700; margin-bottom: 0.2rem;'>Base de Regras SIM 2026</h2>
            <p style='color: #475569; font-size: 0.9rem; margin: 0;'>Consulta estruturada ao conhecimento técnico oficial do Manual do SIM (Portaria nº 1227/2025 do TCE-CE).</p>
        </div>
    """, unsafe_allow_html=True)
    
    termo_busca = st.text_input("🔍 Pesquisar na base de conhecimento", placeholder="Digite um termo, número de tabela, módulo ou regra...")
    
    tab_regras, tab_tabelas, tab_matematicas = st.tabs(["📌 Regras de Validação", "📊 Catálogo de Tabelas", "📐 Validações Matemáticas"])
    
    with tab_regras:
        st.markdown("### Regras Oficiais Catalogadas")
        filtro_modulo = st.selectbox("Filtrar por Módulo", ["Todos"] + list(set(r["modulo"] for r in BASE_CONHECIMENTO_SIM_2026["regras"])))
        
        for regra in BASE_CONHECIMENTO_SIM_2026["regras"]:
            # Aplicação de filtro por termo e módulo
            texto_regra_completo = f"{regra['id_interno']} {regra['modulo']} {regra['tabela']} {regra['regra']} {regra['mensagem_original']} {regra['causa']} {regra['correcao']}".lower()
            if termo_busca.lower() in texto_regra_completo or not termo_busca:
                if filtro_modulo == "Todos" or regra["modulo"] == filtro_modulo:
                    with st.container(border=True):
                        st.markdown(f"**[{regra['id_interno']}] {regra['modulo']} — Tabela {regra['tabela']}**")
                        st.markdown(f"**Regra:** {regra['regra']}")
                        st.markdown(f"**Mensagem Original:** `{regra['mensagem_original']}`")
                        st.markdown(f"**Causa Documentada:** {regra['causa']}")
                        st.markdown(f"**Correção Recomendada:** {regra['correcao']}")
                        st.caption(f"Fonte: {regra['fonte']}")
                        
    with tab_tabelas:
        st.markdown("### Tabelas do SIM 2026")
        for tab in BASE_CONHECIMENTO_SIM_2026["tabelas"]:
            texto_tab_completo = f"tabela {tab['tabela']} {tab['nome']} {tab['modulo']} {tab['finalidade']}".lower()
            if termo_busca.lower() in texto_tab_completo or not termo_busca:
                with st.container(border=True):
                    col1, col2 = st.columns([1, 4])
                    col1.markdown(f"**Tabela {tab['tabela']}**")
                    col2.markdown(f"**{tab['nome']}** (*{tab['modulo']}*)\n\n{tab['finalidade']}\n\n*Fonte: {tab['fonte']}*")
                    
    with tab_matematicas:
        st.markdown("### Fórmulas e Validações Matemáticas")
        for mat in BASE_CONHECIMENTO_SIM_2026["validacoes_matematicas"]:
            texto_mat_completo = f"{mat['id']} {mat['descricao']} {mat['formula']}".lower()
            if termo_busca.lower() in texto_mat_completo or not termo_busca:
                with st.container(border=True):
                    st.markdown(f"**{mat['descricao']}** (`{mat['id']}`)")
                    st.code(mat['formula'], language="text")
                    st.caption(mat['fonte'])
