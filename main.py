import os
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
# BARRA LATERAL (SIDEBAR)
# ==========================================
with st.sidebar:
    st.image("https://img.icons8.com/color/96/law.png", width=60)
    st.title("Suporte Técnico")
    st.markdown("Ferramenta de validação, diagnóstico e correção de inconsistências de layout do SIM TCE-CE.")
    
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

aba1, aba2 = st.tabs(["🔍 Diagnóstico de Erros", "💡 Padrões e Referências"])

with aba1:
    st.info("Cole abaixo o log de erro ou o trecho do arquivo do SIM TCE-CE que necessita de análise:")
    
    # Botão de Exemplo Rápido
    col_btn1, col_btn2 = st.columns([2, 5])
    with col_btn1:
        if st.button("📥 Carregar Exemplo (Veículos)"):
            st.session_state["erro_input"] = (
                "BV202607.VCL - BAIXA NA DESTINAÇÃO DE VEÍCULOS\n"
                "Descrição: Não há relação com o(s) campo(s) ( cd_municipio, dt_versao_orc, cd_orgao, "
                "cd_unid_orc, dt_inclusao_vd, cd_renavam_vm ) que compõe(m) a chave do arquivo VEICULOS_DESTINACOES."
            )
    
    # Área de texto
    user_input = st.text_area(
        "Cole o erro aqui:",
        value=st.session_state.get("erro_input", ""),
        height=160,
        placeholder="Cole o log do erro retornado pelo validador do SIM..."
    )

    # Botão de Ação Principal
    if st.button("🚀 Processar Análise", type="primary"):
        if user_input.strip():
            with st.spinner("Processando diagnóstico otimizado..."):
                try:
                    # Configuração de velocidade e restrição de escopo via prompt
                    model = genai.GenerativeModel("gemini-3.6-flash")
                    
                    prompt = f"""
                    Atue como um analista de suporte técnico especialista no sistema SIM do TCE-CE.
                    Analise o erro de validação de dados abaixo. Forneça um diagnóstico direto e objetivo contendo:
                    1. A causa raiz da inconsistência no layout ou nos arquivos de envio.
                    2. O passo a passo normativo de como corrigir diretamente nos lançamentos ou arquivos do sistema (NÃO utilize scripts SQL, consultas de banco de dados ou comandos de alteração de banco, pois a correção é estritamente via interface ou reexportação de arquivos).

                    Erro reportado:
                    {user_input}
                    """
                    
                    # Otimizando a velocidade de resposta com parâmetros de geração restritos
                    generation_config = {
                        "temperature": 0.2,
                        "max_output_tokens": 1024,
                    }
                    
                    response = model.generate_content(prompt, generation_config=generation_config)
                    
                    st.markdown("---")
                    st.subheader("💡 Diagnóstico e Diretrizes de Correção:")
                    st.success("Análise concluída com alta performance!")
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
