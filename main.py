import os
import re
import csv
import io
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
# MAPEAMENTO POSICIONAL (SIM 2026)
# ==========================================
LAYOUT_MAPA_SIM_2026 = {
    1: {"campo": "Código do Órgão", "tipo": "Texto/String"},
    2: {"campo": "Tipo de Registro", "tipo": "Numérico/Texto"},
    3: {"campo": "Exercício de Referência", "tipo": "Ano (AAAA)"},
    4: {"campo": "Código da Unidade Gestora (UG)", "tipo": "Texto"},
    5: {"campo": "Sub-elemento / Movimentação", "tipo": "Texto"},
    6: {"campo": "Data do Fato (AAAAMMDD)", "tipo": "Data"},
    7: {"campo": "Chave Principal / Identificador (CPF/CNPJ/Item)", "tipo": "Chave/ID"},
    8: {"campo": "Valor / Quantitativo", "tipo": "Numérico"},
    9: {"campo": "Indicador de Situação / Status", "tipo": "Inteiro"},
    10: {"campo": "Competência (AAAAMM)", "tipo": "Mês/Ano"}
}

def analisar_linha_sim(linha_texto, numero_linha):
    f = io.StringIO(linha_texto.strip())
    leitor = csv.reader(f, delimiter=',', quotechar='"')
    try:
        colunas = next(leitor)
    except StopIteration:
        return {"linha": numero_linha, "status": "Erro", "mensagem": "Linha vazia encontrada."}

    erros_encontrados = []
    for indice, valor in enumerate(colunas, start=1):
        info_coluna = LAYOUT_MAPA_SIM_2026.get(indice, {"campo": f"Coluna Extra {indice}"})
        if indice == 6 and len(valor.strip()) != 8:
            erros_encontrados.append(f"Coluna {indice} ({info_coluna['campo']}): Formato de data inválido ('{valor}'). Esperado AAAAMMDD.")
        if indice == 10 and len(valor.strip()) != 6:
            erros_encontrados.append(f"Coluna {indice} ({info_coluna['campo']}): Competência inválida ('{valor}'). Esperado AAAAMM.")

    if erros_encontrados:
        return {"linha": numero_linha, "status": "Rejeitado", "conteudo": linha_texto.strip(), "erros": erros_encontrados}
    else:
        return {"linha": numero_linha, "status": "Aprovado", "conteudo": linha_texto.strip()}

# ==========================================
# BARRA LATERAL (SIDEBAR)
# ==========================================
with st.sidebar:
    st.image("https://img.icons8.com/color/96/law.png", width=60)
    st.title("Suporte Técnico")
    st.markdown("Ferramenta de validação, diagnóstico e correção de inconsistências de layout do SIM TCE-CE.")
    st.markdown("---")
    st.markdown("### 📌 Orientações")
    st.markdown("Utilize este painel para analisar logs de erro, relatórios de ocorrência e arquivos brutos por posições/colunas.")

# ==========================================
# TELA PRINCIPAL
# ==========================================
st.title("⚖️ Assistente SIM TCE-CE - Diagnóstico Técnico")
st.markdown("### Central de análise e correção de erros de validação do Tribunal de Contas.")
st.markdown("---")

# Abas principais (Adicionada a Aba 3 para o Validador Posicional)
aba1, aba2, aba3 = st.tabs(["🔍 Diagnóstico de Logs", "💡 Padrões e Referências", "📊 Validador Posicional (.dat/.txt)"])

with aba1:
    st.info("Cole abaixo o trecho do relatório de ocorrência ou do arquivo do SIM TCE-CE que necessita de análise:")
    
    col_btn1, col_btn2 = st.columns([1, 1])
    with col_btn1:
        if st.button("📥 Exemplo 1: Erro de Veículos (VCL)"):
            st.session_state["erro_input"] = (
                "BV202607.VCL - DESTINAÇÃO DE VEÍCULOS\n"
                "Descrição: Não há relação com o(s) campo(s) ( cd_municipio, dt_versao_orc, cd_orgao, cd_unid_orc ) que compõe(m) a chave do arquivo UNIDADES_ORCAMENTARIAS."
            )
    with col_btn2:
        if st.button("📥 Exemplo 2: Erro de Contratos (LCO)"):
            st.session_state["erro_input"] = (
                "CO202607.LCO - CONTRATOS\n"
                "Descrição: Gestor responsavel pelo Contrato nao encontrado no cadastro de Ordenadores."
            )
    
    user_input = st.text_area(
        "Cole o erro aqui:",
        value=st.session_state.get("erro_input", ""),
        height=160,
        placeholder="Cole o trecho do relatório de ocorrência..."
    )

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

    if st.button("🚀 Processar Análise", type="primary"):
        if user_input.strip():
            with st.spinner("Processando diagnóstico completo..."):
                try:
                    model = genai.GenerativeModel("gemini-1.5-flash") # Atualizado para um modelo estável padrão
                    prompt = f"""
                    Atue como um analista de suporte técnico especialista no sistema SIM do TCE-CE.
                    Analise o erro de validação de dados abaixo (retirado de relatórios oficiais de ocorrência). 
                    Forneça um diagnóstico estruturado estritamente em duas partes claras:
                    
                    ### Causa Raiz
                    (Explique detalhadamente o motivo da inconsistência de layout, chave estrangeira ou cadastro ausente, citando os campos técnicos envolvidos de forma clara).

                    ### Diretrizes de Correção
                    (Forneça orientações didáticas e normativas focadas estritamente na validação de dados, como por exemplo: verificar se o órgão, unidade orçamentária ou data de versão correspondem exatamente aos cadastros oficiais enviados ao TCE-CE).

                    REGRAS OBRIGATÓRIAS:
                    - NUNCA invente nomes de módulos ou telas de ERP. Foque estritamente nos conceitos, campos e nas regras normativas do SIM TCE-CE.
                    - NÃO utilize scripts SQL, consultas de banco de dados ou comandos de alteração de banco.
                    - Certifique-se de concluir a resposta inteira sem cortes.

                    Erro reportado:
                    {user_input}
                    """
                    
                    response = model.generate_content(prompt, generation_config={"temperature": 0.2, "max_output_tokens": 4096})
                    
                    st.markdown("---")
                    st.success("Análise concluída com sucesso!")
                    st.markdown("### 💡 Diagnóstico e Solução Técnica")
                    st.markdown(response.text)
                    
                except Exception as e:
                    st.error(f"Ocorreu um erro ao processar a requisição técnica: {e}")
        else:
            st.warning("⚠️ Por favor, insira ou carregue um texto de erro antes de processar a análise.")

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

with aba3:
    st.subheader("📊 Validação e Diagnóstico Posicional por Colunas")
    st.markdown("Cole o conteúdo bruto do arquivo do SIM (delimitado por vírgulas e aspas) para identificar em qual **coluna exata** o erro está ocorrendo:")
    
    arquivo_texto_input = st.text_area(
        "Cole as linhas do arquivo (.dat / .txt):",
        value='"992","128",202600,"23","02",20260102,"01142796415",119311,3,202603\n"992","128",202600,"30","01",202612,"01465823139","000100",4,2603',
        height=150
    )
    
    if st.button("🔎 Analisar Posicionamento das Colunas"):
        if arquivo_texto_input.strip():
            linhas = arquivo_texto_input.strip().split("\n")
            st.markdown("---")
            for i, linha in enumerate(linhas, start=1):
                if linha.strip():
                    res = analisar_linha_sim(linha, i)
                    if res["status"] == "Rejeitado":
                        st.error(f"Linha {res['linha']} - Rejeitada:")
                        for err in res["erros"]:
                            st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;• {err}")
                    else:
                        st.success(f"Linha {res['linha']} - Aprovada (Estrutura de colunas correta)")
        else:
            st.warning("⚠️ Insira o conteúdo do arquivo para realizar a varredura posicional.")
