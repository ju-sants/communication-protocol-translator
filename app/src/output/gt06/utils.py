import struct
from datetime import datetime, timezone

from app.core.logger import get_logger
from app.src.protocols.gt06.utils import crc_itu
from app.services.redis_service import get_redis
from app.config.settings import settings

logger = get_logger(__name__)
redis_client = get_redis()

def build_location_packet(packet_data: dict, protocol_number: int, serial_number: int, *args) -> bytes:
    """
    Constrói um pacote de localização GT06 a partir de dados de packet_data.
    Suporta diferentes protocol_number (0x22, 0x32, 0xA0).
    """
    if protocol_number not in [0x22, 0x32, 0xA0]:
        logger.error(f"Protocol number {hex(protocol_number)} not supported for location packet creation.")
        return b""

    timestamp: datetime = packet_data.get("timestamp", datetime.now(timezone.utc))
    time_bytes = struct.pack(
        ">BBBBBB",
        timestamp.year % 100,
        timestamp.month,
        timestamp.day,
        timestamp.hour,
        timestamp.minute,
        timestamp.second,
    )

    satellites = packet_data.get("satellites", 0) & 0x0F
    gps_info_byte = satellites

    latitude_val = packet_data.get("latitude", 0.0)
    longitude_val = packet_data.get("longitude", 0.0)
    
    lat_raw = int(abs(latitude_val) * 1800000)
    lon_raw = int(abs(longitude_val) * 1800000)
    lat_lon_bytes = struct.pack(">II", lat_raw, lon_raw)

    speed_kmh = int(packet_data.get("speed_kmh", 0))
    speed_kmh_bytes = struct.pack(">B", speed_kmh)

    direction = int(packet_data.get("direction", 0)) & 0x03FF
    gps_fixed = 1 if packet_data.get("gps_fixed", False) else 0
    
    is_latitude_north = 1 if latitude_val >= 0 else 0
    is_longitude_west = 1 if longitude_val < 0 else 0

    course_status = (gps_fixed << 12) | (is_longitude_west << 11) | (is_latitude_north << 10) | direction
    course_status_bytes = struct.pack(">H", course_status)
    
    content_body = time_bytes + struct.pack(">B", gps_info_byte) + lat_lon_bytes + speed_kmh_bytes + course_status_bytes

    acc_status = 1 if packet_data.get("acc_status", 0) else 0
    is_realtime = 0x00 if packet_data.get("is_realtime", True) else 0x01
    gps_odometer = int(packet_data.get("gps_odometer", 0))
    voltage = float(packet_data.get("voltage", 0.0))
    voltage_raw = int(voltage * 100)

    if protocol_number == 0x22:
        content_body += b'\x00' * 8 # Cellular information bytes to fill up to acc status
        content_body += struct.pack(">B", acc_status)
        content_body += b'\x00' # Data Upload
        content_body += struct.pack(">B", is_realtime) # Real-time/Historical
        content_body += struct.pack(">I", gps_odometer) # Mileage

    elif protocol_number == 0x32:
        content_body += b'\x00' * 9
        content_body += struct.pack(">B", acc_status)
        content_body += b'\x00'
        content_body += struct.pack(">B", is_realtime) 
        content_body += struct.pack(">I", gps_odometer)
        content_body += struct.pack(">H", voltage_raw)

    elif protocol_number == 0xA0:
        content_body += b'\x00' * 16
        content_body += struct.pack(">B", acc_status)
        content_body += b'\x00'
        content_body += struct.pack(">B", is_realtime)
        content_body += struct.pack(">I", gps_odometer)
        content_body += struct.pack(">H", voltage_raw)

    # 1 (protocol_number) + len(content_body) + 2 (serial_number) + 2 (CRC)
    length_value = 1 + len(content_body) + 2 + 2
    length_byte = struct.pack(">B", length_value)

    data_for_crc = length_byte + struct.pack(">B", protocol_number) + content_body + struct.pack(">H", serial_number)
    
    crc = crc_itu(data_for_crc)
    crc_bytes = struct.pack(">H", crc)

    final_packet = (
        b"\x78\x78" +
        data_for_crc +
        crc_bytes +
        b"\x0d\x0a"
    )

    logger.debug(f"Construído pacote de localização GT06 (Protocol {hex(protocol_number)}): {final_packet.hex()}")
    return final_packet

def imei_to_bcd(imei: str) -> bytes:
    if len(imei) != 15 or not imei.isdigit():
        raise ValueError("IMEI must be a 15-digit string.")

    imei_padded = '0' + imei

    bcd_bytes = bytearray()
    for i in range(0, len(imei_padded), 2):
        byte_val = (int(imei_padded[i]) << 4) | int(imei_padded[i+1])
        bcd_bytes.append(byte_val)
    return bytes(bcd_bytes)

def build_login_packet(imei: str, serial_number: int) -> bytes:
    """
    Constrói um pacote de login GT06.
    """
    protocol_number = 0x01
    imei_bcd = imei_to_bcd(imei)

    packet_content_for_crc = (
        struct.pack(">B", protocol_number) +
        imei_bcd +
        struct.pack(">H", serial_number)
    )

    # 1 (protocol) + 8 (IMEI) + 2 (serial) + 2 (CRC placeholder)
    packet_length_value = len(packet_content_for_crc) + 2

    data_for_crc = struct.pack(">B", packet_length_value) + packet_content_for_crc

    crc = crc_itu(data_for_crc)

    full_packet = (
        b"\x78\x78" +
        struct.pack(">B", packet_length_value) +
        packet_content_for_crc +
        struct.pack(">H", crc) +
        b"\x0d\x0a"
    )

    logger.debug(f"Construído pacote de login GT06: {full_packet.hex()}")
    return full_packet


def build_heartbeat_packet(dev_id: str, *args) -> bytes:
    """
    Controi um pacote de Heartbeat GT06.
    """

    protocol_number = struct.pack(">B", 0x13)

    last_output_status = redis_client.hget(dev_id, "last_output_status")
    acc_status = redis_client.hget(dev_id, "acc_status")
    serial = redis_client.hget(dev_id, "last_serial")

    terminal_info_content = (last_output_status << 7) | (1 << 6) | (1 << 2) | (acc_status << 1) | 1
    terminal_info_content_bytes = struct.pack(">B", terminal_info_content)

    voltage_level = struct.pack(">B", 6)
    gsm_signal_strenght = struct.pack(">B", 0x04)
    alarm = struct.pack(">B", 0x00)
    language = struct.pack(">B", 0x02)
    serial = struct.pack(">H", serial)

    data_for_crc = (
        protocol_number +
        terminal_info_content_bytes +
        voltage_level +
        gsm_signal_strenght +
        alarm +
        language +
        serial
    )

    packet_lenght = len(data_for_crc)

    data_for_crc = (struct.pack(">B", packet_lenght) + data_for_crc)

    crc = crc_itu(data_for_crc)

    full_packet = (
        b"\x78\x78" + 
        data_for_crc +
        struct.pack(">B", crc) +
        b"\x0D\x0A"
    )

    return full_packet


def build_alarm_packet(dev_id: str, packet_data: dict, serial_number: int, *args) -> bytes:
    """
    Constrói um pacote de alarme GT06 a partir dos dados em packet_data.
    O pacote de alarme é um pacote de localização com informações de status adicionais.
    """

    protocol_number = 0x16

    timestamp: datetime = packet_data.get("timestamp", datetime.now(timezone.utc))
    time_bytes = struct.pack(
        ">BBBBBB",
        timestamp.year % 100,
        timestamp.month,
        timestamp.day,
        timestamp.hour,
        timestamp.minute,
        timestamp.second,
    )

    satellites = packet_data.get("satellites", 0) & 0x0F
    gps_info_byte = struct.pack(">B", satellites)

    latitude_val = packet_data.get("latitude", 0.0)
    longitude_val = packet_data.get("longitude", 0.0)
    
    lat_raw = int(abs(latitude_val) * 1800000)
    lon_raw = int(abs(longitude_val) * 1800000)
    lat_lon_bytes = struct.pack(">II", lat_raw, lon_raw)

    speed_kmh = int(packet_data.get("speed_kmh", 0))
    speed_kmh_bytes = struct.pack(">B", speed_kmh)

    direction = int(packet_data.get("direction", 0)) & 0x03FF
    gps_fixed = 1 if packet_data.get("gps_fixed", False) else 0
    is_latitude_north = 1 if latitude_val >= 0 else 0
    is_longitude_west = 1 if longitude_val < 0 else 0

    course_status = (gps_fixed << 12) | (is_longitude_west << 11) | (is_latitude_north << 10) | direction
    course_status_bytes = struct.pack(">H", course_status)

    gps_content = time_bytes + gps_info_byte + lat_lon_bytes + speed_kmh_bytes + course_status_bytes


    # Montando início do pacote
                                # LBS Content
    content_body = gps_content + (b"\x00" * 8)

    
    output_status = redis_client.hget(dev_id, "last_output_status")
    output_status = 0 if not output_status else output_status

    gps_tracking = 1
    charge = 1

    acc = redis_client.hget(dev_id, "acc_status")
    acc = 0 if not acc else acc

    terminal_info_byte = (output_status << 7) | (gps_tracking << 6) | (charge << 2) | (acc << 1) | 1
    terminal_info_bytes = struct.pack(">B", terminal_info_byte)

    voltage_level = 6
    voltage_level_bytes = struct.pack(">B", voltage_level)

    gsm_strength = 4
    gsm_strength_bytes = struct.pack(">B", gsm_strength)

    
    global_alarm_id = packet_data.get("global_alarm_id", "normal")
    alarm_id = settings.REVERSE_GLOBAL_ALERT_ID_DICTIONARY.get("gt06").get(global_alarm_id)

    if not alarm_id:
        logger.info(f"Impossível continuar, alarme id não encontrado para dev_id={dev_id}")
        return
     
    language = 0x02
    alarm_language_bytes = struct.pack(">BB", alarm_id, language)
    
    status_content = terminal_info_bytes + voltage_level_bytes + gsm_strength_bytes + alarm_language_bytes


    # Montagem Incremental do Pacote
    content_body += status_content


    # 1 (protocol_number) + len(content_body) + 2 (serial_number) + 2 (CRC)
    length_value = 1 + len(content_body) + 2 + 2
    length_byte = struct.pack(">B", length_value)

    data_for_crc = length_byte + struct.pack(">B", protocol_number) + content_body + struct.pack(">H", serial_number)
    
    crc = crc_itu(data_for_crc)
    crc_bytes = struct.pack(">H", crc)

    final_packet = (
        b"\x78\x78" +
        data_for_crc +
        crc_bytes +
        b"\x0d\x0a"
    )

    logger.debug(f"Construído pacote de Alarme GT06 (Protocol {hex(protocol_number)}): {final_packet.hex()}")
    return final_packet