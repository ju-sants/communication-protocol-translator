from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Dict, Any
import os

from app.src.output.suntech.utils import (
    build_heartbeat_packet as build_suntech_heartbeat_packet, 
    build_location_packet as build_suntech_location_packet
)

from app.src.output.gt06.utils import (
    build_location_packet as build_gt06_location_packet,
    build_heartbeat_packet as build_gt06_heartbeat_packet
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

    # ---------- Utilitários para os protocolos de saída --------------------
    OUTPUT_PROTOCOL_PACKET_BUILDERS: Dict[str, Dict[str, Any]] = {
        "suntech": {
            "location": build_suntech_location_packet,
            "heartbeat": build_suntech_heartbeat_packet,
            },
        "gt06": {
            "location": build_gt06_location_packet,
            "heartbeat": build_gt06_heartbeat_packet,
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