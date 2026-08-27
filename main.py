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
    st.error("⚠️ A chave `GEMINI_API_KEY` não foi encontrada! Configure-a nas 'Secrets' do Streamlit Cloud.")
else:
    genai.configure(api_key=api_key)

# ==========================================
# BARRA LATERAL (SIDEBAR)
# ==========================================
with st.sidebar:
    st.image("https://img.icons8.com/color/96/artificial-intelligence.png", width=70)
    st.title("Painel de Controle")
    st.markdown("Ferramenta de suporte técnico para validação e correção de layouts do SIM TCE-CE.")
    
    st.markdown("---")
    st.subheader("⚙️ Configurações")
    
    # Seletor do Módulo do SIM para contextualizar a IA
    modulo_sim = st.selectbox(
        "Módulo / Arquivo do SIM:",
        [
            "Geral / Outros",
            "Veículos / Frotas (VCL)",
            "Licitações e Contratos",
            "Folha de Pagamento",
            "Execução Orçamentária / Despesa",
            "Receita"
        ]
    )
    
    st.markdown("---")
    st.markdown("### 📌 Sobre")
    pages_info = st.markdown(
        "Este assistente utiliza inteligência artificial avançada (`gemini-3.6-flash`) para diagnosticar inconsistências de layout e chaves estrangeiras."
    )

# ==========================================
# TELA PRINCIPAL
# ==========================================
st.title("⚖️ Assistente SIM TCE-CE - Diagnóstico Inteligente")
st.markdown("### Soluções rápidas e precisas para os erros de validação do Tribunal de Contas.")
st.markdown("---")

# Abas para organizar a navegação
aba1, aba2 = st.tabs(["🔍 Diagnóstico de Erros", "💡 Dicas e Padrões Comuns"])

with aba1:
    st.info("Cole abaixo o log de erro ou o trecho do arquivo do SIM TCE-CE que deseja analisar:")
    
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
    if st.button("🚀 Analisar Erro com IA", type="primary"):
        if user_input.strip():
            with st.spinner("Analisando o erro e gerando a solução técnica..."):
                try:
                    # Utilizando o modelo compatível atualizado
                    model = genai.GenerativeModel("gemini-3.6-flash")
                    
                    prompt = f"""
                    Atue como um analista de suporte técnico especialista no sistema SIM do TCE-CE (Tribunal de Contas dos Municípios / Estado do Ceará).
                    O usuário está trabalhando no módulo/contexto de: {modulo_sim}.
                    
                    Analise o erro de validação de dados abaixo, explique de forma clara a causa raiz (ex: chaves estrangeiras ausentes, formato de data, etc.) e forneça o passo a passo objetivo de como corrigir no arquivo ou no banco de dados:

                    {user_input}
                    """
                    
                    response = model.generate_content(prompt)
                    
                    st.markdown("---")
                    st.subheader("💡 Diagnóstico e Solução Recomendada:")
                    st.success("Análise concluída com sucesso!")
                    st.markdown(response.text)
                    
                except Exception as e:
                    st.error(f"Ocorreu um erro ao consultar o Gemini: {e}")
        else:
            st.warning("⚠️ Por favor, insira ou carregue um texto de erro antes de realizar a análise.")

with aba2:
    st.subheader("Orientações e Boas Práticas para o SIM TCE-CE")
    st.markdown("""
    - **Chaves Estrangeiras:** Certifique-se de que os códigos de referência cruzada (como `cd_municipio`, `cd_orgao`, `cd_unid_orc`) foram devidamente enviados e processados nos arquivos principais/anteriores do trimestre/mês correspondente.
    - **Sequência de Importação:** Respeite rigorosamente a ordem de envio dos arquivos estabelecida pelo manual do SIM para evitar falhas de relacionamento relacional.
    - **Formatação de Campos:** Verifique se não há espaços em branco excedentes, delimitadores incorretos ou formatações de data fora do padrão exigido pela instrução normativa vigente.
    """)
