import os
import re
import time
import streamlit as st
import google.generativeai as genai

# Configuração da página
st.set_page_config(
    page_title="Assistente SIM TCE-CE",
    page_icon="⚖️",
    layout="wide"
)

# Configuração da Chave da API
api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")

if not api_key:
    st.error("⚠️ A chave de configuração não foi encontrada! Configure-a nas 'Secrets' do Streamlit Cloud.")
else:
    genai.configure(api_key=api_key)

# ==========================================
# BARRA LATERAL (SIDEBAR)
# ==========================================
with st.sidebar:
    st.image("https://img.icons8.com/color/96/law.png", width=60)
    st.title("Suporte Técnico")
    st.markdown("Ferramenta de validação, diagnóstico e correção de inconsistências de layout do SIM TCE-CE.")
    st.markdown("---")
    st.markdown("### 📌 Orientações")
    st.markdown("Utilize este painel para analisar logs de erro, identificando de forma didática a posição e a função de cada campo no layout.")

# ==========================================
# TELA PRINCIPAL
# ==========================================
st.title("⚖️ Assistente SIM TCE-CE - Diagnóstico Técnico")
st.markdown("### Central de análise e correção de erros de validação do Tribunal de Contas.")
st.markdown("---")

# Abas principais
aba1, aba2 = st.tabs(["🔍 Diagnóstico de Logs e Posições", "💡 Padrões e Referências"])

with aba1:
    st.info("Cole abaixo o trecho do relatório de ocorrência do SIM TCE-CE que necessita de análise:")
    
    col_btn1, col_btn2 = st.columns([1, 1])
    with col_btn1:
        if st.button("📥 Exemplo 1: Erro de Veículos (VCL)"):
            st.session_state["erro_input"] = (
                "BV202607.VCL - DESTINAÇÃO DE VEÍCULOS\n"
                "Descrição: Não há relação com o(s) campo(s) ( cd_municipio, dt_versao_orc, cd_orgao, cd_unid_orc ) que compõe(m) a chave do arquivo UNIDADES_ORCAMENTARIAS."
            )
    with col_btn2:
        if st.button("📥 Exemplo 2: Erro de Contratos (LCO)"):
            st.session_state["erro_input"] = (
                "CO202607.LCO - CONTRATOS\n"
                "Descrição: Gestor responsavel pelo Contrato nao encontrado no cadastro de Ordenadores."
            )
    
    user_input = st.text_area(
        "Cole o erro aqui:",
        value=st.session_state.get("erro_input", ""),
        height=160,
        placeholder="Cole o trecho do relatório de ocorrência..."
    )

    if user_input.strip():
        st.markdown("**🔍 Indicadores Identificados no Log:**")
        encontrou_ext = re.findall(r'\b[A-Z0-9]+\.(VCL|LCO|PAT|CPF|BAS|DCD)\b', user_input, re.IGNORECASE)
        encontrou_campos = re.findall(r'cd_[a-z_]+|dt_[a-z_]+|nu_[a-z_]+', user_input, re.IGNORECASE)
        
        tags_html = ""
        if encontrou_ext:
            tags_html += f"<span style='background-color:#ffeeba; color:#856404; padding:4px 8px; border-radius:4px; margin-right:5px; font-weight:bold;'>Módulo/Arquivo: {encontrou_ext[0][0].upper()}</span>"
        if encontrou_campos:
            amostra_campos = ", ".join(set(encontrou_campos[:4]))
            tags_html += f"<span style='background-color:#cce5ff; color:#004085; padding:4px 8px; border-radius:4px; margin-right:5px; font-weight:bold;'>Campos Chave: {amostra_campos}</span>"
            
        if tags_html:
            st.markdown(tags_html, unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)

    if st.button("🚀 Processar Análise", type="primary"):
        if user_input.strip():
            with st.spinner("Processando diagnóstico detalhado..."):
                resposta_obtida = None
                sucesso = False
                
                # Lista de modelos para tentativa de fallback caso o principal atinja cota
                modelos_para_tentar = ["gemini-3.6-flash", "gemini-1.5-flash"]
                
                prompt = f"""
                Atue como um analista de suporte técnico especialista no sistema SIM do TCE-CE, com foco em uma linguagem simples, clara e didática.
                Analise o erro de validação de dados abaixo (retirado de relatórios oficiais de ocorrência). 
                
                Forneça um diagnóstico estruturado estritamente nas seguintes partes:
                
                ### 🎯 Causa Raiz em Linguagem Simples
                (Explique o motivo da inconsistência de forma descomplicada, traduzindo o que o erro significa na prática para o usuário).

                ### 📍 Onde Encontrar e O Que Significa Cada Campo
                (Identifique os campos técnicos citados no erro - como cd_municipio, dt_versao_orc, cd_orgao, cd_unid_orc, etc. Explique qual é a função de cada um deles no leiaute e em qual parte/contexto do arquivo eles devem ser conferidos).

                ### ✅ Diretrizes Práticas de Correção
                (Forneça orientações passo a passo claras e diretas de como o usuário deve proceder no sistema de origem ou no arquivo para resolver o problema).

                REGRAS OBRIGATÓRIAS:
                - Use uma linguagem amigável, didática e de fácil compreensão.
                - NUNCA invente nomes de módulos ou telas de ERP. 
                - NÃO utilize scripts SQL ou comandos de banco de dados.
                - Certifique-se de concluir a resposta inteira sem cortes.

                Erro reportado:
                {user_input}
                """
                
                for nome_modelo in modelos_para_tentar:
                    try:
                        model = genai.GenerativeModel(nome_modelo)
                        response = model.generate_content(prompt, generation_config={"temperature": 0.2, "max_output_tokens": 4096})
                        if response and response.text:
                            resposta_obtida = response.text
                            sucesso = True
                            break
                    except Exception as err:
                        # Se for erro de cota (429), aguarda brevemente e tenta o próximo modelo da lista
                        if "429" in str(err) or "quota" in str(err).lower():
                            time.sleep(2)
                            continue
                        else:
                            # Outros erros prosseguem para exibição
                            pass

                if sucesso and resposta_obtida:
                    st.markdown("---")
                    st.success("Análise concluída com sucesso!")
                    st.markdown("### 💡 Diagnóstico e Orientação Detalhada")
                    st.markdown(resposta_obtida)
                else:
                    st.warning("⚠️ O limite de requisições gratuitas foi atingido temporariamente (Erro 429). Por favor, aguarde de 10 a 20 segundos e clique em 'Processar Análise' novamente.")
        else:
            st.warning("⚠️ Por favor, insira ou carregue um texto de erro antes de processar a análise.")

with aba2:
    st.subheader("📚 Guia Prático e Base de Conhecimento SIM 2026")
    st.markdown("Consulte abaixo o catálogo detalhado com os erros mais frequentes, a função dos campos técnicos envolvidos e o passo a passo para a correção.")

    with st.expander("🏛️ 1. Erros de Unidades Orçamentárias e Vínculos (Ex: .VCL, .PAT)"):
        st.markdown("""
        * **Ocorrência Comum no Log:**  
          *Não há relação com o(s) campo(s) (cd_municipio, dt_versao_orc, cd_orgao, cd_unid_orc) que compõe(m) a chave do arquivo UNIDADES_ORCAMENTARIAS.*
        
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
