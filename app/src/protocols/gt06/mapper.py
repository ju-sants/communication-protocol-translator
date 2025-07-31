import struct
from datetime import datetime
import json
import copy

from app.core.logger import get_logger
from app.services.redis_service import get_redis
from app.src.suntech.utils import build_suntech_packet, build_suntech_alv_packet
from app.src.connection.main_server_connection import send_to_main_server

logger = get_logger(__name__)
redis_client = get_redis()


GT06_TO_SUNTECH_ALERT_MAP = {
    0x01: 42,  # SOS -> Suntech: Panic Button
    0x02: 41,  # Power Cut Alarm -> Suntech: Backup Battery Disconnected
    0x19: 14,  # Battery low voltage alarm -> Suntech: Battery Low
    0x03: 15,  # Shock Alarm -> Suntech: Shocked
    0x06: 1,   # Overspeed Alarm -> Suntech: Over Speed
    0xF0: 46,  # Urgent acceleration alarm -> Suntech: Harsh Acceleration
    0xF1: 47,  # Rapid deceleration alarm -> Suntech: Harsh Braking
    0x04: 6,   # Fence In Alarm -> Suntech: Enter Geo-Fence
    0x05: 5,   # Fence Out Alarm -> Suntech: Exit Geo-Fence
    0x13: 147, # Remove alarm -> Suntech: Absent Device Recovered
    0x14: 73,  # car door alarm -> Suntech: Anti-theft
    0xFE: 33,  # ACC On -> Suntech: Ignition On
    0xFF: 34   # ACC Off -> Suntech: Ignition Off
}


def decode_location_packet_v3(body: bytes):

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

        mileage_at = 29
        mileage_km = struct.unpack(">I", body[mileage_at:mileage_at + 4])[0]
        data["gps_odometer"] = mileage_km

        return data

    except Exception as e:
        logger.exception(f"Falha ao decodificar pacote de localização GT06 body_hex={body.hex()}")
        return None

def decode_location_packet_v4(body: bytes):

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

        acc_status = body[27]
        
        status_bits = 0
        if gps_fixed == 1:
            status_bits |= 0b10
        if acc_status == 1:
            status_bits |= 0b1
        data["status_bits"] = status_bits

        is_realtime = body[29] == 0x00

        data["is_realtime"] = is_realtime

        mileage_at = 30
        mileage_km = struct.unpack(">I", body[mileage_at:mileage_at + 4])[0]
        data["gps_odometer"] = mileage_km

        voltage_at = mileage_at + 4
        voltage_raw = struct.unpack(">H", body[voltage_at:voltage_at + 2])[0]
        voltage = voltage_raw * 0.01
        data["voltage"] = round(voltage, 2)

        return data

    except Exception as e:
        logger.exception(f"Falha ao decodificar pacote de localização GT06 body_hex={body.hex()}")
        return None
    
def handle_location_packet(dev_id_str: str, serial: int, body: bytes, protocol_number: int):
    if protocol_number == 0x32:
        location_data = decode_location_packet_v4(body)
    elif protocol_number == 0x22:
        location_data = decode_location_packet_v3(body)

    else:
        logger.info("Tipo de protocolo não mapeado")
        location_data = None

    if not location_data:
        return
    
    handle_ignition_change(dev_id_str, serial, location_data)
    handle_power_change(dev_id_str, serial, location_data)

    suntech_packet = build_suntech_packet(
        "STT",
        dev_id_str,
        location_data,
        serial,
        location_data.get("is_realtime", True)
    )

    if suntech_packet:
        logger.info(f"Pacote Localização SUNTECH traduzido de pacote GT06:\n{suntech_packet}")
        send_to_main_server(dev_id_str, serial, suntech_packet.encode("ascii"))

def handle_alarm_packet(dev_id_str: str, serial: int, body: bytes):

    if len(body) < 33:
        logger.info(f"Pacote de dados de alarme recebido com um tamanho menor do que o esperado, body={body.hex()}")
        return
    
    location_data = decode_location_packet_v3(body[0:32])

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
            logger.info(f"Pacote Alerta SUNTECH traduzido de pacote GT06:\n{suntech_packet}")

            send_to_main_server(dev_id_str, serial, suntech_packet.encode('ascii'))
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
        logger.info(f"Pacote de Heartbeat/KeepAlive SUNTECH traduzido de pacote GT06:\n{suntech_packet}")
        send_to_main_server(dev_id_str, serial, suntech_packet.encode('ascii'))