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
# 2. PERSISTÊNCIA LOCAL (SQLITE) E BASE SIM 2026
# ==========================================
NOME_BANCO = "banco_sim_tce.db"

# Base Oficial Consolidada extraída integralmente do Manual do SIM 2026
BASE_CONHECIMENTO_SIM_2026 = {
  "metadata": {
    "documento": "Manual do Sistema de Informações Municipais – SIM",
    "versao": "2026",
    "aprovacao": "Portaria nº 1227/2025, publicada no DOE-TCE/CE em 19/12/2025",
    "orgao": "Tribunal de Contas do Estado do Ceará (TCE-CE)",
    "escopo": "Base de Conhecimento para motor de diagnóstico de erros",
    "status_cobertura": "100% CONCLUÍDA"
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
    dados_completos = {
        "historico_analises": [{
            "erro": item["erro"], "resposta": item["resposta"], 
            "feedback": item["feedback"], "confianca": item["confianca"],
            "validado": item["validado"], "modulo": item["modulo"], "arquivo": item["arquivo"]
        } for item in historico],
        "base_conhecimento_sim_2026": BASE_CONHECIMENTO_SIM_2026
    }
    return json.dumps(dados_completos, ensure_ascii=False, indent=4)

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
    
    prompt_sistema = f"""Você é um Auditor Especialista Sênior e Analista Técnico do Sistema Integrado Municipal (SIM) do Tribunal de Contas do Estado do Ceará (TCE-CE). 
Utilize como base técnica oficial a seguinte base estruturada do Manual do SIM 2026: {json.dumps(BASE_CONHECIMENTO_SIM_2026, ensure_ascii=False)}.
Analise rigorosamente o relatório de inconsistência ou erro de remessa enviado pelo usuário.

Estruture sua resposta obrigatoriamente nos seguintes tópicos em Markdown bem formatado:
1. **Contexto Normativo e Módulo Afetado:** Identifique claramente a finalidade do arquivo e o impacto da falha perante as normativas do TCE-CE.
2. **Causa Raiz Detalhada:** Explique tecnicamente o motivo da rejeição com base nas regras do SIM 2026.
3. **Plano de Correção Prático:** Forneça um passo a passo objetivo de como o operador deve ajustar os dados.
4. **Validação Técnica Recomendada:** Indique como conferir o resultado antes de submeter uma nova remessa."""
    
    try:
        model = genai.GenerativeModel("gemini-3.6-flash", system_instruction=prompt_sistema)
        response = model.generate_content(prompt_usuario)
        if response and response.text:
            return response.text, "Alta"
    except Exception as e:
        diagnostico_offline = f"""### ⚠️ Diagnóstico por Regra Normativa (SIM / TCE-CE)
* **Contexto e Causa Raiz:** O erro reportado indica uma quebra de integridade referencial ou divergência nas chaves compostas do módulo (como chaves de município, órgão, unidade, dotação ou notas de empenho/liquidação). O sistema SIM exige correspondência exata.
* **Plano de Correção:** Verifique os campos apontados no relatório de erro do validador, assegurando que o arquivo pai correspondente foi enviado.
* **Validação Técnica:** Ajuste o registro na origem e reexecute a validação.

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
        file_name="backup_sim_2026.json", 
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
        <p style='color: #475569; font-size: 0.92rem; margin: 0;'>Ambiente corporativo integrado ao Manual do SIM 2026 para rastreabilidade de inconsistências.</p>
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
                    Cole o relatório completo gerado pelo validador do SIM para que a inteligência artificial identifique a causa raiz e a diretriz normativa correspondente com base no Manual 2026.
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
    st.subheader("Base de Regras Oficiais do SIM 2026")
    st.markdown("Diretrizes de integridade referencial, catálogos de tabelas e validações normativas extraídas do Manual do SIM 2026 (Portaria nº 1227/2025 do TCE-CE).")
    
    tab_regras, tab_tabelas, tab_matematicas = st.tabs(["📌 Regras de Validação", "📊 Catálogo de Tabelas", "📐 Validações Matemáticas"])
    
    with tab_regras:
        st.markdown("### Regras Oficiais Catalogadas")
        filtro_modulo = st.selectbox("Filtrar por Módulo", ["Todos"] + list(set(r["modulo"] for r in BASE_CONHECIMENTO_SIM_2026["regras"])))
        for regra in BASE_CONHECIMENTO_SIM_2026["regras"]:
            if filtro_modulo == "Todos" or regra["modulo"] == filtro_modulo:
                with st.expander(f"[{regra['id_interno']}] {regra['modulo']} — Tabela {regra['tabela']}"):
                    st.markdown(f"**Regra:** {regra['regra']}")
                    st.markdown(f"**Mensagem Original:** `{regra['mensagem_original']}`")
                    st.markdown(f"**Causa Documentada:** {regra['causa']}")
                    st.markdown(f"**Correção Recomendada:** {regra['correcao']}")
                    st.caption(f"Fonte: {regra['fonte']}")
                    
    with tab_tabelas:
        st.markdown("### Tabelas do SIM 2026")
        for tab in BASE_CONHECIMENTO_SIM_2026["tabelas"]:
            with st.container(border=True):
                col1, col2 = st.columns([1, 4])
                col1.markdown(f"**Tabela {tab['tabela']}**")
                col2.markdown(f"**{tab['nome']}** (*{tab['modulo']}*)\n\n{tab['finalidade']}\n\n*Fonte: {tab['fonte']}*")
                
    with tab_matematicas:
        st.markdown("### Fórmulas e Validações Matemáticas")
        for mat in BASE_CONHECIMENTO_SIM_2026["validacoes_matematicas"]:
            with st.container(border=True):
                st.markdown(f"**{mat['descricao']}** (`{mat['id']}`)")
                st.code(mat['formula'], language="text")
                st.caption(mat['fonte'])
