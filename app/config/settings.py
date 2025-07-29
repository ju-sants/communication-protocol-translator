from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SkipValidation
from typing import Dict, Any
import threading

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    LOG_LEVEL: str = "INFO"

    # --- Configurações de Rede ---
    MAIN_SERVER_HOST: str = '127.0.0.1'
    MAIN_SERVER_PORT: int = 12345

    # --- Módulos de Protocolo a serem Carregados ---
    PROTOCOLS: Dict[str, Dict[str, Any]] = {
        "jt808": {
            "port": 65430,
            "handler_path": "app.src.protocols.jt808.handler.handle_connection"
        },
        "gt06": {
            "port": 65431,
            "handler_path": "app.src.protocols.gt06.handler.handle_connection"
        },
        "vl01": {
            "port": 65432,
            "handler_path": "app.src.protocols.vl01.handler.handle_connection"
        }
    }
 
    REDIS_DB_MAIN: int = 2
    REDIS_PASSWORD: str = '...'
    REDIS_HOST: str = '127.0.0.1'
    REDIS_PORT: int = 6379

    jt808_clients: dict = {}
    jt808_clients_lock: SkipValidation = threading.Lock()

settings = Settings()