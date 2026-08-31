import json
import os
import sqlite3
import time
import google.generativeai as genai
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import streamlit as st

# ==========================================
# 1. CONFIGURAÇÃO DA PÁGINA E DESIGN SYSTEM
# ==========================================
st.set_page_config(
    page_title="Assistente SIM TCE-CE",
    page_icon="🤖",
    layout="wide",
)

st.markdown(
    """
    <style>
    :root {
        --bg-main: #F4F6F9;
        --surface: #FFFFFF;
        --border-color: #CBD5E1;
        --border-subtle: #E2E8F0;
        --text-main: #0F172A;
        --text-secondary: #334155;
        --text-muted: #64748B;
        --primary: #0284C7;
        --primary-hover: #0369A1;
    }
    .main {
        background-color: var(--bg-main);
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ==========================================
# 2. MÓDULO DE AUDITORIA E CONCILIAÇÃO CRUZADA
# ==========================================
def renderizar_modulo_auditoria():
    st.subheader("📊 Módulo de Conciliação e Auditoria Cruzada")
    st.markdown("Envie sua planilha CSV ou Excel para comparar os dados informados com o histórico oficial.")

    # Base de dados simulada (Histórico Oficial do Sistema / Banco)
    banco_historico = pd.DataFrame([
        {"contrato": "CT-2026/001", "cpf_gestor": "123.456.789-00", "status_assinatura": "Ativo"},
        {"contrato": "CT-2026/002", "cpf_gestor": "987.654.321-11", "status_assinatura": "Pendente"}
    ])

    # Upload do arquivo
    arquivo_enviado = st.file_uploader("Selecione o arquivo de contratos (CSV ou XLSX)", type=["csv", "xlsx"])

    if arquivo_enviado is not None:
        # Leitura baseada na extensão
        if arquivo_enviado.name.endswith('.csv'):
            df_arquivo = pd.read_csv(arquivo_enviado)
        else:
            df_arquivo = pd.read_excel(arquivo_enviado)

        st.success(f"Arquivo carregado com sucesso! {len(df_arquivo)} linhas encontradas.")

        # Opção de filtro visual
        apenas_erros = st.checkbox("Exibir apenas contratos com divergências ou não encontrados")

        st.markdown("---")

        # Processamento e Cruzamento dos Dados
        resultados = []
        for _, linha in df_arquivo.iterrows():
            contrato_alvo = str(linha.get("contrato", ""))
            match = banco_historico[banco_historico["contrato"] == contrato_alvo]

            if match.empty:
                status_geral = "NAO_ENCONTRADO"
                divergencias = ["Contrato ausente na base histórica"]
                hist_dados = None
            else:
                hist_row = match.iloc[0]
                divergencias = []
                
                if str(linha.get("cpf_gestor")) != str(hist_row["cpf_gestor"]):
                    divergencias.append("cpf_gestor")
                if str(linha.get("assinatura")) != str(hist_row["status_assinatura"]):
                    divergencias.append("assinatura")

                status_geral = "DIVERGENTE" if divergencias else "CONCILIADO"
                hist_dados = hist_row

            resultados.append({
                "contrato": contrato_alvo,
                "status": status_geral,
                "arquivo": linha,
                "historico": hist_dados,
                "divergencias": divergencias
            })

        # Renderização visual em Cards Comparativos
        for res in resultados:
            if apenas_erros and res["status"] == "CONCILIADO":
                continue

            cor_badge = "green" if res["status"] == "CONCILIADO" else ("red" if res["status"] == "NAO_ENCONTRADO" else "orange")

            with st.container():
                cols_cabecalho = st.columns([3, 1])
                cols_cabecalho[0].markdown(f"**Contrato: {res['contrato']}**")
                cols_cabecalho[1].markdown(f":{cor_badge}[**{res['status']}**]")

                col1, col2 = st.columns(2)
                
                with col1:
                    st.info(f"**Dados do Arquivo:**\n\n- CPF Gestor: {res['arquivo'].get('cpf_gestor')}\n- Assinatura: {res['arquivo'].get('assinatura')}")
                
                with col2:
                    if res["historico"] is not None:
                        cpf_cor = "red" if "cpf_gestor" in res["divergencias"] else "inherit"
                        ass_cor = "red" if "assinatura" in res["divergencias"] else "inherit"
                        st.success(f"**Histórico do Sistema:**\n\n- CPF Gestor: :{cpf_cor}[{res['historico']['cpf_gestor']}]\n- Assinatura: :{ass_cor}[{res['historico']['status_assinatura']}]")
                    else:
                        st.error("**Histórico do Sistema:**\n\nRegistro não localizado na base oficial.")
                
                st.markdown("---")

# ==========================================
# 3. ESTRUTURA PRINCIPAL DE NAVEGAÇÃO
# ==========================================
def main():
    st.sidebar.title("Navegação")
    opcao = st.sidebar.radio("Selecione a Página:", ["Assistente IA", "Auditoria e Conciliação"])

    if opcao == "Assistente IA":
        st.title("🤖 Assistente SIM TCE-CE")
        st.write("Bem-vindo ao assistente inteligente.")
        # Adicione aqui o restante da lógica original do seu chat / assistente
    elif opcao == "Auditoria e Conciliação":
        renderizar_modulo_auditoria()

if __name__ == "__main__":
    main()
