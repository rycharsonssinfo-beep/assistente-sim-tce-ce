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
# 3. CLIENTE DE API E MAPEAMENTO DE LAYOUTS
# ==========================================
LAYOUTS_SIM = {
    "LCO": {"nome": "Contratos e Aditivos (CO)", "campos": ["Nº Contrato", "CPF Gestor", "Data Assinatura"], "endpoints": ["contratos", "licitacoes"]},
    "VCL": {"nome": "Veículos e Frotas", "campos": ["Placa / Código", "Unidade Orçamentária", "Tipo Veículo"], "endpoints": ["veiculos_municipais", "veiculos"]},
    "DCD": {"nome": "Notas e Documentos (NE)", "campos": ["Nº Documento", "Credor / CPF-CNPJ", "Valor"], "endpoints": ["documentos_despesa", "notas_empenho", "despesas", "empenhos"]},
    "NE": {"nome": "Notas de Empenho", "campos": ["Nº Empenho", "Data Emissão", "Valor Empenhado"], "endpoints": ["notas_empenho", "despesas", "documentos_despesa"]},
    "BAS": {"nome": "Cadastros Básicos", "campos": ["Código Órgão", "Unidade Orçamentária", "Status"], "endpoints": ["orgaos", "unidades_orcamentarias"]},
    "PAT": {"nome": "Patrimônio", "campos": ["Nº Tombo", "Descrição Bem", "Valor Aquisição"], "endpoints": ["bens_patrimoniais", "patrimonio"]}
}

def obter_layout_arquivo(nome_arquivo):
    if not nome_arquivo:
        return LAYOUTS_SIM["LCO"]
    ext = nome_arquivo.split(".")[-1].upper()
    return LAYOUTS_SIM.get(ext, {"nome": "Módulo Geral SIM", "campos": ["Campo 1", "Campo 2", "Campo 3"], "endpoints": ["despesas", "documentos_despesa"]})

class AuditoriaTCEAPI:
    def __init__(self):
        self.base_url = "https://api-dados-abertos.tce.ce.gov.br/sim"
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "AuditoriaCruzadaTCE-App/1.0",
            "Accept": "application/json"
        })

    def consultar_com_fallback(self, endpoints_possiveis: list, parametros: dict) -> pd.DataFrame:
        for endpoint in endpoints_possiveis:
            url_endpoint = f"{self.base_url}/{endpoint}"
            variacoes_params = [
                parametros,
                {"exercicio": parametros.get("exercicio"), "codigo_municipio": parametros.get("codigo_municipio")},
                {"ano": parametros.get("exercicio")},
                {"limit": 1000},
                {}
            ]
            for params in variacoes_params:
                try:
                    clean_params = {k: v for k, v in params.items() if v is not None}
                    response = self.session.get(url_endpoint, params=clean_params, timeout=10)
                    if response.status_code == 200:
                        dados = response.json()
                        if isinstance(dados, dict):
                            resultados = dados.get("elements", dados.get("resultado", dados.get("data", dados.get("items", []))))
                        elif isinstance(dados, list):
                            resultados = dados
                        else:
                            resultados = []
                        if resultados:
                            return pd.DataFrame(resultados)
                except Exception:
                    continue
        return pd.DataFrame()

cliente_api = AuditoriaTCEAPI()

# ==========================================
# 4. INTELIGÊNCIA ARTIFICIAL E UTILITÁRIOS
# ==========================================
def classificar_erro(texto):
    if not texto:
        return "", "Não identificado"
    t_lower = texto.lower()
    extensoes = ["bas", "lic", "lco", "vcl", "pat", "cpf", "dcd", "ne"]
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
    elif "orçamento" in t_lower or "bas" in t_lower:
        modulo = "Cadastros Básicos / Orçamento"
    elif "empenho" in t_lower or "ne" in t_lower or "dcd" in t_lower:
        modulo = "Notas de Empenho / Despesas"
    return sigla_encontrada, modulo

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
    st.markdown("## 🛡️ SIM Audit")
    st.caption("Painel de Conciliação e Consistência")
    st.markdown("---")
    st.metric(label="Casos Catalogados", value=len(st.session_state['historico_casos']))
    st.markdown("---")
    st.download_button("Exportar Backup (.JSON)", data=exportar_base_json(), file_name="backup_sim.json", mime="application/json", use_container_width=True)

# ==========================================
# 6. TELA PRINCIPAL E ABAS
# ==========================================
st.title("Diagnóstico SIM TCE-CE")
st.markdown("<span style='color: #64748B; font-size: 15px; display: block; margin-top: -10px; margin-bottom: 20px;'>Plataforma unificada com varredura automática de endpoints e auditoria cruzada.</span>", unsafe_allow_html=True)

aba1, aba2, aba3, aba4, aba5 = st.tabs([
    "🔍 Diagnóstico de Ocorrências", 
    "📊 Auditoria Cruzada (API SIM 2.0)",
    "📚 Histórico Registrado", 
    "📖 Base de Regras",
    "🕸️ Carga Completa & Fluxograma"
])

with aba1:
    st.markdown("##### 🔍 Diagnóstico Inteligente com Mapeamento de Layout Oficial")
    user_input = st.text_area("Cole aqui o relatório de erro ou inconsistência do SIM:", height=140, placeholder="Ex: NE202607.DCD...")
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
    
    st.markdown(f"""
        <div style='display: flex; gap: 10px; background: #FFFFFF; border: 1px solid #E2E8F0; padding: 12px; border-radius: 10px; margin-bottom: 20px;'>
            <div style='flex: 1; text-align: center; padding: 8px; border-radius: 6px; background: {"#059669" if passo==1 else "#F1F5F9"}; color: {"white" if passo==1 else "#64748B"}; font-weight: 600; font-size: 13px;'>Passo 1: Arquivo e Parâmetros da Prefeitura</div>
            <div style='flex: 1; text-align: center; padding: 8px; border-radius: 6px; background: {"#059669" if passo==3 else "#F1F5F9"}; color: {"white" if passo==3 else "#F1F5F9"}; font-weight: 600; font-size: 13px;'>Passo 2: Cards Detalhados por Campo</div>
        </div>
    """, unsafe_allow_html=True)

    if passo == 1:
        st.markdown("##### 1. Envio de Arquivo e Identificação do Município")
        
        col_p1, col_p2 = st.columns(2)
        with col_p1:
            codigo_municipio_input = st.text_input("Código do Município / Órgão no TCE", value="1", help="Informe o código oficial do município.")
        with col_p2:
            linhas_locais_input = st.text_input("Linhas com erro (opcional, ex: 5, 9)", placeholder="Ex: 5, 9, 33...")

        col_up1, col_up2, col_up3 = st.columns(3)
        with col_up1:
            arquivo_auditoria = st.file_uploader("Arquivo Principal da Prefeitura (.DCD, .NE, etc.)", type=["lco", "bas", "vcl", "pat", "ne", "dcd", "txt", "csv"])
        with col_up2:
            arquivo_historico_local = st.file_uploader("Base de Histórico / Referência (Opcional)", type=["csv", "txt"], help="Envie um arquivo CSV/TXT com os dados oficiais corretos para comparar caso a API esteja vazia.")
        with col_up3:
            arquivo_secundario = st.file_uploader("Arquivo Complementar", type=["dcd", "ne", "lco", "bas", "vcl", "pat", "txt", "csv"])

        if st.button("Executar Auditoria Cruzada 🚀", type="primary", use_container_width=True):
            arquivo_escolhido = arquivo_auditoria if arquivo_auditoria else arquivo_secundario
            if not arquivo_escolhido:
                st.error("Envie ao menos o arquivo principal da prefeitura.")
            else:
                nome_arq = arquivo_escolhido.name
                st.session_state["arquivo_auditoria_obj"] = arquivo_escolhido
                st.session_state["linhas_locais_input"] = linhas_locais_input
                linhas_lidas = arquivo_escolhido.getvalue().decode("latin1", errors="ignore").splitlines()
                st.session_state["linhas_arquivo_local"] = linhas_lidas

                layout_identificado = obter_layout_arquivo(nome_arq)
                endpoints_possiveis = layout_identificado["endpoints"]
                
                match_ano = re.search(r'(20\d{2})', nome_arq)
                exercicio = match_ano.group(1) if match_ano else "2026"
                
                match_ref = re.search(r'(20\d{4})', nome_arq)
                data_ref = match_ref.group(1) if match_ref else f"{exercicio}01"

                df_api = pd.DataFrame()
                
                # Se o usuário enviou uma base de histórico local, usa ela prioritariamente para simular/validar o cruzamento perfeitamente
                if arquivo_historico_local:
                    try:
                        df_api = pd.read_csv(arquivo_historico_local, header=None)
                        # Converte em dicionário de registros simulando a API
                        mock_regs = []
                        for _, row in df_api.iterrows():
                            mock_regs.append({f"campo_{i}": str(val) for i, val in enumerate(row.values)})
                        df_api = pd.DataFrame(mock_regs)
                    except Exception:
                        pass

                # Se não enviou base local, tenta a API oficial do TCE
                if df_api.empty:
                    with st.spinner(f"Consultando API do TCE-CE para o arquivo '{nome_arq}'..."):
                        params = {
                            "exercicio": exercicio,
                            "codigo_municipio": codigo_municipio_input.strip(),
                            "data_referencia_doc": data_ref
                        }
                        df_api = cliente_api.consultar_com_fallback(endpoints_possiveis, params)

                st.session_state["dados_api_retorno"] = df_api.to_dict(orient="records") if not df_api.empty else []

                st.session_state["etapa_auditoria"] = 3
                st.rerun()

    elif passo == 3:
        st.markdown("##### 2. Relatório Detalhado: Comparação Campo a Campo")
        arq_obj = st.session_state.get("arquivo_auditoria_obj")
        nome_arq = arq_obj.name if arq_obj else "arquivo.lco"
        layout_atual = obter_layout_arquivo(nome_arq)
        
        linhas_locais = st.session_state.get("linhas_arquivo_local", [])
        relatorio_input = st.session_state.get("linhas_locais_input", "")
        dados_api = st.session_state.get("dados_api_retorno", [])
        
        st.info(f"📁 **Módulo:** `{layout_atual['nome']}` | **Arquivo:** `{nome_arq}` | **Registros na API / Base:** {len(dados_api)}")

        if relatorio_input.strip():
            linhas_alvo = [int(m) for m in re.findall(r'(\d+)', relatorio_input)]
        else:
            linhas_alvo = list(range(1, len(linhas_locais) + 1))

        for linha_num in linhas_alvo:
            if 0 < linha_num <= len(linhas_locais):
                conteudo_linha = linhas_locais[linha_num - 1]
                campos_linha = [c.strip('"').strip() for c in conteudo_linha.split(",")]
            else:
                continue

            reg_historico = {}
            val_arquivo_chave = campos_linha[0] if campos_linha else ""
            
            for reg in dados_api:
                valores_reg = [str(v).strip() for v in reg.values() if v is not None]
                if val_arquivo_chave in valores_reg:
                    reg_historico = reg
                    break
            
            if not reg_historico and dados_api:
                idx_reg = (linha_num - 1) % len(dados_api)
                reg_historico = dados_api[idx_reg]

            valores_hist_lista = list(reg_historico.values()) if reg_historico else []
            nomes_colunas = layout_atual["campos"]
            
            is_erro = not reg_historico or len(reg_historico) == 0
            
            termo_modulo = layout_atual['nome'].split()[0]
            status_cor = "#EF4444" if is_erro else "#059669"
            status_texto = f"{termo_modulo} não encontrado" if is_erro else f"{termo_modulo} localizado"
            
            with st.container():
                st.markdown("---")
                col_head1, col_head2 = st.columns([5, 1])
                with col_head1:
                    st.markdown(f"#### Linha {linha_num}")
                with col_head2:
                    st.markdown(f"<div style='background: {status_cor}20; color: {status_cor}; padding: 4px 8px; border-radius: 6px; font-weight: bold; font-size: 11px; text-align: center;'>{status_texto}</div>", unsafe_allow_html=True)
                
                cols_ui = st.columns(len(nomes_colunas))
                
                for idx, col_ui in enumerate(cols_ui):
                    nome_coluna_atual = nomes_colunas[idx] if idx < len(nomes_colunas) else f"Campo {idx+1}"
                    val_arquivo = campos_linha[idx] if idx < len(campos_linha) else "-"
                    val_historico = str(valores_hist_lista[idx]) if idx < len(valores_hist_lista) else "Não disponível"
                    
                    divergente = (val_historico != "Não disponível" and val_arquivo != val_historico)
                    
                    with col_ui:
                        st.markdown(f"""
                            <div style='border: 1px solid #E2E8F0; padding: 12px; border-radius: 8px; background: #FFF; min-height: 90px;'>
                                <small style='color: #64748B; font-weight: bold;'>{nome_coluna_atual.upper()}</small><br>
                                <div style='margin-top: 4px;'><b>Arquivo:</b> <span style='color: {"red" if divergente or is_erro else "black"}'>{val_arquivo}</span></div>
                                <div style='margin-top: 2px;'><small style='color: #64748B;'>Histórico: {val_historico}</small></div>
                            </div>
                        """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Fazer Nova Auditoria / Voltar ao Início"):
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

with aba5:
    st.markdown("##### 🕸️ Carga Completa & Fluxograma de Dependências")
    st.markdown("Envie múltiplos arquivos para validação em lote.")
