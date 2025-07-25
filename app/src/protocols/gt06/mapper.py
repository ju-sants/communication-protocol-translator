import struct
from datetime import datetime
from app.core.logger import get_logger
from app.services.redis_service import get_redis
from app.src.suntech.utils import build_suntech_packet, build_suntech_alv_packet
from app.src.connection.main_server_connection import send_to_main_server
from app.config.settings import settings


logger = get_logger("gt06_mapper")
redis_client = get_redis()


GT06_TO_SUNTECH_ALERT_MAP = {
    0x01: 42,  # SOS -> Panic Button
    0x02: 41,  # Power Cut Alarm -> Power Disconnected
    0x06: 1,   # Overspeed Alarm -> Over Speed
}


def decode_location_packet(body: bytes):

    try:
        data = {}

        year, month, day, hour, minute, second = struct.unpack(">BBBBBB", body[0:6])
        data["timestamp"] = datetime(2000 + year, month, day, hour, minute, second)

        sats_byte = body[6]
        data["satellites"] = sats_byte & 0x0F
    except Exception as e:
        logger.exception(f"Falha ao decodificar pacote de localização GT06 body_hex={body.hex()}")
        return None
