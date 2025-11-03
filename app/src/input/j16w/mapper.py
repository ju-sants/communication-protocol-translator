import struct
from datetime import datetime, timezone, timedelta
import json
import copy
from dateutil import parser

from app.core.logger import get_logger
from app.services.redis_service import get_redis

from ..utils import handle_ignition_change
from app.config.settings import settings

logger = get_logger(__name__)
redis_client = get_redis()

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
        data["gps_fixed"] = gps_fixed

        try: # Colocando dentro de um try except pois essa funcao tbm recebe chamadas para decodificar pacotes de alerta, que não tem as infos abaixo, 
            # Na ordem em que estão abaixo
            
            # LBS INFORMATION
            mcc = struct.unpack(">H", body[18:20])[0]
            mnc = body[20]
            lac = struct.unpack(">H", body[21:23])[0]
            cell_id = int.from_bytes(body[23:26], "big")

            # Saving LBS information universally
            universal_data = {
                "mcc": mcc,
                "mnc": mnc,
                "lac": lac,
                "cell_id": cell_id
            }
            redis_client.hmset("universal_data", universal_data)

            acc_status = body[26]
            data["acc_status"] = acc_status

            is_realtime = body[28] == 0x00

            data["is_realtime"] = is_realtime

            mileage_at = 29
            mileage_km = struct.unpack(">I", body[mileage_at:mileage_at + 4])[0]
            data["gps_odometer"] = mileage_km
        except Exception:
            pass

        return data

    except Exception as e:
        logger.exception(f"Falha ao decodificar pacote de localização J16W body_hex={body.hex()}")
        return None

def handle_location_packet(dev_id_str: str, serial: int, body: bytes, protocol_number: int):
    if protocol_number == 0x22:
        packet_data = decode_location_packet_v3(body)
    else:
        logger.info("Tipo de protocolo não mapeado")
        packet_data = None

    if not packet_data:
        return
        
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
        "power_status": 0 if packet_data.get('voltage', 0.0) > 0 else 1,
    }

    if packet_data.get("voltage"):
        redis_data["last_voltage"] = packet_data["voltage"]

    ign_alert_packet_data = None
    if redis_client.hget(f"tracker:{dev_id_str}", "is_hybrid"):
        # Lidando com o estado da ignição, muito preciso para veículos híbridos.
        last_altered_acc_str = redis_client.hget(f"tracker:{dev_id_str}", "last_altered_acc")
        if last_altered_acc_str:
            last_altered_acc_dt = parser.parse(last_altered_acc_str, ignoretz=True) 

        if not last_altered_acc_str or (packet_data.get("timestamp") and last_altered_acc_dt < packet_data.get("timestamp")):
            # Lidando com mudanças no status da ignição
            ign_alert_packet_data = handle_ignition_change(dev_id_str, copy.deepcopy(packet_data))

            redis_data["acc_status"] = packet_data.get("acc_status")
            redis_data["last_altered_acc"] = packet_data.get("timestamp").isoformat()

    else:
        redis_data["acc_status"] = packet_data.get("acc_status")

    pipeline = redis_client.pipeline()
    pipeline.hmset(f"tracker:{dev_id_str}", redis_data)
    pipeline.hincrby(f"tracker:{dev_id_str}", "total_packets_received", 1)
    pipeline.execute()

    return packet_data, ign_alert_packet_data
def handle_alarm_packet(dev_id_str: str, body: bytes):
    redis_data = {
        "last_active_timestamp": datetime.now(timezone.utc).isoformat(),
        "last_event_type": "alarm",
    }
    pipeline = redis_client.pipeline()
    pipeline.hmset(f"tracker:{dev_id_str}", redis_data)
    pipeline.hincrby(f"tracker:{dev_id_str}", "total_packets_received", 1)
    pipeline.execute()

    if len(body) < 32:
        logger.info(f"Pacote de dados de alarme recebido com um tamanho menor do que o esperado, body={body.hex()}")
        return
    
    alarm_packet_data = decode_location_packet_v3(body[0:18])
    
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
    
    alarm_code = body[30]

    universal_alert_id = settings.UNIVERSAL_ALERT_ID_DICTIONARY.get("j16x_j16").get(alarm_code)

    
    if universal_alert_id:
        logger.info(f"Alarme J16W (0x{alarm_code:02X}) traduzido para Universal ID {universal_alert_id} device_id={dev_id_str}")

        definitive_packet_data["is_realtime"] = True
        definitive_packet_data["universal_alert_id"] = universal_alert_id

        return definitive_packet_data
    
    else:
        logger.warning(f"Alarme J16W não mapeado recebido device_id={dev_id_str}, alarm_code={hex(alarm_code)}")

def handle_heartbeat_packet(dev_id_str: str, serial: int, body: bytes):
    # O pacote de Heartbeat (0x13) contém informações de status
    redis_data = {
        "last_active_timestamp": datetime.now(timezone.utc).isoformat(),
        "last_event_type": "heartbeat",
    }
    terminal_info = body[0]

    output_status = (terminal_info >> 7) & 0b1
    redis_data["last_output_status"] = output_status
    redis_data["last_serial"] = serial

    pipeline = redis_client.pipeline()
    pipeline.hmset(f"tracker:{dev_id_str}", redis_data)
    pipeline.hincrby(f"tracker:{dev_id_str}", "total_packets_received", 1)
    pipeline.execute()

def handle_reply_command_packet(dev_id: str, body: bytes):
    try:
        command_length = body[0] - 4
        command_content = body[6:6 + command_length]
        command_content_str = command_content.decode("ascii", errors="ignore")

        if command_content_str:
            redis_client.hset(f"tracker:{dev_id}", "last_command_reply", command_content_str)
            
            command_content_str = command_content_str.strip().upper()
            last_packet_data_str, last_command = redis_client.hmget(f"tracker:{dev_id}", "last_packet_data", "last_command")
            last_packet_data = json.loads(last_packet_data_str) if last_packet_data_str else {}
            last_packet_data["timestamp"] = datetime.now(timezone.utc)
            
            if last_command:
                if command_content_str == "SET OK":
                    if last_command == "OUTPUT ON":
                        last_packet_data["REPLY"] = "OUTPUT ON"
                    elif last_command == "OUTPUT OFF":
                        last_packet_data["REPLY"] = "OUTPUT OFF"
                    
                    return last_packet_data
                else:
                    logger.warning(f"Resposta a comando não mapeada para enviar reply ao server principal, dev_id={dev_id}, reply={command_content_str}")

    except Exception:
        import traceback
        logger.error(f"Erro ao decodificar comando de REPLY: {traceback.format_exc()}, body={body.hex()}, dev_id={dev_id}")

def handle_information_packet(dev_id: str, body: bytes):
    redis_data = {
        "last_active_timestamp": datetime.now(timezone.utc).isoformat(),
        "last_event_type": "information",
    }
    pipeline = redis_client.pipeline()
    pipeline.hmset(f"tracker:{dev_id}", redis_data)
    pipeline.hincrby(f"tracker:{dev_id}", "total_packets_received", 1)
    
    type = body[0]
    if type == 0x00:
        voltage = struct.unpack(">H", body[1:])
        if voltage:
            voltage = voltage[0] / 100
            logger.info(f"Recebido pacote de informação com dados de voltagem, dev_id={dev_id}, voltage={voltage}")

            redis_data = {
                "last_voltage": voltage,
                "power_status": 0 if voltage > 0 else 1
            }

            pipeline.hmset(f"tracker:{dev_id}", redis_data)
    else:
        pass

    pipeline.execute()