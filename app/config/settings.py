from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Dict, Any

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    LOG_LEVEL: str = "INFO"

    # --- Configurações de Rede e Credenciais ---
    SUNTECH_MAIN_SERVER_HOST: str = '127.0.0.1'
    SUNTECH_MAIN_SERVER_PORT: int = 12345

    GT06_MAIN_SERVER_HOST: str = '127.0.0.1'
    GT06_MAIN_SERVER_PORT: int = 12345
 
    REDIS_DB_MAIN: int = 2
    REDIS_PASSWORD: str = '...'
    REDIS_HOST: str = '127.0.0.1'
    REDIS_PORT: int = 6379

    # --- Módulos de Protocolo a serem Carregados ---
    INPUT_PROTOCOL_HANDLERS: Dict[str, Dict[str, Any]] = {
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
        },
        "nt40": {
            "port": 65433,
            "handler_path": "app.src.protocols.nt40.handler.handle_connection"
        },
        "satellite": {
            "port": 65434,
            "handler_path": "app.src.protocols.satellite.handler.handle_connection"
        }
    }
 
    REDIS_DB_MAIN: int = 2
    REDIS_PASSWORD: str = '...'
    REDIS_HOST: str = '127.0.0.1'
    REDIS_PORT: int = 6379

settings = Settings()