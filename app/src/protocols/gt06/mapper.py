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

        lat_raw, lon_raw = struct.pack(">II", body[7:15])
        lat = lat_raw / 1800000.0
        lon = lon_raw / 1800000.0

        data["speed_km"] = body[15]

        course_status = struct.unpack(">H", body[16:18])[0]

        if (course_status >> 2) & 1: lat = -lat
        if (course_status >> 3) & 1: lon = -lon

        data["latitude"], data["longitude"] = lat, lon

        data["direction"] = course_status & 0x03FF

        gps_fixed = (course_status >> 4) & 1

        # Pulando informações de LBS por enquanto
        acc_status = body[26]

        status_bits = 0
        if gps_fixed == 1:
            status_bits |= 0b10
        if acc_status == 1:
            status_bits |= 0b1
        data["status_bits"] = status_bits

        is_realtime = body[27] == 0x00

        data["is_realtime"] = is_realtime

        mileage_km = struct.unpack(">I", body[28:32])[0]
        data["gps_odometer"] = mileage_km * 1000

        return data

    except Exception as e:
        logger.exception(f"Falha ao decodificar pacote de localização GT06 body_hex={body.hex()}")
        return None
