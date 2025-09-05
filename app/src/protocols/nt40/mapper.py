import struct
from datetime import datetime, timezone, timedelta
import json
import copy

from app.core.logger import get_logger
from app.services.redis_service import get_redis
from app.src.output.suntech.utils import build_suntech_packet, build_suntech_alv_packet, build_suntech_res_packet
from app.src.connection.main_server_connection import send_to_main_server
from app.src.protocols.utils import handle_ignition_change

logger = get_logger(__name__)
redis_client = get_redis()


NT40_TO_SUNTECH_ALERT_MAP = {
    0x01: 42,  # SOS -> Suntech: Panic Button
    0x02: 41,  # Power Cut Alarm -> Suntech: Backup Battery Disconnected
    0x03: 15,  # Shock Alarm -> Suntech: Shocked
    0x04: 33,  # ACC On -> Suntech: Ignition On
    0x05: 34,   # ACC Off -> Suntech: Ignition Off
    0x12: 147, # Remove alarm -> Suntech: Absent Device Recovered

}


def decode_location_packet_x12(body: bytes):

    try:
        data = {}

        year, month, day, hour, minute, second = struct.unpack(">BBBBBB", body[0:6])
        data["timestamp"] = datetime(2000 + year, month, day, hour, minute, second).replace(tzinfo=timezone.utc)

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
        data["gps_fixed"] = gps_fixed

        return data

    except Exception as e:
        logger.exception(f"Falha ao decodificar pacote de localização NT40 body_hex={body.hex()}")
        return None

def decode_location_packet_x22(body: bytes):

    try:
        data = {}

        year, month, day, hour, minute, second = struct.unpack(">BBBBBB", body[0:6])
        data["timestamp"] = datetime(2000 + year, month, day, hour, minute, second).replace(tzinfo=timezone.utc)

        sats_byte = body[12]
        data["satellites"] = sats_byte & 0x0F

        lat_raw, lon_raw = struct.unpack(">II", body[13:21])
        lat = lat_raw / 1800000.0
        lon = lon_raw / 1800000.0

        data["speed_kmh"] = body[21]

        course_status = struct.unpack(">H", body[22:24])[0]

        # Hemisférios (Bit 11 para Latitude Sul, Bit 12 para Longitude Oeste)
        is_latitude_north = (course_status >> 10) & 1
        is_longitude_west = (course_status >> 11) & 1
        
        data['latitude'] = -abs(lat) if not is_latitude_north else abs(lat)
        data['longitude'] = -abs(lon) if is_longitude_west else abs(lon)
            
        data["direction"] = course_status & 0x03FF

        gps_fixed = (course_status >> 12) & 1
        data["gps_fixed"] = gps_fixed

        is_realtime = (course_status >> 13) & 1 == 0
        data["is_realtime"] = is_realtime

        terminal_info = body[33]
        data["terminal_info"]  = terminal_info

        acc_status = (terminal_info >> 1) & 0b1
        data["acc_status"] = acc_status

        output_status = (terminal_info >> 7) & 0b1
        data["output_status"] = output_status
        
        voltage_at = 34
        voltage_raw = struct.unpack(">H", body[voltage_at:voltage_at + 2])[0]
        voltage = voltage_raw * 0.01
        data["voltage"] = round(voltage, 2)

        alarm = body[38]
        data["alarm"] = alarm

        mileage_at = 40
        mileage_km = int.from_bytes(body[mileage_at:mileage_at + 3], "big")
        data["gps_odometer"] = mileage_km * 1000

        return data

    except Exception as e:
        logger.exception(f"Falha ao decodificar pacote de localização NT40 body_hex={body.hex()}")
        return None

def handle_alarm_from_location(dev_id_str, serial,  alarm_packet_data, raw_packet_hex):
    suntech_alert_id = None
    power_cut_alarm = None
    sos_alarm = None

    terminal_info = alarm_packet_data.get("terminal_info")
    logger.info(f"handle_alarm_from_location: terminal_info={bin(terminal_info)}")
    if terminal_info:
        power_cut_alarm = 1 if (terminal_info >> 3) & 0b11 == 0b10 else 0
        sos_alarm = 1 if (terminal_info >> 5) & 0b1 else 0

    if power_cut_alarm is not None and power_cut_alarm:
        suntech_alert_id = 41
    if sos_alarm is not None and sos_alarm:
        suntech_alert_id = 42
    else:
        alarm_code = alarm_packet_data.get("alarm", 0x00)
        logger.info(f"handle_alarm_from_location: alarm_code={alarm_code}")

        if alarm_code not in (0x0, 0x00):
            suntech_alert_id = NT40_TO_SUNTECH_ALERT_MAP.get(alarm_code, 0)
            logger.info(f"Alarme NT40 (0x{alarm_code:02X}) traduzido para Suntech ID {suntech_alert_id} device_id={dev_id_str}")

    
    if suntech_alert_id:
        suntech_packet = build_suntech_packet(
            hdr="ALT",
            dev_id=dev_id_str,
            packet_data=alarm_packet_data,
            serial=serial,
            is_realtime=True,
            alert_id=suntech_alert_id
        )
        if suntech_packet:
            logger.info(f"Pacote Alerta SUNTECH traduzido de pacote NT40:\n{suntech_packet}")

            send_to_main_server(dev_id_str, serial, suntech_packet.encode('ascii'), raw_packet_hex)
    elif suntech_alert_id is not None:
        logger.warning(f"Alarme NT40 não mapeado recebido device_id={dev_id_str}, alarm_code={alarm_packet_data.get('alarm')}, terminal_info={alarm_packet_data.get('terminal_info')}")


def handle_location_packet(dev_id_str: str, serial: int, body: bytes, protocol_number: int, raw_packet_hex: str):
    if protocol_number == 0x12:
        packet_data = decode_location_packet_x12(body)
    elif protocol_number == 0x22:
        packet_data = decode_location_packet_x22(body[9:])
    else:
        logger.info("Tipo de protocolo não mapeado")
        packet_data = None

    if not packet_data:
        return
    
    handle_alarm_from_location(dev_id_str, serial, packet_data, raw_packet_hex)

    handle_ignition_change(dev_id_str, serial, packet_data, raw_packet_hex, "NT40")
    
    last_packet_data = copy.deepcopy(packet_data)
    
    last_packet_data["timestamp"] = last_packet_data["timestamp"].strftime("%Y-%m-%dT%H:%M:%S")

    # Salvando para uso em caso de alarmes
    redis_client.hset(dev_id_str, "imei", dev_id_str) # Explicitly save IMEI
    redis_client.hset(dev_id_str, "last_packet_data", json.dumps(last_packet_data))
    redis_client.hset(dev_id_str, "last_full_location", json.dumps(packet_data, default=str)) # Full location data
    redis_client.hset(dev_id_str, "last_serial", serial)
    redis_client.hset(dev_id_str, "last_active_timestamp", datetime.now(timezone.utc).isoformat())
    redis_client.hset(dev_id_str, "last_event_type", "location")
    redis_client.hincrby(dev_id_str, "total_packets_received", 1)
    redis_client.hset(dev_id_str, "acc_status", packet_data.get('acc_status', 0))
    redis_client.hset(dev_id_str, "power_status", 0 if packet_data.get('voltage', 0.0) > 0 else 1)
    if packet_data.get("output_status") is not None:
        redis_client.hset(dev_id_str, "last_output_status", packet_data.get("output_status"))

    suntech_packet = build_suntech_packet(
        "STT",
        dev_id_str,
        packet_data,
        serial,
        packet_data.get("is_realtime", True)
    )

    if suntech_packet:
        logger.info(f"Pacote Localização SUNTECH traduzido de pacote NT40:\n{suntech_packet}")
        send_to_main_server(dev_id_str, serial, suntech_packet.encode("ascii"), raw_packet_hex)

def handle_alarm_packet(dev_id_str: str, serial: int, body: bytes, raw_packet_hex: str):
    redis_client.hset(dev_id_str, "last_active_timestamp", datetime.now(timezone.utc).isoformat())
    redis_client.hset(dev_id_str, "last_event_type", "alarm")
    redis_client.hincrby(dev_id_str, "total_packets_received", 1)

    if len(body) < 32:
        logger.info(f"Pacote de dados de alarme recebido com um tamanho menor do que o esperado, body={body.hex()}")
        return

    alarm_packet_data = decode_location_packet_x12(body[0:17])

    alarm_datetime = alarm_packet_data.get("timestamp")
    if not alarm_datetime:
        logger.info(f"Pacote de alarme sem data e hora, descartando... dev_id={dev_id_str}")
        return
    
    limit = datetime.now(timezone.utc) - timedelta(minutes=2)

    if not alarm_datetime > limit:
        logger.info(f"Alarme da memória, descartando... dev_id={dev_id_str}")

    last_packet_data_str = redis_client.hget(dev_id_str, "last_packet_data")
    last_packet_data = json.loads(last_packet_data_str)

    definitive_packet_data = {**last_packet_data, **alarm_packet_data}

    if not definitive_packet_data:
        return
    
    alarm_code = body[31]

    suntech_alert_id = NT40_TO_SUNTECH_ALERT_MAP.get(alarm_code)

    
    if suntech_alert_id:
        logger.info(f"Alarme NT40 (0x{alarm_code:02X}) traduzido para Suntech ID {suntech_alert_id} device_id={dev_id_str}")
        suntech_packet = build_suntech_packet(
            hdr="ALT",
            dev_id=dev_id_str,
            packet_data=definitive_packet_data,
            serial=serial,
            is_realtime=True,
            alert_id=suntech_alert_id
        )
        if suntech_packet:
            logger.info(f"Pacote Alerta SUNTECH traduzido de pacote NT40:\n{suntech_packet}")

            send_to_main_server(dev_id_str, serial, suntech_packet.encode('ascii'), raw_packet_hex)
    else:
        logger.warning(f"Alarme NT40 não mapeado recebido device_id={dev_id_str}, alarm_code={hex(alarm_code)}")

def handle_heartbeat_packet(dev_id_str: str, serial: int, body: bytes, raw_packet_hex: str):
    # O pacote de Heartbeat (0x13) contém informações de status
    redis_client.hset(dev_id_str, "last_active_timestamp", datetime.now(timezone.utc).isoformat())
    redis_client.hset(dev_id_str, "last_event_type", "heartbeat")
    redis_client.hincrby(dev_id_str, "total_packets_received", 1)
    
    terminal_info = body[0]
    logger.info(f"HEARTBEAT TERMINAL INFO: {bin(terminal_info)}")
    output_status = (terminal_info >> 7) & 0b1
    redis_client.hset(dev_id_str, "last_output_status", output_status)
    redis_client.hset(dev_id_str, "last_serial", serial)

    # Keep-Alive da Suntech
    suntech_packet = build_suntech_alv_packet(dev_id_str)
    if suntech_packet:
        logger.info(f"Pacote de Heartbeat/KeepAlive SUNTECH traduzido de pacote NT40:\n{suntech_packet}")
        send_to_main_server(dev_id_str, serial, suntech_packet.encode('ascii'), raw_packet_hex)


def handle_reply_command_packet(dev_id: str, serial: int, body: bytes, raw_packet_hex: str):
    try:
        command_content = body[5:]
        command_content_str = command_content.decode("ascii", errors="ignore")

        if command_content_str:
            command_content_str = command_content_str.strip().upper().rstrip('\x00\x01')
            last_packet_data_str = redis_client.hget(dev_id, "last_packet_data")
            last_packet_data = json.loads(last_packet_data_str)
            last_packet_data["timestamp"] = datetime.now(timezone.utc)

            packet = None
            
            if command_content_str == "RELAYER ENABLE OK!":
                packet = build_suntech_res_packet(dev_id, ["CMD", dev_id, "04", "01"], last_packet_data)
            elif command_content_str == "RELAYER DISABLE OK!":
                packet = build_suntech_res_packet(dev_id, ["CMD", dev_id, "04", "02"], last_packet_data)
            else:
                logger.info(f"command_content_str: {command_content_str!r}, length: {len(command_content_str)}")
                logger.info(f"command_content_str == 'RELAYER ENABLE OK!': {command_content_str == 'RELAYER ENABLE OK!'}")
                logger.info(f"command_content_str == 'RELAYER DISABLE OK!': {command_content_str == 'RELAYER DISABLE OK!'}")
                logger.info(f"len('RELAYER ENABLE OK!') = {len('RELAYER ENABLE OK!')}")
                logger.info(f"len('RELAYER DISABLE OK!') = {len('RELAYER DISABLE OK!')}")

            if packet:
                send_to_main_server(dev_id, serial, packet.encode("ascii"), raw_packet_hex)
    except Exception as e:
        logger.error(f"Erro ao decodificar comando de REPLY")