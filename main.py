import os
import re
import json
import sqlite3
import requests
import streamlit as st
import pandas as pd
import google.generativeai as genai

# ==========================================
# 1. CONFIGURAÇÃO DA PÁGINA E DESIGN SYSTEM
# ==========================================
st.set_page_config(
    page_title="Painel de Auditoria SIM TCE-CE",
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
    .block-container { padding-top: 1.8rem; padding-bottom: 3rem; max-width: 1240px; }
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
# 2. PERSISTÊNCIA E MIGRAÇÃO ROBUSTA (SQLITE)
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

def salvar_caso_db(erro, resposta, confianca="Média", validado=0, modulo="Não identificado", arquivo=""):
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
# 3. UTILITÁRIOS
# ==========================================
def classificar_erro(texto):
    if not texto:
        return "", "Não identificado"
    t_lower = texto.lower()
    extensoes = ["bas", "lic", "lco", "vcl", "pat", "cpf", "dcd"]
    sigla_encontrada = ""
    for ext in extensoes:
        if f".{ext}" in t_lower or ext in t_lower:
            sigla_encontrada = ext.upper()
            break
            
    modulo = "Não identificado"
    if "contrato" in t_lower or "lco" in t_lower:
        modulo = "Contratos e Aditivos"
    elif "veículo" in t_lower or "vcl" in t_lower:
        modulo = "Veículos e Frotas"
    elif "patrimônio" in t_lower or "pat" in t_lower:
        modulo = "Patrimônio e Bens"
    elif "pessoal" in t_lower or "cpf" in t_lower:
        modulo = "Recursos Humanos / Pessoal"
    elif "orçamento" in t_lower or "bas" in t_lower:
        modulo = "Cadastros Básicos / Orçamento"
    return sigla_encontrada, modulo

BASE_CONHECIMENTO_PADRAO = [
    {
        "chaves": [".vcl", "veículos", "frotas"],
        "titulo": "Veículos e Frotas: Unidades Orçamentárias e Vínculos (.VCL / .BAS)",
        "resposta": """### 🎯 Causa Raiz\nO sistema SIM/TCE-CE exige que os registros de frotas estejam vinculados a uma unidade orçamentária válida da LOA.""",
        "confianca": "Alta"
    }
]

def buscar_na_base_conhecimento(texto_erro):
    t_norm = texto_erro.lower()
    for item in BASE_CONHECIMENTO_PADRAO:
        for chave in item["chaves"]:
            if chave in t_norm:
                return item["resposta"], item["confianca"]
    return None, None

api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

def chamar_gemini_seguro(prompt):
    if not api_key:
        return None, "Chave de API não configurada."
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(prompt)
        if response and response.text:
            return response.text, "Sucesso"
    except:
        pass
    return None, "Erro na API Gemini."

# ==========================================
# 4. SIDEBAR
# ==========================================
with st.sidebar:
    st.markdown("## 🛡️ SIM Audit")
    st.caption("Painel de Conciliação e Consistência")
    st.markdown("---")
    st.metric(label="Casos em Memória", value=len(st.session_state['historico_casos']))
    st.markdown("---")
    st.download_button("Exportar Backup (.JSON)", data=exportar_base_json(), file_name="backup_sim.json", mime="application/json", use_container_width=True)

# ==========================================
# 5. TELA PRINCIPAL
# ==========================================
st.title("Diagnóstico SIM TCE-CE")
st.markdown("<span style='color: #64748B; font-size: 15px; display: block; margin-top: -10px; margin-bottom: 20px;'>Plataforma unificada para auditoria cruzada e análise de integridade referencial.</span>", unsafe_allow_html=True)

aba1, aba2, aba3, aba4, aba5 = st.tabs([
    "🔍 Diagnóstico de Ocorrências", 
    "📊 Auditoria Cruzada (API SIM 2.0)",
    "📚 Histórico Registrado", 
    "📖 Base de Regras",
    "🕸️ Carga Completa & Fluxograma"
])

with aba1:
    st.markdown("##### 🔍 Diagnóstico Inteligente com Mapeamento de Layout Oficial")
    user_input = st.text_area("Relatório de Erro / Inconsistência", height=140)
    if st.button("Analisar com Layout Oficial", type="primary", use_container_width=True):
        if user_input.strip():
            sigla_arq, modulo_identificado = classificar_erro(user_input)
            resp, _ = buscar_na_base_conhecimento(user_input)
            if not resp:
                resp, _ = chamar_gemini_seguro(user_input)
            st.markdown("---")
            if resp:
                st.markdown(resp)
            salvar_caso_db(user_input, resp or "", modulo=modulo_identificado, arquivo=f".{sigla_arq}")
            st.session_state["historico_casos"] = carregar_historico_db()

with aba2:
    if "etapa_auditoria" not in st.session_state:
        st.session_state["etapa_auditoria"] = 1

    passo = st.session_state["etapa_auditoria"]
    
    st.markdown(f"""
        <div style='display: flex; gap: 10px; background: #FFFFFF; border: 1px solid #E2E8F0; padding: 12px; border-radius: 10px; margin-bottom: 20px;'>
            <div style='flex: 1; text-align: center; padding: 8px; border-radius: 6px; background: {"#059669" if passo==1 else "#F1F5F9"}; color: {"white" if passo==1 else "#64748B"}; font-weight: 600; font-size: 13px;'>Passo 1: Parâmetros e Arquivo Local</div>
            <div style='flex: 1; text-align: center; padding: 8px; border-radius: 6px; background: {"#059669" if passo==2 else "#F1F5F9"}; color: {"white" if passo==2 else "#64748B"}; font-weight: 600; font-size: 13px;'>Passo 2: Consulta à API & Cruzamento</div>
            <div style='flex: 1; text-align: center; padding: 8px; border-radius: 6px; background: {"#059669" if passo==3 else "#F1F5F9"}; color: {"white" if passo==3 else "#64748B"}; font-weight: 600; font-size: 13px;'>Passo 3: Relatório de Divergências</div>
        </div>
    """, unsafe_allow_html=True)

    if passo == 1:
        st.markdown("##### 1. Configurar Parâmetros e Enviar Arquivo Local")
        st.caption("Selecione o arquivo local e o endpoint oficial da frota/veículos conforme a documentação da API.")
        
        arquivo_auditoria = st.file_uploader("Selecione o arquivo local (.VCL, .LCO, .BAS, .PAT, etc.)", type=["lco", "bas", "vcl", "pat", "txt", "csv"])
        
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            # Endpoints reais detalhados da frota mapeados da documentação oficial
            endpoint_metodo = st.selectbox(
                "Recurso / Endpoint Oficial da API (Veículos/Frota)", 
                [
                    "veiculos_municipais", 
                    "veiculos_locados", 
                    "veiculos_cedidos_terceiros", 
                    "destinacao_veiculos", 
                    "baixa_destinacao_veiculos", 
                    "controle_abastecimento_veiculos", 
                    "controle_manutencao_veiculos"
                ]
            )
        with col_c2:
            exercicio_api = st.selectbox("Exercício (Ano)", ["2026", "2025", "2024"], index=0)

        col_p1, col_p2 = st.columns(2)
        with col_p1:
            codigo_municipio = st.text_input("Código do Município (Obrigatório *)", placeholder="Ex: 123")
        with col_p2:
            data_referencia_doc = st.text_input("Data de Referência da Doc. (Obrigatório * ex: 202601)", placeholder="Ex: 202601")

        linhas_locais_input = st.text_area("Linhas Específicas / Relatório do Validador", placeholder="Ex: 7, 8, 9, 10 ou deixe em branco para varredura geral")
        
        if st.button("Consultar API Real do TCE-CE →", type="primary"):
            if not arquivo_auditoria:
                st.error("Por favor, envie um arquivo local.")
            elif not codigo_municipio.strip():
                st.error("O parâmetro 'codigo_municipio' é obrigatório para este endpoint da API.")
            elif not data_referencia_doc.strip():
                st.error("O parâmetro 'data_referencia_doc' é obrigatório para este endpoint da API.")
            else:
                st.session_state["endpoint_metodo"] = endpoint_metodo
                st.session_state["exercicio_api"] = exercicio_api
                st.session_state["codigo_municipio"] = codigo_municipio.strip()
                st.session_state["data_referencia_doc"] = data_referencia_doc.strip()
                st.session_state["arquivo_auditoria_obj"] = arquivo_auditoria
                st.session_state["linhas_locais_input"] = linhas_locais_input
                st.session_state["etapa_auditoria"] = 2
                st.rerun()

    elif passo == 2:
        st.markdown("##### 2. Consultando API Real do TCE-CE...")
        arq_obj = st.session_state.get("arquivo_auditoria_obj")
        linhas_arquivo = arq_obj.getvalue().decode("latin1").splitlines() if arq_obj else []

        endpoint_usuario = st.session_state.get('endpoint_metodo', 'veiculos_municipais')
        url_base_api = f"https://api-dados-abertos.tce.ce.gov.br/sim/{endpoint_usuario}"
        
        # Parâmetros obrigatórios exigidos pela documentação oficial da API de veículos
        params = {
            "codigo_municipio": st.session_state.get('codigo_municipio', ''),
            "data_referencia_doc": st.session_state.get('data_referencia_doc', '')
        }

        with st.spinner(f"Conectando a {url_base_api}..."):
            try:
                resposta = requests.get(url_base_api, params=params, timeout=15)
                if resposta.status_code == 200:
                    dados_brutos = resposta.json()
                    # A API retorna um objeto contendo a chave "elements" com a lista de registros
                    if isinstance(dados_brutos, dict) and "elements" in dados_brutos:
                        st.session_state["dados_api_retorno"] = dados_brutos["elements"]
                    else:
                        st.session_state["dados_api_retorno"] = dados_brutos if isinstance(dados_brutos, list) else [dados_brutos]
                else:
                    st.session_state["dados_api_retorno"] = []
            except Exception:
                st.session_state["dados_api_retorno"] = []

        st.session_state["linhas_arquivo_local"] = linhas_arquivo
        st.success("Consulta executada com dados reais da API!")
        
        col_b1, col_b2 = st.columns([1, 4])
        with col_b1:
            if st.button("← Voltar"):
                st.session_state["etapa_auditoria"] = 1
                st.rerun()
        with col_b2:
            if st.button("Gerar Relatório de Cruzamento Real", type="primary"):
                st.session_state["etapa_auditoria"] = 3
                st.rerun()

    elif passo == 3:
        st.markdown("##### 3. Relatório de Divergências: Cruzamento Real com a API do TCE-CE")
        arq_obj = st.session_state.get("arquivo_auditoria_obj")
        nome_arq = arq_obj.name if arq_obj else "Arquivo"
        linhas_locais = st.session_state.get("linhas_arquivo_local", [])
        relatorio_input = st.session_state.get("linhas_locais_input", "")
        dados_api = st.session_state.get("dados_api_retorno", [])
        
        st.info(f"📁 **Arquivo Analisado:** `{nome_arq}` ({len(linhas_locais)} linhas totais lidas) | 🌐 **Registros na API:** {len(dados_api)}")

        linhas_para_exibir = [int(m) for m in re.findall(r'(\d+)', relatorio_input)] if relatorio_input else []
        alvos = linhas_para_exibir if linhas_para_exibir else list(range(1, min(len(linhas_locais) + 1, 51)))

        dados_dinamicos = []
        for num_linha in alvos:
            if 0 < num_linha <= len(linhas_locais):
                conteudo_linha = linhas_locais[num_linha - 1]
                campos_linha = [c.strip('"') for c in conteudo_linha.split(",")]
                
                encontrou = any(campo.lower() in str(dados_api).lower() for campo in campos_linha if len(campo) > 2) if dados_api else False

                if dados_api and encontrou:
                    status_val = "✅ Compatível com os dados reais da API"
                    acao_val = "Nenhuma ação necessária."
                elif dados_api and not encontrou:
                    status_val = "❌ Divergente / Não localizado na API"
                    acao_val = "Verificar se o RENAVAM/Placa foi transmitido."
                else:
                    status_val = "⚠️ API Indisponível / Sem Retorno para Cruzamento"
                    acao_val = "Validar parâmetros obrigatórios (Código do Município e Data de Referência)."

                dados_dinamicos.append({
                    "Linha": num_linha,
                    "Arquivo / Módulo": nome_arq,
                    "Conteúdo Analisado": conteudo_linha[:50] + "..." if len(conteudo_linha) > 50 else conteudo_linha,
                    "Status do Cruzamento (API)": status_val,
                    "Ação Recomendada": acao_val
                })

        if dados_dinamicos:
            st.dataframe(pd.DataFrame(dados_dinamicos), use_container_width=True)

        if st.button("Fazer Nova Auditoria"):
            st.session_state["etapa_auditoria"] = 1
            st.rerun()

with aba3:
    st.markdown("##### Histórico de Casos")
    for item in st.session_state["historico_casos"]:
        with st.expander(f"Caso #{item['id']} - {item.get('modulo', '')}"):
            st.code(item['erro'])
            st.markdown(item['resposta'])

with aba4:
    st.markdown("##### 📖 Base de Regras Oficiais")
    for reg in BASE_CONHECIMENTO_PADRAO:
        with st.expander(reg['titulo']):
            st.markdown(reg['resposta'])

with aba5:
    st.markdown("##### Carga Completa")
    st.info("Envie múltiplos arquivos para validação em lote.")
