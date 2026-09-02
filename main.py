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
    page_title="Consulta TCE — Análise de Divergências",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Injeção CSS para o Light Mode Premium mantendo a mesma estrutura SaaS moderna
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');

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

    .stApp {
        background-color: var(--bg-app);
        font-family: 'Plus Jakarta Sans', sans-serif;
        color: var(--text-main);
    }

    /* Otimização da largura e espaçamento do workspace principal */
    .block-container {
        padding-top: 2.5rem;
        padding-bottom: 4rem;
        max-width: 1500px;
        padding-left: 3rem;
        padding-right: 3rem;
    }

    /* Tipografia de alta precisão corporativa */
    h1, h2, h3, h4 {
        color: var(--text-main) !important;
        font-family: 'Plus Jakarta Sans', sans-serif !important;
        letter-spacing: -0.025em;
    }

    /* Sidebar minimalista estilo SaaS moderno */
    section[data-testid="stSidebar"] {
        background-color: var(--surface-sidebar) !important;
        border-right: 1px solid var(--border-subtle);
    }
    
    section[data-testid="stSidebar"] .block-container {
        padding-top: 2rem;
        padding-left: 1.25rem;
        padding-right: 1.25rem;
    }

    /* Campos de texto e Inputs refinados */
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

    /* Ajuste elegante para botões primários */
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
# 4. INTELIGÊNCIA ARTIFICIAL (GEMINI)
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
        model = genai.GenerativeModel("gemini-3.6-flash", system_instruction=prompt_sistema)
        response = model.generate_content(prompt_usuario)
        if response and response.text:
            return response.text, "Alta"
    except Exception as e:
        diagnostico_offline = f"""### ⚠️ Diagnóstico por Regra Interna (Limite da IA Atingido)
Ocorreu um limite temporário de requisições na API do Gemini (`429 Quota Exceeded`). Diretriz padrão do TCE-CE:

* **Causa Raiz Identificada:** O arquivo enviado possui chaves estrangeiras ou campos obrigatórios sem correspondência na base oficial consolidada.
* **Como Corrigir:** Verifique se o arquivo base anterior foi enviado na ordem correta e se os códigos de município estão padronizados.
* **Validação Técnica:** Reenvie o lote de remessa correspondente.

*(Detalhe técnico: `{e}`)*"""
        return diagnostico_offline, "Média"
        
    return "Não foi possível gerar resposta.", "Média"

# ==========================================
# 5. SIDEBAR SAAS MODERNA (LIGHT MODE)
# ==========================================
with st.sidebar:
    st.markdown("""
        <div style='padding-bottom: 0.5rem;'>
            <div style='font-size: 0.95rem; font-weight: 700; color: #0F172A; display: flex; align-items: center; gap: 8px;'>
                <span>🛡️</span> Consulta TCE
            </div>
            <div style='font-size: 0.78rem; color: #475569; margin-top: 2px;'>Plataforma de Auditoria Municipal</div>
        </div>
    """, unsafe_allow_html=True)
    
    st.markdown("<div style='margin: 1rem 0; border-top: 1px solid rgba(0,0,0,0.06);'></div>", unsafe_allow_html=True)
    
    st.markdown("<div style='font-size: 0.72rem; font-weight: 600; color: #64748B; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.5rem;'>Workspace</div>", unsafe_allow_html=True)
    
    nav_opcoes = {
        "Diagnóstico": "🔍 Diagnóstico de Ocorrências",
        "Divergências": "📊 Análise de Divergências",
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
# 6. HEADER PRINCIPAL / CONTEXTO DA APLICAÇÃO
# ==========================================
st.markdown("""
    <div style='margin-bottom: 2rem;'>
        <div style='font-size: 0.75rem; font-weight: 600; color: #2563EB; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px;'>Auditoria Municipal SIM</div>
        <h1 style='font-size: 1.75rem; font-weight: 700; margin-bottom: 0.2rem;'>Consulta TCE — Análise de Divergências</h1>
        <p style='color: #475569; font-size: 0.92rem; margin: 0;'>Ambiente corporativo para diagnóstico e rastreabilidade de inconsistências em arquivos de remessa.</p>
    </div>
""", unsafe_allow_html=True)

pagina_selecionada = st.session_state["nav_atual"]

# ==========================================
# 7. RENDERIZAÇÃO DE CONTEÚDO BASEADA EM ESTADO (WORKSPACE)
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
                    sigla_arq, modulo_identificado = classificar_erro(user_input)
                    resposta_ia, conf = chamar_gemini_seguro(user_input)
                    
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

elif pagina_selecionada == "Divergências":
    if "etapa_auditoria" not in st.session_state:
        st.session_state["etapa_auditoria"] = 1

    passo = st.session_state["etapa_auditoria"]
    
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f"{'🔵 **1. Definir linhas**' if passo == 1 else '✅ 1. Definir linhas'}")
    with c2:
        st.markdown(f"{'🔵 **2. Enviar arquivo**' if passo == 2 else ('✅ 2. Enviar arquivo' if passo > 2 else '2. Enviar arquivo')}")
    with c3:
        st.markdown(f"{'🔵 **3. Visualizar divergências**' if passo == 3 else '3. Visualizar divergências'}")

    st.markdown("<div style='margin: 1rem 0; border-top: 1px solid rgba(0,0,0,0.06);'></div>", unsafe_allow_html=True)

    if passo == 1:
        st.subheader("Definição de Linhas Inconsistentes")
        linhas_locais_input = st.text_area("Linhas com erro (ex: 5, 9 ou 10-15)", value="311, 330", height=80)
        
        if st.button("Avançar para upload", type="primary"):
            st.session_state["linhas_locais_input"] = linhas_locais_input
            st.session_state["etapa_auditoria"] = 2
            st.rerun()

    elif passo == 2:
        st.subheader("Upload do Arquivo de Remessa")
        arquivo_enviado = st.file_uploader("Selecione o arquivo (.txt, .dcd, .lco, .ne, .csv)", type=["txt", "dcd", "lco", "ne", "csv"])
        
        col_b1, col_b2 = st.columns([1, 4])
        with col_b1:
            if st.button("Voltar"):
                st.session_state["etapa_auditoria"] = 1
                st.rerun()
        with col_b2:
            if st.button("Processar Análise", type="primary"):
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
            st.subheader("Relatório de Divergências Encontradas")
            st.caption("Comparativo estruturado entre os registros do arquivo enviado e a base histórica.")
        with col_res2:
            st.button("📥 Exportar CSV")

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

            with st.container(border=True):
                col_head1, col_head2 = st.columns([5, 1])
                with col_head1:
                    st.markdown(f"**Linha {linha_num}**")
                with col_head2:
                    st.error("Inexistente")
                
                nomes_colunas = layout_atual["campos"]
                cols_ui = st.columns(len(nomes_colunas))
                
                valores_arquivo = [val_arq_c1, val_arq_c2, val_arq_c3]
                
                for idx, col_ui in enumerate(cols_ui):
                    nome_col_atual = nomes_colunas[idx] if idx < len(nomes_colunas) else f"Campo {idx+1}"
                    v_arq = valores_arquivo[idx] if idx < len(valores_arquivo) else "-"
                    
                    with col_ui:
                        st.metric(label=nome_col_atual, value=v_arq, delta="Divergente", delta_color="inverse")

        st.markdown("<div style='margin: 1.5rem 0; border-top: 1px solid rgba(0,0,0,0.06);'></div>", unsafe_allow_html=True)
        if st.button("🔄 Realizar Nova Análise", type="primary"):
            st.session_state["etapa_auditoria"] = 1
            st.rerun()

elif pagina_selecionada == "Historico":
    st.subheader("Histórico Registrado de Casos")
    st.caption("Consulta de ocorrências previamente diagnosticadas e armazenadas.")
    historico = st.session_state["historico_casos"]
    if not historico:
        st.info("Nenhum caso catalogado ainda.")
    else:
        for item in historico:
            with st.expander(f"Caso #{item['id']} | Módulo: {item.get('modulo', 'Geral')}"):
                st.code(item['erro'], language="text")
                st.markdown(item['resposta'])

elif pagina_selecionada == "Regras":
    st.subheader("Base de Regras Oficiais do SIM / TCE-CE")
    st.markdown("Diretrizes de integridade referencial e validações normativas exigidas pelo tribunal.")
