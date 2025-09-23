import struct
from datetime import datetime, timezone, timedelta
import json
import copy

from app.core.logger import get_logger
from app.services.redis_service import get_redis
from app.config.settings import settings

logger = get_logger(__name__)
redis_client = get_redis()

def decode_location_packet_v3(body: bytes):

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
        logger.exception(f"Falha ao decodificar pacote de localização GT06 body_hex={body.hex()}")
        return None

def decode_location_packet_v4(body: bytes):

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

        # LBS INFORMATION
        mcc = struct.unpack(">H", body[18:20])[0]
        mnc = body[20]
        lac = struct.unpack(">H", body[21:23])[0]
        cell_id = struct.unpack(">I", body[23:27])[0]

        # Saving LBS information universally
        universal_data = {
            "mcc": mcc,
            "mnc": mnc,
            "lac": lac,
            "cell_id": cell_id
        }
        redis_client.hmset("universal_data", universal_data)

        acc_status = body[27]
        data["acc_status"] = acc_status

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

def decode_location_packet_4g(body: bytes):
    """
    Decodifica o pacote de localização do protocolo 4G (0xA0) do rastreador GT06.
    """
    try:
        data = {}

        # Decodifica o timestamp (6 bytes)
        year, month, day, hour, minute, second = struct.unpack(">BBBBBB", body[0:6])
        data["timestamp"] = datetime(2000 + year, month, day, hour, minute, second).replace(tzinfo=timezone.utc)

        # Quantidade de satélites (1 byte)
        sats_byte = body[6]
        data["satellites"] = sats_byte & 0x0F

        # Latitude e Longitude (8 bytes)
        lat_raw, lon_raw = struct.unpack(">II", body[7:15])
        lat = lat_raw / 1800000.0
        lon = lon_raw / 1800000.0

        data["speed_kmh"] = body[15]

        course_status = struct.unpack(">H", body[16:18])[0]
        
        is_latitude_north = (course_status >> 10) & 1
        is_longitude_west = (course_status >> 11) & 1
        
        data['latitude'] = -abs(lat) if not is_latitude_north else abs(lat)
        data['longitude'] = -abs(lon) if is_longitude_west else abs(lon)
            
        data["direction"] = course_status & 0x03FF

        gps_fixed = (course_status >> 12) & 1
        data["gps_fixed"] = gps_fixed

        # LBS INFORMATION
        mcc = struct.unpack(">H", body[18:20])[0]
        
        mcc_int = struct.unpack(">H", mcc)[0]
        mcc_highest_bit = (mcc_int >> 15) & 1
        
        mnc_len = 2 if mcc_highest_bit == 1 else 1 # 
        
        if mnc_len == 1:
            mnc = struct.unpack(">H", body[20:20 + mnc_len])[0]
            lac_start = 21
        else:
            lac_start = 22
            
        lac_end = lac_start + 4
        lac = struct.unpack(">I", body[lac_start:lac_end])[0]

        cell_id_end = lac_end + 8
        cell_id = struct.unpack(">Q", body[lac_end:cell_id_end])[0]
        
        # Saving LBS information universally
        universal_data = {
            "mcc": mcc,
            "mnc": mnc,
            "lac": lac,
            "cell_id": cell_id
        }
        redis_client.hmset("universal_data", universal_data)
        
        acc_status_at = cell_id_end
        acc_status = body[acc_status_at]
        data["acc_status"] = acc_status        

        is_realtime_at = acc_status_at + 2
        is_realtime = body[is_realtime_at] == 0x00
        data["is_realtime"] = is_realtime

        mileage_at = is_realtime_at + 1
        mileage_km = struct.unpack(">I", body[mileage_at:mileage_at + 4])[0]
        data["gps_odometer"] = mileage_km

        if is_realtime: # Só consideraremos a voltagem se for em tempo real, pois posições da memória estão vindo com esse dado problemático
            voltage_at = mileage_at + 4
            voltage_raw = struct.unpack(">H", body[voltage_at:voltage_at + 2])[0]
            voltage = voltage_raw * 0.01 # 
            data["voltage"] = round(voltage, 2)
        else:
            data["voltage"] = 0.0

        return data

    except Exception as e:
        logger.exception(f"Falha ao decodificar pacote de localização 4G GT06 body_hex={body.hex()}")
        return None


def handle_location_packet(dev_id_str: str, serial: int, body: bytes, protocol_number: int):
    if protocol_number == 0x22:
        packet_data = decode_location_packet_v3(body)
    elif protocol_number == 0x32:
        packet_data = decode_location_packet_v4(body)
    elif protocol_number == 0xA0:
        packet_data = decode_location_packet_4g(body)
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
        "acc_status": packet_data.get('acc_status', 0),
        "power_status": 0 if packet_data.get('voltage', 0.0) > 0 else 1,
        "last_voltage": packet_data.get('voltage', 0.0),
    }
    pipeline = redis_client.pipeline()
    pipeline.hmset(dev_id_str, redis_data)
    pipeline.hincrby(dev_id_str, "total_packets_received", 1)
    pipeline.execute()

    return last_packet_data
def handle_alarm_packet(dev_id_str: str, body: bytes):
    redis_data = {
        "last_active_timestamp": datetime.now(timezone.utc).isoformat(),
        "last_event_type": "alarm",
    }
    pipeline = redis_client.pipeline()
    pipeline.hmset(dev_id_str, redis_data)
    pipeline.hincrby(dev_id_str, "total_packets_received", 1)
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

    last_packet_data_str = redis_client.hget(dev_id_str, "last_packet_data")
    last_packet_data = json.loads(last_packet_data_str) if last_packet_data_str else {}

    definitive_packet_data = {**last_packet_data, **alarm_packet_data}

    if not definitive_packet_data:
        return
    
    alarm_code = body[30]

    universal_alert_id = settings.UNIVERSAL_ALERT_ID_DICTIONARY.get("j16x").get(alarm_code)

    
    if universal_alert_id:
        logger.info(f"Alarme GT06 (0x{alarm_code:02X}) traduzido para Universal ID {universal_alert_id} device_id={dev_id_str}")

        definitive_packet_data["is_realtime"] = True
        definitive_packet_data["universal_alert_id"] = universal_alert_id

        return definitive_packet_data
    
    else:
        logger.warning(f"Alarme GT06 não mapeado recebido device_id={dev_id_str}, alarm_code={hex(alarm_code)}")

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
    pipeline.hmset(dev_id_str, redis_data)
    pipeline.hincrby(dev_id_str, "total_packets_received", 1)
    pipeline.execute()

def handle_reply_command_packet(dev_id: str, body: bytes):
    try:
        command_length = body[0] - 4
        command_content = body[5:5 + command_length]
        command_content_str = command_content.decode("ascii", errors="ignore")

        if command_content_str:
            command_content_str = command_content_str.strip().upper()
            last_packet_data_str = redis_client.hget(dev_id, "last_packet_data")
            last_packet_data = json.loads(last_packet_data_str) if last_packet_data_str else {}
            last_packet_data["timestamp"] = datetime.now(timezone.utc)

            if command_content_str in ("RELAY 1 OK", "RELAY 0 OK"):
                if command_content_str == "RELAY 1 OK":
                    last_packet_data["REPLY"] = "OUTPUT ON"
                elif command_content_str == "RELAY 0 OK":
                    last_packet_data["REPLY"] = "OUTPUT OFF"
                
                return last_packet_data
            else:
                logger.warning(f"Resposta a comando não mapeada para enviar reply ao server principal, dev_id={dev_id}")

    except Exception:
        import traceback
        logger.error(f"Erro ao decodificar comando de REPLY: {traceback.format_exc()}, body={body.hex()}, dev_id={dev_id}")