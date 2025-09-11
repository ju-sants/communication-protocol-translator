from pydantic_settings import BaseSettings
from typing import Dict, Any
import os

from app.src.output.suntech.builder import (
    build_location_alarm_packet as build_suntech_alert_location_packet,
    build_heartbeat_packet as build_suntech_heartbeat_packet, 
    build_reply_packet as build_suntech_reply_packet
)

from app.src.output.gt06.builder import (
    build_location_packet as build_gt06_location_packet,
    build_heartbeat_packet as build_gt06_heartbeat_packet,
    build_reply_packet as build_gt06_reply_packet,
    build_alarm_packet as build_gt06_alarm_packet
)

# from app.src.input.jt808.builder import process_suntech_command as process_suntech_command_to_jt808
from app.src.input.j16x.builder import process_suntech_command as process_suntech_command_to_gt06
from app.src.input.vl01.builder import process_suntech_command as process_suntech_command_to_vl01
from app.src.input.nt40.builder import process_suntech_command as process_suntech_command_to_nt40

# from app.src.input.jt808.builder import process_gt06_command as process_gt06_command_to_jt808
from app.src.input.j16x.builder import process_gt06_command as process_gt06_command_to_gt06
from app.src.input.vl01.builder import process_gt06_command as process_gt06_command_to_vl01
from app.src.input.nt40.builder import process_gt06_command as process_gt06_command_to_nt40

class OutputProtocolSettings(BaseSettings):
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
            # "jt808": process_suntech_command_to_jt808,
            "gt06": process_suntech_command_to_gt06,
            "vl01": process_suntech_command_to_vl01,
            "nt40": process_suntech_command_to_nt40
        },
        "gt06": {
            # "jt808": process_gt06_command_to_jt808,
            "gt06": process_gt06_command_to_gt06,
            "vl01": process_gt06_command_to_vl01,
            "nt40": process_gt06_command_to_nt40,
        }
    }

    OUTPUT_PROTOCOL_HOST_ADRESSES: Dict[str, tuple] = {
        "suntech": (os.getenv("SUNTECH_MAIN_SERVER_HOST"), os.getenv("SUNTECH_MAIN_SERVER_PORT")),
        "gt06": (os.getenv("GT06_MAIN_SERVER_HOST"), os.getenv("GT06_MAIN_SERVER_PORT"))
    }

output_protocol_settings = OutputProtocolSettings()