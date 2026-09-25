import streamlit as st
import google.generativeai as genai
from services.tce_api import TCEApiClient
from storage.storage_service import StorageService
from services.error_validation_service import ErrorValidationService
import pandas as pd
import io

# Configuração inicial da página Streamlit
st.set_page_config(
    page_title="Assistente SIM/TCE-CE com IA",
    page_icon="📊",
    layout="wide"
)

# Inicialização dos serviços
storage = StorageService()
api_client = TCEApiClient()

def main():
    st.title("📊 Plataforma Inteligente de Análise e Validação SIM/TCE-CE")
    st.markdown("Assistente modular para análise de divergências, validação de layouts do SIM e consultoria via Inteligência Artificial.")

    # Menu lateral completo com todas as funcionalidades e IA
    st.sidebar.header("Navegação e Ferramentas")
    opcao = st.sidebar.selectbox(
        "Escolha a funcionalidade:",
        ["Visão Geral", "Consulta API TCE", "Validação e Leitura de Ficheiros SIM", "Análise Inteligente por IA"]
    )

    if opcao == "Visão Geral":
        st.subheader("Painel de Controle")
        st.info("Utilize o menu lateral para alternar entre o consumo de dados da API, o módulo de envio e validação de ficheiros do SIM linha a linha, e a Análise por IA.")
        
        api_path = storage.base_dir / "api"
        if api_path.exists():
            st.success("Diretório de dados locais inicializado com sucesso!")
        else:
            st.warning("Nenhum dado local encontrado ainda.")

    elif opcao == "Consulta API TCE":
        st.subheader("Consulta de Dados Abertos - TCE-CE")
        endpoint = st.text_input("Endpoint da API (ex: orgaos, contratos)", value="orgaos")
        
        if st.button("Consultar e Salvar Dados"):
            with st.spinner("Buscando dados na API do TCE-CE..."):
                try:
                    dados = api_client.request(endpoint)
                    if dados:
                        df = pd.DataFrame(dados)
                        st.success(f"Foram encontrados {len(df)} registos com sucesso!")
                        st.dataframe(df.head(10))
                        
                        storage.save_parquet(endpoint.replace("/", "_"), 2026, df)
                        st.info("Dados salvos com sucesso no armazenamento local em formato Parquet.")
                    else:
                        st.warning("Nenhum registo retornado para este endpoint.")
                except Exception as e:
                    st.error(f"Ocorreu um erro ao consultar a API: {e}")

    elif opcao == "Validação e Leitura de Ficheiros SIM":
        st.subheader("Módulo de Envio e Verificação de Erros do SIM")
        st.markdown("Carregue o seu ficheiro de dados do SIM (ex: CSV ou TXT) para inspecionar os erros linha a linha e validar os campos obrigatórios.")
        
        # Componente para carregar o ficheiro real
        uploaded_file = st.file_uploader("Selecione o ficheiro do SIM (CSV, TXT)", type=["csv", "txt"])
        
        # Campo para definir quais colunas são obrigatórias na validação
        campos_obrigatorios_input = st.text_input(
            "Campos obrigatórios (separados por vírgula)", 
            value="codigo_orgao, exercicio, valor"
        )
        
        if uploaded_file is not None:
            try:
                # Leitura dinâmica baseada no tipo de ficheiro
                if uploaded_file.name.endswith('.csv'):
                    df_upload = pd.read_csv(uploaded_file)
                else:
                    # Tenta ler como delimitado ou texto estruturado
                    df_upload = pd.read_csv(uploaded_file, sep=None, engine='python')
                
                st.write("### Pré-visualização dos Dados Carregados:")
                st.dataframe(df_upload.head(10))
                
                if st.button("Executar Validação de Erros Linha a Linha"):
                    campos_obs = [c.strip() for c in campos_obrigatorios_input.split(",") if c.strip()]
                    layout_config = {"campos_obrigatorios": campos_obs}
                    
                    validador = ErrorValidationService(layout_config)
                    registos = df_upload.to_dict(orient="records")
                    
                    resultados = validador.validate_records(registos)
                    
                    if resultados:
                        st.error(f"Atenção: Foram encontrados erros em {len(resultados)} linha(s) do ficheiro!")
                        df_erros = pd.DataFrame([
                            {
                                "Linha": res["linha"],
                                "Erros Detectados": "; ".join([e["mensagem"] for e in res["erros"]])
                            }
                            for res in resultados
                        ])
                        st.dataframe(df_erros)
                        
                        with st.expander("Ver registos detalhados com erro"):
                            st.json(resultados)
                    else:
                        st.success("Parabéns! Nenhum erro de campo obrigatório foi encontrado no ficheiro enviado.")
            except Exception as e:
                st.error(f"Erro ao processar o ficheiro: {e}")

    elif opcao == "Análise Inteligente por IA":
        st.subheader("Assistente de Análise com Inteligência Artificial (Google Gemini)")
        st.markdown("Insira a sua chave de API do Gemini e cole os dados ou mensagens de erro para que a IA ajude a diagnosticar as divergências do SIM/TCE-CE.")
        
        api_key_input = st.text_input("Insira a sua Google Gemini API Key", type="password")
        prompt_usuario = st.text_area("Descreva a divergência, cole o log de erro ou os dados para análise:")
        
        if st.button("Analisar com IA"):
            if not api_key_input:
                st.warning("Por favor, insira a chave da API do Gemini.")
            elif not prompt_usuario:
                st.warning("Por favor, escreva uma instrução ou cole os dados para a IA analisar.")
            else:
                with st.spinner("A IA está a analisar o seu pedido..."):
                    try:
                        genai.configure(api_key=api_key_input)
                        model = genai.GenerativeModel('gemini-pro')
                        response = model.generate_content(
                            f"Você é um especialista técnico em auditoria de contas públicas, divergências do SIM e padrões do TCE-CE. Analise o seguinte contexto:\n\n{prompt_usuario}"
                        )
                        st.success("Análise Concluída:")
                        st.markdown(response.text)
                    except Exception as e:
                        st.error(f"Erro ao comunicar com a API do Gemini: {e}")

if __name__ == "__main__":
    main()
