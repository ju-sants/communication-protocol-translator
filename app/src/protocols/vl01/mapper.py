import struct
from datetime import datetime, timezone, timedelta
import json
import copy

from app.core.logger import get_logger
from app.services.redis_service import get_redis
from .utils import _decode_alarm_location_packet
from app.src.suntech.utils import build_suntech_packet, build_suntech_alv_packet, build_suntech_res_packet
from app.src.connection.main_server_connection import send_to_main_server
from .utils import haversine

logger = get_logger(__name__)
redis_client = get_redis()


VL01_TO_SUNTECH_ALERT_MAP = {
    0x01: 42,  # SOS -> Suntech: Panic Button
    0x02: 41,  # Power Cut Alarm -> Suntech: Power Disconected
    0x03: 15,  # Shock Alarm -> Suntech: Shocked
    0x04: 6,   # Fence In Alarm -> Suntech: Enter Geo-Fence
    0x05: 5,   # Fence Out Alarm -> Suntech: Exit Geo-Fence
    0x06: 1,   # Overspeed Alarm -> Suntech: Over Speed
    0x19: 14,  # Battery low voltage alarm -> Suntech: Battery Low
    0xF0: 46,  # Urgent acceleration alarm -> Suntech: Harsh Acceleration
    0xF1: 47,  # Rapid deceleration alarm -> Suntech: Harsh Braking
    0x13: 147, # Remove alarm -> Suntech: Absent Device Recovered
    0x14: 73,  # car door alarm -> Suntech: Anti-theft
    0xFE: 33,  # ACC On -> Suntech: Ignition On
    0xFF: 34   # ACC Off -> Suntech: Ignition Off
}


def decode_location_packet(body: bytes):

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

        try: # Colocando dentro de um try except pois essa funcao tbm recebe chamadas para decodificar pacotes de alerta, que não tem as infos abaixo, 
            # Na ordem em que estão abaixo
            mcc = struct.unpack(">H", body[18:20])[0]
            mnc_length = 1
            if (mcc >> 15) & 1:
                mnc_length = 2

            acc_at = 20 + mnc_length + 4 + 8
            acc_status = body[acc_at]
            data["acc_status"] = acc_status

            status_bits = 0
            if gps_fixed == 1:
                status_bits |= 0b10
            if acc_status == 1:
                status_bits |= 0b1
            data["status_bits"] = status_bits

            is_realtime = body[acc_at + 2] == 0x00

            data["is_realtime"] = is_realtime

            mileage_at = acc_at + 3
            mileage_km = struct.unpack(">I", body[mileage_at:mileage_at + 4])[0]
            data["gps_odometer_embedded"] = mileage_km
        except:
            pass

        return data

    except Exception as e:
        logger.exception(f"Falha ao decodificar pacote de localização VL01 body_hex={body.hex()}")
        return None

def handle_location_packet(dev_id_str: str, serial: int, body: bytes, raw_packet_hex: str):
    location_data = decode_location_packet(body)

    if not location_data:
        return
    
    if location_data.get("acc_status"):
        # Haversine Odometer Calculation
        last_location_str = redis_client.hget(dev_id_str, "last_location")
        current_odometer = float(redis_client.hget(dev_id_str, "odometer") or 0.0)

        if last_location_str:
            last_location = json.loads(last_location_str)
            last_lat = last_location["latitude"]
            last_lon = last_location["longitude"]
            
            current_lat = location_data["latitude"]
            current_lon = location_data["longitude"]

            distance = haversine(last_lat, last_lon, current_lat, current_lon) * 1000  # Convert to meters
            current_odometer += distance
            logger.info(f"Odometer for {dev_id_str}: {current_odometer/1000:.2f} km (distance added: {distance/1000:.2f} km)")
        else:
            logger.info(f"No previous location for {dev_id_str}. Odometer starting at {current_odometer/1000:.2f} km.")

        location_data["gps_odometer"] = current_odometer
        redis_client.hset(dev_id_str, "odometer", str(current_odometer))
        redis_client.hset(dev_id_str, "last_location", json.dumps({"latitude": location_data["latitude"], "longitude": location_data["longitude"]}))


    last_location_data = copy.deepcopy(location_data)
    
    last_location_data["timestamp"] = last_location_data["timestamp"].strftime("%Y-%m-%dT%H:%M:%S")

    # Salvando para uso em caso de alarmes
    redis_client.hset(dev_id_str, "last_location_data", json.dumps(last_location_data))
    redis_client.hset(dev_id_str, "last_serial", serial)

    suntech_packet = build_suntech_packet(
        "STT",
        dev_id_str,
        location_data,
        serial,
        location_data.get("is_realtime", True),
        voltage_stored=True
    )

    if suntech_packet:
        logger.info(f"Pacote Localização SUNTECH traduzido de pacote VL01:\n{suntech_packet}")
        send_to_main_server(dev_id_str, serial, suntech_packet.encode("ascii"), raw_packet_hex)

def handle_alarm_packet(dev_id_str: str, serial: int, body: bytes, raw_packet_hex: str):

    if len(body) < 17:
        logger.info(f"Pacote de dados de alarme recebido com um tamanho menor do que o esperado, body={body.hex()}")
        return
    
    alarm_location_data = _decode_alarm_location_packet(body[0:16])
    if not alarm_location_data:
        logger.info(f"Pacote de alarme sem dados de localização, descartando... dev_id={dev_id_str}, packet={body}")
        return
    
    alarm_datetime = alarm_location_data.get("timestamp")
    if not alarm_datetime:
        logger.info(f"Pacote de alarme sem data e hora, descartando... dev_id={dev_id_str}")
        return
    
    limit = datetime.now(timezone.utc) - timedelta(minutes=2)

    if not alarm_datetime > limit:
        logger.info(f"Alarme da memória, descartando... dev_id={dev_id_str}")

    last_location_data_str = redis_client.hget(dev_id_str, "last_location_data")
    last_location_data = json.loads(last_location_data_str)

    definitive_location_data = {**last_location_data, **alarm_location_data}

    if not definitive_location_data:
        return
    
    alarm_code = body[16]

    suntech_alert_id = VL01_TO_SUNTECH_ALERT_MAP.get(alarm_code)

    if suntech_alert_id:
        logger.info(f"Alarme VL01 (0x{alarm_code:02X}) traduzido para Suntech ID {suntech_alert_id} device_id={dev_id_str}")
        suntech_packet = build_suntech_packet(
            hdr="ALT",
            dev_id=dev_id_str,
            location_data=definitive_location_data,
            serial=serial,
            is_realtime=True,
            alert_id=suntech_alert_id
        )
        if suntech_packet:
            logger.info(f"Pacote Alerta SUNTECH traduzido de pacote VL01:\n{suntech_packet}")

            send_to_main_server(dev_id_str, serial, suntech_packet.encode('ascii'), raw_packet_hex)
    else:
        logger.warning(f"Alarme VL01 não mapeado recebido device_id={dev_id_str}, alarm_code={hex(alarm_code)}")

def handle_heartbeat_packet(dev_id_str: str, serial: int, body: bytes, raw_packet_hex: str):
    logger.info(f"Pacote de heartbeat recebido de {dev_id_str}, body={body.hex()}")
    # O pacote de Heartbeat (0x13) contém informações de status
    terminal_info = body[0]
    acc_status = 1 if terminal_info & 0b10 else 0
    
    power_alarm_flag = (terminal_info >> 3) & 0b111
    power_status = 1 if power_alarm_flag == 0b010 else 0 # 1 = desconectado
    output_status = (terminal_info >> 7) & 0b1

    logger.info(f"DEVICE {dev_id_str} STATUS: ACC: {acc_status}, Power: {power_status}, Output: {output_status}")
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
            last_location_data_str = redis_client.hget(dev_id, "last_location_data")
            last_location_data = json.loads(last_location_data_str)
            last_location_data["timestamp"] = datetime.now(timezone.utc)

            packet = None
            
            if command_content_str == "RELAY:ON":
                redis_client.hset(dev_id, "last_output_status", 1)
                packet = build_suntech_res_packet(dev_id, ["CMD", dev_id, "04", "01"], last_location_data)
            elif command_content_str == "RELAY:OFF":
                redis_client.hset(dev_id, "last_output_status", 0)
                packet = build_suntech_res_packet(dev_id, ["CMD", dev_id, "04", "02"], last_location_data)
                
            if packet:
                send_to_main_server(dev_id, serial, packet.encode("ascii"), raw_packet_hex)

            pass
    except Exception as e:
        logger.error(f"Erro ao decodificar comando de REPLY")

def handle_information_packet(dev_id: str, serial: int, body: bytes, raw_packet_hex: str):
    
    type = body[0]
    if type == 0x00:
        logger.info(f"Recebido pacote de informação com dados de voltagem, dev_id={dev_id}")
        voltage = struct.unpack(">H", body[1:])
        if voltage:
            voltage = voltage[0] / 100
            redis_client.hset(dev_id, 'last_voltage', voltage)
    else:
        pass