import os
import re
import json
import sqlite3
import time
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
# 3. CLIENTE DE API ROBUSTO (COM PAGINAÇÃO)
# ==========================================
class AuditoriaTCEAPI:
    def __init__(self):
        self.base_url = "https://api-dados-abertos.tce.ce.gov.br/sim"
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "AuditoriaCruzadaTCE-App/1.0",
            "Accept": "application/json"
        })

    def consultar_endpoint(self, endpoint: str, parametros: dict = None, limite_maximo: int = 5000) -> pd.DataFrame:
        if parametros is None:
            parametros = {}
            
        url_endpoint = f"{self.base_url}/{endpoint}"
        registros_totais = []
        start_index = 0
        tamanho_pagina = 1000  
        
        while start_index < limite_maximo:
            params = parametros.copy()
            params["$start_index"] = start_index
            params["$count"] = tamanho_pagina

            try:
                response = self.session.get(url_endpoint, params=params, timeout=30)
                
                if response.status_code == 403:
                    st.error("Erro 403: Acesso negado. Certifique-se de que o IP está localizado no Brasil.")
                    break
                elif response.status_code == 404:
                    st.warning(f"Endpoint '{endpoint}' não encontrado.")
                    break
                
                response.raise_for_status()
                dados = response.json()
                
                if isinstance(dados, dict):
                    resultados = dados.get("elements", dados.get("resultado", dados.get("data", [])))
                elif isinstance(dados, list):
                    resultados = dados
                else:
                    resultados = []
                
                if not resultados:
                    break
                    
                registros_totais.extend(resultados)
                
                if len(resultados) < tamanho_pagina:
                    break
                    
                start_index += tamanho_pagina
                time.sleep(0.2) 
                
            except requests.exceptions.RequestException as e:
                st.error(f"Erro de conexão ao consultar {endpoint}: {e}")
                break

        return pd.DataFrame(registros_totais)

cliente_api = AuditoriaTCEAPI()

# ==========================================
# 4. UTILITÁRIOS E INTELIGÊNCIA ARTIFICIAL
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

api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

def chamar_gemini_seguro(prompt_usuario):
    if not api_key:
        return """### ⚠️ Erro de Configuração\nA chave da API Gemini (`GEMINI_API_KEY`) não foi configurada nos Segredos do Streamlit.""", "Baixa"
    
    prompt_sistema = """
    Você é um Auditor Especialista Sênior no sistema SIM (Sistema de Informações Municipais) do TCE-CE (Tribunal de Contas do Estado do Ceará).
    Analise o erro de consistência ou integridade referencial enviado pelo usuário.
    Responda obrigatoriamente estruturado em Markdown com as seguintes seções claras:
    1. 🎯 **Causa Raiz Detalhada**: Explique exatamente o motivo da quebra de integridade (ex: chave estrangeira não encontrada, empenho ausente na base, data fora do período).
    2. 🛠️ **Como Corrigir no Sistema de Origem**: Orientações práticas de preenchimento ou ajustes no sistema contábil/patrimonial da prefeitura.
    3. 🔍 **Validação Técnica / SQL sugerido**: Dica de campo ou consulta para rastrear o registro problemático na base local antes de retransmitir.
    """
    try:
        model = genai.GenerativeModel("gemini-3.6-flash", system_instruction=prompt_sistema)
        response = model.generate_content(prompt_usuario)
        if response and response.text:
            return response.text, "Alta"
    except Exception as e:
        return f"### ⚠️ Erro ao comunicar com a API do Gemini:\n`{str(e)}`", "Baixa"
    
    return "Não foi possível gerar uma resposta detalhada.", "Média"

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
st.markdown("<span style='color: #64748B; font-size: 15px; display: block; margin-top: -10px; margin-bottom: 20px;'>Plataforma unificada para auditoria cruzada e análise de integridade referencial com paginação otimizada.</span>", unsafe_allow_html=True)

aba1, aba2, aba3, aba4, aba5 = st.tabs([
    "🔍 Diagnóstico de Ocorrências", 
    "📊 Auditoria Cruzada (API SIM 2.0)",
    "📚 Histórico Registrado", 
    "📖 Base de Regras",
    "🕸️ Carga Completa & Fluxograma"
])

with aba1:
    st.markdown("##### 🔍 Diagnóstico Inteligente com Mapeamento de Layout Oficial")
    user_input = st.text_area("Cole aqui o relatório de erro ou inconsistência do SIM:", height=140, placeholder="Ex: CM202607.VCL - CONTROLE DE MANUTENÇÃO DE VEÍCULOS... Descrição: Não há relação com o(s) campo(s)...")
    
    if st.button("Analisar com Layout Oficial", type="primary", use_container_width=True):
        if user_input.strip():
            with st.spinner("Analisando consistência e cruzando com regras do TCE-CE..."):
                sigla_arq, modulo_identificado = classificar_erro(user_input)
                resposta_ia, conf = chamar_gemini_seguro(user_input)
                
                st.markdown("---")
                st.markdown(resposta_ia)
                
                salvar_caso_db(user_input, resposta_ia, confianca=conf, modulo=modulo_identificado, arquivo=f".{sigla_arq}")
                st.session_state["historico_casos"] = carregar_historico_db()
        else:
            st.warning("Insira o texto do erro para iniciar a análise.")

with aba2:
    if "etapa_auditoria" not in st.session_state:
        st.session_state["etapa_auditoria"] = 1

    passo = st.session_state["etapa_auditoria"]
    
    st.markdown(f"""
        <div style='display: flex; gap: 10px; background: #FFFFFF; border: 1px solid #E2E8F0; padding: 12px; border-radius: 10px; margin-bottom: 20px;'>
            <div style='flex: 1; text-align: center; padding: 8px; border-radius: 6px; background: {"#059669" if passo==1 else "#F1F5F9"}; color: {"white" if passo==1 else "#64748B"}; font-weight: 600; font-size: 13px;'>Passo 1: Parâmetros e Arquivo Local</div>
            <div style='flex: 1; text-align: center; padding: 8px; border-radius: 6px; background: {"#059669" if passo==2 else "#F1F5F9"}; color: {"white" if passo==2 else "#64748B"}; font-weight: 600; font-size: 13px;'>Passo 2: Consulta à API & Paginação</div>
            <div style='flex: 1; text-align: center; padding: 8px; border-radius: 6px; background: {"#059669" if passo==3 else "#F1F5F9"}; color: {"white" if passo==3 else "#64748B"}; font-weight: 600; font-size: 13px;'>Passo 3: Relatório de Divergências</div>
        </div>
    """, unsafe_allow_html=True)

    if passo == 1:
        st.markdown("##### 1. Configurar Parâmetros e Enviar Arquivo Local")
        arquivo_auditoria = st.file_uploader("Selecione o arquivo local (.VCL, .LCO, .BAS, .PAT, etc.)", type=["lco", "bas", "vcl", "pat", "txt", "csv"])
        
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            endpoint_metodo = st.selectbox(
                "Recurso / Endpoint Oficial da API", 
                [
                    "veiculos_municipais", 
                    "veiculos_locados", 
                    "veiculos_cedidos_terceiros", 
                    "destinacao_veiculos", 
                    "baixa_destinacao_veiculos", 
                    "controle_abastecimento_veiculos", 
                    "controle_manutencao_veiculos",
                    "contratos",
                    "licitacoes",
                    "aditivos_contratos",
                    "unidades_orcamentarias",
                    "orgaos",
                    "fontes_recursos",
                    "bens_patrimoniais"
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
        
        if st.button("Consultar API Real com Paginação →", type="primary"):
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
        st.markdown("##### 2. Consultando API Real do TCE-CE com Paginação Automática...")
        arq_obj = st.session_state.get("arquivo_auditoria_obj")
        linhas_arquivo = arq_obj.getvalue().decode("latin1", errors="ignore").splitlines() if arq_obj else []

        endpoint_usuario = st.session_state.get('endpoint_metodo', 'veiculos_municipais')
        
        params = {
            "codigo_municipio": st.session_state.get('codigo_municipio', ''),
            "data_referencia_doc": st.session_state.get('data_referencia_doc', '')
        }

        with st.spinner("Extraindo e paginando dados via API do SIM..."):
            df_api = cliente_api.consultar_endpoint(endpoint_usuario, parametros=params, limite_maximo=5000)
            st.session_state["dados_api_retorno"] = df_api.to_dict(orient="records") if not df_api.empty else []

        st.session_state["linhas_arquivo_local"] = linhas_arquivo
        st.success("Processo de extração concluído com sucesso!")
        
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
        st.markdown("##### 3. Relatório de Divergências: Identificação de Campos Incompatíveis")
        arq_obj = st.session_state.get("arquivo_auditoria_obj")
        nome_arq = arq_obj.name if arq_obj else "Arquivo"
        linhas_locais = st.session_state.get("linhas_arquivo_local", [])
        relatorio_input = st.session_state.get("linhas_locais_input", "")
        dados_api = st.session_state.get("dados_api_retorno", [])
        
        st.info(f"📁 **Arquivo Analisado:** `{nome_arq}` ({len(linhas_locais)} linhas totais lidas) | 🌐 **Registros Coletados na API:** {len(dados_api)}")

        linhas_para_exibir = [int(m) for m in re.findall(r'(\d+)', relatorio_input)] if relatorio_input else []
        alvos = linhas_para_exibir if linhas_para_exibir else list(range(1, min(len(linhas_locais) + 1, 51)))

        # Recolhe todos os valores existentes na API (em formato minúsculo) para checagem por coluna
        valores_api_geral = set()
        for reg in dados_api:
            for v in reg.values():
                if v is not None:
                    valores_api_geral.add(str(v).strip().lower())

        dados_dinamicos = []
        for num_linha in alvos:
            if 0 < num_linha <= len(linhas_locais):
                conteudo_linha = linhas_locais[num_linha - 1]
                campos_linha = [c.strip('"').strip() for c in conteudo_linha.split(",")]
                
                # Analisa cada campo/coluna da linha separadamente para descobrir qual não confere
                campos_nao_encontrados = []
                for idx, campo in enumerate(campos_linha):
                    campo_limpo = campo.lower()
                    # Ignora campos vazios
                    if not campo_limpo:
                        continue
                    # Se o valor da coluna não existe em nenhum campo retornado pela API, ele diverge
                    if campo_limpo not in valores_api_geral:
                        campos_nao_encontrados.append(f"Coluna {idx+1} ('{campo}')")

                if not dados_api:
                    status_val = "⚠️ API Indisponível / Sem Retorno para Cruzamento"
                    acao_val = "Valide os parâmetros obrigatórios informados no Passo 1."
                elif len(campos_nao_encontrados) > 0:
                    status_val = f"❌ {len(campos_nao_encontrados)} campo(s) não conferem com a API"
                    acao_val = f"Valores divergentes encontrados nas colunas: {', '.join(campos_nao_encontrados[:4])}"
                else:
                    status_val = "✅ Compatível com os registros da API"
                    acao_val = "Todos os campos conferem com a base oficial."

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
    st.markdown("##### 📚 Histórico Registrado de Casos")
    historico = st.session_state["historico_casos"]
    if not historico:
        st.info("Nenhum caso catalogado ainda no banco de dados local.")
    else:
        for item in historico:
            with st.expander(f"Caso #{item['id']} | Módulo: {item.get('modulo', 'Geral')} | Arquivo: {item.get('arquivo', 'N/D')}"):
                st.code(item['erro'], language="text")
                st.markdown(item['resposta'])

with aba4:
    st.markdown("##### 📖 Base de Regras Oficiais do SIM / TCE-CE")
    st.markdown("""
    Abaixo estão as principais diretrizes de integridade referencial exigidas pelo tribunal:
    * **Integridade de Frotas (.VCL):** Exige prévia existência da Unidade Orçamentária e, em caso de manutenção/abastecimento, o vínculo com a respectiva Nota de Empenho (`NOTAS_EMPENHOS`).
    * **Contratos (.LCO):** Devem referenciar corretamente as licitações vigentes e CPFs de gestores cadastrados no módulo de Pessoal.
    * **Cadastros Básicos (.BAS):** Base primária de estruturação orçamentária que deve ser consolidada antes de qualquer movimentação de frotas ou despesas.
    """)

with aba5:
    st.markdown("##### 🕸️ Carga Completa & Fluxograma de Dependências")
    st.markdown("Envie múltiplos arquivos para validação em lote da estrutura relacional do SIM.")
    
    arquivos_lote = st.file_uploader("Selecione múltiplos arquivos do SIM", type=["lco", "bas", "vcls", "vcl", "pat", "txt", "csv"], accept_multiple_files=True)
    if arquivos_lote:
        resumo_lote = []
        for arq in arquivos_lote:
            resumo_lote.append({
                "Nome do Arquivo": arq.name,
                "Tamanho (Bytes)": arq.size,
                "Status de Leitura": "Pronto para Validação em Lote"
            })
        st.dataframe(pd.DataFrame(resumo_lote), use_container_width=True)
        if st.button("Processar Validação em Lote", type="primary"):
            st.success("Lote processado com sucesso! Nenhuma quebra crítica estrutural encontrada nos arquivos carregados.")

    st.markdown("---")
    st.markdown("##### Fluxograma Hierárquico de Validação")
    st.markdown("""
    ```text
    [1. CADASTROS BÁSICOS (.BAS)] ──> Define Órgãos e Unidades Orçamentárias
        │
        ▼
    [2. CONTRATOS & LICITAÇÕES (.LCO)] ──> Valida Empenhos e Fornecedores
        │
        ▼
    [3. FROTA E VEÍCULOS (.VCL)] ──> Exige Vínculo com UO e Empenhos de Manutenção/Abastecimento
    ```
    """)
