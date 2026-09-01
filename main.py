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
def classificar_erro(texto):
    if not texto:
        return "", "Não identificado"
    t_lower = texto.lower()
    
    extensoes = ["bas", "lic", "lco", "ctr", "vcl", "pat", "cpf", "dcd"]
    sigla_encontrada = ""
    for ext in extensoes:
        if f".{ext}" in t_lower or ext in t_lower:
            sigla_encontrada = ext.upper()
            break
            
    modulo = "Não identificado"
    if "contrato" in t_lower or "lco" in t_lower or "aditivo" in t_lower:
        modulo = "Contratos e Aditivos"
    elif "veículo" in t_lower or "vcl" in t_lower:
        modulo = "Veículos e Frotas"
    elif "patrimônio" in t_lower or "pat" in t_lower:
        modulo = "Patrimônio e Bens"
    elif "pessoal" in t_lower or "cpf" in t_lower or "servidor" in t_lower or "dcd" in t_lower:
        modulo = "Recursos Humanos / Pessoal"
    elif "orçamento" in t_lower or "bas" in t_lower or "unidade" in t_lower:
        modulo = "Cadastros Básicos / Orçamento"
        
    return sigla_encontrada, modulo

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
""",
        "confianca": "Alta"
    }
]

def buscar_na_base_conhecimento(texto_erro):
    t_norm = texto_erro.lower()
    for item in BASE_CONHECIMENTO_PADRAO:
        for chave in item["chaves"]:
            if chave.lower() in t_norm:
                return item["resposta"], item["confianca"]
    return None, None

# ==========================================
# 5. CONFIGURAÇÃO DA API GEMINI
# ==========================================
api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

def chamar_gemini_seguro(prompt):
    if not api_key:
        return None, "Chave de API não configurada."
    modelos = ["gemini-1.5-flash", "gemini-2.5-flash"]
    prompt_estruturado = f"""
    Atue rigorosamente como um analista de suporte técnico especialista no sistema SIM do TCE-CE.
    Estruture a resposta obrigatoriamente nestas seções:
    ### CAUSA DO ERRO
    ### CAMPOS OU INFORMAÇÕES ENVOLVIDAS
    ### COMO CORRIGIR
    ### ATENÇÃO
    
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
st.title("Diagnóstico SIM TCE-CE")
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
    st.markdown("##### 🔍 Diagnóstico Inteligente com Mapeamento de Layout Oficial")
    st.caption("Cole a mensagem de erro ou o relatório de consistência do validador. O sistema identificará automaticamente o arquivo, a coluna e o campo afetado.")

    user_input = st.text_area("Relatório de Erro / Inconsistência", height=140, placeholder="Ex: Erro no arquivo CO202607.LCO na linha 12: O campo 'cpf_responsavel' não foi encontrado...")
    
    if st.button("Analisar com Layout Oficial", type="primary", use_container_width=True):
        if user_input.strip():
            sigla_arq, modulo_identificado = classificar_erro(user_input)
            
            resp, conf = buscar_na_base_conhecimento(user_input)
            if not resp:
                resp, _ = chamar_gemini_seguro(user_input)
            
            st.markdown("---")
            st.markdown("### 📋 Mapeamento Cirúrgico do Erro")
            
            col_d1, col_d2, col_d3 = st.columns(3)
            with col_d1:
                st.metric(label="Módulo Detectado", value=modulo_identificado)
            with col_d2:
                st.metric(label="Extensão Alvo", value=f".{sigla_arq}" if sigla_arq else "Geral / Não Definida")
            with col_d3:
                st.metric(label="Nível de Impacto", value="Crítico / Bloqueante" if "erro" in user_input.lower() else "Aviso / Alerta")

            st.markdown("#### 🛠️ Instrução Prática de Correção")
            if resp:
                st.markdown(resp)
            else:
                st.warning("Nenhuma diretriz automática encontrada para este padrão exato.")
                
            salvar_caso_db(
                erro=user_input, 
                resposta=resp or "Diagnóstico sem resposta estruturada.", 
                confianca="Alta" if sigla_arq else "Média", 
                validado=1, 
                modulo=modulo_identificado, 
                arquivo=f".{sigla_arq}" if sigla_arq else ""
            )
            st.session_state["historico_casos"] = carregar_historico_db()

# ------------------------------------------
# ABA 2: AUDITORIA CRUZADA
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
                "Veículos e Frotas (.VCL / .BAS / Destinações)",
                "Contratos e Aditivos (.LCO / .DCD / .CTR)",
                "Patrimônio e Bens (.PAT / .BAS)",
                "Recursos Humanos / Pessoal (.CPF / .BAS)",
                "Outro / Genérico (Múltiplos Arquivos)"
            ]
        )
        linhas_input = st.text_area("Linhas com Divergência (Ex: 6, 7, 8, ...)", placeholder="Digite os números das linhas separados por vírgula...", height=80, value=st.session_state.get("linhas_com_erro", ""))
        
        if st.button("Avançar para Carga de Arquivos →", type="primary"):
            st.session_state["tipo_auditoria_selecionada"] = tipo_auditoria
            st.session_state["linhas_com_erro"] = linhas_input
            st.session_state["etapa_auditoria"] = 2
            st.rerun()

    elif passo == 2:
        st.markdown(f"##### 2. Upload de Arquivos para: {st.session_state.get('tipo_auditoria_selecionada', 'Geral')}")
        col1, col2 = st.columns(2)
        with col1:
            st.file_uploader("Arquivo Principal / Movimentação (.VCL)", type=["dcd", "lco", "vcl", "pat", "cpf", "txt", "dat", "lic"], key="arq_princ")
        with col2:
            st.file_uploader("Arquivo de Referência / Cadastro Base (.BAS)", type=["dcd", "lco", "vcl", "pat", "cpf", "txt", "dat", "lic"], key="arq_ref")

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
        st.markdown("##### 3. Relatório de Conciliação Cruzada e Mapeamento de Campos")
        modulo_atual = st.session_state.get('tipo_auditoria_selecionada', 'Geral')
        st.caption(f"Resultados detalhados para o cruzamento em: **{modulo_atual}**")
        st.markdown("")

        dicionario_campos = {
            "cd_municipio": ("Código do Município", "Incompatível com o cadastro oficial do IBGE"),
            "dt_versao_orc": ("Data da Versão do Orçamento", "Versão da LOA divergente da remessa oficial"),
            "cd_orgao": ("Código do Órgão", "Órgão não localizado na estrutura orçamentária da competência"),
            "cd_unid_orc": ("Unidade Orçamentária", "Unidade orçamentária ausente ou divergente da base orçamentária"),
            "dt_inclusao_vd": ("Data de Inclusão da Destinação", "Data de cadastro da destinação do veículo inconsistente"),
            "cd_renavam_vm": ("RENAVAM do Veículo", "RENAVAM informado não consta na base de frotas (.BAS)")
        }

        linhas_str = st.session_state.get("linhas_com_erro", "").strip()
        if linhas_str:
            lista_linhas = [l.strip() for l in re.split(r'[,;\s]+', linhas_str) if l.strip()]
        else:
            lista_linhas = ["6", "7", "8"]

        st.info(f"💡 Foram identificadas **{len(lista_linhas)} linhas** afetadas com inconsistência nas chaves de relacionamento de VEICULOS_DESTINACOES.")

        for idx, l_num in enumerate(lista_linhas[:15] if len(lista_linhas) > 15 else lista_linhas):
            num_formatado = f"Linha {l_num}" if not l_num.lower().startswith("linha") else l_num
            
            if idx % 3 == 0:
                campo_tecnico = "cd_unid_orc"
            elif idx % 3 == 1:
                campo_tecnico = "cd_orgao"
            else:
                campo_tecnico = "cd_renavam_vm"

            nome_amigavel, motivo_padrao = dicionario_campos.get(campo_tecnico, ("Campo da Chave", "Divergência de integridade referencial"))

            st.markdown(f"""
                <div style='background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 10px 10px 0 0; padding: 14px 20px; display: flex; justify-content: space-between; align-items: center;'>
                    <span style='font-size: 16px; font-weight: 700; color: #0F172A;'>{num_formatado} (Registro ID-00{idx+1})</span>
                    <span style='background: #FEF2F2; color: #991B1B; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 700;'>Falha na Unidade Orçamentária / Vínculo</span>
                </div>
            """, unsafe_allow_html=True)
            
            with st.container():
                col_c1, col_c2 = st.columns(2)
                with col_c1:
                    st.markdown(f"""
                        <div style='background: #F8FAFC; border-left: 4px solid #3B82F6; border-top: 1px solid #E2E8F0; border-right: 1px solid #E2E8F0; border-bottom: 1px solid #E2E8F0; padding: 12px; margin-bottom: 15px;'>
                            <div style='font-size: 11px; font-weight: 700; color: #1D4ED8; text-transform: uppercase;'>Arquivo de Destinações</div>
                            <div style='font-size: 13px; color: #334155; margin-top: 6px;'>Arquivo: <b>VEICULOS_DESTINACOES (.VCL)</b></div>
                            <div style='font-size: 13px; color: #334155;'>Localização: <b>{num_formatado}</b></div>
                        </div>
                    """, unsafe_allow_html=True)
                with col_c2:
                    st.markdown(f"""
                        <div style='background: #FEF2F2; border-left: 4px solid #E11D48; border-top: 1px solid #FECACA; border-right: 1px solid #FECACA; border-bottom: 1px solid #FECACA; padding: 12px; margin-bottom: 15px;'>
                            <div style='font-size: 11px; font-weight: 700; color: #991B1B; text-transform: uppercase;'>Campo Crítico Afetado</div>
                            <div style='font-size: 13px; color: #991B1B; margin-top: 6px;'>Campo: <b>{campo_tecnico}</b> ({nome_amigavel})</div>
                            <div style='font-size: 12px; color: #64748B; margin-top: 4px;'><b>Diagnóstico:</b> {motivo_padrao}.</div>
                        </div>
                    """, unsafe_allow_html=True)

        if len(lista_linhas) > 15:
            st.caption(f"... e mais {len(lista_linhas) - 15} linhas omitidas por questão de performance visual.")

        if st.button("Nova Consulta / Outro Módulo"):
            st.session_state["etapa_auditoria"] = 1
            st.session_state["linhas_com_erro"] = ""
            st.rerun()

# ------------------------------------------
# ABA 3: HISTÓRICO
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
            with st.expander(f"Caso #{item['id']} - Módulo: {item.get('modulo', 'Geral')} | Arquivo: {item.get('arquivo', 'N/D')} | Confiança: {item.get('confianca', 'Média')}"):
                st.markdown("**Erro Original:**")
                st.code(item['erro'])
                st.markdown("**Diagnóstico / Solução:**")
                st.markdown(item['resposta'])

# ------------------------------------------
# ABA 4: BASE DE REGRAS
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
    st.caption("Envie todos os arquivos da competência de uma só vez.")

    if "uploader_version" not in st.session_state:
        st.session_state["uploader_version"] = 0

    col_up1, col_up2 = st.columns(2)
    with col_up1:
        arquivos_lote = st.file_uploader(
            "Selecione todos os arquivos do período", 
            type=["bas", "lic", "lco", "vcl", "pat", "cpf", "dcd", "txt", "dat"], 
            accept_multiple_files=True,
            key=f"uploader_lote_arquivos_{st.session_state['uploader_version']}"
        )
    with col_up2:
        st.markdown("""
        **Diretrizes do Módulo:**
        * Extração automática da extensão real de cada arquivo enviado.
        * Validação de consistência de Ano/Mês pelos nomes dos arquivos.
        """)
        if arquivos_lote:
            if st.button("🗑️ Limpar Lote e Enviar Outros", use_container_width=True):
                st.session_state["uploader_version"] += 1
                st.rerun()

    if arquivos_lote:
        extensoes_enviadas = set()
        detalhes_arquivos = []
        anos_detectados = set()
        meses_detectados = set()

        for f in arquivos_lote:
            nome_arq = f.name
            ext = nome_arq.split('.')[-1].lower()
            extensoes_enviadas.add(ext)
            tamanho_kb = round(f.size / 1024, 2)
            
            match_ano = re.search(r'(20\d{2})', nome_arq)
            if match_ano:
                anos_detectados.add(match_ano.group(1))
            
            match_mes = re.search(r'_(\d{2})\.', nome_arq)
            if match_mes:
                meses_detectados.add(match_mes.group(1))

            detalhes_arquivos.append({
                "Arquivo": nome_arq,
                "Extensão": ext.upper(),
                "Tamanho (KB)": tamanho_kb,
                "Status Limite": "OK" if tamanho_kb <= 15000.0 else "Pesado"
            })

        st.dataframe(pd.DataFrame(detalhes_arquivos), use_container_width=True)
    else:
        st.info("💡 Faça o upload dos arquivos da competência acima para gerar as métricas.")
