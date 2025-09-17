from pydantic_settings import BaseSettings
from typing import Dict, Any
import os

from app.src.output.suntech4g.builder import (
    build_location_alarm_packet as build_suntech_alert_location_packet,
    build_heartbeat_packet as build_suntech_heartbeat_packet, 
    build_reply_packet as build_suntech_reply_packet
)
from app.src.output.suntech4g.mapper import map_to_universal_command as map_to_universal_suntech_command

from app.src.output.gt06.builder import (
    build_location_packet as build_gt06_location_packet,
    build_heartbeat_packet as build_gt06_heartbeat_packet,
    build_reply_packet as build_gt06_reply_packet,
    build_alarm_packet as build_gt06_alarm_packet
)
from app.src.output.gt06.mapper import map_to_universal_command as map_to_universal_gt06_command

class OutputProtocolSettings(BaseSettings):
    # ---------- Utilitários para os protocolos de saída --------------------
    OUTPUT_PROTOCOL_PACKET_BUILDERS: Dict[str, Dict[str, Any]] = {
        "suntech4g": {
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

    OUTPUT_PROTOCOL_COMMAND_MAPPERS: Dict[str, Any] = {
        "gt06": map_to_universal_gt06_command,
        "suntech4g": map_to_universal_suntech_command
    }

    OUTPUT_PROTOCOL_HOST_ADRESSES: Dict[str, tuple] = {
        "suntech4g": (os.getenv("SUNTECH_MAIN_SERVER_HOST"), os.getenv("SUNTECH_MAIN_SERVER_PORT")),
        "gt06": (os.getenv("GT06_MAIN_SERVER_HOST"), os.getenv("GT06_MAIN_SERVER_PORT"))
    }

output_protocol_settings = OutputProtocolSettings()