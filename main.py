import os
import streamlit as st
import google.generativeai as genai

# Configuração da página do Streamlit
st.set_page_config(
    page_title="Assistente SIM TCE-CE",
    page_icon="🤖",
    layout="wide"
)

# Configuração da Chave da API do Gemini (Lê das Secrets do Streamlit ou do ambiente)
api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")

if not api_key:
    st.error("⚠️ A chave `GEMINI_API_KEY` não foi encontrada! Configure-a nas 'Secrets' do Streamlit Cloud.")
else:
    genai.configure(api_key=api_key)

# Título da aplicação
st.title("🤖 Assistente SIM TCE-CE - Diagnóstico e Correção de Erros")
st.write("Bem-vindo ao seu assistente inteligente integrado ao Google Gemini.")

# --- COLOQUE AQUI A SUA LÓGICA / INTERFACE DO STREAMLIT ---
# Exemplo de campo de entrada para os erros do SIM:
user_input = st.text_area("Cole aqui o erro ou trecho do arquivo do SIM TCE-CE para análise:")

if st.button("Analisar Erro"):
    if user_input:
        with st.spinner("Analisando com o Gemini..."):
            try:
                # Usando o modelo recomendado do Gemini
                model = genai.GenerativeModel("gemini-1.5-flash")
                prompt = f"Atue como um especialista técnico no sistema SIM do TCE-CE. Analise e corrija o seguinte erro:\n\n{user_input}"
                response = model.generate_content(prompt)
                
                st.subheader("💡 Diagnóstico e Solução:")
                st.markdown(response.text)
            except Exception as e:
                st.error(f"Ocorreu um erro ao consultar o Gemini: {e}")
    else:
        st.warning("Por favor, insira um texto para análise.")