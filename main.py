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
# 1. CONFIGURAÇÃO DA PÁGINA E DESIGN SYSTEM (CSS)
# ==========================================
st.set_page_config(
    page_title="Assistente SIM TCE-CE",
    page_icon="⚖️",
    layout="wide"
)

st.markdown("""
    <style>
    /* Cores Globais e Tipografia Base */
    :root {
        --bg-main: #F8FAFC;
        --surface: #FFFFFF;
        --border-subtle: #E2E8F0;
        --text-main: #0F172A;
        --text-secondary: #475569;
        --text-muted: #64748B;
        --primary: #0284C7;
        --primary-hover: #0369A1;
    }

    .main {
        background-color: var(--bg-main);
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }

    /* Ocultar elementos padrão excessivos do Streamlit se necessário, mantendo a limpeza */
    .block-container {
        padding-top: 2rem;
        padding-bottom: 3rem;
        max-width: 1200px;
    }

    /* Tipografia e Cabeçalhos */
    h1, h2, h3 {
        color: var(--text-main);
        font-weight: 600;
        letter-spacing: -0.025em;
    }
    
    /* Estilização Moderna de Abas (Tabs) */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: transparent;
        border-bottom: 1px solid var(--border-subtle);
        padding-bottom: 0px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 42px;
        background-color: transparent;
        border-radius: 6px 6px 0 0;
        color: var(--text-secondary);
        font-weight: 500;
        font-size: 14px;
        border: none;
        padding: 0 16px;
    }
    .stTabs [aria-selected="true"] {
        background-color: var(--surface) !important;
        color: var(--primary) !important;
        border: 1px solid var(--border-subtle);
        border-bottom: 1px solid var(--surface);
        font-weight: 600;
    }

    /* Cartões e Containers Sutis */
    .element-container, .stMarkdown {
        color: var(--text-main);
    }

    /* Botões Principais e Secundários */
    .stButton button {
        border-radius: 6px;
        font-weight: 500;
        font-size: 14px;
        transition: all 0.15s ease;
    }

    /* Ajustes finos em Inputs e Textareas */
    .stTextArea textarea, .stTextInput input {
        border-radius: 6px !important;
        border-color: var(--border-subtle) !important;
        background-color: var(--surface) !important;
        color: var(--text-main) !important;
    }
    .stTextArea textarea:focus, .stTextInput input:focus {
        border-color: var(--primary) !important;
        box-shadow: 0 0 0 1px var(--primary) !important;
    }

    /* Sidebar Profissional e Discreta */
    section[data-testid="stSidebar"] {
        background-color: #F1F5F9;
        border-right: 1px solid var(--border-subtle);
    }
    section[data-testid="stSidebar"] .block-container {
        padding-top: 1.5rem;
    }

    /* Expander Moderno */
    div[data-testid="stExpander"] {
        background-color: var(--surface);
        border: 1px solid var(--border-subtle);
        border-radius: 6px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.02);
    }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. PERSISTÊNCIA ROBUSTA (SQLITE + FEEDBACK)
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
            feedback INTEGER DEFAULT 0
        )
    """)
    cursor.execute("PRAGMA table_info(casos)")
    colunas = [col[1] for col in cursor.fetchall()]
    if "feedback" not in colunas:
        cursor.execute("ALTER TABLE casos ADD COLUMN feedback INTEGER DEFAULT 0")
    conn.commit()
    conn.close()

def carregar_historico_db():
    inicializar_banco()
    conn = sqlite3.connect(NOME_BANCO)
    cursor = conn.cursor()
    cursor.execute("SELECT id, erro, resposta, feedback FROM casos ORDER BY id DESC")
    dados = cursor.fetchall()
    conn.close()
    return [{"id": row[0], "erro": row[1], "resposta": row[2], "feedback": row[3]} for row in dados]

def salvar_caso_db(erro, resposta):
    inicializar_banco()
    conn = sqlite3.connect(NOME_BANCO)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT OR IGNORE INTO casos (erro, resposta, feedback) VALUES (?, ?, 0)", (erro, resposta))
        conn.commit()
    except Exception as e:
        print(f"Erro ao inserir no banco: {e}")
    finally:
        conn.close()

def atualizar_feedback_db(caso_id, novo_valor):
    inicializar_banco()
    conn = sqlite3.connect(NOME_BANCO)
    cursor = conn.cursor()
    cursor.execute("UPDATE casos SET feedback = ? WHERE id = ?", (novo_valor, caso_id))
    conn.commit()
    conn.close()

def exportar_base_json():
    historico = carregar_historico_db()
    dados_limpos = [{"erro": item["erro"], "resposta": item["resposta"], "feedback": item["feedback"]} for item in historico]
    return json.dumps(dados_limpos, ensure_ascii=False, indent=4)

def importar_base_json(arquivo_carregado):
    try:
        conteudo = json.load(arquivo_carregado)
        if isinstance(conteudo, list):
            inicializar_banco()
            conn = sqlite3.connect(NOME_BANCO)
            cursor = conn.cursor()
            for item in conteudo:
                if "erro" in item and "resposta" in item:
                    fb = item.get("feedback", 0)
                    cursor.execute("INSERT OR IGNORE INTO casos (erro, resposta, feedback) VALUES (?, ?, ?)", (item["erro"], item["resposta"], fb))
            conn.commit()
            conn.close()
            return True
    except Exception as e:
        print(f"Erro na importação: {e}")
    return False

if "historico_casos" not in st.session_state:
    st.session_state["historico_casos"] = carregar_historico_db()

# ==========================================
# 3. CONFIGURAÇÃO DA API GEMINI
# ==========================================
api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")

if not api_key:
    st.error("A chave de configuração não foi encontrada. Configure-a nas 'Secrets' do Streamlit Cloud.")
else:
    genai.configure(api_key=api_key)

# ==========================================
# 4. BARRA LATERAL (SIDEBAR REORGANIZADA E LIMPA)
# ==========================================
with st.sidebar:
    st.markdown("### SIM TCE-CE")
    st.caption("Assistente de Diagnóstico Técnico")
    st.markdown("---")
    
    st.markdown("**Sobre a Ferramenta**")
    st.markdown("<span style='font-size: 13px; color: #475569;'>Plataforma com busca semântica, feedback de utilidade e persistência SQLite para apoio na validação de layouts.</span>", unsafe_allow_html=True)
    
    st.markdown("---")
    st.markdown("**Base Permanente**")
    st.markdown(f"<span style='font-size: 20px; font-weight: 600; color: #0F172A;'>{len(st.session_state['historico_casos'])}</span> <span style='font-size: 13px; color: #64748B;'>casos armazenados</span>", unsafe_allow_html=True)
    
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
            if importar_base_json(arquivo_submetido):
                st.session_state["historico_casos"] = carregar_historico_db()
                st.success("Histórico restaurado com sucesso.")
                st.rerun()
            else:
                st.error("Erro ao processar o arquivo enviado.")

    st.markdown("---")
    st.caption("Desenvolvido para otimização de rotinas contábeis.")

# ==========================================
# 5. TELA PRINCIPAL E ABAS
# ==========================================
st.markdown("### Assistente de Diagnóstico SIM TCE-CE")
st.markdown("<span style='color: #475569; font-size: 15px;'>Central inteligente de análise de consistências, tradução de logs e consulta de orientações técnicas.</span>", unsafe_allow_html=True)
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
    st.markdown("##### Entrada de Dados do Relatório de Ocorrência")
    st.markdown("<span style='font-size: 13px; color: #64748B;'>Cole abaixo o trecho do relatório de ocorrência do PGI/SIM TCE-CE para gerar o diagnóstico técnico.</span>", unsafe_allow_html=True)
    
    # Exemplos rápidos estilizados como ações discretas
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
        height=140,
        placeholder="Cole o trecho do erro aqui..."
    )

    if user_input.strip():
        encontrou_ext = re.findall(r'\b[A-Z0-9]+\.(VCL|LCO|PAT|CPF|BAS|DCD)\b', user_input, re.IGNORECASE)
        encontrou_campos = re.findall(r'cd_[a-z_]+|dt_[a-z_]+|nu_[a-z_]+', user_input, re.IGNORECASE)
        
        badges_html = "<div style='display: flex; gap: 8px; margin: 12px 0 16px 0; flex-wrap: wrap; align-items: center;'>"
        if encontrou_ext:
            badges_html += f"<span style='background-color: #E0F2FE; color: #0369A1; padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: 500; border: 1px solid #BAE6FD;'>Módulo: {encontrou_ext[0][0].upper()}</span>"
        if encontrou_campos:
            amostra_campos = ", ".join(set(encontrou_campos[:4]))
            badges_html += f"<span style='background-color: #FEF3C7; color: #B45309; padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: 500; border: 1px solid #FDE68A;'>Chaves: {amostra_campos}</span>"
        badges_html += "</div>"
            
        if encontrou_ext or encontrou_campos:
            st.markdown(badges_html, unsafe_allow_html=True)

    if st.button("Processar Análise Técnica", type="primary", use_container_width=True):
        if user_input.strip():
            texto_limpo = user_input.strip()
            
            tem_estrutura_log = bool(re.search(r'\b([A-Z0-9]+\.(VCL|LCO|PAT|CPF|BAS|DCD|DAT|TXT))\b|cd_[a-z_]+|dt_[a-z_]+|nu_[a-z_]+|descrição:|ocorrência', texto_limpo, re.IGNORECASE))
            
            if not tem_estrutura_log and len(texto_limpo) < 15:
                st.warning("O texto inserido não parece ser um relatório de erro válido do SIM TCE-CE. Cole um trecho oficial de ocorrência contendo módulos ou campos técnicos.")
            else:
                caso_existente = next((item for item in st.session_state["historico_casos"] if item["erro"].strip() == texto_limpo), None)
                
                if caso_existente:
                    st.markdown("---")
                    st.success("Diagnóstico recuperado instantaneamente do Banco de Dados Permanente.")
                    st.markdown("##### Diagnóstico e Orientação Técnica")
                    st.markdown(caso_existente["resposta"])
                else:
                    with st.spinner("Analisando leiaute e consultando diretrizes de suporte..."):
                        resposta_obtida = None
                        sucesso = False
                        
                        modelos_para_tentar = ["gemini-3.6-flash", "gemini-1.5-flash", "gemini-2.5-flash"]
                        
                        prompt = f"""
                        Atue como um analista de suporte técnico especialista no sistema SIM do TCE-CE, com foco em uma linguagem simples, clara e didática.
                        Analise o erro de validação de dados abaixo (retirado de relatórios oficiais de ocorrência). 
                        
                        Forneça um diagnóstico estruturado estritamente nas seguintes partes:
                        
                        ### 🎯 Causa Raiz em Linguagem Simples
                        (Explique o motivo da inconsistência de forma descomplicada, traduzindo o que o erro significa na prática para o usuário).

                        ### 📍 Onde Encontrar e O Que Significa Cada Campo
                        (Identifique os campos técnicos citados no erro - como cd_municipio, dt_versao_orc, cd_orgao, nu_registro_bem, etc. Explique qual é a função de cada um deles no leiaute e em qual parte/contexto do arquivo eles devem ser conferidos).

                        ### ✅ Diretrizes Práticas de Correção
                        (Forneça orientações passo a passo claras e diretas de como o usuário deve proceder no sistema de origem ou no arquivo para resolver o problema).

                        REGRAS OBRIGATÓRIAS:
                        - Use uma linguagem amigável, didática e de fácil compreensão.
                        - NUNCA invente nomes de módulos ou telas de ERP. 
                        - NÃO utilize scripts SQL ou comandos de banco de dados.
                        - Certifique-se de concluir a resposta inteira sem cortes.

                        Erro reportado:
                        {texto_limpo}
                        """
                        
                        for nome_modelo in modelos_para_tentar:
                            tentativas = 2
                            for tentativa in range(tentativas):
                                try:
                                    model = genai.GenerativeModel(nome_modelo)
                                    response = model.generate_content(prompt, generation_config={"temperature": 0.2, "max_output_tokens": 4096})
                                    if response and response.text:
                                        resposta_obtida = response.text
                                        sucesso = True
                                        break
                                except Exception as err:
                                    err_str = str(err).lower()
                                    if "429" in err_str or "quota" in err_str:
                                        time.sleep(3 * (tentativa + 1))
                                        continue
                                    else:
                                        break
                            if sucesso:
                                break

                        if sucesso and resposta_obtida:
                            salvar_caso_db(texto_limpo, resposta_obtida)
                            st.session_state["historico_casos"] = carregar_historico_db()
                            
                            st.markdown("---")
                            st.success("Análise concluída com sucesso e gravada no Banco de Dados SQLite.")
                            st.markdown("##### Diagnóstico e Orientação Técnica")
                            st.markdown(resposta_obtida)
                        else:
                            st.error("O limite de requisições gratuitas da API foi atingido (Erro 429). O sistema tentou modelos alternativos, mas todos retornaram sobrecarga momentânea.")
                            st.info("Dica: Aguarde alguns segundos ou pesquise na aba Histórico Permanente se este caso já foi solucionado anteriormente.")
        else:
            st.warning("Por favor, insira ou carregue um texto de erro antes de processar a análise.")

# ------------------------------------------
# ABA 2: HISTÓRICO COM BUSCA SEMÂNTICA E FEEDBACK
# ------------------------------------------
with aba2:
    st.markdown("##### Repositório de Casos Resolvidos")
    st.markdown("<span style='font-size: 13px; color: #64748B;'>Consulte os casos salvos utilizando busca inteligente por similaridade e avalie a utilidade das respostas.</span>", unsafe_allow_html=True)
    st.markdown("")

    if not st.session_state["historico_casos"]:
        st.info("Ainda não há casos salvos na base permanente. Realize sua primeira análise na aba de Diagnóstico.")
    else:
        termo_busca_historico = st.text_input(
            "Pesquisa Semântica no Histórico", 
            placeholder="Digite termos vagos ou descrições (ex: erro de chave, unidades, patrimônio)..."
        ).lower()

        casos_atuais = st.session_state["historico_casos"]

        if termo_busca_historico.strip():
            corpus = [f"{c['erro']} {c['resposta']}" for c in casos_atuais]
            corpus.append(termo_busca_historico)
            
            try:
                vectorizer = TfidfVectorizer().fit_transform(corpus)
                vetores = vectorizer.toarray()
                vetor_busca = vetores[-1]
                vetores_corpus = vetores[:-1]
                
                similaridades = cosine_similarity([vetor_busca], vetores_corpus)[0]
                casos_com_score = list(zip(casos_atuais, similaridades))
                casos_com_score = sorted(casos_com_score, key=lambda x: x[1], reverse=True)
                
                casos_filtrados = [item[0] for item in casos_com_score if item[1] > 0.02 or termo_busca_historico in item[0]['erro'].lower()]
            except Exception:
                casos_filtrados = [c for c in casos_atuais if termo_busca_historico in c['erro'].lower() or termo_busca_historico in c['resposta'].lower()]
        else:
            casos_filtrados = sorted(casos_atuais, key=lambda x: x['feedback'], reverse=True)

        if not casos_filtrados:
            st.warning("Nenhum caso correspondente encontrado na base permanente com este critério.")
        else:
            st.markdown(f"<span style='font-size: 13px; color: #64748B;'>Exibindo <b>{len(casos_filtrados)}</b> de <b>{len(casos_atuais)}</b> registro(s)</span>", unsafe_allow_html=True)
            st.markdown("")
            
            for idx, caso in enumerate(casos_filtrados):
                # Badges de status discretos
                if caso['feedback'] == 1:
                    status_badge = "<span style='background-color: #DCFCE7; color: #166534; padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: 500;'>Aprovado</span>"
                elif caso['feedback'] == -1:
                    status_badge = "<span style='background-color: #FEF2F2; color: #991B1B; padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: 500;'>Requer atenção</span>"
                else:
                    status_badge = "<span style='background-color: #F1F5F9; color: #475569; padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: 500;'>Não avaliado</span>"
                
                titulo_resumo = caso["erro"].split("\n")[0] if "\n" in caso["erro"] else caso["erro"][:65]
                
                with st.expander(f"Caso #{caso['id']} — {titulo_resumo}  |  {status_badge}"):
                    st.markdown("**Log Registrado:**")
                    st.markdown(f"> {caso['erro']}")
                    st.markdown("---")
                    st.markdown(caso["resposta"])
                    st.markdown("---")
                    
                    col_fb1, col_fb2, col_fb3 = st.columns([2, 2, 6])
                    with col_fb1:
                        if st.button("Resposta útil", key=f"btn_sim_{caso['id']}"):
                            atualizar_feedback_db(caso['id'], 1)
                            st.session_state["historico_casos"] = carregar_historico_db()
                            st.success("Caso marcado como útil.")
                            st.rerun()
                    with col_fb2:
                        if st.button("Precisa melhorar", key=f"btn_nao_{caso['id']}"):
                            atualizar_feedback_db(caso['id'], -1)
                            st.session_state["historico_casos"] = carregar_historico_db()
                            st.warning("Feedback registrado.")
                            st.rerun()
                    with col_fb3:
                        status_atual_txt = "Aprovado pela equipe" if caso['feedback'] == 1 else ("Requer atenção" if caso['feedback'] == -1 else "Ainda não avaliado")
                        st.markdown(f"<span style='font-size: 12px; color: #64748B; line-height: 2.2;'>Curadoria: <b>{status_atual_txt}</b></span>", unsafe_allow_html=True)

# ------------------------------------------
# ABA 3: BASE DE CONHECIMENTO E REFERÊNCIAS
# ------------------------------------------
with aba3:
    st.markdown("##### Base de Conhecimento e Padrões SIM 2026")
    st.markdown("<span style='font-size: 13px; color: #64748B;'>Consulte os guias rápidos e manuais de orientação técnica organizados por módulos.</span>", unsafe_allow_html=True)
    st.markdown("")
    
    termo_busca = st.text_input("Filtrar guias de referência", placeholder="Digite ex: 'Veículos', 'Contratos', 'Patrimônio'...").lower()

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
        Se precisar analisar um arquivo texto (`.dat` ou `.txt`) linha por linha, lembre-se de que os dados são separados por **vírgulas e entre aspas**:
        * **Primeiras colunas:** Geralmente identificam o código do órgão e o tipo de registro/layout.
        * **Colunas centrais:** Costumam abrigar datas (no formato `AAAAMMDD`) e chaves principais (CPFs, CNPJs ou números de processos).
        * **Últimas colunas:** Geralmente traz valores numéricos e a competência de referência (no formato `AAAAMM`).
        
        *Dica de Ouro:* Sempre que o PGI emitir um relatório de ocorrência apontando uma linha, verifique a chave principal para localizar rapidamente o registro duplicado ou incorreto no sistema contábil.
        """)
