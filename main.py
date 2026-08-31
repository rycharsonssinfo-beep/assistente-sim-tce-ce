import os
import re
import json
import time
import sqlite3
import streamlit as st
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

    /* Estilização Moderna de Abas (Tabs) */
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

    /* Botões */
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

    /* Inputs e Textareas */
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

    /* Sidebar Estruturada */
    section[data-testid="stSidebar"] {
        background-color: #EBF2F7;
        border-right: 1px solid var(--border-color);
    }
    section[data-testid="stSidebar"] .block-container {
        padding-top: 1.5rem;
    }

    /* Expanders com Bordas Mais Nítidas */
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
    # Migração segura para bases existentes
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
    # Feedback positivo marca automaticamente como validado e confianca alta
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
# 3. UTILITÁRIOS DE NORMALIZAÇÃO E CLASSIFICAÇÃO
# ==========================================
def normalizar_texto(texto):
    if not texto:
        return ""
    # Remove espaços duplicados, quebras excessivas, padroniza maiúsculas/minúsculas para busca
    t = texto.lower()
    t = re.sub(r'\s+', ' ', t).strip()
    return t

def classificar_erro(texto):
    ext_match = re.findall(r'\b([A-Z0-9]+)\.(VCL|LCO|PAT|CPF|BAS|DCD|DAT|TXT)\b', texto, re.IGNORECASE)
    modulo_map = {
        "VCL": "Veículos",
        "LCO": "Contratos e Aditivos",
        "PAT": "Patrimônio",
        "CPF": "Recursos Humanos / Pessoal",
        "BAS": "Cadastros Básicos",
        "DCD": "Dívida Consolidada"
    }
    
    arquivo_sigla = ""
    modulo = "Não identificado"
    
    if ext_match:
        arquivo_sigla = ext_match[0][1].upper()
        modulo = modulo_map.get(arquivo_sigla, "Outros Módulos")
    else:
        # Busca por termos chaves alternativos
        t_lower = texto.lower()
        if "veículo" in t_lower or "vcl" in t_lower:
            arquivo_sigla, modulo = "VCL", "Veículos"
        elif "contrato" in t_lower or "lco" in t_lower:
            arquivo_sigla, modulo = "LCO", "Contratos e Aditivos"
        elif "patrimônio" in t_lower or "pat" in t_lower:
            arquivo_sigla, modulo = "PAT", "Patrimônio"
        elif "servidor" in t_lower or "folha" in t_lower or "cpf" in t_lower:
            arquivo_sigla, modulo = "CPF", "Recursos Humanos / Pessoal"
            
    return arquivo_sigla, modulo

# ==========================================
# 4. BASE DE CONHECIMENTO EXTERNALIZADA (JSON/ESTRUTURADA)
# ==========================================
BASE_CONHECIMENTO_PADRAO = [
    {
        "chaves": ["unidades_orcamentarias", "cd_municipio", "dt_versao_orc", "cd_orgao", "cd_unid_orc", ".vcl", ".pat"],
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
    melhor_match = None
    max_pontos = 0
    
    for item in BASE_CONHECIMENTO_PADRAO:
        pontos = 0
        for chave in item["chaves"]:
            if chave.lower() in t_norm:
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
    
    # 1. Busca Exata Normalizada
    for caso in historico:
        if normalizar_texto(caso["erro"]) == texto_norm:
            return caso, "Exata", 1.0
            
    # 2. Busca Semântica Avançada (TF-IDF + Similaridade + Feedback)
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
            # Atribui bônus se houver feedback positivo (validado)
            bonus_feedback = 0.15 if caso.get("validado", 0) == 1 else 0.0
            pontuacao_final = sim + bonus_feedback
            
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
# 6. CONFIGURAÇÃO DA API GEMINI E TRATAMENTO DE ERROS
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
                    return None, "Erro de Timeout: A API demorou muito para responder. Tente novamente."
                else:
                    break
    return None, "Erro 429 / Limite de requisições excedido ou indisponibilidade temporária da API."

# ==========================================
# 7. BARRA LATERAL (SIDEBAR COM BLOCOS)
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
                st.success(f"Histórico restaurado com sucesso! {qtd_imp} registro(s) processados.")
                st.rerun()
            else:
                st.error("Erro ao processar o arquivo enviado ou formato JSON inválido.")

    st.markdown("---")
    st.caption("Desenvolvido para otimização de rotinas contábeis.")

# ==========================================
# 8. TELA PRINCIPAL E ABAS
# ==========================================
st.markdown("### Assistente de Diagnóstico SIM TCE-CE")
st.markdown("<span style='color: #334155; font-size: 15px;'>Central inteligente de análise de consistências, tradução de logs e consulta de orientações técnicas.</span>", unsafe_allow_html=True)
st.markdown("---")

aba1, aba2, aba3 = st.tabs([
    "Diagnóstico Inteligente", 
    "Histórico Permanente", 
    "Base de Conhecimento"
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

    # Proteção de limite de caracteres
    num_chars = len(user_input)
    st.caption(f"Caracteres: {num_chars} / {LIMITE_CARACTERES}")

    if num_chars > LIMITE_CARACTERES:
        st.warning("O relatório informado é muito extenso. Envie preferencialmente o trecho relacionado à ocorrência para melhor assertividade.")

    if user_input.strip():
        sigla_arq, modulo_identificado = classificar_erro(user_input)
        encontrou_campos = re.findall(r'cd_[a-z_]+|dt_[a-z_]+|nu_[a-z_]+', user_input, re.IGNORECASE)
        
        badges_html = "<div style='display: flex; gap: 8px; margin: 12px 0 16px 0; flex-wrap: wrap; align-items: center;'>"
        if sigla_arq:
            badges_html += f"<span style='background-color: #E0F2FE; color: #0369A1; padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 600; border: 1px solid #7DD3FC;'>Módulo: {modulo_identificado} (.</span><span style='background-color: #E0F2FE; color: #0369A1; padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 600; border: 1px solid #7DD3FC;'>{sigla_arq})</span>"
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
            
            # ORDEM DE INTELIGÊNCIA E REAPROVEITAMENTO:
            # 1. Base de Conhecimento Estruturada
            resposta_obtida, confianca_obtida = buscar_na_base_conhecimento(texto_limpo)
            origem_resposta = "Base de Conhecimento"
            
            # 2. Histórico (Exato ou Semelhante Validado)
            if not resposta_obtida:
                caso_encontrado, tipo_match, score = buscar_caso_no_historico(texto_limpo)
                if caso_encontrado and (tipo_match in ["Exata", "Validado e Semelhante"] or score >= 0.70):
                    resposta_obtida = caso_encontrado["resposta"]
                    confianca_obtida = caso_encontrado.get("confianca", "Alta" if tipo_match=="Exata" else "Média")
                    origem_resposta = f"Histórico Permanente ({tipo_match})"
            
            # 3. Consulta IA Gemini (Somente se necessário)
            if not resposta_obtida:
                with st.spinner("Analisando leiaute e consultando diretrizes de suporte..."):
                    # Verifica se há caso parcialmente semelhante para fornecer contexto à IA
                    caso_parcial, _, _ = buscar_caso_no_historico(texto_limpo)
                    contexto_auxiliar = caso_parcial["resposta"] if caso_parcial else None
                    
                    resp_ia, status_ia = chamar_gemini_seguro(texto_limpo, contexto_anterior=contexto_auxiliar)
                    
                    if resp_ia and status_ia == "Sucesso":
                        resposta_obtida = resp_ia
                        confianca_obtida = "Média" if "Média" in resp_ia else "Alta"
                        origem_resposta = "Inteligência Artificial (Gemini)"
                        # Salva automaticamente na base com status não validado inicialmente
                        salvar_caso_db(texto_limpo, resposta_obtida, confianca=confianca_obtida, validado=0, modulo=modulo_identificado, arquivo=sigla_arq)
                        st.session_state["historico_casos"] = carregar_historico_db()
                    else:
                        st.error(f"Falha na consulta ao serviço de IA: {status_ia}")
                        resposta_obtida = None

            if resposta_obtida:
                st.markdown("---")
                st.success(f"Diagnóstico obtido com sucesso via **{origem_resposta}**!")
                
                # Exibição do nível de confiança visual
                cor_conf = "#166534" if confianca_obtida == "Alta" else ("#B45309" if confianca_obtida == "Média" else "#991B1B")
                bg_conf = "#DCFCE7" if confianca_obtida == "Alta" else ("#FEF3C7" if confianca_obtida == "Média" else "#FEF2F2")
                
                st.markdown(f"""
                    <div style='display: flex; justify-content: space-between; align-items: center; background: white; border: 1px solid #CBD5E1; border-radius: 8px 8px 0 0; padding: 14px 24px; border-bottom: none;'>
                        <span style='font-weight: 600; color: #0F172A;'>Diagnóstico e Orientação Técnica</span>
                        <span style='background-color: {bg_conf}; color: {cor_conf}; padding: 3px 10px; border-radius: 6px; font-size: 12px; font-weight: 600;'>Nível de Confiabilidade: {confianca_obtida}</span>
                    </div>
                    <div style='background: white; border: 1px solid #CBD5E1; border-radius: 0 0 8px 8px; padding: 24px;'>
                        {resposta_obtida}
                    </div>
                """, unsafe_allow_html=True)

# ------------------------------------------
# ABA 2: HISTÓRICO COM BUSCA HÍBRIDA E FEEDBACK
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
            # Ordena priorizando validados e feedback positivo
            casos_filtrados = sorted(casos_atuais, key=lambda x: (x.get('validado', 0), x.get('feedback', 0)), reverse=True)

        if not casos_filtrados:
            st.warning("Nenhum caso correspondente encontrado na base permanente com este critério.")
        else:
            st.markdown(f"<span style='font-size: 13px; color: #475569;'>Exibindo <b>{len(casos_filtrados)}</b> de <b>{len(casos_atuais)}</b> registro(s)</span>", unsafe_allow_html=True)
            st.markdown("")
            
            for idx, caso in enumerate(casos_filtrados):
                titulo_resumo = caso["erro"].split("\n")[0] if "\n" in caso["erro"] else caso["erro"][:65]
                
                with st.expander(f"Caso #{caso['id']} — {titulo_resumo}  [{caso.get('modulo', 'Geral')}]"):
                    # Badge de status interno
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
                    with col_fb3:
                        status_txt = "Validado e Confiável" if caso.get('validado', 0) == 1 else "Aguardando Curadoria"
                        st.markdown(f"<span style='font-size: 12px; color: #475569; line-height: 2.2;'>Curadoria: <b>{status_txt}</b></span>", unsafe_allow_html=True)

# ------------------------------------------
# ABA 3: BASE DE CONHECIMENTO E REFERÊNCIAS
# ------------------------------------------
with aba3:
    st.markdown("")
    st.markdown("##### Base de Conhecimento e Padrões SIM 2026")
    st.markdown("<span style='font-size: 13px; color: #475569;'>Consulte os guias rápidos e manuais de orientação técnica organizados por módulos.</span>", unsafe_allow_html=True)
    st.markdown("")
    
    termo_busca = st.text_input("Filtrar guias de referência", placeholder="Digite ex: 'Veículos', 'Contratos', 'Patrimônio'...").lower()
    st.markdown("")

    with st.expander("🏛️ Erros de Unidades Orçamentárias e Vínculos (Ex: .VCL, .PAT)"):
        st.markdown("""
        * **Ocorrência Comum no Log:**  
          *Não há relação com o(s) campo(s) ( cd_municipio, dt_versao_orc, cd_orgao, cd_unid_orc ) que compõe(m) a chave do arquivo UNIDADES_ORCAMENTARIAS.*
        
        * **O que significam os campos envolvidos?**
          * `cd_municipio`: Código oficial do município regulado pelo IBGE.
          * `dt_versao_orc`: Data da versão do orçamento vigente que foi enviada. Ela precisa ser idêntica à cadastrada na LOA/PPA.
          * `cd_orgao` e `cd_unid_orc`: Código do Órgão e da Unidade Orçamentária responsáveis pela despesa ou bem.
        
        * **Como corrigir de forma simples:**
          1. Certifique-se de que a carga dos arquivos orçamentários básicos foi enviada e aprovada **antes** de enviar os dados de veículos, patrimônio ou almoxarifado.
          2. Confira se a data da versão do orçamento informada no sistema contábil bate exatamente com a remessa oficial da LOA.
        """)

    with st.expander("📝 Erros em Contratos, Aditivos e Ordenadores (Ex: .LCO)"):
        st.markdown("""
        * **Ocorrência Comum no Log:**  
          *Gestor responsável pelo Contrato não encontrado no cadastro de Ordenadores* ou *Aditivo sem Contrato Original vinculado*.
        
        * **O que significam os campos envolvidos?**
          * `nu_contrato` / `aa_contrato`: Número e ano do contrato original.
          * `cpf_responsavel` / `cd_ordenador`: Identificação do gestor ou ordenador de despesas autorizado.

        * **Como corrigir de forma simples:**
          1. **Para o contrato:** O contrato original deve constar obrigatoriamente na remessa da competência correta antes que qualquer termo aditivo seja transmitido.
          2. **Para o gestor:** O CPF do ordenador de despesa deve estar ativo e devidamente informado na remessa de agentes públicos/responsáveis daquele respectivo mês.
        """)

    with st.expander("👥 Inconsistências na Folha de Pagamento e Servidores"):
        st.markdown("""
        * **Ocorrência Comum no Log:**  
          *Divergência ou ausência de vínculo empregatício para o CPF informado no arquivo de remessa de pessoal.*

        * **O que significam os campos envolvidos?**
          * `nu_cpf`: CPF do servidor ou agente público.
          * `cd_cargo` / `nu_matricula`: Identificação funcional na estrutura de cargos da prefeitura ou câmara.

        * **Como corrigir de forma simples:**
          1. Verifique se o servidor foi cadastrado no arquivo de servidores ativos/inativos antes de receber lançamentos de pagamento (folha).
          2. Confirme se houve alteração de cargo ou regime jurídico não atualizada no sistema de origem.
        """)

    with st.expander("📌 Guia Rápido: Como Ler os Campos nas Linhas dos Arquivos"):
        st.markdown("""
        * Se precisar analisar um arquivo texto (`.dat` ou `.txt`) linha por linha, lembre-se de que os dados são separados por **vírgulas e entre aspas**:
        * **Primeiras colunas:** Geralmente identificam o código do órgão e o tipo de registro/layout.
        * **Colunas centrais:** Costumam abrigar datas (no formato `AAAAMMDD`) e chaves principais (CPFs, CNPJs ou números de processos).
        * **Últimas colunas:** Geralmente traz valores numéricos e a competência de referência (no formato `AAAAMM`).
        
        *Dica de Ouro:* Sempre que o PGI emitir um relatório de ocorrência apontando uma linha, verifique a chave principal para localizar rapidamente o registro duplicado ou incorreto no sistema contábil.
        """)
