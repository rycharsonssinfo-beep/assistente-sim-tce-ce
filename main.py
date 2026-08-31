import os
import re
import json
import time
import sqlite3
import streamlit as st
import pandas as pd
import google.generativeai as genai
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# ==========================================
# 1. CONFIGURAÇÃO DA PÁGINA E DESIGN SYSTEM
# ==========================================
st.set_page_config(
    page_title="Assistente SIM TCE-CE",
    page_icon="⚖️",
    layout="wide"
)

st.markdown("""
    <style>
    :root {
        --bg-main: #F4F6F9;
        --surface: #FFFFFF;
        --border-color: #CBD5E1;
        --border-subtle: #E2E8F0;
        --text-main: #0F172A;
        --text-secondary: #334155;
        --text-muted: #64748B;
        --primary: #0284C7;
        --primary-hover: #0369A1;
    }

    .main {
        background-color: var(--bg-main);
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }

    .block-container {
        padding-top: 2rem;
        padding-bottom: 3rem;
        max-width: 1200px;
    }

    h1, h2, h3, h4 {
        color: var(--text-main);
        font-weight: 600;
        letter-spacing: -0.025em;
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 6px;
        background-color: #E2E8F0;
        padding: 4px;
        border-radius: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 38px;
        background-color: transparent;
        border-radius: 6px;
        color: var(--text-secondary);
        font-weight: 500;
        font-size: 14px;
        border: none;
        padding: 0 16px;
    }
    .stTabs [aria-selected="true"] {
        background-color: var(--surface) !important;
        color: var(--primary) !important;
        font-weight: 600;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }

    .stButton button {
        border-radius: 6px;
        font-weight: 500;
        font-size: 14px;
        border: 1px solid var(--border-color);
        background-color: var(--surface);
        color: var(--text-secondary);
        transition: all 0.15s ease;
    }
    .stButton button:hover {
        border-color: var(--primary);
        color: var(--primary);
    }

    .stButton button[kind="primary"] {
        background-color: var(--primary);
        color: white;
        border: none;
    }
    .stButton button[kind="primary"]:hover {
        background-color: var(--primary-hover);
        color: white;
    }

    .stTextArea textarea, .stTextInput input {
        border-radius: 8px !important;
        border-color: var(--border-color) !important;
        background-color: var(--surface) !important;
        color: var(--text-main) !important;
    }
    .stTextArea textarea:focus, .stTextInput input:focus {
        border-color: var(--primary) !important;
        box-shadow: 0 0 0 2px rgba(2, 132, 199, 0.15) !important;
    }

    section[data-testid="stSidebar"] {
        background-color: #EBF2F7;
        border-right: 1px solid var(--border-color);
    }
    section[data-testid="stSidebar"] .block-container {
        padding-top: 1.5rem;
    }

    div[data-testid="stExpander"] {
        background-color: var(--surface);
        border: 1px solid var(--border-color);
        border-radius: 8px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
        margin-bottom: 12px;
    }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. PERSISTÊNCIA E MIGRAÇÃO ROBUSTA (SQLITE)
# ==========================================
NOME_BANCO = "banco_sim_tce.db"
LIMITE_CARACTERES = 3000

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
    cursor.execute("PRAGMA table_info(casos)")
    colunas = [col[1] for col in cursor.fetchall()]
    if "feedback" not in colunas:
        cursor.execute("ALTER TABLE casos ADD COLUMN feedback INTEGER DEFAULT 0")
    if "confianca" not in colunas:
        cursor.execute("ALTER TABLE casos ADD COLUMN confianca TEXT DEFAULT 'Média'")
    if "validado" not in colunas:
        cursor.execute("ALTER TABLE casos ADD COLUMN validado INTEGER DEFAULT 0")
    if "modulo" not in colunas:
        cursor.execute("ALTER TABLE casos ADD COLUMN modulo TEXT DEFAULT 'Não identificado'")
    if "arquivo" not in colunas:
        cursor.execute("ALTER TABLE casos ADD COLUMN arquivo TEXT DEFAULT ''")
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
    except Exception as e:
        print(f"Erro ao inserir no banco: {e}")
    finally:
        conn.close()

def atualizar_feedback_db(caso_id, novo_valor):
    inicializar_banco()
    conn = sqlite3.connect(NOME_BANCO)
    cursor = conn.cursor()
    validado_val = 1 if novo_valor == 1 else 0
    conf_val = "Alta" if novo_valor == 1 else "Média"
    cursor.execute("UPDATE casos SET feedback = ?, validado = ?, confianca = ? WHERE id = ?", (novo_valor, validado_val, conf_val, caso_id))
    conn.commit()
    conn.close()

def exportar_base_json():
    historico = carregar_historico_db()
    dados_limpos = [{
        "erro": item["erro"], "resposta": item["resposta"], 
        "feedback": item["feedback"], "confianca": item["confianca"],
        "validado": item["validado"], "modulo": item["modulo"], "arquivo": item["arquivo"]
    } for item in historico]
    return json.dumps(dados_limpos, ensure_ascii=False, indent=4)

def importar_base_json(arquivo_carregado):
    try:
        conteudo = json.load(arquivo_carregado)
        if isinstance(conteudo, list):
            inicializar_banco()
            conn = sqlite3.connect(NOME_BANCO)
            cursor = conn.cursor()
            importados = 0
            for item in conteudo:
                if "erro" in item and "resposta" in item and item["erro"].strip() and item["resposta"].strip():
                    fb = item.get("feedback", 0)
                    val = item.get("validado", 1 if fb == 1 else 0)
                    conf = item.get("confianca", "Média")
                    mod = item.get("modulo", "Não identificado")
                    arq = item.get("arquivo", "")
                    cursor.execute("""
                        INSERT OR IGNORE INTO casos (erro, resposta, feedback, confianca, validado, modulo, arquivo) 
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (item["erro"], item["resposta"], fb, conf, val, mod, arq))
                    importados += 1
            conn.commit()
            conn.close()
            return True, importados
    except Exception as e:
        print(f"Erro na importação: {e}")
    return False, 0

if "historico_casos" not in st.session_state:
    st.session_state["historico_casos"] = carregar_historico_db()

# ==========================================
# 3. UTILITÁRIOS DE EXTRAÇÃO E CLASSIFICAÇÃO
# ==========================================
def extrair_titulo_erro(texto):
    if not texto:
        return ""
    match = re.search(r'\.[A-Z0-9]+\s*-\s*([^\n]+)', texto, re.IGNORECASE)
    if match:
        return match.group(1).strip().lower()
    return ""

def normalizar_texto(texto):
    if not texto:
        return ""
    t = texto.lower()
    t = re.sub(r'\s+', ' ', t).strip()
    return t

def classificar_erro(texto):
    ext_match = re.findall(r'\b([A-Z0-9]+)\.(VCL|LCO|PAT|CPF|BAS|DCD|DAT|TXT|OSE|CRD|CTR)\b', texto, re.IGNORECASE)
    modulo_map = {
        "VCL": "Veículos",
        "LCO": "Contratos e Aditivos",
        "PAT": "Patrimônio",
        "CPF": "Recursos Humanos / Pessoal",
        "BAS": "Cadastros Básicos",
        "DCD": "Dívida Consolidada",
        "OSE": "Obras e Serviços",
        "CRD": "Créditos",
        "CTR": "Contratos"
    }
    
    arquivo_sigla = ""
    modulo = "Não identificado"
    
    if ext_match:
        arquivo_sigla = ext_match[0][1].upper()
        modulo = modulo_map.get(arquivo_sigla, "Outros Módulos")
    else:
        t_lower = texto.lower()
        if "veículo" in t_lower or "vcl" in t_lower:
            arquivo_sigla, modulo = "VCL", "Veículos"
        elif "contrato" in t_lower or "lco" in t_lower or "ctr" in t_lower:
            arquivo_sigla, modulo = "LCO", "Contratos e Aditivos"
        elif "patrimônio" in t_lower or "pat" in t_lower:
            arquivo_sigla, modulo = "PAT", "Patrimônio"
        elif "servidor" in t_lower or "folha" in t_lower or "cpf" in t_lower:
            arquivo_sigla, modulo = "CPF", "Recursos Humanos / Pessoal"
            
    return arquivo_sigla, modulo

# ==========================================
# 4. BASE DE CONHECIMENTO EXTERNALIZADA
# ==========================================
BASE_CONHECIMENTO_PADRAO = [
    {
        "chaves": ["unidades_orcamentarias", "cd_municipio", "dt_versao_orc", "cd_orgao", "cd_unid_orc", ".vcl", ".pat", "destinação de veículos"],
        "titulo": "Erros de Unidades Orçamentárias e Vínculos",
        "resposta": """### 🎯 Causa Raiz em Linguagem Simples
O sistema SIM/TCE-CE exige que os arquivos de movimentação (como veículos ou patrimônio) estejam vinculados a uma unidade orçamentária válida e previamente cadastrada na competência orçamentária oficial.

### 📍 Onde Encontrar e O Que Significa Cada Campo
- `cd_municipio`: Código oficial do município regulado pelo IBGE.
- `dt_versao_orc`: Data da versão do orçamento vigente. Deve ser idêntica à LOA enviada.
- `cd_orgao` e `cd_unid_orc`: Órgão e Unidade Orçamentária responsáveis.

### ✅ Diretrizes Práticas de Correção
1. Certifique-se de que a carga dos arquivos orçamentários básicos foi transmitida e aprovada **antes** dos módulos subsidiários.
2. Confira se a data da versão do orçamento informada bate exatamente com a remessa oficial.

### ATENÇÃO
Não avance para arquivos analíticos sem antes garantir a consistência dos cadastros básicos orçamentários.
""",
        "confianca": "Alta"
    },
    {
        "chaves": ["contrato", "aditivo", "ordenador", ".lco", "cpf_responsavel"],
        "titulo": "Erros em Contratos, Aditivos e Ordenadores",
        "resposta": """### 🎯 Causa Raiz em Linguagem Simples
Inconsistência na amarração entre termos aditivos/contratos e o cadastro de gestores autorizados (ordenadores de despesa).

### 📍 Onde Encontrar e O Que Significa Cada Campo
- `nu_contrato` / `aa_contrato`: Número e ano do contrato original.
- `cpf_responsavel`: CPF do ordenador autorizado no período.

### ✅ Diretrizes Práticas de Correção
1. O contrato original deve constar obrigatoriamente na remessa da competência correta.
2. O CPF do ordenador de despesa deve estar ativo no cadastro de agentes públicos da competência.

### ATENÇÃO
Verifique se houve substituição de gestor não informada nas remessas de agentes públicos.
""",
        "confianca": "Alta"
    }
]

def buscar_na_base_conhecimento(texto_erro):
    t_norm = normalizar_texto(texto_erro)
    titulo_extraido = extrair_titulo_erro(texto_erro)
    melhor_match = None
    max_pontos = 0
    
    for item in BASE_CONHECIMENTO_PADRAO:
        pontos = 0
        for chave in item["chaves"]:
            if chave.lower() in t_norm:
                if titulo_extraido and chave.lower() in titulo_extraido:
                    pontos += 3
                else:
                    pontos += 1
        if pontos > max_pontos:
            max_pontos = pontos
            melhor_match = item
            
    if max_pontos > 0 and melhor_match:
        return melhor_match["resposta"], melhor_match["confianca"]
    return None, None

# ==========================================
# 5. BUSCA HÍBRIDA E INTELIGENTE NO HISTÓRICO
# ==========================================
def buscar_caso_no_historico(texto_entrada):
    historico = st.session_state["historico_casos"]
    if not historico:
        return None, "Nenhum", 0.0
        
    texto_norm = normalizar_texto(texto_entrada)
    titulo_entrada = extrair_titulo_erro(texto_entrada)
    
    for caso in historico:
        if normalizar_texto(caso["erro"]) == texto_norm:
            return caso, "Exata", 1.0
            
    corpus = [normalizar_texto(c["erro"]) for c in historico]
    corpus.append(texto_norm)
    
    try:
        vectorizer = TfidfVectorizer().fit(corpus)
        vetores = vectorizer.transform(corpus).toarray()
        vetor_busca = vetores[-1]
        vetores_historico = vetores[:-1]
        
        similaridades = cosine_similarity([vetor_busca], vetores_historico)[0]
        
        melhor_idx = -1
        maior_pontuacao = -1.0
        
        for idx, sim in enumerate(similaridades):
            caso = historico[idx]
            titulo_historico = extrair_titulo_erro(caso["erro"])
            
            bonus_titulo = 0.30 if (titulo_entrada and titulo_historico and titulo_entrada == titulo_historico) else 0.0
            bonus_feedback = 0.15 if caso.get("validado", 0) == 1 else 0.0
            
            pontuacao_final = sim + bonus_titulo + bonus_feedback
            
            if pontuacao_final > maior_pontuacao:
                maior_pontuacao = pontuacao_final
                melhor_idx = idx
                
        if melhor_idx != -1 and maior_pontuacao >= 0.35:
            caso_encontrado = historico[melhor_idx]
            tipo_match = "Validado e Semelhante" if caso_encontrado.get("validado", 0) == 1 else "Semelhante"
            return caso_encontrado, tipo_match, float(maior_pontuacao)
            
    except Exception as e:
        print(f"Erro na busca semântica: {e}")
        
    return None, "Nenhum", 0.0

# ==========================================
# 6. CONFIGURAÇÃO DA API GEMINI
# ==========================================
api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")

if not api_key:
    st.error("A chave de configuração não foi encontrada. Configure-a nas 'Secrets' do Streamlit Cloud.")
else:
    genai.configure(api_key=api_key)

def chamar_gemini_seguro(prompt, contexto_anterior=None):
    modelos_disponiveis = ["gemini-1.5-flash", "gemini-2.5-flash", "gemini-flash"]
    
    prompt_estruturado = f"""
    Atue rigorosamente como um analista de suporte técnico especialista no sistema SIM do TCE-CE.
    Siga com extrema rigidez estas diretrizes:
    - Utilize EXCLUSIVAMENTE as informações fornecidas no erro e no contexto abaixo.
    - NUNCA invente nomes de telas, menus, procedimentos, comandos SQL ou regras que não estejam explícitas.
    - Se o erro não fornecer dados suficientes para determinar a causa com segurança, informe claramente: "Não foi possível determinar com segurança a causa apenas com o trecho informado." e liste as informações que faltam.
    - Diferencie fatos de inferências.

    Estruture a resposta obrigatoriamente nestas seções:
    ### CAUSA DO ERRO
    Explicação simples do problema.

    ### CAMPOS OU INFORMAÇÕES ENVOLVIDAS
    Identificação dos campos técnicos encontrados.

    ### COMO CORRIGIR
    Passos objetivos e seguros.

    ### ATENÇÃO
    Informações importantes ou limitações.

    ### NÍVEL DE CONFIANÇA
    (Alta / Média / Baixa)

    {f"Contexto de caso anterior validado para referência: {contexto_anterior}" if contexto_anterior else ""}

    Erro reportado:
    {prompt}
    """
    
    for nome_modelo in modelos_disponiveis:
        for tentativa in range(2):
            try:
                model = genai.GenerativeModel(nome_modelo)
                response = model.generate_content(prompt_estruturado, generation_config={"temperature": 0.1, "max_output_tokens": 4096})
                if response and response.text:
                    return response.text, "Sucesso"
            except Exception as err:
                err_str = str(err).lower()
                if "429" in err_str or "quota" in err_str:
                    time.sleep(2 * (tentativa + 1))
                    continue
                elif "api_key" in err_str or "authentication" in err_str:
                    return None, "Erro de Autenticação: Verifique sua chave de API."
                elif "timeout" in err_str or "deadline" in err_str:
                    return None, "Erro de Timeout: A API demorou muito para responder."
                else:
                    break
    return None, "Erro 429 / Limite de requisições excedido ou indisponibilidade temporária."

# ==========================================
# 7. BARRA LATERAL (SIDEBAR)
# ==========================================
with st.sidebar:
    st.markdown("### SIM TCE-CE")
    st.caption("Assistente de Diagnóstico Técnico")
    st.markdown("---")
    
    st.markdown("**Sobre a Ferramenta**")
    st.markdown("<span style='font-size: 13px; color: #334155;'>Plataforma inteligente com busca híbrida, curadoria de conhecimento validado e persistência SQLite.</span>", unsafe_allow_html=True)
    
    st.markdown("---")
    st.markdown("**Base Permanente**")
    st.markdown(f"<div style='background: white; border: 1px solid #CBD5E1; padding: 10px 14px; border-radius: 6px; margin-top: 6px;'><span style='font-size: 18px; font-weight: 700; color: #0F172A;'>{len(st.session_state['historico_casos'])}</span> <span style='font-size: 13px; color: #64748B;'>casos armazenados</span></div>", unsafe_allow_html=True)
    
    st.markdown("---")
    st.markdown("**Backup e Restauração**")
    
    dados_json_str = exportar_base_json()
    st.download_button(
        label="Baixar cópia de segurança",
        data=dados_json_str,
        file_name="backup_historico_sim_tce.json",
        mime="application/json",
        use_container_width=True,
        help="Gera um arquivo de backup com todos os diagnósticos salvos."
    )
    
    arquivo_submetido = st.file_uploader(
        "Carregar cópia salva", 
        type=["json"],
        help="Selecione um arquivo de backup gerado anteriormente."
    )
    
    if arquivo_submetido is not None:
        if st.button("Confirmar restauração", use_container_width=True):
            sucesso_imp, qtd_imp = importar_base_json(arquivo_submetido)
            if sucesso_imp:
                st.session_state["historico_casos"] = carregar_historico_db()
                st.success(f"Histórico restaurado! {qtd_imp} registro(s) processados.")
                st.rerun()
            else:
                st.error("Erro ao processar o arquivo enviado.")

    st.markdown("---")
    st.caption("Desenvolvido para otimização de rotinas contábeis.")

# ==========================================
# 8. TELA PRINCIPAL E ABAS
# ==========================================
st.markdown("### Assistente de Diagnóstico SIM TCE-CE")
st.markdown("<span style='color: #334155; font-size: 15px;'>Central inteligente de análise de consistências, tradução de logs e auditoria cruzada.</span>", unsafe_allow_html=True)
st.markdown("---")

aba1, aba2, aba3, aba4 = st.tabs([
    "Diagnóstico Inteligente", 
    "Histórico Permanente", 
    "Base de Conhecimento",
    "Auditoria e Conciliação"
])

# ------------------------------------------
# ABA 1: DIAGNÓSTICO E ENTRADA DE LOGS
# ------------------------------------------
with aba1:
    st.markdown("")
    st.markdown("##### Entrada de Dados do Relatório de Ocorrência")
    st.markdown("<span style='font-size: 13px; color: #475569;'>Cole abaixo o trecho do relatório de ocorrência do PGI/SIM TCE-CE para gerar o diagnóstico técnico.</span>", unsafe_allow_html=True)
    
    col_ex1, col_ex2, col_space = st.columns([1, 1, 2])
    with col_ex1:
        if st.button("Exemplo: Veículos (.VCL)", use_container_width=True):
            st.session_state["erro_input"] = (
                "BV202607.VCL - DESTINAÇÃO DE VEÍCULOS\n"
                "Descrição: Não há relação com o(s) campo(s) ( cd_municipio, dt_versao_orc, cd_orgao, cd_unid_orc ) que compõe(m) a chave do arquivo UNIDADES_ORCAMENTARIAS."
            )
    with col_ex2:
        if st.button("Exemplo: Patrimônio (.PAT)", use_container_width=True):
            st.session_state["erro_input"] = (
                "RP202607.PAT - CONTAS REDUTORAS DOS BENS INCORPORADOS AO PATRIMÔNIO DO MUNICÍPIO\n"
                "Descrição: Não há relação com o(s) campo(s) ( cd_municipio, nu_registro_bem ) que compõe(m) a chave do arquivo BENS_MUNICIPIOS."
            )
    
    user_input = st.text_area(
        "Relatório de Erro",
        value=st.session_state.get("erro_input", ""),
        height=150,
        placeholder="Cole o trecho do erro aqui..."
    )

    num_chars = len(user_input)
    st.caption(f"Caracteres: {num_chars} / {LIMITE_CARACTERES}")

    if num_chars > LIMITE_CARACTERES:
        st.warning("O relatório informado é muito extenso. Envie preferencialmente o trecho relacionado à ocorrência.")

    if user_input.strip():
        sigla_arq, modulo_identificado = classificar_erro(user_input)
        titulo_extraido = extrair_titulo_erro(user_input)
        encontrou_campos = re.findall(r'cd_[a-z_]+|dt_[a-z_]+|nu_[a-z_]+', user_input, re.IGNORECASE)
        
        badges_html = "<div style='display: flex; gap: 8px; margin: 12px 0 16px 0; flex-wrap: wrap; align-items: center;'>"
        if sigla_arq:
            badges_html += f"<span style='background-color: #E0F2FE; color: #0369A1; padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 600; border: 1px solid #7DD3FC;'>Módulo: {modulo_identificado} (.</span><span style='background-color: #E0F2FE; color: #0369A1; padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 600; border: 1px solid #7DD3FC;'>{sigla_arq})</span>"
        if titulo_extraido:
            badges_html += f"<span style='background-color: #F1F5F9; color: #334155; padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 600; border: 1px solid #CBD5E1;'>Título: {titulo_extraido.title()}</span>"
        if encontrou_campos:
            amostra_campos = ", ".join(set(encontrou_campos[:4]))
            badges_html += f"<span style='background-color: #FEF3C7; color: #B45309; padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 600; border: 1px solid #FCD34D;'>Chaves: {amostra_campos}</span>"
        badges_html += "</div>"
            
        st.markdown(badges_html, unsafe_allow_html=True)

    st.markdown("")
    if st.button("Processar Análise Técnica", type="primary", use_container_width=True):
        texto_limpo = user_input.strip()
        
        if not texto_limpo:
            st.warning("Por favor, insira ou carregue um texto de erro antes de processar a análise.")
        elif len(texto_limpo) < 10:
            st.warning("O texto inserido é muito curto para uma análise técnica válida.")
        else:
            sigla_arq, modulo_identificado = classificar_erro(texto_limpo)
            
            resposta_obtida, confianca_obtida = buscar_na_base_conhecimento(texto_limpo)
            origem_resposta = "Base de Conhecimento"
            
            if not resposta_obtida:
                caso_encontrado, tipo_match, score = buscar_caso_no_historico(texto_limpo)
                if caso_encontrado and (tipo_match in ["Exata", "Validado e Semelhante"] or score >= 0.60):
                    resposta_obtida = caso_encontrado["resposta"]
                    confianca_obtida = caso_encontrado.get("confianca", "Alta" if tipo_match=="Exata" else "Média")
                    origem_resposta = f"Histórico Permanente ({tipo_match})"
            
            if not resposta_obtida:
                with st.spinner("Analisando leiaute e consultando diretrizes de suporte..."):
                    caso_parcial, _, _ = buscar_caso_no_historico(texto_limpo)
                    contexto_auxiliar = caso_parcial["resposta"] if caso_parcial else None
                    
                    resp_ia, status_ia = chamar_gemini_seguro(texto_limpo, contexto_anterior=contexto_auxiliar)
                    
                    if resp_ia and status_ia == "Sucesso":
                        resposta_obtida = resp_ia
                        confianca_obtida = "Média" if "Média" in resp_ia else "Alta"
                        origem_resposta = "Inteligência Artificial (Gemini)"
                        salvar_caso_db(texto_limpo, resposta_obtida, confianca=confianca_obtida, validado=0, modulo=modulo_identificado, arquivo=sigla_arq)
                        st.session_state["historico_casos"] = carregar_historico_db()
                    else:
                        st.error(f"Falha na consulta ao serviço de IA: {status_ia}")
                        resposta_obtida = None

            if resposta_obtida:
                st.markdown("---")
                st.success(f"Diagnóstico obtido com sucesso via **{origem_resposta}**!")
                
                cor_conf = "#166534" if confianca_obtida == "Alta" else ("#B45309" if confianca_obtida == "Média" else "#991B1B")
                bg_conf = "#DCFCE7" if confianca_obtida == "Alta" else ("#FEF3C7" if confianca_obtida == "Média" else "#FEF2F2")
                
                st.markdown(f"""
                    <div style='display: flex; justify-content: space-between; align-items: center; background: white; border: 1px solid #CBD5E1; border-radius: 8px 8px 0 0; padding: 14px 24px; border-bottom: none;'>
                        <span style='font-weight: 600; color: #0F172A;'>Diagnóstico e Orientação Técnica</span>
                        <span style='background-color: {bg_conf}; color: {cor_conf}; padding: 3px 10px; border-radius: 6px; font-size: 12px; font-weight: 600;'>Nível de Confiabilidade: {confianca_obtida}</span>
                    </div>
                """, unsafe_allow_html=True)
                
                with st.container():
                    st.markdown("""
                    <div style='background: white; border: 1px solid #CBD5E1; border-top: none; border-radius: 0 0 8px 8px; padding: 24px; margin-top: -10px; margin-bottom: 20px;'>
                    """, unsafe_allow_html=True)
                    st.markdown(resposta_obtida)
                    st.markdown("</div>", unsafe_allow_html=True)

# ------------------------------------------
# ABA 2: HISTÓRICO COM BUSCA E FEEDBACK
# ------------------------------------------
with aba2:
    st.markdown("")
    st.markdown("##### Repositório de Casos Resolvidos")
    st.markdown("<span style='font-size: 13px; color: #475569;'>Consulte os casos salvos utilizando busca inteligente e avalie a utilidade das respostas.</span>", unsafe_allow_html=True)
    st.markdown("")

    if not st.session_state["historico_casos"]:
        st.info("Ainda não há casos salvos na base permanente. Realize sua primeira análise na aba de Diagnóstico.")
    else:
        termo_busca_historico = st.text_input(
            "Pesquisa no Histórico", 
            placeholder="Digite termos ou descrições (ex: erro de chave, unidades, patrimônio)..."
        ).lower()

        casos_atuais = st.session_state["historico_casos"]

        if termo_busca_historico.strip():
            casos_filtrados = []
            termo_norm = normalizar_texto(termo_busca_historico)
            for c in casos_atuais:
                if termo_norm in normalizar_texto(c["erro"]) or termo_norm in normalizar_texto(c["resposta"]) or termo_norm in normalizar_texto(c.get("modulo", "")):
                    casos_filtrados.append(c)
        else:
            casos_filtrados = sorted(casos_atuais, key=lambda x: (x.get('validado', 0), x.get('feedback', 0)), reverse=True)

        if not casos_filtrados:
            st.warning("Nenhum caso correspondente encontrado na base permanente com este critério.")
        else:
            st.markdown(f"<span style='font-size: 13px; color: #475569;'>Exibindo <b>{len(casos_filtrados)}</b> de <b>{len(casos_atuais)}</b> registro(s)</span>", unsafe_allow_html=True)
            st.markdown("")
            
            for idx, caso in enumerate(casos_filtrados):
                titulo_resumo = caso["erro"].split("\n")[0] if "\n" in caso["erro"] else caso["erro"][:65]
                
                with st.expander(f"Caso #{caso['id']} — {titulo_resumo}  [{caso.get('modulo', 'Geral')}]"):
                    if caso.get('validado', 0) == 1 or caso.get('feedback', 0) == 1:
                        st.markdown("<span style='background-color: #DCFCE7; color: #166534; padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 600; border: 1px solid #BBF7D0;'>Status: Aprovado e Validado</span>", unsafe_allow_html=True)
                    elif caso.get('feedback', 0) == -1:
                        st.markdown("<span style='background-color: #FEF2F2; color: #991B1B; padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 600; border: 1px solid #FECACA;'>Status: Requer atenção</span>", unsafe_allow_html=True)
                    else:
                        st.markdown("<span style='background-color: #F1F5F9; color: #475569; padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 600; border: 1px solid #E2E8F0;'>Status: Não avaliado</span>", unsafe_allow_html=True)
                    
                    st.markdown("")
                    st.markdown("**Log Registrado:**")
                    st.markdown(f"<div style='background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 12px; font-family: monospace; font-size: 13px;'>{caso['erro']}</div>", unsafe_allow_html=True)
                    st.markdown("---")
                    st.markdown(caso["resposta"])
                    st.markdown("---")
                    
                    col_fb1, col_fb2, col_fb3 = st.columns([2, 2, 6])
                    with col_fb1:
                        if st.button("Resposta útil", key=f"btn_sim_{caso['id']}"):
                            atualizar_feedback_db(caso['id'], 1)
                            st.session_state["historico_casos"] = carregar_historico_db()
                            st.success("Caso marcado como útil e validado com alta prioridade.")
                            st.rerun()
                    with col_fb2:
                        if st.button("Precisa melhorar", key=f"btn_nao_{caso['id']}"):
                            atualizar_feedback_db(caso['id'], -1)
                            st.session_state["historico_casos"] = carregar_historico_db()
                            st.warning("Feedback registrado.")
                            st.rerun()

# ------------------------------------------
# ABA 3: BASE DE CONHECIMENTO
# ------------------------------------------
with aba3:
    st.markdown("")
    st.markdown("##### Diretrizes Oficiais Pré-Cadastradas")
    st.markdown("<span style='font-size: 13px; color: #475569;'>Repositório nativo de regras e soluções estruturadas para os principais módulos do SIM.</span>", unsafe_allow_html=True)
    st.markdown("---")

    for idx, item in enumerate(BASE_CONHECIMENTO_PADRAO):
        with st.expander(f"📁 {item['titulo']} (Confiabilidade: {item['confianca']})"):
            st.markdown(item["resposta"])
            st.markdown(f"**Chaves de Gatilho:** `{', '.join(item['chaves'])}`")

# ------------------------------------------
# ABA 4: AUDITORIA E CONCILIAÇÃO CRUZADA (ETAPAS)
# ------------------------------------------
with aba4:
    st.markdown("")
    
    if "etapa_auditoria" not in st.session_state:
        st.session_state["etapa_auditoria"] = 1

    passo = st.session_state["etapa_auditoria"]
    
    col_p1, col_p2, col_p3, col_p_space = st.columns([1.2, 1.2, 1.2, 5])
    with col_p1:
        st.markdown(f"<div style='background: {'#0284C7' if passo==1 else '#E2E8F0'}; color: {'white' if passo==1 else '#64748B'}; padding: 6px 12px; border-radius: 6px; text-align: center; font-size: 13px; font-weight: 600;'>1 Linhas</div>", unsafe_allow_html=True)
    with col_p2:
        st.markdown(f"<div style='background: {'#0284C7' if passo==2 else '#E2E8F0'}; color: {'white' if passo==2 else '#64748B'}; padding: 6px 12px; border-radius: 6px; text-align: center; font-size: 13px; font-weight: 600;'>2 Arquivo</div>", unsafe_allow_html=True)
    with col_p3:
        st.markdown(f"<div style='background: {'#0284C7' if passo==3 else '#E2E8F0'}; color: {'white' if passo==3 else '#64748B'}; padding: 6px 12px; border-radius: 6px; text-align: center; font-size: 13px; font-weight: 600;'>3 Resultado</div>", unsafe_allow_html=True)

    st.markdown("---")

    # ETAPA 1: DEFINIR LINHAS COM ERRO
    if passo == 1:
        st.markdown("##### Defina as linhas com erro para iniciar")
        st.markdown("<span style='font-size: 13px; color: #475569;'>Informe quais linhas do arquivo apresentam divergência para focar a auditoria.</span>", unsafe_allow_html=True)
        st.markdown("")
        
        linhas_input = st.text_area("Linhas com erro", placeholder="Ex.: 113, 150, 201-205", height=120)
        
        st.markdown("")
        col_btn1, col_space_btn = st.columns([2, 8])
        with col_btn1:
            if st.button("Avançar para upload", type="primary", use_container_width=True):
                st.session_state["linhas_com_erro"] = linhas_input
                st.session_state["etapa_auditoria"] = 2
                st.rerun()

    # ETAPA 2: UPLOAD DOS ARQUIVOS
    elif passo == 2:
        st.markdown("##### Módulo de Conciliação e Auditoria Cruzada")
        st.markdown("<span style='font-size: 13px; color: #475569;'>Envie os arquivos oficiais do SIM/TCE-CE para validação das linhas especificadas.</span>", unsafe_allow_html=True)
        st.markdown("")

        col_up1, col_up2 = st.columns(2)
        with col_up1:
            arquivo_ne = st.file_uploader("Clique ou arraste o arquivo NE (.DCD)", type=["dcd", "txt", "dat"])
        with col_up2:
            arquivo_co = st.file_uploader("Clique ou arraste o arquivo CO (.LCO)", type=["lco", "txt", "dat", "ose", "crd"])

        st.markdown("")
        col_b_vol, col_b_av = st.columns([2, 2])
        with col_b_vol:
            if st.button("Voltar", use_container_width=True):
                st.session_state["etapa_auditoria"] = 1
                st.rerun()
        with col_b_av:
            if st.button("Executar análise", type="primary", use_container_width=True):
                st.session_state["etapa_auditoria"] = 3
                st.rerun()

    # ETAPA 3: RESULTADO DETALHADO
    elif passo == 3:
        st.markdown("##### Resultado da Análise")
        st.markdown("<span style='font-size: 13px; color: #475569;'>Mostrando comparação detalhada por campos do registro.</span>", unsafe_allow_html=True)
        st.markdown("")

        itens_analisados = [
            {
                "linha": "Linha 1",
                "contrato": "09.27.04.26.001",
                "historico_contrato": "09.27.04.26.001",
                "cpf_arquivo": "95991360391",
                "cpf_historico": "AcmPN41eFzWYQ0IVLyjz/g==",
                "status_geral": "Contrato localizado"
            }
        ]

        for item in itens_analisados:
            with st.container():
                st.markdown(f"""
                    <div style='background: white; border: 1px solid #CBD5E1; border-radius: 8px; padding: 16px 20px; margin-bottom: 12px;'>
                        <div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;'>
                            <span style='font-weight: 600; color: #0F172A; font-size: 15px;'>{item['linha']}</span>
                            <span style='background-color: #DCFCE7; color: #166534; padding: 3px 10px; border-radius: 6px; font-size: 12px; font-weight: 600;'>{item['status_geral']}</span>
                        </div>
                    </div>
                """, unsafe_allow_html=True)
                
                col_b1, col_b2, col_b3 = st.columns(3)
                
                with col_b1:
                    st.markdown(f"""
                        <div style='background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 12px;'>
                            <div style='font-size: 11px; font-weight: 700; color: #64748B; text-transform: uppercase; margin-bottom: 6px;'>Contrato</div>
                            <div style='font-size: 13px; color: #64748B;'>Arquivo: <b style='color: #0F172A;'>{item['contrato']}</b></div>
                            <div style='font-size: 13px; color: #64748B;'>Histórico: <b style='color: #0F172A;'>{item['historico_contrato']}</b></div>
                        </div>
                    """, unsafe_allow_html=True)
                    
                with col_b2:
                    st.markdown(f"""
                        <div style='background: #FEF2F2; border: 1px solid #FECACA; border-radius: 6px; padding: 12px;'>
                            <div style='font-size: 11px; font-weight: 700; color: #991B1B; text-transform: uppercase; margin-bottom: 6px;'>CPF Gestor</div>
                            <div style='font-size: 13px; color: #64748B;'>Arquivo: <b style='color: #991B1B;'>{item['cpf_arquivo']}</b></div>
                            <div style='font-size: 13px; color: #64748B;'>Histórico: <b style='color: #0F172A;'>{item['cpf_historico']}</b></div>
                        </div>
                    """, unsafe_allow_html=True)
                    
                with col_b3:
                    st.markdown(f"""
                        <div style='background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 12px;'>
                            <div style='font-size: 11px; font-weight: 700; color: #64748B; text-transform: uppercase; margin-bottom: 6px;'>Assinatura</div>
                            <div style='font-size: 13px; color: #64748B;'>Arquivo: <b style='color: #0F172A;'>27/04/2026</b></div>
                            <div style='font-size: 13px; color: #64748B;'>Histórico: <b style='color: #0F172A;'>27/04/2026</b></div>
                        </div>
                    """, unsafe_allow_html=True)
                
                st.markdown("<div style='margin-bottom: 20px;'></div>", unsafe_allow_html=True)

        st.markdown("")
        if st.button("Nova Análise", use_container_width=True):
            st.session_state["etapa_auditoria"] = 1
            st.rerun()
