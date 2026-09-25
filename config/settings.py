import os
from pathlib import Path

# Diretórios principais
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

# Configuração da API do TCE-CE
TCE_API_BASE_URL = "https://dados.tce.ce.gov.br/api/v1/"

# Configurações de logging ou outras globais da aplicação
LOG_LEVEL = "INFO"
