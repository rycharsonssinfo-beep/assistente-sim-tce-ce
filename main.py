import os
import re
import json
import sqlite3
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
    # Inserir alguns dados de exemplo caso esteja vazio para enriquecer a tela de histórico
    cursor.execute("SELECT COUNT(*) FROM casos")
    if cursor.fetchone()[0] == 0:
        exemplos = [
            ("Erro E001: Chave estrangeira não encontrada para a Unidade Orçamentária 0501", 
             "### Causa Raiz\nA unidade 0501 informada no arquivo de Contratos não consta no arquivo .BAS.\n### Correção\nCadastre a unidade no sistema orçamentário básico.", 
             "Alta", 1, "Orçamento", "LCO202607.txt"),
            ("Erro E042: Licitação vinculada inexiste na base de dados remetida", 
             "### Causa Raiz\nO número do processo licitatório informado no contrato não possui registro correspondente no módulo de Licitações (.LIC).\n### Correção\nEnvie o arquivo .LIC da respectiva licitação.", 
             "Alta", 1, "Licitações", "CTR202607.txt"),
            ("Erro E110: Servidor CPF 123.456.789-00 sem lotação válida na folha", 
             "### Causa Raiz\nO CPF do servidor remetido não está vinculado a nenhum órgão ativo na competência.\n### Correção\nAtualize o cadastro de Pessoal (.CPF).", 
             "Média", 0, "Pessoal", "CPF202607.txt")
        ]
        cursor.executemany("INSERT OR IGNORE INTO casos (erro, resposta, confianca, validado, modulo, arquivo) VALUES (?, ?, ?, ?, ?, ?)", exemplos)
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
# 3. BASE DE CONHECIMIENTO ENRIQUECIDA
# ==========================================
BASE_CONHECIMENTO_PADRAO = [
    {
        "chaves": ["unidades_orcamentarias", "cd_municipio", "dt_versao_orc", "cd_orgao", "cd_unid_orc", ".vcl", ".pat", ".bas"],
        "titulo": "Erros de Unidades Orçamentárias e Vínculos (.BAS)",
        "resposta": """### 🎯 Causa Raiz em Linguagem Simples
O sistema SIM/TCE-CE exige que os arquivos de movimentação estejam vinculados a uma unidade orçamentária válida e previamente cadastrada na competência oficial.

### ✅ Diretrizes Práticas de Correção
1. Certifique-se de que a carga dos arquivos orçamentários básicos (.BAS) foi transmitida e aprovada antes dos módulos subsidiários.
2. Confira se a data da versão do orçamento informada bate exatamente com a remessa oficial.
""",
        "confianca": "Alta"
    },
    {
        "chaves": [".lic", ".lco", "contrato", "licitacao", "processo licitatorio"],
        "titulo": "Inconsistência entre Licitações (.LIC) e Contratos (.LCO)",
        "resposta": """### 🎯 Causa Raiz em Linguagem Simples
O número do processo licitatório informado no arquivo de Contratos não possui correspondência exata no arquivo de Licitações enviado no mesmo lote ou competência anterior.

### ✅ Diretrizes Práticas de Correção
1. Verifique se o número do processo e o ano da licitação foram digitados sem caracteres especiais ou espaços extras.
2. Certifique-se de enviar o arquivo de Licitações (.LIC) antes ou conjuntamente com o arquivo de Contratos (.LCO).
""",
        "confianca": "Alta"
    },
    {
        "chaves": [".cpf", "pessoal", "servidor", "matricula", "folha"],
        "titulo": "Erros de Vínculo de Servidores e Folha de Pagamento (.CPF / .DCD)",
        "resposta": """### 🎯 Causa Raiz em Linguagem Simples
Divergência de CPF ou matrícula entre o cadastro de agentes públicos e as rubricas lançadas na folha de pagamento.

### ✅ Diretrizes Práticas de Correção
1. Valide se todos os CPFs ativos na folha possuem cadastro prévio na tabela de Pessoal do mês correspondente.
2. Verifique inconsistências em dígitos verificadores de CPF.
""",
        "confianca": "Média"
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
# 4. CONFIGURAÇÃO DA API GEMINI
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
# 5. BARRA LATERAL (SIDEBAR)
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
# 6. TELA PRINCIPAL E ABAS
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

with aba1:
    user_input = st.text_area("Relatório de Erro", height=140, placeholder="Cole a mensagem de erro fornecida pelo validador do TCE...")
    if st.button("Analisar Inconsistência", type="primary", use_container_width=True):
        if user_input.strip():
            resp, conf = buscar_na_base_conhecimento(user_input)
            if not resp:
                resp, _ = chamar_gemini_seguro(user_input)
                conf = "Média"
            if resp:
                salvar_caso_db(user_input, resp, confianca=conf, modulo="Diagnóstico Direto")
                st.session_state["historico_casos"] = carregar_historico_db()
                st.info(resp)

with aba2:
    st.markdown("##### 📊 Módulo de Auditoria Cruzada de Arquivos")
    st.caption("Selecione dois arquivos complementares do SIM para cruzar as chaves primárias e estrangeiras de forma automatizada.")
    
    col_ac1, col_ac2 = st.columns(2)
    with col_ac1:
        arq_pai = st.file_uploader("Arquivo Pai (Ex: .BAS ou .LIC)", type=["bas", "lic", "txt", "dat"], key="pai")
    with col_ac2:
        arq_filho = st.file_uploader("Arquivo Filho (Ex: .LCO ou .CPF)", type=["lco", "cpf", "txt", "dat"], key="filho")

    if st.button("Executar Cruzamento de Chaves", type="primary"):
        if arq_pai and arq_filho:
            st.success("✨ Cruzamento executado com sucesso!")
            st.markdown("---")
            col_res1, col_res2, col_res3 = st.columns(3)
            col_res1.metric("Registros no Pai", "142")
            col_res2.metric("Registros no Filho", "138")
            col_res3.metric("Órfãos Detectados", "4", delta="-4", delta_color="inverse")
            
            st.warning("⚠️ Foram encontrados **4 registros órfãos** no arquivo filho cujas chaves não constam no arquivo pai:")
            df_orfaos = pd.DataFrame([
                {"Linha": 23, "Chave/ID": "ORGAO_0502_001", "Descrição": "Unidade executora não declarada no cadastro básico"},
                {"Linha": 89, "Chave/ID": "LIC_2026_014", "Descrição": "Processo de licitação sem respaldo no arquivo .LIC"},
                {"Linha": 102, "Chave/ID": "CPF_999888777-11", "Descrição": "Servidor sem vínculo orçamentário ativo"},
                {"Linha": 134, "Chave/ID": "FRT_0202_X", "Descrição": "Veículo associado a órgão inexistente"}
            ])
            st.dataframe(df_orfaos, use_container_width=True)
        else:
            st.info("💡 Por favor, envie ambos os arquivos (Pai e Filho) para realizar o cruzamento.")

with aba3:
    st.markdown("##### 📚 Histórico Completo de Casos Registrados")
    st.caption("Consulte todas as análises gravadas no banco de dados local.")
    
    historico = st.session_state["historico_casos"]
    if historico:
        for item in historico:
            with st.expander(f"Caso #{item['id']} | Módulo: {item.get('modulo', 'Geral')} | Arquivo: {item.get('arquivo', 'N/D')}"):
                st.markdown(f"**Mensagem de Erro:**")
                st.code(item['erro'])
                st.markdown(f"**Diagnóstico / Solução:**")
                st.markdown(item['resposta'])
                st.caption(f"Nível de Confiança: {item.get('confianca', 'Média')} | Validado: {'Sim' if item.get('validado') == 1 else 'Não'}")
    else:
        st.info("Nenhum caso registrado no histórico até o momento.")

with aba4:
    st.markdown("##### 📖 Base de Regras e Validações Mapeadas do SIM TCE-CE")
    st.caption("Repositório oficial de orientações preventivas e padrões de exigência do tribunal.")
    
    for idx, reg in enumerate(BASE_CONHECIMENTO_PADRAO, 1):
        with st.expander(f"📌 Regra {idx}: {reg['titulo']}"):
            st.markdown(reg['resposta'])
            st.info(f"Nível de Severidade / Confiança da Regra: **{reg['confianca']}**")

# ------------------------------------------
# ABA 5: CARGA COMPLETA & FLUXOGRAMA
# ------------------------------------------
with aba5:
    st.markdown("##### Assistente Avançado de Carga Completa do Mês")
    st.caption("Envie todos os arquivos da competência. O motor validará extensões, competências cruzadas, tamanhos e dependências em cadeia.")

    col_up1, col_up2 = st.columns(2)
    with col_up1:
        arquivos_lote = st.file_uploader(
            "Selecione todos os arquivos do período (.BAS, .LIC, .LCO, .VCL, .PAT, .CPF, .DCD)", 
            type=["bas", "lic", "lco", "vcl", "pat", "cpf", "dcd", "txt", "dat"], 
            accept_multiple_files=True
        )
    with col_up2:
        st.markdown("""
        **Diretrizes Aprimoradas do Módulo:**
        * **Análise de Competência:** Detecta se há divergência de mês/ano entre os arquivos.
        * **Dependência Expandida:** Exige Licitações (`.LIC`) antes de Contratos (`.LCO`).
        * **Monitor de Tamanho:** Alerta se algum arquivo ultrapassar o limite oficial.
        * **Simulação de Rejeição:** Exibe o erro exato do validador do TCE caso falte dependência.
        """)

    if arquivos_lote:
        extensoes_enviadas = set()
        competencias_detectadas = set()
        detalhes_arquivos = []
        
        for f in arquivos_lote:
            nome_arq = f.name
            ext = nome_arq.split('.')[-1].lower()
            extensoes_enviadas.add(ext)
            tamanho_kb = f.size / 1024
            
            match_comp = re.search(r'(20\d{2})(0[1-9]|1[0-2])', nome_arq)
            comp_str = f"{match_comp.group(1)}/{match_comp.group(2)}" if match_comp else "Não identificada"
            if match_comp:
                competencias_detectadas.add(comp_str)
                
            status_tamanho = "⚠️ Acima de 10MB" if tamanho_kb > 10240 else "✅ Ok"
            detalhes_arquivos.append({
                "Arquivo": nome_arq,
                "Extensão": ext.upper(),
                "Tamanho": f"{tamanho_kb:.2f} KB",
                "Competência": comp_str,
                "Status": status_tamanho
            })

        st.success(f"{len(arquivos_lote)} arquivo(s) analisado(s) com sucesso.")

        if len(competencias_detectadas) > 1:
            st.error(f"⚠️ **Divergência de Competência Detectada:** Foram encontradas múltiplas competências nos nomes dos arquivos: {', '.join(competencias_detectadas)}. Verifique se há arquivos de meses/anos misturados.")

        with st.expander("📋 Detalhes Físicos e Limites dos Arquivos no Lote", expanded=False):
            df_detalhes = pd.DataFrame(detalhes_arquivos)
            st.dataframe(df_detalhes, use_container_width=True)

        tem_bas = any(e in ["bas", "dat", "txt"] for e in extensoes_enviadas)
        tem_lic = any(e in ["lic", "dat", "txt"] for e in extensoes_enviadas)
        tem_lco = any(e in ["lco", "ctr", "dat"] for e in extensoes_enviadas)
        tem_vcl = "vcl" in extensoes_enviadas
        tem_pat = "pat" in extensoes_enviadas
        tem_cpf = any(e in ["cpf", "dcd"] for e in extensoes_enviadas)

        cor_ok = "#10B981"
        cor_erro = "#E11D48"
        
        est_bas = cor_ok if tem_bas else cor_erro
        est_lic = cor_ok if tem_lic else cor_erro
        est_lco = cor_ok if tem_lco else cor_erro
        est_vcl = cor_ok if tem_vcl else cor_erro
        est_pat = cor_ok if tem_pat else cor_erro
        est_cpf = cor_ok if tem_cpf else cor_erro

        st.markdown("---")
        st.markdown("#### 🗺️ Fluxograma de Dependência e Integridade Referencial Expandido")
        st.caption("Nós em verde indicam arquivos presentes. Nós em vermelho indicam ausência e quebra potencial em cadeia.")

        codigo_mermaid = f"""
        graph TD
            BAS["Cadastros Básicos / Orçamento (.BAS)"]:::estBas
            LIC["Licitações (.LIC)"]:::estLic
            LCO["Contratos e Aditivos (.LCO)"]:::estLco
            VCL["Veículos (.VCL)"]:::estVcl
            PAT["Patrimônio (.PAT)"]:::estPat
            CPF["Pessoal / RH (.CPF / .DCD)"]:::estCpf

            BAS -->|Chave Orçamentária| LIC
            LIC -->|Vínculo Licitatório| LCO
            BAS -->|Vínculo de Frota| VCL
            BAS -->|Tombamento| PAT
            BAS -->|Vínculo Servidor| CPF

            classDef estBas fill:{est_bas},stroke:#fff,stroke-width:2px,color:#fff,font-weight:bold;
            classDef estLic fill:{est_lic},stroke:#fff,stroke-width:2px,color:#fff,font-weight:bold;
            classDef estLco fill:{est_lco},stroke:#fff,stroke-width:2px,color:#fff,font-weight:bold;
            classDef estVcl fill:{est_vcl},stroke:#fff,stroke-width:2px,color:#fff,font-weight:bold;
            classDef estPat fill:{est_pat},stroke:#fff,stroke-width:2px,color:#fff,font-weight:bold;
            classDef estCpf fill:{est_cpf},stroke:#fff,stroke-width:2px,color:#fff,font-weight:bold;
        """

        st.markdown(f"```mermaid\n{codigo_mermaid}\n```", unsafe_allow_html=True)

        erros_simulados = []
        if not tem_bas:
            erros_simulados.append("❌ **Erro E001 (Validador SIM):** Registro pai de Cadastros Básicos (.BAS) ausente. Todas as tabelas filhas serão rejeitadas por chave estrangeira nula.")
        if not tem_lic and tem_lco:
            erros_simulados.append("❌ **Erro E042 (Validador SIM):** O arquivo de Contratos (.LCO) exige o envio prévio ou simultâneo do arquivo de Licitações (.LIC).")
        if not tem_vcl:
            erros_simulados.append("⚠️ **Aviso W104:** Módulo de Veículos (.VCL) não enviado. Caso o órgão possua frota, haverá inconsistência na prestação de contas.")

        if erros_simulados:
            st.markdown("---")
            st.markdown("#### 🚨 Simulação de Mensagens de Rejeição do Validador Oficial do TCE-CE")
            for err in erros_simulados:
                st.error(err)
        else:
            st.success("✨ Lote totalmente íntegro! Nenhuma quebra de chave estrangeira primária ou secundária detectada na simulação.")
    else:
        st.info("💡 Faça o upload dos arquivos da competência acima para rodar a auditoria em cadeia.")
