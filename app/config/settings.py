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
            "port": 65432,
            "handler_path": "app.src.protocols.jt808.handler.handle_connection"
        },
        "gt06": {
            "port": 65433,
            "handler_path": "app.src.protocols.gt06.handler.handle_connection"
        }
    }

    # IDs de Alerta Suntech que são INFERIDOS, não traduzidos diretamente
    SUNTECH_IGNITION_ON_ALERT_ID: int = 33
    SUNTECH_IGNITION_OFF_ALERT_ID: int = 34
    SUNTECH_POWER_CONNECTED_ALERT_ID: int = 40
    SUNTECH_POWER_DISCONNECTED_ALERT_ID: int = 41

    # IDs de Alerta Suntech para Geocerca (baseado na direção)
    SUNTECH_GEOFENCE_ENTER_ALERT_ID: int = 6
    SUNTECH_GEOFENCE_EXIT_ALERT_ID: int = 5
    
    REDIS_DB_MAIN: int = 2
    REDIS_PASSWORD: str = '...'
    REDIS_HOST: str = '127.0.0.1'
    REDIS_PORT: int = 6379

    jt808_clients: dict = {}
    jt808_clients_lock: SkipValidation[threading.Lock] = threading.Lock()

settings = Settings()