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

        lat_raw, lon_raw = struct.unpack(">II", body[7:15])
        lat = lat_raw / 1800000.0
        lon = lon_raw / 1800000.0

        data["speed_kmh"] = body[15]

        course_status = struct.unpack(">H", body[16:18])[0]

        # Hemisférios (Bit 11 para Latitude Sul, Bit 12 para Longitude Oeste)
        is_latitude_north = (course_status >> 10) & 1
        is_longitude_west = (course_status >> 11) & 1
        
        data['latitude'] = -abs(lat) if not is_latitude_north else abs(lat)
        data['longitude'] = -abs(lon) if is_longitude_west else abs(lon)
            
        data["direction"] = course_status & 0x03FF

        gps_fixed = (course_status >> 12) & 1

        acc_status = body[26]

        status_bits = 0
        if gps_fixed == 1:
            status_bits |= 0b10
        if acc_status == 1:
            status_bits |= 0b1
        data["status_bits"] = status_bits

        is_realtime = body[28] == 0x00

        data["is_realtime"] = is_realtime

        mileage_km = struct.unpack(">I", body[29:33])[0]
        data["gps_odometer"] = mileage_km * 1000

        return data

    except Exception as e:
        logger.exception(f"Falha ao decodificar pacote de localização GT06 body_hex={body.hex()}")
        return None


def handle_location_packet(dev_id_str: str, serial: int, body: bytes):
    location_data = decode_location_packet(body)

    if not location_data:
        return
    
    suntech_packet = build_suntech_packet(
        "STT",
        dev_id_str,
        location_data,
        serial,
        location_data.get("is_realtime", True)
    )

    if suntech_packet:
        send_to_main_server(dev_id_str, serial, suntech_packet.encode("ascii"))

def handle_alarm_packet(dev_id_str: str, serial: int, body: bytes):

    location_data = decode_location_packet(body[0:32])

    if not location_data:
        return
    
    alarm_language_byte = body[32]
    alarm_code = alarm_language_byte

    suntech_alert_id = GT06_TO_SUNTECH_ALERT_MAP.get(alarm_code)

    
    if suntech_alert_id:
        logger.info(f"Alarme GT06 (0x{alarm_code:02X}) traduzido para Suntech ID {suntech_alert_id} device_id={dev_id_str}")
        suntech_packet = build_suntech_packet(
            hdr="ALT",
            dev_id=dev_id_str,
            location_data=location_data,
            serial=serial,
            is_realtime=location_data.get('is_realtime', True),
            alert_id=suntech_alert_id
        )
        if suntech_packet:
            send_to_main_server(dev_id_str, suntech_packet.encode('ascii'))
    else:
        logger.warning(f"Alarme GT06 não mapeado recebido device_id={dev_id_str}, alarm_code={hex(alarm_code)}")

def handle_heartbeat_packet(dev_id_str: str, serial: int, body: bytes):
    # O pacote de Heartbeat (0x13) contém informações de status
    terminal_info = body[0]
    acc_status = terminal_info & 0b10 

    power_alarm_flag = (terminal_info >> 3) & 0b111
    current_power_status = 1 if power_alarm_flag == 0b010 else 0 # 1 = desconectado

    # Atualiza o status da ignição no Redis
    redis_client.hset(dev_id_str, 'acc_status', 1 if acc_status else 0)
    redis_client.hset(dev_id_str, "power_status", current_power_status)

    # Keep-Alive da Suntech
    suntech_packet = build_suntech_alv_packet(dev_id_str)
    if suntech_packet:
        send_to_main_server(dev_id_str, suntech_packet.encode('ascii'))