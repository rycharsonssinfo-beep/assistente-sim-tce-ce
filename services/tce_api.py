import requests
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class TCEApiClient:
    """
    Cliente universal para consumo da API de Dados Abertos do SIM/TCE-CE.
    """
    def __init__(self, base_url: str = "https://dados.tce.ce.gov.br/api/v1/"):
        self.base_url = base_url

    def request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        params = params or {}
        params.setdefault('$format', 'json')
        params.setdefault('$count', 1000)
        
        all_elements = []
        start_index = 0
        
        try:
            while True:
                params['$start_index'] = start_index
                response = requests.get(url, params=params, timeout=30)
                
                if response.status_code != 200:
                    logger.error(f"Erro na API {endpoint}: Status {response.status_code} - {response.text}")
                    break
                
                data = response.json()
                elements = data.get('elements', [])
                
                if not elements:
                    break
                    
                all_elements.extend(elements)
                
                if len(elements) < 1000:
                    break
                    
                start_index += 1000
                
        except Exception as e:
            logger.exception(f"Exceção ao requisitar {endpoint}: {e}")
            raise
            
        return all_elements
