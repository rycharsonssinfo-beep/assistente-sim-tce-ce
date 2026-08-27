import os
import re
import streamlit as st
import google.generativeai as genai

# Configuração da página (Modo Wide e ícone customizado)
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
    st.subheader("🎨 Aparência da Interface")
    modo_escuro = st.toggle("Ativar Modo Escuro", value=False)
    
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

# Abas limpas
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
        st.markdown("**🔍 IndicadoresIdentificados no Log:**")
        
        # Lógica para varrer termos críticos no texto colado
        encontrou_vcl = re.findall(r'\b[A-Z0-9]+\.VCL\b', user_input, re.IGNORECASE)
        encontrou_campos = re.findall(r'cd_[a-z_]+|dt_[a-z_]+', user_input, re.IGNORECASE)
        encontrou_tabelas = re.findall(r'UNIDADES_ORCAMENTARIAS|VEICULOS_DESTINACOES', user_input, re.IGNORECASE)
        
        # Exibição visual limpa por tags usando colunas / markdown customizado
        tags_html = ""
        if encontrou_vcl:
            tags_html += f"<span style='background-color:#ffeeba; color:#856404; padding:4px 8px; border-radius:4px; margin-right:5px; font-weight:bold;'>Arquivo: {encontrou_vcl[0]}</span>"
        if encontrou_tabelas:
            tags_html += f"<span style='background-color:#d4edda; color:#155724; padding:4px 8px; border-radius:4px; margin-right:5px; font-weight:bold;'>Tabela Ref: {encontrou_tabelas[0]}</span>"
        if encontrou_campos:
            # Mostra alguns campos-chave encontrados
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
                    
                    # Layout em Cartões (Cards) visuais para separar as etapas
                    st.markdown("### 💡 Diagnóstico e Solução Técnica")
                    
                    # Exibindo o texto gerado de forma limpa
                    st.markdown(response.text)
                    
                except Exception as e:
                    st.error(f"Ocorreu um erro ao processar a requisição técnica: {e}")
        else:
            st.warning("⚠️ Por favor, insira ou carregue um texto de erro antes de processar a análise.")

with aba2:
    st.subheader("Diretrizes e Boas Práticas para o SIM TCE-CE")
    st.markdown("""
    - **Integridade de Registros:** Certifique-se de que os dados informados nos arquivos dependentes (como códigos de municípios, órgãos e unidades orçamentárias) coincidam perfeitamente com os cadastros oficiais enviados.
    - **Sequência de Transmissão:** Respeite rigorosamente a ordem de exportação dos arquivos exigida pelo manual de instruções do TCE-CE.
    - **Ajustes de Layout:** Corrija as divergências diretamente no sistema gerador de arquivos antes de realizar uma nova validação.
    """)
