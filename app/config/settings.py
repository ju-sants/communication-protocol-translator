from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Dict, Any, Union

import os

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    LOG_LEVEL: str = "INFO"

    # --- Configurações Gerais do Servidor ---
    STANDARD_HYBRID_OUTPUT_PROTOCOL: str = "gt06" # Protocolo de Saída padrão para dispositivos híbridos
    
    AUTO_GT06_OUTPUT_PROTOCOLS: list = ["gp900m", "j16w", "j16x-j16", "j16x_j16", "vl01", "vl03"]
    AUTO_SUNTECH_OUTPUT_PROTOCOLS: list = ["satellital", "nt40", "suntech2g", "suntech4g"]

    # --- Configurações para history service ---
    HISTORY_LIMIT: int = 10000
    DISK_BATCH_SIZE: int = 500
    CACHE_DIR: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/cache"
    HISTORY_SERVICE_QUEUE: str = "history_service:packet_queue"

    # --- Configurações de Rede e Credenciais ---
    SUNTECH_MAIN_SERVER_HOST: str = '127.0.0.1'
    SUNTECH_MAIN_SERVER_PORT: int = 12345

    GT06_MAIN_SERVER_HOST: str = '127.0.0.1'
    GT06_MAIN_SERVER_PORT: int = 12345
 
    REDIS_DB_MAIN: int = 2
    REDIS_PASSWORD: str = '...'
    REDIS_HOST: str = '127.0.0.1'
    REDIS_PORT: int = 6379

    API_BASE_URL: str = "..."
    API_X_TOKEN: str = "..."
    API_ORIGIN: str = "..."
    API_REFERER: str = "..."

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
        "satellital": {
            "port": 65434,
            "handler_path": "app.src.input.satellital.handler.handle_connection"
        },
        "suntech2g": {
            "port": 65435,
            "handler_path": "app.src.input.suntech2g.handler.handle_connection"
        },
        "suntech4g": {
            "port": 65436,
            "handler_path": "app.src.input.suntech4g.handler.handle_connection"
        },
        "gp900m": {
            "port": 65437,
            "handler_path": "app.src.input.gp900m.handler.handle_connection"
        },
        "vl03": {
            "port": 65438,
            "handler_path": "app.src.input.vl03.handler.handle_connection"
        }
    }

    # -------------- Dicionários Globais Para IDs de Alerta ----------------------
    UNIVERSAL_ALERT_ID_GLOSSARY: Dict[int, str] = {
        6501: "Over Speed",
        6502: "Under Speed",
        6503: "GPS Antenna Disconnected",
        6504: "GPS Antenna Connected",
        6505: "Exit Geofence",
        6506: "Enter Geofence",
        6514: "Battery Low",
        6515: "Shocked",
        6517: "Motion Detected",
        6533: "Ignition On",
        6534: "Ignition Off",
        6540: "Power Connected",
        6541: "Power Disconnected",
        6542: "Panic Button",
        6573: "Anti Theft",
    }

    UNIVERSAL_ALERT_ID_DICTIONARY: Dict[str, Dict[int, Union[int, str]]] = {
        "suntech4g": {
            1: 6501, 3: 6503, 4: 6504, 5: 6505, 6: 6506, 14: 6514, 15: 6515, 17: 6517, 33: 6533, 34: 6534,
            40: 6540, 41: 6541, 42: 6542, 73: 6573
        },
        "suntech2g": {
            1: 6501, 14: 6514, 15: 6515, 17: 6517, 40: 6540,
            41: 6541
        },
        "j16x_j16": {
            0x01: 6542, 0x02: 6541, 0x19: 6514, 0x03: 6515, 0x06: 6501,
            0x04: 6506, 0x05: 6505, 0x14: 6573, 0xFE: 6533, 0xFF: 6534
        },
        # "jt808": {
        #     0: 6542, 1: 6501, 5: 6503, 8: 6541, 27: 6573, 20: 6505, 21: 6505
        # },
        "vl01": {
            0x01: 6542, 0x02: 6541, 0x03: 6515, 0x04: 6506, 0x05: 6505, 0x06: 6501,
            0x19: 6514, 0xF0: 6546, 0xF1: 6547, 0xFE: 6533, 0xFF: 6534
        },
        "vl03": {
            0x01: 6542, 0x02: 6541, 0x03: 6515, 0x04: 6506, 0x05: 6505, 0x06: 6501,
            0x19: 6514, 0xF0: 6546, 0xF1: 6547, 0xFE: 6533, 0xFF: 6534
        },
        "nt40": {
            0x01: 6542, 0x02: 6541, 0x03: 6515, 0x04: 6533, 0x05: 6534, 0x12: 6647
        },
        "gp900m": {
            0x04: 6541, 0x05: 6540, 0x13: 6501, 0x14: 6502, 0x1C: 6517, 0x0E: 6533, 0x0F: 6534, 0x1020: 6533, 0x1000: 6534,
            0x0C: "OUTPUT ON", 0x0D: "OUTPUT OFF"
        }
    }

    # Mapeamento reverso para consultas mais rápidas
    REVERSE_UNIVERSAL_ALERT_ID_DICTIONARY: Dict[str, Dict[Union[str, int], int]] = {
        protocol: {v: k for k, v in alerts.items()}
        for protocol, alerts in UNIVERSAL_ALERT_ID_DICTIONARY.items()
    }

settings = Settings()