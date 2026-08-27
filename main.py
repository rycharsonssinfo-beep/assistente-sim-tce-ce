import os
import re
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
# BARRA LATERAL (SIDEBAR) - Limpa
# ==========================================
with st.sidebar:
    st.image("https://img.icons8.com/color/96/law.png", width=60)
    st.title("Suporte Técnico")
    st.markdown("Ferramenta de validação, diagnóstico e correção de inconsistências de layout do SIM TCE-CE.")
    
    st.markdown("---")
    st.markdown("### 📌 Orientações")
    st.markdown(
        "Utilize este painel para analisar logs de erro e relatórios de ocorrência do validador, obtendo diretrizes normativas para adequação dos arquivos."
    )

# ==========================================
# TELA PRINCIPAL
# ==========================================
st.title("⚖️ Assistente SIM TCE-CE - Diagnóstico Técnico")
st.markdown("### Central de análise e correção de erros de validação do Tribunal de Contas.")
st.markdown("---")

# Abas principais
aba1, aba2 = st.tabs(["🔍 Diagnóstico de Erros", "💡 Padrões e Referências"])

with aba1:
    st.info("Cole abaixo o trecho do relatório de ocorrência ou do arquivo do SIM TCE-CE que necessita de análise:")
    
    # Botões de Exemplos Rápidos baseados em relatórios reais
    col_btn1, col_btn2 = st.columns([1, 1])
    with col_btn1:
        if st.button("📥 Exemplo 1: Erro de Veículos (VCL)"):
            st.session_state["erro_input"] = (
                "BV202607.VCL - DESTINAÇÃO DE VEÍCULOS\n"
                "Descrição: Não há relação com o(s) campo(s) ( cd_municipio, dt_versao_orc, cd_orgao, "
                "cd_unid_orc ) que compõe(m) a chave do arquivo UNIDADES_ORCAMENTARIAS."
            )
    with col_btn2:
        if st.button("📥 Exemplo 2: Erro de Contratos (LCO)"):
            st.session_state["erro_input"] = (
                "CO202607.LCO - CONTRATOS\n"
                "Descrição: Gestor responsavel pelo Contrato nao encontrado no cadastro de Ordenadores."
            )
    
    # Área de texto
    user_input = st.text_area(
        "Cole o erro aqui:",
        value=st.session_state.get("erro_input", ""),
        height=160,
        placeholder="Cole o trecho do relatório de ocorrência..."
    )

    # --- DESTAQUE VISUAL DE PALAVRAS-CHAVE (BADGES) ---
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

    # Botão de Ação Principal
    if st.button("🚀 Processar Análise", type="primary"):
        if user_input.strip():
            with st.spinner("Processando diagnóstico completo..."):
                try:
                    model = genai.GenerativeModel("gemini-3.6-flash")
                    
                    # Prompt ajustado para focar em linguagem didática e proibir nomes fictícios de módulos de ERP
                    prompt = f"""
                    Atue como um analista de suporte técnico especialista no sistema SIM do TCE-CE.
                    Analise o erro de validação de dados abaixo (retirado de relatórios oficiais de ocorrência). 
                    Forneça um diagnóstico estruturado estritamente em duas partes claras:
                    
                    ### Causa Raiz
                    (Explique detalhadamente o motivo da inconsistência de layout, chave estrangeira ou cadastro ausente, citando os campos técnicos envolvidos de forma clara).

                    ### Diretrizes de Correção
                    (Forneça orientações didáticas e normativas focadas estritamente na validação de dados, como por exemplo: verificar se o órgão, unidade orçamentária ou data de versão correspondem exatamente aos cadastros oficiais enviados ao TCE-CE).

                    REGRAS OBRIGATÓRIAS:
                    - NUNCA invente nomes de módulos ou telas de ERP (como "módulo de frotas", "transporte", etc.). Foque estritamente nos conceitos, campos e nas regras normativas do SIM TCE-CE.
                    - NÃO utilize scripts SQL, consultas de banco de dados ou comandos de alteração de banco.
                    - Certifique-se de concluir a resposta inteira sem cortes.

                    Erro reportado:
                    {user_input}
                    """
                    
                    generation_config = {
                        "temperature": 0.2,
                        "max_output_tokens": 4096,
                    }
                    
                    response = model.generate_content(prompt, generation_config=generation_config)
                    
                    st.markdown("---")
                    st.success("Análise concluída com sucesso!")
                    st.markdown("### 💡 Diagnóstico e Solução Técnica")
                    st.markdown(response.text)
                    
                except Exception as e:
                    st.error(f"Ocorreu um erro ao processar a requisição técnica: {e}")
        else:
            st.warning("⚠️ Por favor, insira ou carregue um texto de erro antes de processar a análise.")

# ==========================================
# ABA 2: GUIA DE PADRÕES E REFERÊNCIAS
# ==========================================
with aba2:
    st.subheader("📚 Guia Prático com Base em Relatórios de Ocorrência")
    st.markdown("Consulte abaixo as orientações estruturadas para os erros mais frequentes identificados nas remessas mensais.")

    with st.expander("🔗 1. Integridade Referencial (Chaves Estrangeiras em Veículos e Bens)"):
        st.markdown("""
        * **Ocorrência Comum:** Erros nos arquivos `.VCL` (Veículos) ou `.PAT` (Patrimônio) indicando que não há relação com os campos de UO ou Notas de Empenho.
        * **Como corrigir:** Verifique se o Órgão (`cd_orgao`) e a Unidade Orçamentária (`cd_unid_orc`) em questão estão cadastrados e ativos para o período de referência exigido pelo TCE-CE. Confirme se a Data da Versão do Orçamento (`dt_versao_orc`) cadastrada corresponde exatamente à data enviada na carga orçamentária vigente.
        """)

    with st.expander("📝 2. Cadastros Prévios Obrigatórios (Contratos e Gestores)"):
        st.markdown("""
        * **Ocorrência Comum:** Avisos de *Contrato Aditivo sem Contrato Original cadastrado* ou *Gestor responsável não encontrado no cadastro de Ordenadores*.
        * **Como corrigir:** Certifique-se de que o contrato original foi devidamente exportado e validado nas remessas correspondentes antes do envio de aditivos. Valide também se o CPF do ordenador de despesa consta formalmente na remessa de agentes públicos da respectiva competência.
        """)

    with st.expander("🔄 3. Duplicidade de Registros no Banco"):
        st.markdown("""
        * **Ocorrência Comum:** Alerta informando que o registro já existe no banco de dados do validador (comum em arquivos de manutenção de veículos ou contas bancárias).
        * **Como corrigir:** Revise os arquivos de remessa mensal para eliminar lançamentos duplicados ou reenvios indevidos de registros que já foram aceitos em processamentos anteriores.
        """)
