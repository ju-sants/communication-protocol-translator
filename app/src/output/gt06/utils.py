import struct
from datetime import datetime, timezone
from app.core.logger import get_logger
from app.src.protocols.gt06.utils import crc_itu

logger = get_logger(__name__)

def build_location_packet(location_data: dict, protocol_number: int, serial_number: int) -> bytes:
    """
    Constrói um pacote de localização GT06 a partir de dados de location_data.
    Suporta diferentes protocol_number (0x22, 0x32, 0xA0).
    """
    if protocol_number not in [0x22, 0x32, 0xA0]:
        logger.error(f"Protocol number {hex(protocol_number)} not supported for location packet creation.")
        return b""

    timestamp: datetime = location_data.get("timestamp", datetime.now(timezone.utc))
    time_bytes = struct.pack(
        ">BBBBBB",
        timestamp.year % 100,
        timestamp.month,
        timestamp.day,
        timestamp.hour,
        timestamp.minute,
        timestamp.second,
    )

    satellites = location_data.get("satellites", 0) & 0x0F
    gps_info_byte = satellites

    latitude_val = location_data.get("latitude", 0.0)
    longitude_val = location_data.get("longitude", 0.0)
    
    lat_raw = int(abs(latitude_val) * 1800000)
    lon_raw = int(abs(longitude_val) * 1800000)
    lat_lon_bytes = struct.pack(">II", lat_raw, lon_raw)

    speed_kmh = int(location_data.get("speed_kmh", 0))

    direction = int(location_data.get("direction", 0)) & 0x03FF
    gps_fixed = 1 if location_data.get("gps_fixed", False) else 0
    
    is_latitude_north = 1 if latitude_val >= 0 else 0
    is_longitude_west = 1 if longitude_val < 0 else 0

    course_status = (gps_fixed << 12) | (is_longitude_west << 11) | (is_latitude_north << 10) | direction
    course_status_bytes = struct.pack(">H", course_status)
    
    content_body = time_bytes + struct.pack(">B", gps_info_byte) + lat_lon_bytes + struct.pack(">B", speed_kmh) + course_status_bytes

    acc_status = 1 if location_data.get("acc_status", 0) else 0
    is_realtime = 0x00 if location_data.get("is_realtime", True) else 0x01
    gps_odometer = int(location_data.get("gps_odometer", 0))
    voltage = float(location_data.get("voltage", 0.0))
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