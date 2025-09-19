import struct
from datetime import datetime, timezone, timedelta
import json
import copy

from app.core.logger import get_logger
from app.services.redis_service import get_redis
from app.config.settings import settings
from .utils import _decode_alarm_location_packet
from app.src.session.output_sessions_manager import send_to_main_server
from .utils import haversine

logger = get_logger(__name__)
redis_client = get_redis()

def _decode_location_packet(body: bytes):

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

        try: # Colocando dentro de um try except pois essa funcao tbm recebe chamadas para decodificar pacotes de alerta, que não tem as infos abaixo, 
            # Na ordem em que estão abaixo
            mcc = struct.unpack(">H", body[18:20])[0]
            mnc_length = 1
            if (mcc >> 15) & 1:
                mnc_length = 2

            acc_at = 20 + mnc_length + 4 + 8
            acc_status = body[acc_at]
            data["acc_status"] = acc_status

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
    packet_data = _decode_location_packet(body)

    if not packet_data:
        return
    
    if packet_data.get("acc_status"):
        # Haversine Odometer Calculation
        # Fetch multiple values at once
        redis_state = redis_client.hgetall(f"tracker:{dev_id_str}")
        last_location_str = redis_state.get("last_location")
        current_odometer = float(redis_state.get("odometer", 0.0))

        if last_location_str:
            last_location = json.loads(last_location_str)
            last_lat = last_location["latitude"]
            last_lon = last_location["longitude"]
            
            current_lat = packet_data["latitude"]
            current_lon = packet_data["longitude"]

            distance = haversine(last_lat, last_lon, current_lat, current_lon) * 1000  # Convert to meters
            current_odometer += distance
            logger.info(f"Odometer for {dev_id_str}: {current_odometer/1000:.2f} km (distance added: {distance/1000:.2f} km)")
        else:
            logger.info(f"No previous location for {dev_id_str}. Odometer starting at {current_odometer/1000:.2f} km.")

        packet_data["gps_odometer"] = current_odometer

        redis_data = {
            "odometer": str(current_odometer),
            "last_location": json.dumps({"latitude": packet_data["latitude"], "longitude": packet_data["longitude"]})
        }

        pipeline = redis_client.pipeline()
        pipeline.hmset(f"tracker:{dev_id_str}", redis_data)
        pipeline.execute()

    else:
        # Fetch multiple values at once
        redis_state = redis_client.hgetall(f"tracker:{dev_id_str}")
        last_odometer = redis_state.get("odometer")
        if last_odometer:
            packet_data["gps_odometer"] = float(last_odometer)
        else:
            packet_data["gps_odometer"] = 0.0

    last_packet_data = copy.deepcopy(packet_data)
    
    last_packet_data["timestamp"] = last_packet_data["timestamp"].strftime("%Y-%m-%dT%H:%M:%S")

    # Salvando para uso em caso de alarmes
    redis_data = {
        "imei": dev_id_str,
        "last_packet_data": json.dumps(last_packet_data),
        "last_full_location": json.dumps(packet_data, default=str),
        "last_serial": serial,
        "last_active_timestamp": datetime.now(timezone.utc).isoformat(),
        "last_event_type": "location",
    }
    pipeline = redis_client.pipeline()
    pipeline.hmset(f"tracker:{dev_id_str}", redis_data)
    pipeline.hincrby(f"tracker:{dev_id_str}", "total_packets_received", 1)
    pipeline.execute()

    send_to_main_server(dev_id_str, packet_data, serial, raw_packet_hex, original_protocol="VL01")

def handle_alarm_packet(dev_id_str: str, serial: int, body: bytes, raw_packet_hex: str):
    redis_data = {
        "last_active_timestamp": datetime.now(timezone.utc).isoformat(),
        "last_event_type": "alarm",
    }
    pipeline = redis_client.pipeline()
    pipeline.hmset(f"tracker:{dev_id_str}", redis_data)
    pipeline.hincrby(f"tracker:{dev_id_str}", "total_packets_received", 1)
    pipeline.execute()

    if len(body) < 17:
        logger.info(f"Pacote de dados de alarme recebido com um tamanho menor do que o esperado, body={body.hex()}")
        return
    
    alarm_packet_data = _decode_alarm_location_packet(body[0:16])
    if not alarm_packet_data:
        logger.info(f"Pacote de alarme sem dados de localização, descartando... dev_id={dev_id_str}, packet={body}")
        return
    
    alarm_datetime = alarm_packet_data.get("timestamp")
    if not alarm_datetime:
        logger.info(f"Pacote de alarme sem data e hora, descartando... dev_id={dev_id_str}")
        return
    
    limit = datetime.now(timezone.utc) - timedelta(minutes=2)

    if not alarm_datetime > limit:
        logger.info(f"Alarme da memória, descartando... dev_id={dev_id_str}")

    last_packet_data_str = redis_client.hget(f"tracker:{dev_id_str}", "last_packet_data")
    last_packet_data = json.loads(last_packet_data_str) if last_packet_data_str else {}

    definitive_packet_data = {**last_packet_data, **alarm_packet_data}

    if not definitive_packet_data:
        return
    
    alarm_code = body[16]

    universal_alert_id = settings.UNIVERSAL_ALERT_ID_DICTIONARY.get("vl01").get(alarm_code)

    if universal_alert_id:
        logger.info(f"Alarme VL01 (0x{alarm_code:02X}) traduzido para Global ID {universal_alert_id} device_id={dev_id_str}")

        send_to_main_server(dev_id_str, definitive_packet_data, serial, raw_packet_hex, original_protocol="VL01", type="alert")
    else:
        logger.warning(f"Alarme VL01 não mapeado recebido device_id={dev_id_str}, alarm_code={hex(alarm_code)}")

def handle_heartbeat_packet(dev_id_str: str, serial: int, body: bytes, raw_packet_hex: str):
    logger.info(f"Pacote de heartbeat recebido de {dev_id_str}, body={body.hex()}")
    # O pacote de Heartbeat (0x13) contém informações de status
    redis_data = {
        "last_active_timestamp": datetime.now(timezone.utc).isoformat(),
        "last_event_type": "heartbeat",
    }
    terminal_info = body[0]
    acc_status = 1 if terminal_info & 0b10 else 0
    
    power_alarm_flag = (terminal_info >> 3) & 0b111
    power_status = 1 if power_alarm_flag == 0b010 else 0 # 1 = desconectado
    output_status = (terminal_info >> 7) & 0b1

    logger.info(f"DEVICE {dev_id_str} STATUS: ACC: {acc_status}, Power: {power_status}, Output: {output_status}")
    redis_data["last_serial"] = serial
    
    pipeline = redis_client.pipeline()
    pipeline.hmset(f"tracker:{dev_id_str}", redis_data)
    pipeline.hincrby(f"tracker:{dev_id_str}", "total_packets_received", 1)
    pipeline.execute()

    # Keep-Alive
    send_to_main_server(dev_id_str, serial=serial, raw_packet_hex=raw_packet_hex, original_protocol="VL01", type="heartbeat")

def handle_reply_command_packet(dev_id: str, serial: int, body: bytes, raw_packet_hex: str):
    try:
        command_content = body[5:]
        command_content_str = command_content.decode("ascii", errors="ignore")
        if command_content_str:
            last_packet_data_str = redis_client.hget(f"tracker:{dev_id}", "last_packet_data")
            last_packet_data = json.loads(last_packet_data_str) if last_packet_data_str else {}
            last_packet_data["timestamp"] = datetime.now(timezone.utc)

            if command_content_str == "RELAY:ON":
                redis_client.hset(f"tracker:{dev_id}", "last_output_status", 1)
                last_packet_data["REPLY"] = "OUTPUT ON"
            elif command_content_str == "RELAY:OFF":
                redis_client.hset(f"tracker:{dev_id}", "last_output_status", 0)
                last_packet_data["REPLY"] = "OUTPUT OFF"

            send_to_main_server(dev_id, last_packet_data, serial, raw_packet_hex, original_protocol="VL01", type="command_reply")

    except Exception as e:
        logger.error(f"Erro ao decodificar comando de REPLY: {e} body={body.hex()}, dev_id={dev_id}")

def handle_information_packet(dev_id: str, serial: int, body: bytes, raw_packet_hex: str):
    redis_data = {
        "last_active_timestamp": datetime.now(timezone.utc).isoformat(),
        "last_event_type": "information",
    }
    pipeline = redis_client.pipeline()
    pipeline.hmset(f"tracker:{dev_id}", redis_data)
    pipeline.hincrby(f"tracker:{dev_id}", "total_packets_received", 1)
    
    type = body[0]
    if type == 0x00:
        logger.info(f"Recebido pacote de informação com dados de voltagem, dev_id={dev_id}")
        voltage = struct.unpack(">H", body[1:])
        if voltage:
            voltage = voltage[0] / 100
            redis_data = {
                "last_voltage": voltage,
                "power_status": 0 if voltage > 0 else 1
            }

            pipeline.hmset(f"tracker:{dev_id}", 'last_voltage', voltage)
    else:
        pass
    pipeline.execute()
