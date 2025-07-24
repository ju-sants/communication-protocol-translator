from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SkipValidation
from typing import Dict
import threading

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    LOG_LEVEL: str = "INFO"

    JT808_LISTENER_PORT: int = 65432
    MAIN_SERVER_HOST: str = '127.0.0.1'
    MAIN_SERVER_PORT: int = 12345

    JT808_TO_SUNTECH_ALERT_MAP: Dict[int, int] = {
        0: 42,  # Bit 0 (SOS) -> Alert 42 (Panic Button)
        1: 1,   # Bit 1 (Over-speed) -> Alert 1 (Over Speed)
        5: 3,   # Bit 5 (GNSS Antenna not connected) -> Alert 3 (GPS Antenna Disconnected)
        8: 41,  # Bit 8 (Main power cut off) -> Alert 41 (Power Disconnected)
        27: 73, # Bit 27 (Illegal fire) -> Alert 73 (Anti-Theft)
        20: 5,  # Bit 20 (in/out area) -> Usaremos 5 (Exit) ou 6 (Enter)
        21: 5,  # Bit 21 (in/out routine) -> Usaremos 5 (Exit) ou 6 (Enter)
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