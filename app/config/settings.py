from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Dict, Any
import os

from app.src.output.suntech.utils import (
    build_location_packet as build_suntech_alert_location_packet,
    build_heartbeat_packet as build_suntech_heartbeat_packet, 
    build_reply_packet as build_suntech_reply_packet
)

from app.src.output.gt06.utils import (
    build_location_packet as build_gt06_location_packet,
    build_heartbeat_packet as build_gt06_heartbeat_packet,
    build_reply_packet as build_gt06_reply_packet,
    build_alarm_packet as build_gt06_alarm_packet
)

from app.src.protocols.jt808.builder import process_suntech_command as process_suntech_command_to_jt808
from app.src.protocols.gt06.builder import process_suntech_command as process_suntech_command_to_gt06
from app.src.protocols.vl01.builder import process_suntech_command as process_suntech_command_to_vl01
from app.src.protocols.nt40.builder import process_suntech_command as process_suntech_command_to_nt40
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

     # -------------- Dicionários Globais Para IDs de Alerta ----------------------
    GLOBAL_ALERT_ID_DICTIONARY = {
        "suntech": {
            1: 6501, 3: 6503, 4: 6504, 5: 6505, 6: 6506, 14: 6514, 15: 6515, 33: 6533, 34: 6534,
            41: 6541, 42: 6542, 46: 6546, 47: 6547, 73: 6573, 147: 6647
        },
        "gt06": {
            0x01: 6542, 0x02: 6541, 0x19: 6514, 0x03: 6515, 0x06: 6501, 0xF0: 6546,
            0xF1: 6547, 0x04: 6506, 0x05: 6505, 0x13: 6647, 0x14: 6573, 0xFE: 6533,
            0xFF: 6534
        },
        "jt808": {
            0: 6542, 1: 6501, 5: 6503, 8: 6541, 27: 6573, 20: 6505, 21: 6505
        },
        "vl01": {
            0x01: 6542, 0x02: 6541, 0x03: 6515, 0x04: 6506, 0x05: 6505, 0x06: 6501,
            0x19: 6514, 0xF0: 6546, 0xF1: 6547, 0x13: 6647, 0x14: 7653, 0xFE: 6533,
            0xFF: 6534
        },
        "nt40": {
            0x01: 6542, 0x02: 6541, 0x03: 6515, 0x04: 33, 0x05: 6534, 0x12: 6647
        }
    }

    # Mapeamento reverso para consultas mais rápidas
    REVERSE_GLOBAL_ALERT_ID_DICTIONARY = {
        protocol: {v: k for k, v in alerts.items()}
        for protocol, alerts in GLOBAL_ALERT_ID_DICTIONARY.items()
    }


    # ---------- Utilitários para os protocolos de saída --------------------
    OUTPUT_PROTOCOL_PACKET_BUILDERS: Dict[str, Dict[str, Any]] = {
        "suntech": {
            "location": build_suntech_alert_location_packet,
            "alert": build_suntech_alert_location_packet,
            "heartbeat": build_suntech_heartbeat_packet,
            "command_reply": build_suntech_reply_packet
            },
        "gt06": {
            "location": build_gt06_location_packet,
            "alert": build_gt06_alarm_packet,
            "heartbeat": build_gt06_heartbeat_packet,
            "command_reply": build_gt06_reply_packet
            }
    }

    OUTPUT_PROTOCOL_COMMAND_PROCESSORS: Dict[str, Dict[str, Any]] = {
        "suntech": {
            "jt808": process_suntech_command_to_jt808,
            "gt06": process_suntech_command_to_gt06,
            "vl01": process_suntech_command_to_vl01,
            "nt40": process_suntech_command_to_nt40
        }
    }

    OUTPUT_PROTOCOL_HOST_ADRESSES = {
        "suntech": (os.getenv("SUNTECH_MAIN_SERVER_HOST"), os.getenv("SUNTECH_MAIN_SERVER_PORT")),
        "gt06": (os.getenv("GT06_MAIN_SERVER_HOST"), os.getenv("GT06_MAIN_SERVER_PORT"))
    }

settings = Settings()