import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

class ErrorValidationService:
    """
    Módulo genérico de verificação de erros estruturais e de conteúdo nos arquivos do SIM.
    """
    def __init__(self, layout_config: Dict[str, Any]):
        self.layout_config = layout_config

    def validate_records(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        validation_results = []
        required_fields = self.layout_config.get("campos_obrigatorios", [])
        
        for index, record in enumerate(records, start=1):
            erros_linha = []
            
            # Validação de Campos Obrigatórios / Nulos
            for field in required_fields:
                val = record.get(field)
                if val is None or str(val).strip() == "":
                    erros_linha.append({
                        "tipo_erro": "CAMPO_OBRIGATORIO_VAZIO",
                        "campo": field,
                        "mensagem": f"O campo obrigatório '{field}' está vazio ou ausente."
                    })
            
            if erros_linha:
                validation_results.append({
                    "linha": index,
                    "registro": record,
                    "status": "ERRO NO ARQUIVO",
                    "erros": erros_linha
                })
                
        return validation_results
