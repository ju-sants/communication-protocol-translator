import struct
from datetime import datetime, timezone
import json
import copy

from app.core.logger import get_logger
from app.services.redis_service import get_redis
from ..utils import handle_ignition_change
from app.config.settings import settings

logger = get_logger(__name__)
redis_client = get_redis()

def decode_timestamp(timestamp_bytes: bytes):
    timestamp = int.from_bytes(timestamp_bytes, "big")
    
    seconds = timestamp % 60
    minutes = int(timestamp / 60) % 60
    hours = int(timestamp / (60 * 60)) % 24
    days = 1 + int(timestamp / (60 * 60 * 24)) % 31
    month = 1 + int(timestamp / (60 * 60 * 24 * 31)) % 12
    year = 2000 + int(timestamp / (60 * 60 * 24 * 31 * 12))

    return datetime(year, month, days, hours, minutes, seconds)

def decode_general_report(payload: bytes):

    data = {}
    try:
        mask = int.from_bytes(payload[:4], "big")
        logger.debug(f"mask={bin(mask)}")
        parser_at = 4
        if mask & 0b1: # Product ID present
            parser_at = 5

        if (mask >> 1) & 0b1: # GPS timestamp present
            gps_timestamp_bytes = payload[parser_at:parser_at + 4]
            data["timestamp"] = decode_timestamp(gps_timestamp_bytes)
            logger.debug(f"gps_timestamp_bytes={gps_timestamp_bytes.hex()}, timestamp={data['timestamp']}")

            parser_at += 4

        if (mask >> 2) & 0b1: # Lat e Lon present
            lat_long_bytes = payload[parser_at:parser_at + 8]
            logger.debug(f"lat_long_bytes={lat_long_bytes.hex()}")
            
            encodedLat, encodedLon = struct.unpack(">II", lat_long_bytes)
            latitude = (encodedLat / 1000000.0) - 90.0
            longitude = (encodedLon / 1000000.0) - 180.0

            data["latitude"] = latitude
            data["longitude"] = longitude
            logger.debug(f"encodedLat={encodedLat}, encodedLon={encodedLon}, latitude={latitude}, longitude={longitude}")

            parser_at += 8

        if (mask >> 3) & 0b1: # Speed And Direction Degrees present
            speed_degree = payload[parser_at:parser_at + 3]
            logger.debug(f"speed_degree={speed_degree.hex()}")

            speed_kmh, direction = struct.unpack(">BH", speed_degree)
            
            data["speed_kmh"] = speed_kmh 
            data["direction"] = direction
            logger.debug(f"speed_kmh={speed_kmh}, direction={direction}")
            
            parser_at += 3

        if (mask >> 4) & 0b1: # GPS Altitude present
            logger.debug(f"GPS Altitude present, skipping 2 bytes")
            parser_at += 2

        if (mask >> 5) & 0b1: # GPS Accuracy present
            gps_accuracy_byte = int.from_bytes(payload[parser_at:parser_at + 1], "big")
            logger.debug(f"gps_accuracy_byte={hex(gps_accuracy_byte)}")

            # Deslocamos 4 bits para a direita e aplicamos a máscara 0x0F para termos certeza de ter isolado os bits 4-7, depois aplicamos uma máscara para descobrir se o gps está fixado, se os três primeiros bits do nibble forem 001.
            gps_fixed = (gps_accuracy_byte >> 4) & 0x0F & 0b111 == 1
            satellites = gps_accuracy_byte & 0x0F
            
            data["gps_fixed"] = gps_fixed
            data["satellites"] = satellites
            logger.debug(f"gps_fixed={gps_fixed}, satellites={satellites}")

            parser_at += 2

        if (mask >> 6) & 0b1: # Main Voltage present
            main_voltage_bytes = payload[parser_at:parser_at + 2]
            logger.debug(f"main_voltage_bytes={main_voltage_bytes.hex()}")

            main_voltage = int.from_bytes(main_voltage_bytes, "big")
            voltage = main_voltage / 1000
            
            data["voltage"] = voltage
            logger.debug(f"main_voltage={main_voltage}, voltage={voltage}")

            parser_at += 2

        if (mask >> 7) & 0b1: # Battery Voltage present
            logger.debug(f"Battery Voltage present, skipping 2 bytes")
            parser_at += 2

        if (mask >> 8) & 0b1: # Aux Voltage present
            logger.debug(f"Aux Voltage present, skipping 2 bytes")
            parser_at += 2

        if (mask >> 9) & 0b1: # Solar Voltage present
            logger.debug(f"Solar Voltage present, skipping 2 bytes")
            parser_at += 2

        if (mask >> 10) & 0b1: # Cellular Service present
            logger.debug(f"Cellular Service present, skipping 5 bytes")
            parser_at += 5

        if (mask >> 11) & 0b1: # RSSI present
            logger.debug(f"RSSI present, skipping 1 byte")
            parser_at += 1

        if (mask >> 12) & 0b1: # GPIO A-D present
            gpio_ad = int.from_bytes(payload[parser_at:parser_at + 1], 'big')
            logger.debug(f"gpio_ad={bin(gpio_ad)}")

            acc_status = gpio_ad & 0b1
            output_status = (gpio_ad >> 4) & 0b1
            
            data["acc_status"] = acc_status
            data["output_status"] = output_status

            parser_at += 1

        if (mask >> 13) & 0b1: # GPIO E-H present
            gpio_eh = payload[parser_at:parser_at + 1]
            logger.debug(f"gpio_eh={bin(int.from_bytes(gpio_eh, 'big'))}")

            parser_at += 1

        if (mask >> 14) & 0b1: # Odometer present
            odometer_bytes = payload[parser_at:parser_at + 4]
            logger.debug(f"odometer_bytes={odometer_bytes.hex()}")

            odometer = int.from_bytes(odometer_bytes, "big")
            odometer = odometer * 100

            data["gps_odometer"] = odometer
            logger.debug(f"odometer={odometer}")

        return data
    except Exception as e:
        logger.exception(f"Falha ao decodificar pacote de localização GP900M body_hex={payload.hex()}")
        return None

def handle_general_report(dev_id_str: str, serial: int, payload: bytes, event: int, payload_value_starts_at: int):
    packet_data = decode_general_report(payload[payload_value_starts_at:]) # Enviando o payload depois dos bytes de tipo
    if not packet_data:
        return
    
    alarm_packet_data = None
    if event:
        universal_alert_id = settings.UNIVERSAL_ALERT_ID_DICTIONARY.get(event)
        if universal_alert_id:
            alarm_packet_data = copy.deepcopy(packet_data)
            alarm_packet_data["universal_alert_id"] = universal_alert_id

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
        "last_voltage": packet_data.get("voltage"),
        "last_output_status": packet_data.get("output_status")
    }


    ign_alert_packet_data = None
    if redis_client.hget(f"tracker:{dev_id_str}", "is_hybrid"):
        # Lidando com o estado da ignição, muito preciso para veículos híbridos.
        last_altered_acc_str = redis_client.hget(f"tracker:{dev_id_str}", "last_altered_acc")
        if last_altered_acc_str:
            last_altered_acc_dt = datetime.fromisoformat(last_altered_acc_str)

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

    return packet_data, alarm_packet_data, ign_alert_packet_data

def handle_odometer_read(dev_id_str, serial_number, payload, event, payload_value_starts_at):
    pass