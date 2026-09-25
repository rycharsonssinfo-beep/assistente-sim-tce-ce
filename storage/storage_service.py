import os
import pandas as pd
import json
from pathlib import Path

class StorageService:
    """
    Serviço responsável por gerenciar o armazenamento local de dados
    em formato Parquet e metadados/configurações em JSON.
    """
    def __init__(self, base_dir: str = "data"):
        self.base_dir = Path(base_dir)
        self.api_dir = self.base_dir / "api"
        self.metadata_dir = self.base_dir / "metadata"
        self.historico_dir = self.base_dir / "historico"
        self.logs_dir = self.base_dir / "logs"
        
        # Garante que a árvore de diretórios base exista
        for d in [self.api_dir, self.metadata_dir, self.historico_dir, self.logs_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def save_parquet(self, tipo: str, exercicio: int, df: pd.DataFrame) -> None:
        """Salva um DataFrame pandas no formato Parquet otimizado."""
        target_dir = self.api_dir / tipo.upper() / str(exercicio)
        target_dir.mkdir(parents=True, exist_ok=True)
        file_path = target_dir / "data.parquet"
        df.to_parquet(file_path, index=False)

    def read_parquet(self, tipo: str, exercicio: int) -> pd.DataFrame:
        """Lê um arquivo Parquet e retorna um DataFrame pandas."""
        file_path = self.api_dir / tipo.upper() / str(exercicio) / "data.parquet"
        if file_path.exists():
            return pd.read_parquet(file_path)
        return pd.DataFrame()

    def save_json(self, sub_dir: str, filename: str, data: dict) -> None:
        """Salva um dicionário em formato JSON."""
        target_dir = self.base_dir / sub_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        file_path = target_dir / filename
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def read_json(self, sub_dir: str, filename: str) -> dict:
        """Lê um arquivo JSON e retorna um dicionário."""
        file_path = self.base_dir / sub_dir / filename
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}
