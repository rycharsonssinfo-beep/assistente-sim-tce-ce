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
# 1. CONFIGURAÇÃO DA PÁGINA E DESIGN SYSTEM (NOVA IDENTIDADE)
# ==========================================
st.set_page_config(
    page_title="Painel de Auditoria SIM TCE-CE",
    page_icon="🛡️",
    layout="wide"
)

# Estilização CSS renovada (Paleta Emerald / Dark Slate)
st.markdown("""
    <style>
    :root {
        --bg-main: #F8FAFC;
        --surface: #FFFFFF;
        --border-color: #E2E8F0;
        --border-strong: #CBD5E1;
        --text-main: #0F172A;
        --text-muted: #64748B;
        --primary: #059669; /* Verde Esmeralda */
        --primary-hover: #047857;
        --accent-danger: #E11D48;
        --accent-success: #10B981;
    }

    .main {
        background-color: var(--bg-main);
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }

    .block-container {
        padding-top: 1.8rem;
        padding-bottom: 3rem;
        max-width: 1240px;
    }

    /* Títulos e Cabeçalhos */
    h1, h2, h3, h4 {
        color: var(--text-main);
        font-weight: 700;
        letter-spacing: -0.03em;
    }

    /* Abas Customizadas */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: #F1F5F9;
        padding: 6px;
        border-radius: 10px;
        border: 1px solid var(--border-color);
    }
    .stTabs [data-baseweb="tab"] {
        height: 40px;
        background-color: transparent;
        border-radius: 6px;
        color: var(--text-muted);
        font-weight: 600;
        font-size: 13px;
        border: none;
        padding: 0 18px;
    }
    .stTabs [aria-selected="true"] {
        background-color: var(--surface) !important;
        color: var(--primary) !important;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }

    /* Botões */
    .stButton button {
        border-radius: 8px;
        font-weight: 600;
        font-size: 14px;
        border: 1px solid var(--border-strong);
        background-color: var(--surface);
        color: var(--text-main);
        transition: all 0.2s ease;
    }
    .stButton button:hover {
        border-color: var(--primary);
        color: var(--primary);
        background-color: #F0FDF4;
    }

    .stButton button[kind="primary"] {
        background-color: var(--primary);
        color: white;
        border: none;
    }
    .stButton button[kind="primary"]:hover {
        background-color: var(--primary-hover);
        color: white;
        box-shadow: 0 4px 6px -1px rgba(5, 150, 105, 0.3);
    }

    /* Sidebar */
    section[data-testid="stSidebar"] {
        background-color: #F1F5F9;
        border-right: 1px solid var(--border-color);
    }

    /* Cards Personalizados para Auditoria */
    .card-audit {
        background: white;
        border: 1px solid var(--border-color);
        border-radius: 10px;
        padding: 16px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.03);
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
    st.markdown("## 🛡️ SIM Audit")
    st.caption("Painel de Conciliação e Consistência")
    st.markdown("---")
    
    st.markdown("**Status da Base**")
    st.metric(label="Casos em Memória", value=len(st.session_state['historico_casos']))
    
    st.markdown("---")
    st.markdown("**Gestão de Dados**")
    
    dados_json_str = exportar_base_json()
    st.download_button(
        label="Exportar Backup (.JSON)",
        data=dados_json_str,
        file_name="backup_audit_sim_tce.json",
        mime="application/json",
        use_container_width=True
    )
    
    arquivo_submetido = st.file_uploader(
        "Importar Backup", 
        type=["json"]
    )
    
    if arquivo_submetido is not None:
        if st.button("Restaurar Base", use_container_width=True):
            sucesso_imp, qtd_imp = importar_base_json(arquivo_submetido)
            if sucesso_imp:
                st.session_state["historico_casos"] = carregar_historico_db()
                st.success(f"{qtd_imp} caso(s) importado(s)!")
                st.rerun()

# ==========================================
# 8. TELA PRINCIPAL E ABAS
# ==========================================
st.title("Audit & Diagnóstico SIM TCE-CE")
st.markdown("<span style='color: #64748B; font-size: 15px; display: block; margin-top: -10px; margin-bottom: 20px;'>Plataforma unificada para auditoria cruzada de arquivos e diagnóstico rápido de consistência.</span>", unsafe_allow_html=True)

aba1, aba2, aba3, aba4 = st.tabs([
    "🔍 Diagnóstico de Ocorrências", 
    "📊 Auditoria Cruzada",
    "📚 Histórico Registrado", 
    "📖 Base de Regras"
])

# ------------------------------------------
# ABA 1: DIAGNÓSTICO E ENTRADA DE LOGS
# ------------------------------------------
with aba1:
    st.markdown("##### Entrada de Logs e Inconsistências")
    
    col_ex1, col_ex2, col_space = st.columns([1.5, 1.5, 2])
    with col_ex1:
        if st.button("Carregar Exemplo: Veículos", use_container_width=True):
            st.session_state["erro_input"] = (
                "BV202607.VCL - DESTINAÇÃO DE VEÍCULOS\n"
                "Descrição: Não há relação com o(s) campo(s) ( cd_municipio, dt_versao_orc, cd_orgao, cd_unid_orc ) que compõe(m) a chave do arquivo UNIDADES_ORCAMENTARIAS."
            )
    with col_ex2:
        if st.button("Carregar Exemplo: Patrimônio", use_container_width=True):
            st.session_state["erro_input"] = (
                "RP202607.PAT - CONTAS REDUTORAS DOS BENS INCORPORADOS AO PATRIMÔNIO DO MUNICÍPIO\n"
                "Descrição: Não há relação com o(s) campo(s) ( cd_municipio, nu_registro_bem ) que compõe(m) a chave do arquivo BENS_MUNICIPIOS."
            )
    
    user_input = st.text_area(
        "Relatório de Erro",
        value=st.session_state.get("erro_input", ""),
        height=140,
        placeholder="Cole a mensagem de erro fornecida pelo validador do TCE..."
    )

    if user_input.strip():
        sigla_arq, modulo_identificado = classificar_erro(user_input)
        titulo_extraido = extrair_titulo_erro(user_input)
        encontrou_campos = re.findall(r'cd_[a-z_]+|dt_[a-z_]+|nu_[a-z_]+', user_input, re.IGNORECASE)
        
        st.markdown(f"""
            <div style='background: #ECFDF5; border: 1px solid #A7F3D0; padding: 10px 16px; border-radius: 8px; margin-bottom: 15px;'>
                <span style='color: #065F46; font-size: 13px; font-weight: 600;'>Módulo Identificado: {modulo_identificado} ({sigla_arq if sigla_arq else 'Geral'})</span>
                {f" | <span style='color: #047857; font-size: 13px;'>Chaves: {', '.join(set(encontrou_campos[:3]))}</span>" if encontrou_campos else ""}
            </div>
        """, unsafe_allow_html=True)

    if st.button("Analisar Inconsistência", type="primary", use_container_width=True):
        texto_limpo = user_input.strip()
        
        if not texto_limpo:
            st.warning("Insira o texto da ocorrência antes de processar.")
        else:
            sigla_arq, modulo_identificado = classificar_erro(texto_limpo)
            resposta_obtida, confianca_obtida = buscar_na_base_conhecimento(texto_limpo)
            origem_resposta = "Base de Conhecimento"
            
            if not resposta_obtida:
                caso_encontrado, tipo_match, score = buscar_caso_no_historico(texto_limpo)
                if caso_encontrado and (tipo_match in ["Exata", "Validado e Semelhante"] or score >= 0.60):
                    resposta_obtida = caso_encontrado["resposta"]
                    confianca_obtida = caso_encontrado.get("confianca", "Alta")
                    origem_resposta = f"Histórico ({tipo_match})"
            
            if not resposta_obtida:
                with st.spinner("Consultando motor de IA..."):
                    caso_parcial, _, _ = buscar_caso_no_historico(texto_limpo)
                    resp_ia, status_ia = chamar_gemini_seguro(texto_limpo, contexto_anterior=caso_parcial["resposta"] if caso_parcial else None)
                    
                    if resp_ia and status_ia == "Sucesso":
                        resposta_obtida = resp_ia
                        confianca_obtida = "Média"
                        origem_resposta = "Modelos IA"
                        salvar_caso_db(texto_limpo, resposta_obtida, confianca=confianca_obtida, validado=0, modulo=modulo_identificado, arquivo=sigla_arq)
                        st.session_state["historico_casos"] = carregar_historico_db()

            if resposta_obtida:
                st.markdown("---")
                st.markdown(f"### Resultado da Análise (`{origem_resposta}`)")
                st.info(resposta_obtida)

# ------------------------------------------
# ABA 2: AUDITORIA E CONCILIAÇÃO CRUZADA (ETAPAS REDESENHADAS)
# ------------------------------------------
with aba2:
    if "etapa_auditoria" not in st.session_state:
        st.session_state["etapa_auditoria"] = 1

    passo = st.session_state["etapa_auditoria"]
    
    # Barra de Etapas em Estilo Pipeline
    st.markdown(f"""
        <div style='display: flex; gap: 10px; background: #FFFFFF; border: 1px solid #E2E8F0; padding: 12px; border-radius: 10px; margin-bottom: 20px;'>
            <div style='flex: 1; text-align: center; padding: 8px; border-radius: 6px; background: {"#059669" if passo==1 else "#F1F5F9"}; color: {"white" if passo==1 else "#64748B"}; font-weight: 600; font-size: 13px;'>
                Passo 1: Definir Alvos
            </div>
            <div style='flex: 1; text-align: center; padding: 8px; border-radius: 6px; background: {"#059669" if passo==2 else "#F1F5F9"}; color: {"white" if passo==2 else "#64748B"}; font-weight: 600; font-size: 13px;'>
                Passo 2: Enviar Fontes
            </div>
            <div style='flex: 1; text-align: center; padding: 8px; border-radius: 6px; background: {"#059669" if passo==3 else "#F1F5F9"}; color: {"white" if passo==3 else "#64748B"}; font-weight: 600; font-size: 13px;'>
                Passo 3: Relatório Final
            </div>
        </div>
    """, unsafe_allow_html=True)

    # ETAPA 1
    if passo == 1:
        st.markdown("##### 1. Informe as Linhas com Divergência")
        st.caption("Especifique os números das linhas sinalizadas pelo relatório do TCE para direcionar a varredura.")
        
        linhas_input = st.text_area("Seleção de Linhas", placeholder="Exemplo: 10, 15, 22-30", height=100)
        
        if st.button("Avançar para Carga de Arquivos →", type="primary"):
            st.session_state["linhas_com_erro"] = linhas_input
            st.session_state["etapa_auditoria"] = 2
            st.rerun()

    # ETAPA 2
    elif passo == 2:
        st.markdown("##### 2. Upload de Arquivos de Origem e Destino")
        st.caption("Carregue as remessas para execução da auditoria cruzada.")
        
        col1, col2 = st.columns(2)
        with col1:
            st.file_uploader("Arquivo A (.DCD / Remessa)", type=["dcd", "txt", "dat"])
        with col2:
            st.file_uploader("Arquivo B (.LCO / Referência)", type=["lco", "txt", "dat"])

        col_b1, col_b2 = st.columns([1, 4])
        with col_b1:
            if st.button("← Voltar"):
                st.session_state["etapa_auditoria"] = 1
                st.rerun()
        with col_b2:
            if st.button("Executar Conciliação", type="primary"):
                st.session_state["etapa_auditoria"] = 3
                st.rerun()

    # ETAPA 3: DESIGN EXCLUSIVO DE CARDS
    elif passo == 3:
        st.markdown("##### 3. Conciliação por Campo do Registro")
        st.caption("Abaixo estão destacados os campos auditados e a indicação de conformidade.")
        st.markdown("")

        # Registro de Exemplo com Layout em Cards Limpos
        itens_analisados = [
            {
                "linha": "Linha 1",
                "contrato": "09.27.04.26.001",
                "historico_contrato": "09.27.04.26.001",
                "cpf_arquivo": "95991360391",
                "cpf_historico": "AcmPN41eFzWYQ0IVLyjz/g==",
                "status_geral": "Contrato Localizado com Divergência de CPF"
            }
        ]

        for item in itens_analisados:
            # Header do Card Principal
            st.markdown(f"""
                <div style='background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 10px 10px 0 0; padding: 14px 20px; display: flex; justify-content: space-between; align-items: center;'>
                    <span style='font-size: 16px; font-weight: 700; color: #0F172A;'>{item['linha']}</span>
                    <span style='background: #FEF2F2; color: #991B1B; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 700;'>{item['status_geral']}</span>
                </div>
            """, unsafe_allow_html=True)
            
            # Container de Conteúdo Usando Colunas do Streamlit
            with st.container():
                col_c1, col_c2, col_c3 = st.columns(3)
                
                with col_c1:
                    st.markdown("""
                        <div style='background: #F8FAFC; border-left: 4px solid #10B981; border-top: 1px solid #E2E8F0; border-right: 1px solid #E2E8F0; border-bottom: 1px solid #E2E8F0; padding: 12px; margin-bottom: 15px;'>
                            <div style='font-size: 11px; font-weight: 700; color: #059669; text-transform: uppercase;'>NÚMERO DO CONTRATO</div>
                            <div style='font-size: 13px; color: #334155; margin-top: 6px;'>Remessa: <b>09.27.04.26.001</b></div>
                            <div style='font-size: 13px; color: #334155;'>Base SIM: <b>09.27.04.26.001</b></div>
                        </div>
                    """, unsafe_allow_html=True)

                with col_c2:
                    st.markdown("""
                        <div style='background: #FEF2F2; border-left: 4px solid #E11D48; border-top: 1px solid #FECACA; border-right: 1px solid #FECACA; border-bottom: 1px solid #FECACA; padding: 12px; margin-bottom: 15px;'>
                            <div style='font-size: 11px; font-weight: 700; color: #991B1B; text-transform: uppercase;'>CPF DO GESTOR</div>
                            <div style='font-size: 13px; color: #991B1B; margin-top: 6px;'>Remessa: <b>95991360391</b></div>
                            <div style='font-size: 13px; color: #334155;'>Base SIM: <b>AcmPN41eFzWYQ0IVLyjz/g==</b></div>
                        </div>
                    """, unsafe_allow_html=True)

                with col_c3:
                    st.markdown("""
                        <div style='background: #F8FAFC; border-left: 4px solid #10B981; border-top: 1px solid #E2E8F0; border-right: 1px solid #E2E8F0; border-bottom: 1px solid #E2E8F0; padding: 12px; margin-bottom: 15px;'>
                            <div style='font-size: 11px; font-weight: 700; color: #059669; text-transform: uppercase;'>DATA ASSINATURA</div>
                            <div style='font-size: 13px; color: #334155; margin-top: 6px;'>Remessa: <b>27/04/2026</b></div>
                            <div style='font-size: 13px; color: #334155;'>Base SIM: <b>27/04/2026</b></div>
                        </div>
                    """, unsafe_allow_html=True)

        if st.button("Nova Consulta"):
            st.session_state["etapa_auditoria"] = 1
            st.rerun()

# ------------------------------------------
# ABA 3: HISTÓRICO PERMANENTE
# ------------------------------------------
with aba3:
    st.markdown("##### Histórico de Casos Analisados")
    
    termo = st.text_input("Filtrar no Histórico", placeholder="Digite palavras-chave...").lower()
    casos = st.session_state["historico_casos"]
    
    if termo:
        casos = [c for c in casos if termo in c["erro"].lower() or termo in c["resposta"].lower()]
        
    for item in casos:
        with st.expander(f"Caso #{item['id']} - {item.get('modulo', 'Geral')}"):
            st.code(item['erro'])
            st.markdown(item['resposta'])

# ------------------------------------------
# ABA 4: BASE DE REGRAS
# ------------------------------------------
with aba4:
    st.markdown("##### Regras Mapeadas do SIM TCE-CE")
    for reg in BASE_CONHECIMENTO_PADRAO:
        with st.expander(f"📌 {reg['titulo']}"):
            st.markdown(reg['resposta'])
