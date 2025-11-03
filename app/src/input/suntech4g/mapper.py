import json
from datetime import datetime, timezone
import copy
from dateutil import parser

from ..utils import handle_ignition_change
from app.config.settings import settings
from app.core.logger import get_logger
from app.services.redis_service import get_redis

logger = get_logger(__name__)
redis_client = get_redis()

def handle_stt_packet(fields: list) -> dict:
    try:
        dev_id = fields[1]

        report_map = fields[2]
        
        packet_data = {}
        serial = 0
        if report_map == "FFF83F":

            packet_data = {
                "is_realtime": fields[5] == "1",
                "timestamp": datetime(int(fields[6][:4]), int(fields[6][4:6]), int(fields[6][6:8]),
                                int(fields[7][:2]), int(fields[7][3:5]), int(fields[7][6:8])),
                "latitude": float(fields[8]),
                "longitude": float(fields[9]),
                "speed_kmh": float(fields[10]),
                "direction": float(fields[11]),
                "satellites": int(fields[12]),
                "gps_fixed": fields[13] == "1",
                "acc_status": int(fields[14]) & 0b1,
                "output_status": int(fields[15]) & 0b1,
                "voltage": float(fields[21]),
                "gps_odometer": int(fields[23])
            }

            serial = int(fields[22]) if fields[22].isdigit() else 0
        
        # Normalizando dados para armazenamento em Redis
        timestamp_str = packet_data["timestamp"].strftime("%Y-%m-%dT%H:%M:%S")
        packet_data_redis = packet_data.copy()
        packet_data_redis["timestamp"] = timestamp_str

        redis_data = {
            "last_output_status": packet_data["output_status"],
            "last_voltage": packet_data["voltage"],
            "last_packet_data": json.dumps(packet_data_redis),
            "last_active_timestamp": datetime.now().isoformat(),
            "last_event_type": "emergency",
            "power_status": 0 if packet_data.get('voltage', 0.0) > 0 else 1,
        }

        ign_alert_packet_data = None
        # Lidando com o estado da ignição, muito preciso para veículos híbridos.
        is_hybrid, last_altered_acc_str = redis_client.hmget(f"tracker:{fields[1]}", "is_hybrid", "last_altered_acc")

        if is_hybrid:
            if last_altered_acc_str:
                last_altered_acc_dt = parser.parse(last_altered_acc_str, ignoretz=True) 

            if not last_altered_acc_str or (packet_data.get("timestamp") and last_altered_acc_dt < packet_data.get("timestamp")):
                # Lidando com mudanças no status da ignição
                ign_alert_packet_data = handle_ignition_change(fields[1], copy.deepcopy(packet_data))

                redis_data["acc_status"] = packet_data.get("acc_status")
                redis_data["last_altered_acc"] = packet_data.get("timestamp").isoformat()
        
        else:
            redis_data["acc_status"] = packet_data.get("acc_status")

        pipe = redis_client.pipeline()
        pipe.hincrby(f"tracker:{dev_id}", "total_packets_received", 1)
        pipe.hmset(f"tracker:{dev_id}", redis_data)

        pipe.execute()

        return packet_data, ign_alert_packet_data, serial

    except (ValueError, IndexError) as e:
        import traceback
        traceback.print_exc()
        logger.error(f"Error parsing STT packet: {e}")
        return {}, 0

def handle_alt_packet(fields: list) -> dict:
    try:
        dev_id = fields[1]

        report_map = fields[2]
        
        packet_data = {}
        suntech4g_alert_id = None
        if report_map == "FFF83F":

            packet_data = {
                "is_realtime": fields[5] == "1",
                "timestamp": datetime(int(fields[6][:4]), int(fields[6][4:6]), int(fields[6][6:8]),
                                int(fields[7][:2]), int(fields[7][3:5]), int(fields[7][6:8])),
                "latitude": float(fields[8]),
                "longitude": float(fields[9]),
                "speed_kmh": float(fields[10]),
                "direction": float(fields[11]),
                "satellites": int(fields[12]),
                "gps_fixed": fields[13] == "1",
                "acc_status": int(fields[14]) & 0b1,
                "output_status": int(fields[15]) & 0b1,
                "voltage": float(fields[21]),
                "gps_odometer": int(fields[23])
            }

            suntech4g_alert_id = int(fields[16])


        # Mapeamento de IDs de Alerta
        universal_alert_id = settings.UNIVERSAL_ALERT_ID_DICTIONARY.get("suntech4g", {}).get(suntech4g_alert_id, 0)
        if universal_alert_id:
            packet_data["universal_alert_id"] = universal_alert_id

        # Normalizando dados para armazenamento em Redis
        timestamp_str = packet_data["timestamp"].strftime("%Y-%m-%dT%H:%M:%S")
        packet_data_redis = packet_data.copy()
        packet_data_redis["timestamp"] = timestamp_str

        redis_data = {
            "last_output_status": packet_data["output_status"],
            "last_voltage": packet_data["voltage"],
            "last_packet_data": json.dumps(packet_data_redis),
            "last_active_timestamp": datetime.now().isoformat(),
            "last_event_type": "emergency",
            "power_status": 0 if packet_data.get('voltage', 0.0) > 0 else 1,
        }

        ign_alert_packet_data = None
        # Lidando com o estado da ignição, muito preciso para veículos híbridos.
        is_hybrid, last_altered_acc_str = redis_client.hmget(f"tracker:{dev_id}", "is_hybrid", "last_altered_acc")

        if is_hybrid:
            if last_altered_acc_str:
                last_altered_acc_dt = parser.parse(last_altered_acc_str, ignoretz=True) 

            if not last_altered_acc_str or (packet_data.get("timestamp") and last_altered_acc_dt < packet_data.get("timestamp")):
                # Lidando com mudanças no status da ignição
                ign_alert_packet_data = handle_ignition_change(dev_id, copy.deepcopy(packet_data))

                redis_data["acc_status"] = packet_data.get("acc_status")
                redis_data["last_altered_acc"] = packet_data.get("timestamp").isoformat()

        pipe = redis_client.pipeline()
        pipe.hincrby(f"tracker:{dev_id}", "total_packets_received", 1)
        pipe.hmset(f"tracker:{dev_id}", redis_data)

        pipe.execute()

        return packet_data, ign_alert_packet_data
    except (ValueError, IndexError) as e:
        logger.error(f"Error parsing ALT packet: {e}")
        return {}

def handle_reply_packet(dev_id: str, fields: list) -> dict:
    try:
        reply_group = fields[2]
        reply_action = fields[3]
        error = int(fields[-1])

        packet_data_str = redis_client.hget(f"tracker:{fields[2]}", "last_packet_data")
        packet_data = json.loads(packet_data_str) if packet_data_str else {}
        packet_data["timestamp"] = datetime.now()

        if reply_group == "04" and reply_action == "02" and not error:
            packet_data["REPLY"] = "OUTPUT OFF"
            redis_client.hset(f"tracker:{dev_id}", "last_command_reply", "Unblocked")

        elif reply_group == "04" and reply_action == "01" and not error:
            packet_data["REPLY"] = "OUTPUT ON"
            redis_client.hset(f"tracker:{dev_id}", "last_command_reply", "Blocked")

        else:
            logger.warning(f"Unknown reply command received: {';'.join(fields)}")

        return packet_data
    except Exception as e:
        logger.error(f"Error parsing CMD packet: {e}")
        return {}