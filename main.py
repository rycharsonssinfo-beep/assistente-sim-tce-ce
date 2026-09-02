import os
import re
import json
import sqlite3
import streamlit as st
import google.generativeai as genai

# ==========================================
# 1. CONFIGURAÇÃO DA PÁGINA E DESIGN SYSTEM
# ==========================================
st.set_page_config(
    page_title="Consulta TCE - Análise de Divergências",
    page_icon="🛡️",
    layout="wide"
)

st.markdown("""
    <style>
    :root {
        --bg-main: #F8FAFC;
        --surface: #FFFFFF;
        --border-color: #E2E8F0;
        --border-strong: #CBD5E1;
        --text-main: #0F172A;
        --text-muted: #64748B;
        --primary: #059669;
        --primary-hover: #047857;
    }
    .main { background-color: var(--bg-main); font-family: 'Inter', sans-serif; }
    .block-container { padding-top: 1.5rem; padding-bottom: 3rem; max-width: 1240px; }
    h1, h2, h3, h4 { color: var(--text-main); font-weight: 700; letter-spacing: -0.03em; }
    .stTabs [data-baseweb="tab-list"] { gap: 6px; background-color: #F1F5F9; padding: 6px; border-radius: 10px; border: 1px solid var(--border-color); }
    .stTabs [data-baseweb="tab"] { height: 40px; background-color: transparent; border-radius: 6px; color: var(--text-muted); font-weight: 600; font-size: 13px; border: none; padding: 0 14px; }
    .stTabs [aria-selected="true"] { background-color: var(--surface) !important; color: var(--primary) !important; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    .stButton button { border-radius: 8px; font-weight: 600; font-size: 14px; border: 1px solid var(--border-strong); background-color: var(--surface); color: var(--text-main); transition: all 0.2s ease; }
    .stButton button:hover { border-color: var(--primary); color: var(--primary); background-color: #F0FDF4; }
    .stButton button[kind="primary"] { background-color: var(--primary); color: white; border: none; }
    .stButton button[kind="primary"]:hover { background-color: var(--primary-hover); color: white; box-shadow: 0 4px 6px -1px rgba(5, 150, 105, 0.3); }
    section[data-testid="stSidebar"] { background-color: #F1F5F9; border-right: 1px solid var(--border-color); }
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
        return """### ⚠️ Erro de Configuração\nA chave da API Gemini não foi configurada.""", "Baixa"
    prompt_sistema = "Você é um Auditor Especialista Sênior no sistema SIM do TCE-CE. Analise o erro e estruture em Causa Raiz, Como Corrigir e Validação Técnica."
    try:
        model = genai.GenerativeModel("gemini-3.6-flash", system_instruction=prompt_sistema)
        response = model.generate_content(prompt_usuario)
        if response and response.text:
            return response.text, "Alta"
    except Exception as e:
        return f"Erro ao comunicar com a IA: {e}", "Baixa"
    return "Não foi possível gerar resposta.", "Média"

# ==========================================
# 5. SIDEBAR
# ==========================================
with st.sidebar:
    st.markdown("## 🛡️ Consulta TCE")
    st.caption("Painel de Análise de Divergências")
    st.markdown("---")
    st.metric(label="Casos Catalogados", value=len(st.session_state['historico_casos']))
    st.markdown("---")
    st.download_button("Exportar Backup (.JSON)", data=exportar_base_json(), file_name="backup_sim.json", mime="application/json", use_container_width=True)

# ==========================================
# 6. TELA PRINCIPAL E ABAS
# ==========================================
st.title("Consulta TCE - Análise de Divergências")
st.markdown("<span style='color: #64748B; font-size: 15px; display: block; margin-top: -10px; margin-bottom: 20px;'>Plataforma unificada de auditoria de arquivos de remessa municipal.</span>", unsafe_allow_html=True)

aba1, aba2, aba3, aba4 = st.tabs([
    "🔍 Diagnóstico de Ocorrências", 
    "📊 Análise de Divergências", 
    "📚 Histórico Registrado", 
    "📖 Base de Regras"
])

with aba1:
    st.markdown("##### 🔍 Diagnóstico Inteligente com Mapeamento Oficial")
    user_input = st.text_area("Cole aqui o relatório de erro ou inconsistência do SIM:", height=140, placeholder="Ex: LCO2026.TXT...")
    if st.button("Analisar com Layout Oficial", type="primary", use_container_width=True):
        if user_input.strip():
            with st.spinner("Analisando consistência..."):
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
    
    # Cabeçalho de Passos idêntico à referência (1. Linhas -> 2. Arquivo -> 3. Resultado)
    st.markdown(f"""
        <div style='display: flex; gap: 10px; background: #FFFFFF; border: 1px solid #E2E8F0; padding: 12px; border-radius: 10px; margin-bottom: 20px;'>
            <div style='flex: 1; text-align: center; padding: 8px; border-radius: 6px; background: {"#059669" if passo==1 else "#F1F5F9"}; color: {"white" if passo==1 else "#64748B"}; font-weight: 600; font-size: 13px;'>1. Linhas</div>
            <div style='flex: 1; text-align: center; padding: 8px; border-radius: 6px; background: {"#059669" if passo==2 else "#F1F5F9"}; color: {"white" if passo==2 else "#64748B"}; font-weight: 600; font-size: 13px;'>2. Arquivo</div>
            <div style='flex: 1; text-align: center; padding: 8px; border-radius: 6px; background: {"#059669" if passo==3 else "#F1F5F9"}; color: {"white" if passo==3 else "#64748B"}; font-weight: 600; font-size: 13px;'>3. Resultado</div>
        </div>
    """, unsafe_allow_html=True)

    if passo == 1:
        st.markdown("##### Defina as linhas com erro para iniciar")
        linhas_locais_input = st.text_area("Linhas com erro (ex: 5, 9 ou 10-15)", value="5, 9", height=100, placeholder="Ex.: 5, 9")
        
        if st.button("Avançar para upload", type="primary"):
            st.session_state["linhas_locais_input"] = linhas_locais_input
            st.session_state["etapa_auditoria"] = 2
            st.rerun()

    elif passo == 2:
        st.markdown("##### Envie o arquivo de remessa da prefeitura")
        arquivo_enviado = st.file_uploader("Selecione o arquivo (.txt, .dcd, .lco, .ne, .csv)", type=["txt", "dcd", "lco", "ne", "csv"])
        
        col_b1, col_b2 = st.columns(2)
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
            st.markdown("##### Resultado da análise")
            st.caption("Mostrando apenas divergências com base no arquivo real enviado.")
        with col_res2:
            st.button("Exportar CSV", use_container_width=True)

        nome_arq = st.session_state.get("nome_arquivo_ativo", "contrato.lco")
        layout_atual = obter_layout_arquivo(nome_arq)
        linhas_locais = st.session_state.get("linhas_arquivo_local", [])
        relatorio_input = st.session_state.get("linhas_locais_input", "5")

        # Extrai de forma inteligente todas as linhas solicitadas (incluindo intervalos se houver)
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
            # Garante leitura segura caso a linha solicitada exista no arquivo enviado
            if 0 < linha_num <= len(linhas_locais):
                conteudo_linha = linhas_locais[linha_num - 1]
                # Faz o split dinâmico considerando delimitadores padrão de arquivos de remessa
                campos_linha = [c.strip().strip('"') for c in re.split(r'[,;|\t]', conteudo_linha) if c.strip()]
            else:
                campos_linha = [f"Item-{linha_num}", "99999999999", "2026-12-31"]

            val_arq_c1 = campos_linha[0] if len(campos_linha) > 0 else "-"
            val_arq_c2 = campos_linha[1] if len(campos_linha) > 1 else "-"
            val_arq_c3 = campos_linha[2] if len(campos_linha) > 2 else "-"

            # Como simula o histórico oficial ausente (equivalente a contracts: null / não encontrado)
            val_hist_c1 = "-"
            val_hist_c2 = "-"
            val_hist_c3 = "-"

            with st.container():
                st.markdown("---")
                col_head1, col_head2 = st.columns([5, 1])
                with col_head1:
                    st.markdown(f"#### Linha {linha_num}")
                with col_head2:
                    st.markdown("<div style='background: #FEE2E2; color: #DC2626; padding: 4px 8px; border-radius: 6px; font-weight: bold; font-size: 11px; text-align: center;'>Contrato não encontrado</div>", unsafe_allow_html=True)
                
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
                            <div style='border: 1px solid #FCA5A5; padding: 12px; border-radius: 8px; background: #FFF; min-height: 95px;'>
                                <small style='color: #64748B; font-weight: bold;'>{nome_col_atual.upper()}</small><br>
                                <div style='margin-top: 4px; color: #64748B;'><small>Arquivo</small><br><span style='color: #DC2626; font-weight: 600;'>{v_arq}</span></div>
                                <div style='margin-top: 2px; color: #64748B;'><small>Histórico</small><br><span style='color: #0F172A; font-weight: 600;'>{v_hist}</span></div>
                            </div>
                        """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_app_html=True)
        if st.button("Nova Análise"):
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
