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

# Configuração da Chave da API do Gemini
api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")

if not api_key:
    st.error("⚠️ A chave de configuração não foi encontrada! Configure-a nas 'Secrets' do Streamlit Cloud.")
else:
    genai.configure(api_key=api_key)

# ==========================================
# BARRA LATERAL (SIDEBAR) & PREFERÊNCIAS
# ==========================================
with st.sidebar:
    st.image("https://img.icons8.com/color/96/law.png", width=60)
    st.title("Suporte Técnico")
    st.markdown("Ferramenta de validação, diagnóstico e correção de inconsistências de layout do SIM TCE-CE.")
    
    st.markdown("---")
    st.subheader("🎨 Aparência e Tema")
    st.info("💡 **Dica:** Para alternar o tema oficial, clique no menu superior direito do Streamlit (⋮) ➔ **Settings** ➔ **Theme** (Dark/Light).")
    
    st.markdown("---")
    st.markdown("### 📌 Orientações")
    st.markdown(
        "Utilize este painel para analisar logs de erro gerados pelo sistema de validação, obtendo diretrizes normativas para adequação dos arquivos."
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
    st.info("Cole abaixo o log de erro ou o trecho do arquivo do SIM TCE-CE que necessita de análise:")
    
    # Botão de Exemplo Rápido
    col_btn1, col_btn2 = st.columns([2, 5])
    with col_btn1:
        if st.button("📥 Carregar Exemplo (Veículos)"):
            st.session_state["erro_input"] = (
                "BV202607.VCL - DESTINAÇÃO DE VEÍCULOS\n"
                "Descrição: Não há relação com o(s) campo(s) ( cd_municipio, dt_versao_orc, cd_orgao, "
                "cd_unid_orc ) que compõe(m) a chave do arquivo UNIDADES_ORCAMENTARIAS."
            )
    
    # Área de texto
    user_input = st.text_area(
        "Cole o erro aqui:",
        value=st.session_state.get("erro_input", ""),
        height=160,
        placeholder="Cole o log do erro retornado pelo validador do SIM..."
    )

    # --- DESTAQUE VISUAL DE PALAVRAS-CHAVE (BADGES) ---
    if user_input.strip():
        st.markdown("**🔍 Indicadores Identificados no Log:**")
        
        encontrou_vcl = re.findall(r'\b[A-Z0-9]+\.VCL\b', user_input, re.IGNORECASE)
        encontrou_campos = re.findall(r'cd_[a-z_]+|dt_[a-z_]+', user_input, re.IGNORECASE)
        encontrou_tabelas = re.findall(r'UNIDADES_ORCAMENTARIAS|VEICULOS_DESTINACOES', user_input, re.IGNORECASE)
        
        tags_html = ""
        if encontrou_vcl:
            tags_html += f"<span style='background-color:#ffeeba; color:#856404; padding:4px 8px; border-radius:4px; margin-right:5px; font-weight:bold;'>Arquivo: {encontrou_vcl[0]}</span>"
        if encontrou_tabelas:
            tags_html += f"<span style='background-color:#d4edda; color:#155724; padding:4px 8px; border-radius:4px; margin-right:5px; font-weight:bold;'>Tabela Ref: {encontrou_tabelas[0]}</span>"
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
                    
                    prompt = f"""
                    Atue como um analista de suporte técnico especialista no sistema SIM do TCE-CE.
                    Analise o erro de validação de dados abaixo. Forneça um diagnóstico estruturado estritamente em duas partes claras:
                    
                    ### Causa Raiz
                    (Explique detalhadamente o motivo da inconsistência no layout ou na relação entre os arquivos).

                    ### Passo a Passo Normativo
                    (Forneça o procedimento objetivo de como corrigir diretamente nos lançamentos, telas ou rotinas do sistema).

                    IMPORTANTE: 
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
# ABA 2 APRIMORADA: GUIA DE PADRÕES E REFERÊNCIAS
# ==========================================
with aba2:
    st.subheader("📚 Guia Prático de Padrões e Erros Comuns - SIM TCE-CE")
    st.markdown("Consulte abaixo as orientações estruturadas para os principais tipos de falhas de validação encontrados no sistema.")

    with st.expander("🔗 1. Erros de Chave Estrangeira e Integridade Referencial"):
        st.markdown("""
        * **O que significa:** O registro enviado em um arquivo secundário (ex: *Veículos*, *Licitações*, *Contratos*) não encontrou correspondência exata nos dados cadastrais principais (como Órgãos ou Unidades Orçamentárias).
        * **Campos envolvidos comumente:** `cd_municipio`, `dt_versao_orc`, `cd_orgao`, `cd_unid_orc`.
        * **Como corrigir:** Verifique se o arquivo principal da remessa (contendo a Unidade Orçamentária ou Órgão) foi exportado e processado corretamente. Certifique-se de que os códigos numéricos digitados no lançamento da despesa/frota coincidem perfeitamente com o cadastro oficial do exercício.
        """)

    with st.expander("📅 2. Divergências de Datas e Versões Orçamentárias (`dt_versao_orc`)"):
        st.markdown("""
        * **O que significa:** A data de versão do orçamento informada no lançamento do movimento difere da data enviada na tabela de UOs da mesma remessa.
        * **Como corrigir:** Acesse o cadastro de origem no seu sistema de gestão (ERP), localize o registro que apresenta divergência de data de versão e alinhe o período para corresponder rigorosamente à competência/versão da remessa vigente no TCE-CE.
        """)

    with st.expander("📁 3. Nomenclatura e Sequência de Arquivos (.VCL, .TXT)"):
        st.markdown("""
        * **O que significa:** Falhas na extensão, caracteres corrompidos ou envio de arquivos fora da ordem cronológica exigida pelo manual de instruções.
        * **Como corrigir:** Valide se o nome do arquivo gerado pelo seu sistema segue estritamente o padrão normativo do ano vigente (ex: prefixo do município + ano/mês + extensão do módulo). Respeite a ordem de importação recomendada pelo validador.
        """)
