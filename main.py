import streamlit as st
from services.tce_api import TCEApiClient
from storage.storage_service import StorageService
from services.error_validation_service import ErrorValidationService
import pandas as pd

# Configuração inicial da página Streamlit
st.set_page_config(
    page_title="Assistente SIM/TCE-CE",
    page_icon="📊",
    layout="wide"
)

# Inicialização dos serviços
storage = StorageService()
api_client = TCEApiClient()

def main():
    st.title("📊 Plataforma de Análise e Validação SIM/TCE-CE")
    st.markdown("Bem-vindo ao assistente modular para análise de divergências, validação de arquivos e consumo de dados do SIM.")

    # Menu lateral para navegação simples
    st.sidebar.header("Navegação")
    opcao = st.sidebar.selectbox(
        "Escolha a funcionalidade:",
        ["Visão Geral", "Consulta API TCE", "Validação de Erros"]
    )

    if opcao == "Visão Geral":
        st.subheader("Painel de Controle")
        st.info("Utilize o menu lateral para navegar entre o consumo de dados da API do TCE-CE e os módulos de validação de erros.")
        
        # Exibe métricas rápidas de armazenamento local se houver
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
                        st.success(f"Foram encontrados {len(df)} registros com sucesso!")
                        st.dataframe(df.head(10))
                        
                        # Salvando localmente em Parquet
                        storage.save_parquet(endpoint.replace("/", "_"), 2026, df)
                        st.info("Dados salvos com sucesso no armazenamento local em formato Parquet.")
                    else:
                        st.warning("Nenhum registro retornado para este endpoint.")
                except Exception as e:
                    st.error(f"Ocorreu um erro ao consultar a API: {e}")

    elif opcao == "Validação de Erros":
        st.subheader("Módulo de Verificação de Erros do SIM")
        st.markdown("Insira as regras de validação ou selecione o layout para verificar inconsistências estruturais.")
        
        # Exemplo prático de teste do ErrorValidationService
        campo_obrigatorio = st.text_input("Campo obrigatório para testar (ex: codigo_orgao)", value="codigo_orgao")
        
        if st.button("Executar Simulação de Validação"):
            layout_exemplo = {"campos_obrigatorios": [campo_obrigatorio]}
            validador = ErrorValidationService(layout_exemplo)
            
            # Dados simulados para teste
            dados_teste = [
                {campo_obrigatorio: "123", "descricao": "Órgão A"},
                {campo_obrigatorio: "", "descricao": "Órgão B (Erro esperado)"},
                {campo_obrigatorio: "456", "descricao": "Órgão C"}
            ]
            
            resultados = validador.validate_records(dados_teste)
            
            if resultados:
                st.warning(f"Foram encontrados erros em {len(resultados)} registro(s):")
                st.json(resultados)
            else:
                st.success("Nenhum erro encontrado nos dados de teste!")

if __name__ == "__main__":
    main()
