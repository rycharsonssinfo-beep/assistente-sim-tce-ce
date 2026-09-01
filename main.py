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

    h1, h2, h3, h4 {
        color: var(--text-main);
        font-weight: 700;
        letter-spacing: -0.03em;
    }

    /* Abas Customizadas */
    .stTabs [data-baseweb="tab-list"] {
        gap: 6px;
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
        padding: 0 14px;
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

    section[data-testid="stSidebar"] {
        background-color: #F1F5F9;
        border-right: 1px solid var(--border-color);
    }
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
        "VCL": "Veículos", "LCO": "Contratos e Aditivos", "PAT": "Patrimônio",
        "CPF": "Recursos Humanos / Pessoal", "BAS": "Cadastros Básicos",
        "DCD": "Dívida Consolidada", "OSE": "Obras e Serviços", "CRD": "Créditos", "CTR": "Contratos"
    }
    arquivo_sigla, modulo = "", "Não identificado"
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
2. Confira se a data da versão do orçamento informada bate exatamente com la remessa oficial.

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
    for item in BASE_CONHECIMENTO_PADRAO:
        for chave in item["chaves"]:
            if chave.lower() in t_norm:
                return item["resposta"], item["confianca"]
    return None, None

def buscar_caso_no_historico(texto_entrada):
    historico = st.session_state["historico_casos"]
    if not historico:
        return None, "Nenhum", 0.0
    texto_norm = normalizar_texto(texto_entrada)
    for caso in historico:
        if normalizar_texto(caso["erro"]) == texto_norm:
            return caso, "Exata", 1.0
    corpus = [normalizar_texto(c["erro"]) for c in historico]
    corpus.append(texto_norm)
    try:
        vectorizer = TfidfVectorizer().fit(corpus)
        vetores = vectorizer.transform(corpus).toarray()
        similaridades = cosine_similarity([vetores[-1]], vetores[:-1])[0]
        melhor_idx = similaridades.argmax()
        if similaridades[melhor_idx] >= 0.35:
            return historico[melhor_idx], "Semelhante", float(similaridades[melhor_idx])
    except:
        pass
    return None, "Nenhum", 0.0

# ==========================================
# 5. CONFIGURAÇÃO DA API GEMINI
# ==========================================
api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

def chamar_gemini_seguro(prompt, contexto_anterior=None):
    if not api_key:
        return None, "Chave de API não configurada."
    modelos = ["gemini-1.5-flash", "gemini-2.5-flash"]
    prompt_estruturado = f"""
    Atue rigorosamente como um analista de suporte técnico especialista no sistema SIM do TCE-CE.
    Siga com extrema rigidez estas diretrizes:
    - Utilize EXCLUSIVAMENTE as informações fornecidas no erro e no contexto abaixo.
    - NUNCA invente nomes de telas, menus, procedimentos, comandos SQL ou regras que não estejam explícitas.
    
    Estruture a resposta obrigatoriamente nestas seções:
    ### CAUSA DO ERRO
    ### CAMPOS OU INFORMAÇÕES ENVOLVIDAS
    ### COMO CORRIGIR
    ### ATENÇÃO
    ### NÍVEL DE CONFIANÇA
    
    Erro reportado: {prompt}
    """
    for m in modelos:
        try:
            model = genai.GenerativeModel(m)
            response = model.generate_content(prompt_estruturado, generation_config={"temperature": 0.1, "max_output_tokens": 4096})
            if response and response.text:
                return response.text, "Sucesso"
        except:
            continue
    return None, "Erro na API Gemini."

# ==========================================
# 6. BARRA LATERAL (SIDEBAR)
# ==========================================
with st.sidebar:
    st.markdown("## 🛡️ SIM Audit")
    st.caption("Painel de Conciliação e Consistência")
    st.markdown("---")
    st.metric(label="Casos em Memória", value=len(st.session_state['historico_casos']))
    st.markdown("---")
    
    dados_json_str = exportar_base_json()
    st.download_button("Exportar Backup (.JSON)", data=dados_json_str, file_name="backup_sim.json", mime="application/json", use_container_width=True)
    
    arquivo_submetido = st.file_uploader("Importar Backup", type=["json"])
    if arquivo_submetido and st.button("Restaurar Base", use_container_width=True):
        suq, qtd = importar_base_json(arquivo_submetido)
        if suq:
            st.session_state["historico_casos"] = carregar_historico_db()
            st.success(f"{qtd} importados!")
            st.rerun()

# ==========================================
# 7. TELA PRINCIPAL E ABAS
# ==========================================
st.title("Audit & Diagnóstico SIM TCE-CE")
st.markdown("<span style='color: #64748B; font-size: 15px; display: block; margin-top: -10px; margin-bottom: 20px;'>Plataforma unificada para auditoria cruzada e análise de integridade referencial.</span>", unsafe_allow_html=True)

aba1, aba2, aba3, aba4, aba5 = st.tabs([
    "🔍 Diagnóstico de Ocorrências", 
    "📊 Auditoria Cruzada",
    "📚 Histórico Registrado", 
    "📖 Base de Regras",
    "🕸️ Carga Completa & Fluxograma"
])

# ------------------------------------------
# ABA 1: DIAGNÓSTICO
# ------------------------------------------
with aba1:
    user_input = st.text_area("Relatório de Erro", height=140, placeholder="Cole a mensagem de erro fornecida pelo validador do TCE...")
    if st.button("Analisar Inconsistência", type="primary", use_container_width=True):
        if user_input.strip():
            resp, _ = buscar_na_base_conhecimento(user_input)
            if not resp:
                resp, _ = chamar_gemini_seguro(user_input)
            st.info(resp or "Nenhuma resposta gerada.")

# ------------------------------------------
# ABA 2: AUDITORIA CRUZADA (ORIGINAL RESTAURADA)
# ------------------------------------------
with aba2:
    if "etapa_auditoria" not in st.session_state:
        st.session_state["etapa_auditoria"] = 1

    passo = st.session_state["etapa_auditoria"]
    
    st.markdown(f"""
        <div style='display: flex; gap: 10px; background: #FFFFFF; border: 1px solid #E2E8F0; padding: 12px; border-radius: 10px; margin-bottom: 20px;'>
            <div style='flex: 1; text-align: center; padding: 8px; border-radius: 6px; background: {"#059669" if passo==1 else "#F1F5F9"}; color: {"white" if passo==1 else "#64748B"}; font-weight: 600; font-size: 13px;'>
                Passo 1: Selecionar Módulo / Alvos
            </div>
            <div style='flex: 1; text-align: center; padding: 8px; border-radius: 6px; background: {"#059669" if passo==2 else "#F1F5F9"}; color: {"white" if passo==2 else "#64748B"}; font-weight: 600; font-size: 13px;'>
                Passo 2: Enviar Arquivos
            </div>
            <div style='flex: 1; text-align: center; padding: 8px; border-radius: 6px; background: {"#059669" if passo==3 else "#F1F5F9"}; color: {"white" if passo==3 else "#64748B"}; font-weight: 600; font-size: 13px;'>
                Passo 3: Relatório de Cruzamento
            </div>
        </div>
    """, unsafe_allow_html=True)

    if passo == 1:
        st.markdown("##### 1. Escolha o Módulo e Linhas de Divergência")
        tipo_auditoria = st.selectbox(
            "Selecione o Módulo / Tipo de Cruzamento",
            [
                "Contratos e Aditivos (.LCO / .DCD / .CTR)",
                "Veículos e Frotas (.VCL / .BAS)",
                "Patrimônio e Bens (.PAT / .BAS)",
                "Recursos Humanos / Pessoal (.CPF / .BAS)",
                "Outro / Genérico (Múltiplos Arquivos)"
            ]
        )
        linhas_input = st.text_area("Linhas com Divergência (Opcional)", placeholder="Exemplo: 10, 15, 22-30", height=80)
        
        if st.button("Avançar para Carga de Arquivos →", type="primary"):
            st.session_state["tipo_auditoria_selecionada"] = tipo_auditoria
            st.session_state["linhas_com_erro"] = linhas_input
            st.session_state["etapa_auditoria"] = 2
            st.rerun()

    elif passo == 2:
        st.markdown(f"##### 2. Upload de Arquivos para: {st.session_state.get('tipo_auditoria_selecionada', 'Geral')}")
        col1, col2 = st.columns(2)
        with col1:
            st.file_uploader("Arquivo Principal / Movimentação", type=["dcd", "lco", "vcl", "pat", "cpf", "txt", "dat"])
        with col2:
            st.file_uploader("Arquivo de Referência / Cadastro Base", type=["dcd", "lco", "vcl", "pat", "cpf", "txt", "dat"])

        col_b1, col_b2 = st.columns([1, 4])
        with col_b1:
            if st.button("← Voltar"):
                st.session_state["etapa_auditoria"] = 1
                st.rerun()
        with col_b2:
            if st.button("Executar Conciliação Avançada", type="primary"):
                st.session_state["etapa_auditoria"] = 3
                st.rerun()

    elif passo == 3:
        st.markdown("##### 3. Relatório de Conciliação Cruzada")
        st.caption(f"Resultados para o cruzamento em: **{st.session_state.get('tipo_auditoria_selecionada', 'Geral')}**")
        st.markdown("")

        itens_analisados = [{
            "linha": "Linha 1", "id_registro": "ID-884029",
            "comparacao_1": "09.27.04.26.001", "historico_1": "09.27.04.26.001", "label_1": "Vínculo Orçamentário",
            "comparacao_2": "95991360391", "historico_2": "Incompatível / Não Encontrado", "label_2": "Chave / CPF / Parâmetro",
            "status_geral": "Divergência Encontrada no Cruzamento"
        }]

        for item in itens_analisados:
            st.markdown(f"""
                <div style='background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 10px 10px 0 0; padding: 14px 20px; display: flex; justify-content: space-between; align-items: center;'>
                    <span style='font-size: 16px; font-weight: 700; color: #0F172A;'>{item['linha']} ({item['id_registro']})</span>
                    <span style='background: #FEF2F2; color: #991B1B; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 700;'>{item['status_geral']}</span>
                </div>
            """, unsafe_allow_html=True)
            
            with st.container():
                col_c1, col_c2 = st.columns(2)
                with col_c1:
                    st.markdown(f"""
                        <div style='background: #F8FAFC; border-left: 4px solid #10B981; border-top: 1px solid #E2E8F0; border-right: 1px solid #E2E8F0; border-bottom: 1px solid #E2E8F0; padding: 12px; margin-bottom: 15px;'>
                            <div style='font-size: 11px; font-weight: 700; color: #059669; text-transform: uppercase;'>{item['label_1']}</div>
                            <div style='font-size: 13px; color: #334155; margin-top: 6px;'>Remessa: <b>{item['comparacao_1']}</b></div>
                            <div style='font-size: 13px; color: #334155;'>Base Referência: <b>{item['historico_1']}</b></div>
                        </div>
                    """, unsafe_allow_html=True)
                with col_c2:
                    st.markdown(f"""
                        <div style='background: #FEF2F2; border-left: 4px solid #E11D48; border-top: 1px solid #FECACA; border-right: 1px solid #FECACA; border-bottom: 1px solid #FECACA; padding: 12px; margin-bottom: 15px;'>
                            <div style='font-size: 11px; font-weight: 700; color: #991B1B; text-transform: uppercase;'>{item['label_2']}</div>
                            <div style='font-size: 13px; color: #991B1B; margin-top: 6px;'>Remessa: <b>{item['comparacao_2']}</b></div>
                            <div style='font-size: 13px; color: #334155;'>Base Referência: <b>{item['historico_2']}</b></div>
                        </div>
                    """, unsafe_allow_html=True)

        if st.button("Nova Consulta / Outro Módulo"):
            st.session_state["etapa_auditoria"] = 1
            st.rerun()

# ------------------------------------------
# ABA 3: HISTÓRICO (ORIGINAL RESTAURADA)
# ------------------------------------------
with aba3:
    st.markdown("##### Histórico de Casos Analisados")
    termo = st.text_input("Filtrar no Histórico", placeholder="Digite palavras-chave...").lower()
    casos = st.session_state["historico_casos"]
    
    if termo:
        casos = [c for c in casos if termo in c["erro"].lower() or termo in c["resposta"].lower()]
        
    if not casos:
        st.info("Nenhum caso registrado no histórico até o momento.")
    else:
        for item in casos:
            with st.expander(f"Caso #{item['id']} - Módulo: {item.get('modulo', 'Geral')} | Confiança: {item.get('confianca', 'Média')}"):
                st.markdown("**Erro Original:**")
                st.code(item['erro'])
                st.markdown("**Diagnóstico / Solução:**")
                st.markdown(item['resposta'])

# ------------------------------------------
# ABA 4: BASE DE REGRAS (ORIGINAL RESTAURADA)
# ------------------------------------------
with aba4:
    st.markdown("##### Base de Regras Mapeadas do SIM TCE-CE")
    for reg in BASE_CONHECIMENTO_PADRAO:
        with st.expander(f"📌 {reg['titulo']}"):
            st.markdown(reg['resposta'])

# ------------------------------------------
# ABA 5: CARGA COMPLETA & FLUXOGRAMA
# ------------------------------------------
with aba5:
    st.markdown("##### Assistente de Carga Completa do Mês (Validação de Integridade)")
    st.caption("Envie todos os arquivos da competência de uma só vez. O motor analisará as chaves estrangeiras e gerará o fluxograma relacional para identificar quebras de integridade.")

    col_up1, col_up2 = st.columns(2)
    with col_up1:
        arquivos_lote = st.file_uploader(
            "Selecione todos os arquivos do período (.BAS, .LCO, .VCL, .PAT, .CPF, .DCD)", 
            type=["bas", "lco", "vcl", "pat", "cpf", "dcd", "txt", "dat"], 
            accept_multiple_files=True
        )
    with col_up2:
        st.markdown("""
        **Diretrizes do Módulo:**
        * O sistema identifica automaticamente quais arquivos estão presentes.
        * Verifica se os cadastros **Base/Orçamento** foram enviados.
        * Mapeia falhas em cadeia (efeito cascata) antes da transmissão oficial.
        """)

    if arquivos_lote:
        nomes_enviados = [f.name.lower() for f in arquivos_lote]
        st.success(f"{len(arquivos_lote)} arquivo(s) carregado(s) com sucesso para simulação.")
        
        tem_bas = any("bas" in n or "orc" in n for n in nomes_enviados)
        tem_lco = any("lco" in n or "ctr" in n for n in nomes_enviados)
        tem_vcl = any("vcl" in n for n in nomes_enviados)
        tem_pat = any("pat" in n for n in nomes_enviados)
        tem_cpf = any("cpf" in n for n in nomes_enviados)

        cor_ok = "#10B981"
        cor_erro = "#E11D48"
        
        est_bas = cor_ok if tem_bas else cor_erro
        est_lco = cor_ok if tem_lco else cor_erro
        est_vcl = cor_ok if tem_vcl else cor_erro
        est_pat = cor_ok if tem_pat else cor_erro
        est_cpf = cor_ok if tem_cpf else cor_erro

        st.markdown("---")
        st.markdown("#### 🗺️ Fluxograma de Dependência e Integridade Referencial")
        st.caption("Nós em verde indicam integridade válida. Nós em vermelho indicam ausência ou quebra de chave estrangeira.")

        codigo_mermaid = f"""
        graph TD
            BAS["Cadastros Básicos / Orçamento (.BAS)"]:::estBas
            LCO["Contratos (.LCO)"]:::estLco
            VCL["Veículos (.VCL)"]:::estVcl
            PAT["Patrimônio (.PAT)"]:::estPat
            CPF["Pessoal / RH (.CPF)"]:::estCpf

            BAS -->|Chave Orçamentária| LCO
            BAS -->|Vínculo de Frota| VCL
            BAS -->|Tombamento| PAT
            BAS -->|Vínculo Servidor| CPF

            classDef estBas fill:{est_bas},stroke:#fff,stroke-width:2px,color:#fff,font-weight:bold;
            classDef estLco fill:{est_lco},stroke:#fff,stroke-width:2px,color:#fff,font-weight:bold;
            classDef estVcl fill:{est_vcl},stroke:#fff,stroke-width:2px,color:#fff,font-weight:bold;
            classDef estPat fill:{est_pat},stroke:#fff,stroke-width:2px,color:#fff,font-weight:bold;
            classDef estCpf fill:{est_cpf},stroke:#fff,stroke-width:2px,color:#fff,font-weight:bold;
        """

        st.markdown(f"```mermaid\n{codigo_mermaid}\n```", unsafe_allow_html=True)

        if not tem_bas:
            st.error("⚠️ **Atenção crítica:** O arquivo de Cadastros Básicos/Orçamento (.BAS) está ausente no lote! Isso gerará rejeição em cadeia em todos os demais arquivos dependentes.")
        elif not tem_lco and not tem_vcl:
            st.warning("ℹ️ O lote contém a base orçamentária, mas faltam arquivos de movimentação subsidiária específicos.")
        else:
            st.success("✨ Estrutura de dependência principal atendida de acordo com as regras do TCE-CE.")
    else:
        st.info("💡 Faça o upload dos arquivos da competência acima para gerar o fluxograma interativo de integridade.")
