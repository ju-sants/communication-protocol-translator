from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Dict, Any

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    LOG_LEVEL: str = "INFO"

    API_BASE_URL: str = "..."
    API_X_TOKEN: str = "..."
    API_ORIGIN: str = "..."
    API_REFERER: str = "..."

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
        "j16w": {
            "port": 65430,
            "handler_path": "app.src.input.j16w.handler.handle_connection"
        },
        "j16x_j16": {
            "port": 65431,
            "handler_path": "app.src.input.j16x_j16.handler.handle_connection"
        },
        "vl01": {
            "port": 65432,
            "handler_path": "app.src.input.vl01.handler.handle_connection"
        },
        "nt40": {
            "port": 65433,
            "handler_path": "app.src.input.nt40.handler.handle_connection"
        },
        "satellite": {
            "port": 65434,
            "handler_path": "app.src.input.satellite.handler.handle_connection"
        },
        "suntech2g": {
            "port": 65435,
            "handler_path": "app.src.input.suntech2g.handler.handle_connection"
        },
        "suntech4g": {
            "port": 65436,
            "handler_path": "app.src.input.suntech4g.handler.handle_connection"
        }
    }

     # -------------- Dicionários Globais Para IDs de Alerta ----------------------
    UNIVERSAL_ALERT_ID_DICTIONARY: Dict[str, Dict[int, int]] = {
        "suntech4g": {
            1: 6501, 3: 6503, 4: 6504, 5: 6505, 6: 6506, 14: 6514, 15: 6515, 17: 6517, 33: 6533, 34: 6534,
            40: 6540, 41: 6541, 42: 6542, 46: 6546, 47: 6547, 73: 6573, 147: 6647
        },
        "suntech2g": {
            1: 6501, 14: 6514, 15: 6515, 17: 6517, 40: 6540,
            41: 6541
        },
        "j16x_j16": {
            0x01: 6542, 0x02: 6541, 0x19: 6514, 0x03: 6515, 0x06: 6501, 0xF0: 6546,
            0xF1: 6547, 0x04: 6506, 0x05: 6505, 0x13: 6647, 0x14: 6573, 0xFE: 6533,
            0xFF: 6534
        },
        # "jt808": {
        #     0: 6542, 1: 6501, 5: 6503, 8: 6541, 27: 6573, 20: 6505, 21: 6505
        # },
        "vl01": {
            0x01: 6542, 0x02: 6541, 0x03: 6515, 0x04: 6506, 0x05: 6505, 0x06: 6501,
            0x19: 6514, 0xF0: 6546, 0xF1: 6547, 0x13: 6647, 0x14: 7653, 0xFE: 6533,
            0xFF: 6534
        },
        "nt40": {
            0x01: 6542, 0x02: 6541, 0x03: 6515, 0x04: 6533, 0x05: 6534, 0x12: 6647
        }
    }

    # Mapeamento reverso para consultas mais rápidas
    REVERSE_UNIVERSAL_ALERT_ID_DICTIONARY: Dict[str, Dict[int, int]] = {
        protocol: {v: k for k, v in alerts.items()}
        for protocol, alerts in UNIVERSAL_ALERT_ID_DICTIONARY.items()
    }

settings = Settings()