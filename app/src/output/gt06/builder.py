import struct
from datetime import datetime, timezone

from app.core.logger import get_logger
from app.src.input.utils import crc_itu
from app.services.redis_service import get_redis
from ..utils import normalize_dev_id
from app.config.settings import settings

logger = get_logger(__name__)
redis_client = get_redis()

def build_location_packet(dev_id, packet_data: dict, serial_number: int, *args) -> bytes:
    """
    Constrói um pacote de localização GT06 a partir de dados de packet_data.
    Suporta diferentes protocol_number (0x22, 0x32, 0xA0).
    """
    protocol_number = 0xA0 # Deixaremos um valor constante por hora

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
    gps_info_byte = 0xC0 | satellites

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

    # Getting the saved LBS information
    universal_data_info = redis_client.hgetall("universal_data")
    mcc = int(universal_data_info.get("mcc", 0))
    mnc = int(universal_data_info.get("mnc", 0))
    lac = int(universal_data_info.get("lac", 0))
    cell_id = int(universal_data_info.get("cell_id", 0))

    if protocol_number == 0x12:
        content_body += struct.pack(">H", mcc)
        content_body += struct.pack(">B", mnc)
        content_body += struct.pack(">H", lac)
        content_body += cell_id.to_bytes(3, "big")

    elif protocol_number == 0x22:
        content_body += struct.pack(">H", mcc)
        content_body += struct.pack(">B", mnc)
        content_body += struct.pack(">H", lac)
        content_body += cell_id.to_bytes(3, "big")

        content_body += struct.pack(">B", acc_status)
        content_body += b'\x00' # Data Upload
        content_body += struct.pack(">B", is_realtime) # Real-time/Historical
        content_body += struct.pack(">I", gps_odometer) # Mileage

    elif protocol_number == 0x32:
        content_body += struct.pack(">H", mcc)
        content_body += struct.pack(">B", mnc)
        content_body += struct.pack(">H", lac)
        content_body += struct.pack(">I", cell_id)

        content_body += struct.pack(">B", acc_status)
        content_body += b'\x00'
        content_body += struct.pack(">B", is_realtime) 
        content_body += struct.pack(">I", gps_odometer)
        content_body += struct.pack(">H", voltage_raw)
        content_body += b"\x00" * 6

    elif protocol_number == 0xA0:
        content_body += struct.pack(">H", mcc)
        if (mcc >> 15) == 1:
            content_body += struct.pack(">H", mnc)
        else:
            content_body += struct.pack(">B", mnc)

        content_body += struct.pack(">I", lac)
        content_body += struct.pack(">Q", cell_id)


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
    if len(imei) > 15 or len(imei) < 15 or not imei.isdigit():
        raise ValueError("IMEI must be a 15-digit string.")
    
    imei_padded = "0" + imei
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

    imei_normalized = normalize_dev_id(imei)[-15:]
    redis_client.hset(f"tracker:{imei}", "output_id", imei_normalized)

    imei_bcd = imei_to_bcd(imei_normalized)

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

    redis_data = redis_client.hmget(f"tracker:{dev_id}", "last_output_status", "acc_status", "last_serial")
    last_output_status = redis_data[0] if redis_data[0] else "0"
    acc_status = redis_data[1] if redis_data[1] else "0"
    serial = redis_data[2] if redis_data[2] else "0"

    terminal_info_content = (int(last_output_status) << 7) | (1 << 6) | (1 << 2) | (int(acc_status) << 1) | 1
    terminal_info_content_bytes = struct.pack(">B", terminal_info_content)

    voltage_level = struct.pack(">B", 6)
    gsm_signal_strenght = struct.pack(">B", 0x04)
    alarm = struct.pack(">B", 0x00)
    language = struct.pack(">B", 0x02)
    serial = struct.pack(">H", int(serial))

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
        struct.pack(">H", crc) +
        b"\x0D\x0A"
    )

    return full_packet


def build_alarm_packet(dev_id: str, packet_data: dict, serial_number: int, *args, managed_alert: bool = False) -> bytes:
    """
    Constrói um pacote de alarme GT06 a partir dos dados em packet_data.
    O pacote de alarme é um pacote de localização com informações de status adicionais.
    """

    # Condição para híbridos
    universal_alert_id = packet_data.get("universal_alert_id")
    if not managed_alert:
        if redis_client.hget(f"tracker:{dev_id}", "hybrid_id") and universal_alert_id in (6533, 6534):
            logger.info(f"Alerta de ignição para híbridos é gerenciada pelo servidor tradutor. dev_id={dev_id}")
            return b""
    
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
    content_body = gps_content + (b"\x00" * 9)

    redis_data = redis_client.hmget(f"tracker:{dev_id}", "last_output_status", "acc_status")
    output_status = redis_data[0] if redis_data[0] else "0"
    acc = redis_data[1] if redis_data[1] else "0"

    gps_tracking = 1
    charge = 1

    voltage_level = 6
    voltage_level_bytes = struct.pack(">B", voltage_level)

    gsm_strength = 4
    gsm_strength_bytes = struct.pack(">B", gsm_strength)

    
    alarm_id = settings.REVERSE_UNIVERSAL_ALERT_ID_DICTIONARY.get("vl01").get(universal_alert_id)

    if not alarm_id:
        logger.info(f"Impossível continuar, alarme id não encontrado para dev_id={dev_id}, universal_alert_id={universal_alert_id}")
        return
    
    terminal_info_byte = (int(output_status) << 7) | (gps_tracking << 6) | (0b10 << 3) if alarm_id == 0x02 else 0 | (charge << 2) | (int(acc) << 1) | 1
    terminal_info_bytes = struct.pack(">B", terminal_info_byte)

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

def build_reply_packet(dev_id: str, packet_data: dict, serial_number: int, *args) -> bytes:
    """
    Constrói um pacote de RESPOSTA de um comando, enviado do terminal para o servidor.
    Protocolo 0x15.
    """
    protocol_number = 0x15

    universal_command_reply = packet_data.get("REPLY")

    command_reply = None
    if universal_command_reply == "OUTPUT ON":
        command_reply = "RELAY 1 OK"
    elif universal_command_reply == "OUTPUT OFF":
        command_reply = "RELAY 0 OK"
    else:
        logger.warning(f"Resposta de comando universal desconhecido recebido: {universal_command_reply}, dev_id={dev_id}")
        return b''

    command_bytes = command_reply.encode('ascii')
    
    server_flag = b"\x00\x00\x00\x01"

    len_of_command = len(server_flag) + len(command_bytes)
    len_of_command_bytes = struct.pack(">B", len_of_command)
    
    language_bytes = struct.pack(">H", 0x0002)

    # O corpo do conteúdo da informação
    information_content = len_of_command_bytes + server_flag + command_bytes + language_bytes

    # 1 (protocolo) + len(information_content) + 2 (serial) + 2 (CRC)
    packet_length_value = 1 + len(information_content) + 2 + 2
    packet_length_bytes = struct.pack(">B", packet_length_value)
    
    # Montando os dados para o cálculo do CRC
    data_for_crc = (
        packet_length_bytes +
        struct.pack(">B", protocol_number) +
        information_content +
        struct.pack(">H", serial_number)
    )
    
    crc = crc_itu(data_for_crc)
    crc_bytes = struct.pack(">H", crc)

    final_packet = (
        b"\x78\x78" +
        data_for_crc +
        crc_bytes +
        b"\x0d\x0a"
    )

    logger.debug(f"Construído pacote de Resposta do Terminal GT06 (Protocol {hex(protocol_number)}): {final_packet.hex()}")
    return final_packet

def build_voltage_info_packet(packet_data: dict, serial_number: int) -> bytes:
    """
    Constrói um pacote de informação (Protocolo 0x94),
    enviando exclusivamente a informação de voltagem externa (Sub-protocolo 0x00).
    """
    protocol_number = 0x94
    sub_protocol_number = 0x00

    voltage = float(packet_data.get("voltage", 0.0))
    voltage_raw = int(voltage * 100)
    information_content = struct.pack(">H", voltage_raw)

    body_packet = (
        struct.pack(">B", protocol_number) +
        struct.pack(">B", sub_protocol_number) +
        information_content +
        struct.pack(">H", serial_number)
    )

    packet_length_value = len(body_packet) + 2
    packet_length_bytes = struct.pack(">H", packet_length_value)

    data_for_crc = packet_length_bytes + body_packet
    
    crc = crc_itu(data_for_crc)
    crc_bytes = struct.pack(">H", crc)

    final_packet = (
        b"\x79\x79" + 
        data_for_crc +
        crc_bytes +   
        b"\x0d\x0a"   
    )

    logger.debug(f"Construído pacote de Informação (Protocol {hex(protocol_number)}): {final_packet.hex()}")
    return final_packet