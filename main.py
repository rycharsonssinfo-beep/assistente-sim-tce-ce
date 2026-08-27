import os
import streamlit as st
import google.generativeai as genai

# Configuração da página (Modo Wide e ícone customizado)
st.set_page_config(
    page_title="Assistente SIM TCE-CE",
    page_icon="⚖️",
    layout="wide"
)

# Configuração da Chave da API do Gemini (Mantida em segundo plano sem exposição na UI)
api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")

if not api_key:
    st.error("⚠️ A chave de configuração não foi encontrada! Configure-a nas 'Secrets' do Streamlit Cloud.")
else:
    genai.configure(api_key=api_key)

# ==========================================
# BARRA LATERAL (SIDEBAR) - Limpa e Institucional
# ==========================================
with st.sidebar:
    st.image("https://img.icons8.com/color/96/law.png", width=60)
    st.title("Suporte Técnico")
    st.markdown("Ferramenta de validação, diagnóstico e correção de inconsistências de layout do SIM TCE-CE.")
    
    st.markdown("---")
    st.markdown("### 📌 Orientações")
    st.markdown(
        "Utilize este painel para analisar logs de erro gerados pelo sistema de validação, obtendo diretrizes técnicas para correção dos registros."
    )

# ==========================================
# TELA PRINCIPAL
# ==========================================
st.title("⚖️ Assistente SIM TCE-CE - Diagnóstico Técnico")
st.markdown("### Central de análise e correção de erros de validação do Tribunal de Contas.")
st.markdown("---")

# Abas limpas para organizar o fluxo
aba1, aba2 = st.tabs(["🔍 Diagnóstico de Erros", "💡 Padrões e Referências"])

with aba1:
    st.info("Cole abaixo o log de erro ou o trecho do arquivo do SIM TCE-CE que necessita de análise:")
    
    # Botão de Exemplo Rápido para teste instantâneo
    col_btn1, col_btn2 = st.columns([2, 5])
    with col_btn1:
        if st.button("📥 Carregar Exemplo (Veículos)"):
            st.session_state["erro_input"] = (
                "BV202607.VCL - BAIXA NA DESTINAÇÃO DE VEÍCULOS\n"
                "Descrição: Não há relação com o(s) campo(s) ( cd_municipio, dt_versao_orc, cd_orgao, "
                "cd_unid_orc, dt_inclusao_vd, cd_renavam_vm ) que compõe(m) a chave do arquivo VEICULOS_DESTINACOES."
            )
    
    # Área de texto vinculada ao estado da sessão
    user_input = st.text_area(
        "Cole o erro aqui:",
        value=st.session_state.get("erro_input", ""),
        height=160,
        placeholder="Cole o log do erro retornado pelo validador do SIM..."
    )

    # Botão de Ação Principal
    if st.button("🚀 Processar Análise", type="primary"):
        if user_input.strip():
            with st.spinner("Processando diagnóstico e diretrizes de correção..."):
                try:
                    # Configuração de modelo e prompt direcionado a respostas técnicas estruturadas
                    model = genai.GenerativeModel("gemini-3.6-flash")
                    
                    prompt = f"""
                    Atue como um analista de suporte técnico especialista sênior no sistema SIM do TCE-CE (Tribunal de Contas dos Municípios / Estado do Ceará).
                    Analise o erro de validação de dados abaixo. Forneça uma resposta estritamente técnica, objetiva e estruturada contendo:
                    1. Causa raiz detalhada do problema.
                    2. O passo a passo normativo/técnico para correção.
                    3. Sempre que houver comandos SQL, scripts ou trechos estruturados de correção, coloque-os isolados em blocos de código markdown (```sql ou ```text) para facilitar a cópia rápida pelo operador.

                    Erro reportado:
                    {user_input}
                    """
                    
                    response = model.generate_content(prompt)
                    
                    st.markdown("---")
                    st.subheader("💡 Diagnóstico e Solução Técnica:")
                    st.success("Análise processada com sucesso!")
                    
                    # Exibição limpa da resposta gerada
                    st.markdown(response.text)
                    
                except Exception as e:
                    st.error(f"Ocorreu um erro ao processar a requisição técnica: {e}")
        else:
            st.warning("⚠️ Por favor, insira ou carregue um texto de erro antes de processar a análise.")

with aba2:
    st.subheader("Diretrizes e Boas Práticas para o SIM TCE-CE")
    st.markdown("""
    - **Integridade Referencial (Chaves Estrangeiras):** Certifique-se de que os códigos de relacionamento (como `cd_municipio`, `cd_orgao`, `cd_unid_orc`) foram devidamente enviados e processados nos arquivos base correspondentes ao período.
    - **Sequência de Transmissão:** Respeite rigorosamente a ordem cronológica e a dependência entre os módulos exigidas pelo manual de instruções do TCE-CE.
    - **Formatação de Registros:** Valide a ausência de caracteres especiais indesejados, delimitadores corrompidos ou formatações de datas fora do padrão normativo vigente.
    """)
