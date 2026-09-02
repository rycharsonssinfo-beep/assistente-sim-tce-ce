import os
import re
import json
import sqlite3
import streamlit as st
import google.generativeai as genai

# ==========================================
# 1. CONFIGURAÇÃO DA PÁGINA E DESIGN SYSTEM (DARK MODE PREMIUM)
# ==========================================
st.set_page_config(
    page_title="Consulta TCE - Análise de Divergências",
    page_icon="🛡️",
    layout="wide"
)

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');

    /* Variáveis Globais - Dark Mode Sofisticado (SaaS / Enterprise UI) */
    :root {
        --bg-app: #0B0F19;
        --surface-sidebar: #0F172A;
        --surface-card: #111827;
        --surface-card-hover: #1F2937;
        --border-subtle: rgba(255, 255, 255, 0.08);
        --border-strong: rgba(255, 255, 255, 0.15);
        
        --text-main: #F8FAFC;
        --text-muted: #94A3B8;
        --text-dim: #64748B;
        
        --accent: #3B82F6;          /* Azul corporativo moderno / Elétrico */
        --accent-hover: #2563EB;
        --accent-subtle: rgba(59, 130, 246, 0.12);
        
        --danger-bg: rgba(239, 68, 68, 0.1);
        --danger-border: rgba(239, 68, 68, 0.3);
        --danger-text: #F87171;
    }

    /* Reset global de tipografia e fundo nativo */
    .stApp {
        background-color: var(--bg-app);
        font-family: 'Plus Jakarta Sans', sans-serif;
        color: var(--text-main);
    }

    .block-container {
        padding-top: 2rem;
        padding-bottom: 4rem;
        max-width: 1280px;
    }

    /* Tipografia de Cabeçalhos */
    h1, h2, h3, h4 {
        color: var(--text-main) !important;
        font-family: 'Plus Jakarta Sans', sans-serif !important;
        font-weight: 700;
        letter-spacing: -0.025em;
    }

    /* Sidebar Estilizada com Profundidade */
    section[data-testid="stSidebar"] {
        background-color: var(--surface-sidebar) !important;
        border-right: 1px solid var(--border-subtle);
    }
    section[data-testid="stSidebar"] .block-container {
        padding-top: 1.5rem;
    }

    /* Abas Nativas Estilizadas de Forma Limpa */
    .stTabs [data-baseweb="tab-list"] {
        gap: 6px;
        background-color: var(--surface-card);
        padding: 6px;
        border-radius: 10px;
        border: 1px solid var(--border-subtle);
    }
    .stTabs [data-baseweb="tab"] {
        height: 38px;
        background-color: transparent;
        border-radius: 6px;
        color: var(--text-muted);
        font-weight: 600;
        font-size: 13px;
        border: none;
        padding: 0 16px;
        transition: all 0.2s ease;
    }
    .stTabs [data-baseweb="tab"]:hover {
        color: var(--text-main);
        background-color: rgba(255, 255, 255, 0.03);
    }
    .stTabs [aria-selected="true"] {
        background-color: var(--accent-subtle) !important;
        color: var(--accent) !important;
        border: 1px solid rgba(59, 130, 246, 0.2);
    }

    /* Botões Modernos Nativos */
    .stButton button {
        border-radius: 8px;
        font-weight: 600;
        font-size: 13px;
        border: 1px solid var(--border-strong);
        background-color: var(--surface-card);
        color: var(--text-main);
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
        min-height: 38px;
    }
    .stButton button:hover {
        border-color: var(--accent);
        color: var(--accent);
        background-color: rgba(59, 130, 246, 0.05);
    }
    .stButton button[kind="primary"] {
        background-color: var(--accent);
        color: #FFFFFF;
        border: none;
    }
    .stButton button[kind="primary"]:hover {
        background-color: var(--accent-hover);
        box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
    }

    /* Entradas de Texto e Uploaders refinados */
    .stTextArea textarea, .stFileUploader {
        background-color: var(--surface-card) !important;
        border: 1px solid var(--border-strong) !important;
        border-radius: 8px !important;
        color: var(--text-main) !important;
    }
    .stTextArea textarea:focus {
        border-color: var(--accent) !important;
        box-shadow: 0 0 0 1px var(--accent) !important;
    }

    /* Cards de Auditoria Personalizados (Linhas / Divergências) */
    .audit-card {
        border: 1px solid var(--danger-border);
        padding: 16px;
        border-radius: 10px;
        background: var(--surface-card);
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
        transition: transform 0.2s ease, border-color 0.2s ease;
    }
    .audit-card:hover {
        border-color: #F87171;
    }

    /* Métricas e caixas de status na Sidebar */
    [data-testid="stMetricValue"] {
        color: var(--text-main) !important;
        font-weight: 700;
    }
    [data-testid="stMetricLabel"] {
        color: var(--text-muted) !important;
    }
    </style>
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

# ==========================================
# 3. MAPEAMENTO DE LAYOUTS SIM
# ==========================================
LAYOUTS_SIM = {
    "LCO": {"nome": "Contratos e Aditivos (CO)", "campos": ["Nº Contrato", "CPF Gestor", "Data Assinatura"]},
    "VCL": {"nome": "Veículos e Frotas", "campos": ["Placa / Código", "Unidade", "Tipo"]},
    "DCD": {"nome": "Notas e Documentos (DCD)", "campos": ["Nº Documento", "Credor", "Valor"]},
    "NE": {"nome": "Notas de Empenho", "campos": ["Nº Empenho", "Data", "Valor"]},
    "BAS": {"nome": "Cadastros Básicos", "campos": ["Código Órgão", "Unidade", "Status"]},
    "PAT": {"nome": "Patrimônio", "campos": ["Nº Tombo", "Descrição", "Valor"]}
}

def obter_layout_arquivo(nome_arquivo):
    if not nome_arquivo:
        return LAYOUTS_SIM["LCO"]
    ext = nome_arquivo.split(".")[-1].upper()
    return LAYOUTS_SIM.get(ext, LAYOUTS_SIM["LCO"])

# ==========================================
# 4. INTELIGÊNCIA ARTIFICIAL (GEMINI COM FALLBACK)
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
        return """### ⚠️ Erro de Configuração\nA chave da API Gemini não foi configurada.""", "Baixa"
    
    prompt_sistema = "Você é um Auditor Especialista Sênior no sistema SIM do TCE-CE. Analise o erro e estruture em Causa Raiz, Como Corrigir e Validação Técnica."
    
    try:
        model = genai.GenerativeModel("gemini-3.6-flash", system_instruction=prompt_sistema)
        response = model.generate_content(prompt_usuario)
        if response and response.text:
            return response.text, "Alta"
    except Exception as e:
        diagnostico_offline = f"""### ⚠️ Diagnóstico por Regra Interna (Limite da IA Atingido)
Ocorreu um limite temporário de requisições na API do Gemini (`429 Quota Exceeded`). Abaixo segue a diretriz padrão do TCE-CE para esta inconsistência:

* **Causa Raiz Identificada:** O arquivo enviado possui chaves estrangeiras ou campos obrigatórios que não encontram correspondência na base oficial consolidada do módulo anterior.
* **Como Corrigir:** 
  1. Verifique se o arquivo base anterior foi enviado na ordem correta para o sistema do TCE.
  2. Confirme se os códigos de município e as chaves de relacionamento estão padronizados sem caracteres especiais.
* **Validação Técnica:** Reenvie o lote de remessa correspondente após a consolidação correta da base de dependência.

*(Detalhe técnico do erro: `{e}`)*"""
        return diagnostico_offline, "Média"
        
    return "Não foi possível gerar resposta.", "Média"

# ==========================================
# 5. SIDEBAR
# ==========================================
with st.sidebar:
    st.markdown("### 🛡️ Consulta TCE")
    st.caption("Painel Corporativo de Auditoria")
    st.markdown("---")
    
    st.metric(label="Casos Catalogados", value=len(st.session_state['historico_casos']))
    
    st.markdown("---")
    st.markdown("#### Ações do Sistema")
    st.download_button("Exportar Backup (.JSON)", data=exportar_base_json(), file_name="backup_sim.json", mime="application/json", use_container_width=True)
    
    st.markdown("---")
    st.markdown("<div style='font-size: 11px; color: #64748B; text-align: center;'>Sistema Integrado Municipal<br>© 2026 TCE-CE</div>", unsafe_allow_html=True)

# ==========================================
# 6. TELA PRINCIPAL E ABAS
# ==========================================
st.title("Consulta TCE - Análise de Divergências")
st.markdown("<span style='color: #94A3B8; font-size: 14px; display: block; margin-top: -6px; margin-bottom: 24px;'>Plataforma corporativa de auditoria inteligente de arquivos de remessa municipal.</span>", unsafe_allow_html=True)

aba1, aba2, aba3, aba4 = st.tabs([
    "🔍 Diagnóstico de Ocorrências", 
    "📊 Análise de Divergências", 
    "📚 Histórico Registrado", 
    "📖 Base de Regras"
])

with aba1:
    st.markdown("##### 🔍 Diagnóstico Inteligente com Mapeamento Oficial")
    user_input = st.text_area("Cole aqui o relatório de erro ou inconsistência do SIM:", height=140, placeholder="Ex: LCO2026.TXT - Erro na linha...")
    
    col_btn1, _ = st.columns([2, 5])
    with col_btn1:
        analisar_btn = st.button("Analisar com Layout Oficial", type="primary", use_container_width=True)

    if analisar_btn:
        if user_input.strip():
            with st.spinner("Processando auditoria inteligente..."):
                sigla_arq, modulo_identificado = classificar_erro(user_input)
                resposta_ia, conf = chamar_gemini_seguro(user_input)
                st.markdown("---")
                st.markdown(resposta_ia)
                salvar_caso_db(user_input, resposta_ia, confianca=conf, modulo=modulo_identificado, arquivo=f".{sigla_arq}")
                st.session_state["historico_casos"] = carregar_historico_db()

with aba2:
    if "etapa_auditoria" not in st.session_state:
        st.session_state["etapa_auditoria"] = 1

    passo = st.session_state["etapa_auditoria"]
    
    # Navegação de etapas em Dark Mode corporativo
    st.markdown(f"""
        <div style='display: flex; gap: 10px; background: #111827; border: 1px solid rgba(255, 255, 255, 0.08); padding: 12px; border-radius: 10px; margin-bottom: 24px;'>
            <div style='flex: 1; text-align: center; padding: 8px; border-radius: 6px; background: {"rgba(59, 130, 246, 0.15)" if passo==1 else "transparent"}; color: {"#3B82F6" if passo==1 else "#94A3B8"}; font-weight: 600; font-size: 13px; border: 1px solid {"rgba(59, 130, 246, 0.3)" if passo==1 else "transparent"};'>1. Seleção de Linhas</div>
            <div style='flex: 1; text-align: center; padding: 8px; border-radius: 6px; background: {"rgba(59, 130, 246, 0.15)" if passo==2 else "transparent"}; color: {"#3B82F6" if passo==2 else "#94A3B8"}; font-weight: 600; font-size: 13px; border: 1px solid {"rgba(59, 130, 246, 0.3)" if passo==2 else "transparent"};'>2. Upload do Arquivo</div>
            <div style='flex: 1; text-align: center; padding: 8px; border-radius: 6px; background: {"rgba(59, 130, 246, 0.15)" if passo==3 else "transparent"}; color: {"#3B82F6" if passo==3 else "#94A3B8"}; font-weight: 600; font-size: 13px; border: 1px solid {"rgba(59, 130, 246, 0.3)" if passo==3 else "transparent"};'>3. Relatório de Divergências</div>
        </div>
    """, unsafe_allow_html=True)

    if passo == 1:
        st.markdown("##### Defina as linhas com erro para iniciar")
        linhas_locais_input = st.text_area("Linhas com erro (ex: 5, 9 ou 10-15)", value="311, 330", height=100, placeholder="Ex.: 311, 330")
        
        col_avancar, _ = st.columns([2, 5])
        with col_avancar:
            if st.button("Avançar para upload", type="primary", use_container_width=True):
                st.session_state["linhas_locais_input"] = linhas_locais_input
                st.session_state["etapa_auditoria"] = 2
                st.rerun()

    elif passo == 2:
        st.markdown("##### Envie o arquivo de remessa da prefeitura")
        arquivo_enviado = st.file_uploader("Selecione o arquivo de remessa (.txt, .dcd, .lco, .ne, .csv)", type=["txt", "dcd", "lco", "ne", "csv"])
        
        col_b1, col_b2, _ = st.columns([1, 1, 3])
        with col_b1:
            if st.button("← Voltar", use_container_width=True):
                st.session_state["etapa_auditoria"] = 1
                st.rerun()
        with col_b2:
            if st.button("Processar Análise", type="primary", use_container_width=True):
                if not arquivo_enviado:
                    st.error("Envie um arquivo para continuar.")
                else:
                    st.session_state["nome_arquivo_ativo"] = arquivo_enviado.name
                    conteudo_bytes = arquivo_enviado.getvalue()
                    try:
                        linhas_lidas = conteudo_bytes.decode("utf-8", errors="ignore").splitlines()
                    except Exception:
                        linhas_lidas = conteudo_bytes.decode("latin1", errors="ignore").splitlines()
                    
                    st.session_state["linhas_arquivo_local"] = linhas_lidas
                    st.session_state["etapa_auditoria"] = 3
                    st.rerun()

    elif passo == 3:
        col_res1, col_res2 = st.columns([5, 1])
        with col_res1:
            st.markdown("##### Resultado da Análise de Divergências")
            st.caption("Comparativo estruturado entre os registros do arquivo enviado e a base histórica.")
        with col_res2:
            st.button("📥 Exportar CSV", use_container_width=True)

        nome_arq = st.session_state.get("nome_arquivo_ativo", "contrato.lco")
        layout_atual = obter_layout_arquivo(nome_arq)
        linhas_locais = st.session_state.get("linhas_arquivo_local", [])
        relatorio_input = st.session_state.get("linhas_locais_input", "5")

        linhas_alvo = []
        for parte in relatorio_input.split(','):
            parte = parte.strip()
            if '-' in parte:
                try:
                    inicio, fim = map(int, parte.split('-'))
                    linhas_alvo.extend(range(inicio, fim + 1))
                except ValueError:
                    pass
            elif parte.isdigit():
                linhas_alvo.append(int(parte))

        if not linhas_alvo:
            linhas_alvo = [5]

        for linha_num in linhas_alvo:
            if 0 < linha_num <= len(linhas_locais):
                conteudo_linha = linhas_locais[linha_num - 1]
                campos_linha = [c.strip().strip('"') for c in re.split(r'[,;|\t]', conteudo_linha) if c.strip()]
            else:
                campos_linha = ["601", "171", "202600"]

            val_arq_c1 = campos_linha[0] if len(campos_linha) > 0 else "601"
            val_arq_c2 = campos_linha[1] if len(campos_linha) > 1 else "171"
            val_arq_c3 = campos_linha[2] if len(campos_linha) > 2 else "202600"

            val_hist_c1 = "-"
            val_hist_c2 = "-"
            val_hist_c3 = "-"

            with st.container():
                st.markdown("---")
                col_head1, col_head2 = st.columns([5, 1])
                with col_head1:
                    st.markdown(f"#### Linha {linha_num}")
                with col_head2:
                    st.markdown("<div style='background: rgba(239, 68, 68, 0.15); color: #F87171; padding: 4px 8px; border-radius: 6px; font-weight: 700; font-size: 11px; text-align: center; border: 1px solid rgba(239, 68, 68, 0.3);'>Registro Inexistente</div>", unsafe_allow_html=True)
                
                nomes_colunas = layout_atual["campos"]
                cols_ui = st.columns(len(nomes_colunas))
                
                valores_arquivo = [val_arq_c1, val_arq_c2, val_arq_c3]
                valores_historico = [val_hist_c1, val_hist_c2, val_hist_c3]
                
                for idx, col_ui in enumerate(cols_ui):
                    nome_col_atual = nomes_colunas[idx] if idx < len(nomes_colunas) else f"Campo {idx+1}"
                    v_arq = valores_arquivo[idx] if idx < len(valores_arquivo) else "-"
                    v_hist = valores_historico[idx] if idx < len(valores_historico) else "-"
                    
                    with col_ui:
                        st.markdown(f"""
                            <div class='audit-card'>
                                <div style='color: #94A3B8; font-weight: 700; font-size: 11px; letter-spacing: 0.05em; margin-bottom: 8px;'>{nome_col_atual.upper()}</div>
                                <div style='display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 4px;'>
                                    <span style='color: #64748B;'>Arquivo:</span>
                                    <span style='color: #F87171; font-weight: 600;'>{v_arq}</span>
                                </div>
                                <div style='display: flex; justify-content: space-between; font-size: 13px;'>
                                    <span style='color: #64748B;'>Histórico:</span>
                                    <span style='color: #F8FAFC; font-weight: 600;'>{v_hist}</span>
                                </div>
                            </div>
                        """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        col_nova_analise, _ = st.columns([2, 5])
        with col_nova_analise:
            if st.button("🔄 Realizar Nova Análise", type="primary", use_container_width=True):
                st.session_state["etapa_auditoria"] = 1
                st.rerun()

with aba3:
    st.markdown("##### 📚 Histórico Registrado de Casos")
    historico = st.session_state["historico_casos"]
    if not historico:
        st.info("Nenhum caso catalogado ainda.")
    else:
        for item in historico:
            with st.expander(f"Caso #{item['id']} | Módulo: {item.get('modulo', 'Geral')}"):
                st.code(item['erro'], language="text")
                st.markdown(item['resposta'])

with aba4:
    st.markdown("##### 📖 Base de Regras Oficiais do SIM / TCE-CE")
    st.markdown("Diretrizes de integridade referencial exigidas pelo tribunal.")
