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
# 1. CONFIGURAÇÃO DA PÁGINA E ESTILO VISUAL
# ==========================================
st.set_page_config(
    page_title="Assistente SIM TCE-CE",
    page_icon="⚖️",
    layout="wide"
)

st.markdown("""
    <style>
    .main {
        background-color: #F8FAFC;
    }
    h1, h2, h3 {
        color: #0F172A;
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }
    .stMetric {
        background-color: #FFFFFF;
        padding: 15px;
        border-radius: 8px;
        border: 1px solid #E2E8F0;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    blockquote {
        border-left: 4px solid #0284C7;
        background-color: #F1F5F9;
        padding: 10px 15px;
        border-radius: 0 6px 6px 0;
        color: #334155;
    }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. PERSISTÊNCIA ROBUSTA (SQLITE + FEEDBACK)
# ==========================================
NOME_BANCO = "banco_sim_tce.db"

def inicializar_banco():
    """Cria a tabela de casos resolvidos com coluna de feedback se não existir."""
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
    """Carrega todos os casos salvos no banco SQLite."""
    inicializar_banco()
    conn = sqlite3.connect(NOME_BANCO)
    cursor = conn.cursor()
    cursor.execute("SELECT id, erro, resposta, feedback FROM casos ORDER BY id DESC")
    dados = cursor.fetchall()
    conn.close()
    return [{"id": row[0], "erro": row[1], "resposta": row[2], "feedback": row[3]} for row in dados]

def salvar_caso_db(erro, resposta):
    """Insere um novo caso no banco SQLite."""
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
    """Atualiza o feedback (1 para útil, -1 para não útil) de um caso."""
    inicializar_banco()
    conn = sqlite3.connect(NOME_BANCO)
    cursor = conn.cursor()
    cursor.execute("UPDATE casos SET feedback = ? WHERE id = ?", (novo_valor, caso_id))
    conn.commit()
    conn.close()

def exportar_base_json():
    """Exporta registros do banco para JSON."""
    historico = carregar_historico_db()
    dados_limpos = [{"erro": item["erro"], "resposta": item["resposta"], "feedback": item["feedback"]} for item in historico]
    return json.dumps(dados_limpos, ensure_ascii=False, indent=4)

def importar_base_json(arquivo_carregado):
    """Importa e mescla dados de um arquivo de backup externo."""
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
    st.error("⚠️ A chave de configuração não foi encontrada! Configure-a nas 'Secrets' do Streamlit Cloud.")
else:
    genai.configure(api_key=api_key)

# ==========================================
# 4. BARRA LATERAL (SIDEBAR PROFISSIONAL)
# ==========================================
with st.sidebar:
    st.markdown("### ⚖️ SIM TCE-CE")
    st.caption("Painel Técnico de Suporte e Diagnóstico")
    st.markdown("---")
    
    st.markdown("**📌 Sobre a Ferramenta**")
    st.markdown("Plataforma com busca semântica, feedback de utilidade e persistência SQLite para apoio na validação de layouts.")
    
    st.markdown("---")
    st.metric(label="Casos na Base Permanente", value=len(st.session_state["historico_casos"]))
    
    st.markdown("---")
    st.markdown("### 💾 Salvamento e Cópia")
    
    dados_json_str = exportar_base_json()
    st.download_button(
        label="📥 Baixar Cópia de Segurança",
        data=dados_json_str,
        file_name="backup_historico_sim_tce.json",
        mime="application/json",
        use_container_width=True,
        help="Gera um arquivo com todos os diagnósticos salvos para você guardar no seu computador."
    )
    
    arquivo_submetido = st.file_uploader(
        "📤 Carregar Cópia Salva", 
        type=["json"],
        help="Selecione um arquivo de backup gerado anteriormente para recuperar seus casos salvos."
    )
    
    if arquivo_submetido is not None:
        if st.button("🔄 Confirmar Restauração", use_container_width=True):
            if importar_base_json(arquivo_submetido):
                st.session_state["historico_casos"] = carregar_historico_db()
                st.success("Histórico de casos restaurado com sucesso!")
                st.rerun()
            else:
                st.error("Erro ao processar o arquivo enviado. Certifique-se de que é um backup válido.")

    st.markdown("---")
    st.caption("Desenvolvido para otimização de rotinas contábeis.")

# ==========================================
# 5. TELA PRINCIPAL E ABAS
# ==========================================
st.title("Assistente de Diagnóstico SIM TCE-CE")
st.markdown("Central inteligente de análise de consistências, tradução de logs e consulta de orientações técnicas.")
st.markdown("---")

aba1, aba2, aba3 = st.tabs([
    "🔍 Diagnóstico Inteligente", 
    "📂 Histórico Permanente", 
    "💡 Base de Conhecimento"
])

# ------------------------------------------
# ABA 1: DIAGNÓSTICO E ENTRADA DE LOGS
# ------------------------------------------
with aba1:
    st.markdown("#### 📥 Entrada de Dados do Relatório de Ocorrência")
    st.info("Cole abaixo o trecho do relatório de ocorrência do PGI/SIM TCE-CE para gerar o diagnóstico técnico.")
    
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("🚗 Exemplo: Veículos (.VCL)", use_container_width=True):
            st.session_state["erro_input"] = (
                "BV202607.VCL - DESTINAÇÃO DE VEÍCULOS\n"
                "Descrição: Não há relação com o(s) campo(s) ( cd_municipio, dt_versao_orc, cd_orgao, cd_unid_orc ) que compõe(m) a chave do arquivo UNIDADES_ORCAMENTARIAS."
            )
    with col_btn2:
        if st.button("🏛️ Exemplo: Patrimônio (.PAT)", use_container_width=True):
            st.session_state["erro_input"] = (
                "RP202607.PAT - CONTAS REDUTORAS DOS BENS INCORPORADOS AO PATRIMÔNIO DO MUNICÍPIO\n"
                "Descrição: Não há relação com o(s) campo(s) ( cd_municipio, nu_registro_bem ) que compõe(m) a chave do arquivo BENS_MUNICIPIOS."
            )
    
    user_input = st.text_area(
        "Relatório de Erro:",
        value=st.session_state.get("erro_input", ""),
        height=150,
        placeholder="Cole o trecho do erro aqui..."
    )

    if user_input.strip():
        encontrou_ext = re.findall(r'\b[A-Z0-9]+\.(VCL|LCO|PAT|CPF|BAS|DCD)\b', user_input, re.IGNORECASE)
        encontrou_campos = re.findall(r'cd_[a-z_]+|dt_[a-z_]+|nu_[a-z_]+', user_input, re.IGNORECASE)
        
        tags_html = ""
        if encontrou_ext:
            tags_html += f"<span style='background-color:#E0F2FE; color:#0369A1; padding:4px 10px; border-radius:6px; margin-right:8px; font-weight:600; font-size:13px;'>📦 Módulo: {encontrou_ext[0][0].upper()}</span>"
        if encontrou_campos:
            amostra_campos = ", ".join(set(encontrou_campos[:4]))
            tags_html += f"<span style='background-color:#FEF3C7; color:#B45309; padding:4px 10px; border-radius:6px; margin-right:8px; font-weight:600; font-size:13px;'>🔑 Chaves: {amostra_campos}</span>"
            
        if tags_html:
            st.markdown(f"<div style='margin-bottom: 15px;'>{tags_html}</div>", unsafe_allow_html=True)

    if st.button("🚀 Processar Análise Técnica", type="primary", use_container_width=True):
        if user_input.strip():
            texto_limpo = user_input.strip()
            
            tem_estrutura_log = bool(re.search(r'\b([A-Z0-9]+\.(VCL|LCO|PAT|CPF|BAS|DCD|DAT|TXT))\b|cd_[a-z_]+|dt_[a-z_]+|nu_[a-z_]+|descrição:|ocorrência', texto_limpo, re.IGNORECASE))
            
            if not tem_estrutura_log and len(texto_limpo) < 15:
                st.warning("⚠️ O texto inserido não parece ser um relatório de erro válido do SIM TCE-CE. Cole um trecho oficial de ocorrência contendo módulos ou campos técnicos.")
            else:
                caso_existente = next((item for item in st.session_state["historico_casos"] if item["erro"].strip() == texto_limpo), None)
                
                if caso_existente:
                    st.markdown("---")
                    st.success("⚡ Diagnóstico recuperado instantaneamente do Banco de Dados Permanente (0 chamadas à API)!")
                    st.markdown("### 💡 Diagnóstico e Orientação Técnica")
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
                            st.success("Análise concluída com sucesso e gravada no Banco de Dados SQLite!")
                            st.markdown("### 💡 Diagnóstico e Orientação Técnica")
                            st.markdown(resposta_obtida)
                        else:
                            st.error("⚠️ O limite de requisições gratuitas da API foi atingido (Erro 429). O sistema tentou modelos alternativos, mas todos retornaram sobrecarga momentânea.")
                            st.info("💡 **Dica:** Aguarde alguns segundos ou pesquise na aba **Histórico Permanente** se este caso já foi solucionado anteriormente.")
        else:
            st.warning("⚠️ Por favor, insira ou carregue um texto de erro antes de processar a análise.")

# ------------------------------------------
# ABA 2: HISTÓRICO COM BUSCA SEMÂNTICA E FEEDBACK
# ------------------------------------------
with aba2:
    st.markdown("#### 📂 Repositório de Casos Resolvidos (Busca Semântica & Curadoria)")
    st.markdown("Consulte os casos salvos. O sistema utiliza busca inteligente por similaridade e permite avaliar a utilidade das respostas.")

    if not st.session_state["historico_casos"]:
        st.info("Ainda não há casos salvos na base permanente. Realize sua primeira análise na aba de Diagnóstico.")
    else:
        termo_busca_historico = st.text_input(
            "🔍 Pesquisa Semântica no Histórico:", 
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
            st.warning("Nenhum caso correspondente encontrado na base permanente com este critério semântico.")
        else:
            st.markdown(f"**Resultados exibidos:** {len(casos_filtrados)} de {len(casos_atuais)} registro(s)")
            st.markdown("---")
            
            for idx, caso in enumerate(casos_filtrados):
                icone_status = "⭐ " if caso['feedback'] == 1 else ("⚠️ " if caso['feedback'] == -1 else "")
                titulo_resumo = caso["erro"].split("\n")[0] if "\n" in caso["erro"] else caso["erro"][:65]
                
                with st.expander(f"{icone_status}Caso #{caso['id']}: {titulo_resumo}"):
                    st.markdown(f"**Log Registrado:**")
                    st.markdown(f"> {caso['erro']}")
                    st.markdown("---")
                    st.markdown(caso["resposta"])
                    st.markdown("---")
                    
                    col_fb1, col_fb2, col_fb3 = st.columns([2, 2, 6])
                    with col_fb1:
                        if st.button("👍 Resposta Útil", key=f"btn_sim_{caso['id']}"):
                            atualizar_feedback_db(caso['id'], 1)
                            st.session_state["historico_casos"] = carregar_historico_db()
                            st.success("Obrigado pelo feedback! Caso marcado como útil.")
                            st.rerun()
                    with col_fb2:
                        if st.button("👎 Precisa Melhorar", key=f"btn_nao_{caso['id']}"):
                            atualizar_feedback_db(caso['id'], -1)
                            st.session_state["historico_casos"] = carregar_historico_db()
                            st.warning("Feedback registrado.")
                            st.rerun()
                    with col_fb3:
                        status_atual_txt = "⭐ Aprovado pela equipe" if caso['feedback'] == 1 else ("⚠️ Requer atenção" if caso['feedback'] == -1 else "Ainda não avaliado")
                        st.caption(f"Status de Curadoria: **{status_atual_txt}**")

# ------------------------------------------
# ABA 3: BASE DE CONHECIMENTO E REFERÊNCIAS
# ------------------------------------------
with aba3:
    st.markdown("#### 📚 Base de Conhecimento e Padrões SIM 2026")
    
    termo_busca = st.text_input("🔍 Filtrar guias de referência:", placeholder="Digite ex: 'Veículos', 'Contratos', 'Patrimônio'...").lower()

    with st.expander("🏛️ 1. Erros de Unidades Orçamentárias e Vínculos (Ex: .VCL, .PAT)"):
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

    with st.expander("📝 2. Erros em Contratos, Aditivos e Ordenadores (Ex: .LCO)"):
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

    with st.expander("👥 3. Inconsistências na Folha de Pagamento e Servidores"):
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

    with st.expander("📌 4. Guia Rápido: Como Ler os Campos nas Linhas dos Arquivos"):
        st.markdown("""
        Se precisar analisar um arquivo texto (`.dat` ou `.txt`) linha por linha, lembre-se de que os dados são separados por **vírgulas e entre aspas**:
        * **Primeiras colunas:** Geralmente identificam o código do órgão e o tipo de registro/layout.
        * **Colunas centrais:** Costumam abrigar datas (no formato `AAAAMMDD`) e chaves principais (CPFs, CNPJs ou números de processos).
        * **Últimas colunas:** Geralmente trazem valores numéricos e a competência de referência (no formato `AAAAMM`).
        
        *Dica de Ouro:* Sempre que o PGI emitir um relatório de ocorrência apontando uma linha, verifique a chave principal (geralmente a coluna de identificação) para localizar rapidamente o registro duplicado ou incorreto no sistema contábil.
        """)
