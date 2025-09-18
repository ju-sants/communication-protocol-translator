import json
from datetime import datetime, timezone

from ..utils import handle_ignition_change
from app.config.settings import settings
from app.src.session.output_sessions_manager import send_to_main_server
from app.core.logger import get_logger
from app.services.redis_service import get_redis

logger = get_logger(__name__)
redis_client = get_redis()

def handle_stt_packet(fields: list, standard: str) -> dict:
    try:
        dev_id = fields[1]

        if standard not in ["ST300", "SA200"]:
            logger.warning(f"Unknown standard '{standard}' for STT packet from device {dev_id}")
            return {}, 0
        
        if standard == "ST300":
            packet_data = {
                "timestamp": datetime(int(fields[4][:4]), int(fields[4][4:6]), int(fields[4][6:8]),
                                    int(fields[5][:2]), int(fields[5][3:5]), int(fields[5][6:8]), tzinfo=timezone.utc),
                "latitude": float(fields[7]),
                "longitude": float(fields[8]),
                "speed_kmh": float(fields[9]),
                "direction": float(fields[10]),
                "satellites": int(fields[11]),
                "gps_fixed": fields[12] == "1",
                "odometer": int(fields[13]),
                "voltage": float(fields[14]),
                "acc_status": int(fields[15][0]),
                "output_status": int(fields[15][4]),
                "is_realtime": len(fields) > 20 and fields[20] == "1",
            }

            serial = int(fields[17]) if fields[17].isdigit() else 0
        
        elif standard == "SA200":
            packet_data = {
                "timestamp": datetime(int(fields[3][:4]), int(fields[3][4:6]), int(fields[3][6:8]),
                                    int(fields[4][:2]), int(fields[4][3:5]), int(fields[4][6:8]), tzinfo=timezone.utc),
                "latitude": float(fields[6]),
                "longitude": float(fields[7]),
                "speed_kmh": float(fields[8]),
                "direction": float(fields[9]),
                "satellites": int(fields[10]),
                "gps_fixed": fields[11] == "1",
                "odometer": int(fields[12]),
                "voltage": float(fields[13]),
                "acc_status": int(fields[14][0]),
                "output_status": int(fields[14][4]),
                "is_realtime": len(fields) > 19 and fields[19] == "1",
            }

            serial = int(fields[16]) if fields[16].isdigit() else 0

        # Lidando com mudanças no status da ignição
        alert_packet_data = handle_ignition_change(dev_id, serial, packet_data, raw_packet_hex=";".join(fields), original_protocol="suntech2g")
        if alert_packet_data and alert_packet_data.get("universal_alert_id"):
            send_to_main_server(dev_id, packet_data=alert_packet_data, serial=serial, raw_packet_hex=";".join(fields), original_protocol="suntech2g", type="alert")

        # Normalizando dados para armazenamento em Redis
        timestamp_str = packet_data["timestamp"].strftime("%Y-%m-%dT%H:%M:%S")
        packet_data_redis = packet_data.copy()
        packet_data_redis["timestamp"] = timestamp_str

        redis_data = {
            "last_output_status": packet_data["output_status"],
            "last_voltage": packet_data["voltage"],
            "last_serial": serial,
            "last_packet_data": json.dumps(packet_data_redis),
            "last_active_timestamp": datetime.now(timezone.utc).isoformat(),
            "last_event_type": "location",
            "acc_status": packet_data.get('acc_status', 0),
            "power_status": 0 if packet_data.get('voltage', 0.0) > 0 else 1,
        }

        pipe = redis_client.pipeline()
        pipe.hincrby(dev_id, "total_packets_received", 1)
        pipe.hmset(dev_id, redis_data)

        pipe.execute()

        print(redis_client.hget(dev_id, "acc_status"))

        logger.info(f"STT packet mapped data: {packet_data}")
        return packet_data, serial

    except (ValueError, IndexError) as e:
        logger.error(f"Error parsing STT packet: {e}")
        return {}, 0

def handle_emg_packet(fields: list, standard: str) -> dict:
    try:
        if standard not in ["ST300", "SA200"]:
            logger.warning(f"Unknown standard '{standard}' for EMG packet from device {fields[1]}")
            return {}
        
        if standard == "ST300":
            packet_data = {
                "timestamp": datetime(int(fields[4][:4]), int(fields[4][4:6]), int(fields[4][6:8]),
                                    int(fields[5][:2]), int(fields[5][3:5]), int(fields[5][6:8]), tzinfo=timezone.utc),
                "latitude": float(fields[7]),
                "longitude": float(fields[8]),
                "speed_kmh": float(fields[9]),
                "direction": float(fields[10]),
                "satellites": int(fields[11]),
                "gps_fixed": fields[12] == "1",
                "odometer": int(fields[13]),
                "voltage": float(fields[14]),
                "acc_status": fields[15][0],
                "output_status": fields[15][4],
                "emergency_type": fields[16],
                "is_realtime": len(fields) > 19 and fields[19] == "1",
            }
        
        elif standard == "SA200":
            packet_data = {
                "timestamp": datetime(int(fields[3][:4]), int(fields[3][4:6]), int(fields[3][6:8]),
                                    int(fields[4][:2]), int(fields[4][3:5]), int(fields[4][6:8]), tzinfo=timezone.utc),
                "latitude": float(fields[6]),
                "longitude": float(fields[7]),
                "speed_kmh": float(fields[8]),
                "direction": float(fields[9]),
                "satellites": int(fields[10]),
                "gps_fixed": fields[11] == "1",
                "odometer": int(fields[12]),
                "voltage": float(fields[13]),
                "acc_status": fields[14][0],
                "output_status": fields[14][4],
                "emergency_type": fields[15],
                "is_realtime": len(fields) > 19 and fields[19] == "1",
            }

        # Lidando com mudanças no status da ignição
        alert_packet_data = handle_ignition_change(fields[1], 0, packet_data, raw_packet_hex=";".join(fields), original_protocol="suntech2g")
        if alert_packet_data and alert_packet_data.get("universal_alert_id"):
            send_to_main_server(fields[1], packet_data=alert_packet_data, serial=0, raw_packet_hex=";".join(fields), original_protocol="suntech2g", type="alert")

        # Normalizando dados para armazenamento em Redis
        timestamp_str = packet_data["timestamp"].strftime("%Y-%m-%dT%H:%M:%S")
        packet_data_redis = packet_data.copy()
        packet_data_redis["timestamp"] = timestamp_str

        redis_data = {
            "last_output_status": packet_data["output_status"],
            "last_voltage": packet_data["voltage"],
            "last_packet_data": json.dumps(packet_data_redis),
            "last_active_timestamp": datetime.now(timezone.utc).isoformat(),
            "last_event_type": "emergency",
            "acc_status": packet_data.get('acc_status', 0),
            "power_status": 0 if packet_data.get('voltage', 0.0) > 0 else 1,
        }

        pipe = redis_client.pipeline()
        pipe.hincrby(fields[1], "total_packets_received", 1)
        pipe.hmset(fields[1], redis_data)
        
        pipe.execute()

        logger.info(f"EMG packet mapped data: {packet_data}")
        return packet_data

    except (ValueError, IndexError) as e:
        logger.error(f"Error parsing EMG packet: {e}")
        return {}

def handle_evt_packet(fields: list, standard: str) -> dict:
    try:
        if standard not in ["ST300", "SA200"]:
            logger.warning(f"Unknown standard '{standard}' for EVT packet from device {fields[1]}")
            return {}
        
        if standard == "ST300":
            packet_data = {
                "timestamp": datetime(int(fields[4][:4]), int(fields[4][4:6]), int(fields[4][6:8]),
                                    int(fields[5][:2]), int(fields[5][3:5]), int(fields[5][6:8]), tzinfo=timezone.utc),
                "latitude": float(fields[7]),
                "longitude": float(fields[8]),
                "speed_kmh": float(fields[9]),
                "direction": float(fields[10]),
                "satellites": int(fields[11]),
                "gps_fixed": fields[12] == "1",
                "odometer": int(fields[13]),
                "voltage": float(fields[14]),
                "acc_status": fields[15][0],
                "output_status": fields[15][4],
                "event_type": fields[16],
                "is_realtime": len(fields) > 19 and fields[19] == "1",
            }
        
        elif standard == "SA200":
            packet_data = {
                "timestamp": datetime(int(fields[3][:4]), int(fields[3][4:6]), int(fields[3][6:8]),
                                    int(fields[4][:2]), int(fields[4][3:5]), int(fields[4][6:8]), tzinfo=timezone.utc),
                "latitude": float(fields[6]),
                "longitude": float(fields[7]),
                "speed_kmh": float(fields[8]),
                "direction": float(fields[9]),
                "satellites": int(fields[10]),
                "gps_fixed": fields[11] == "1",
                "odometer": int(fields[12]),
                "voltage": float(fields[13]),
                "acc_status": fields[14][0],
                "output_status": fields[14][4],
                "event_type": fields[15],
                "is_realtime": len(fields) > 19 and fields[19] == "1",
            }

        # Lidando com mudanças no status da ignição
        alert_packet_data = handle_ignition_change(fields[1], 0, packet_data, raw_packet_hex=";".join(fields), original_protocol="suntech2g")
        if alert_packet_data and alert_packet_data.get("universal_alert_id"):
            send_to_main_server(fields[1], packet_data=alert_packet_data, serial=0, raw_packet_hex=";".join(fields), original_protocol="suntech2g", type="alert")


        # Normalizando dados para armazenamento em Redis
        timestamp_str = packet_data["timestamp"].strftime("%Y-%m-%dT%H:%M:%S")
        packet_data_redis = packet_data.copy()
        packet_data_redis["timestamp"] = timestamp_str

        redis_data = {
            "last_output_status": packet_data["output_status"],
            "last_voltage": packet_data["voltage"],
            "last_packet_data": json.dumps(packet_data_redis),
            "last_active_timestamp": datetime.now(timezone.utc).isoformat(),
            "last_event_type": "event",
            "acc_status": packet_data.get('acc_status', 0),
            "power_status": 0 if packet_data.get('voltage', 0.0) > 0 else 1,
        }

        pipe = redis_client.pipeline()
        pipe.hincrby(fields[1], "total_packets_received", 1)
        pipe.hmset(fields[1], redis_data)

        pipe.execute()

        logger.info(f"EVT packet mapped data: {packet_data}")
        return packet_data

    except (ValueError, IndexError) as e:
        logger.error(f"Error parsing EVT packet: {e}")
        return {}

def handle_alt_packet(fields: list, standard: str) -> dict:
    try:
        if standard not in ["ST300", "SA200"]:
            logger.warning(f"Unknown standard '{standard}' for ALT packet from device {fields[1]}")
            return {}
        
        if standard == "ST300":
            packet_data = {
                "timestamp": datetime(int(fields[4][:4]), int(fields[4][4:6]), int(fields[4][6:8]),
                                    int(fields[5][:2]), int(fields[5][3:5]), int(fields[5][6:8]), tzinfo=timezone.utc),
                "latitude": float(fields[7]),
                "longitude": float(fields[8]),
                "speed_kmh": float(fields[9]),
                "direction": float(fields[10]),
                "satellites": int(fields[11]),
                "gps_fixed": fields[12] == "1",
                "odometer": int(fields[13]),
                "voltage": float(fields[14]),
                "acc_status": fields[15][0],
                "output_status": fields[15][4],
                "is_realtime": len(fields) > 19 and fields[19] == "1",
            }

            suntech2g_alert_id = fields[16]

        elif standard == "SA200":
            packet_data = {
                "timestamp": datetime(int(fields[3][:4]), int(fields[3][4:6]), int(fields[3][6:8]),
                                    int(fields[4][:2]), int(fields[4][3:5]), int(fields[4][6:8]), tzinfo=timezone.utc),
                "latitude": float(fields[6]),
                "longitude": float(fields[7]),
                "speed_kmh": float(fields[8]),
                "direction": float(fields[9]),
                "satellites": int(fields[10]),
                "gps_fixed": fields[11] == "1",
                "odometer": int(fields[12]),
                "voltage": float(fields[13]),
                "acc_status": fields[14][0],
                "output_status": fields[14][4],
                "is_realtime": len(fields) > 19 and fields[19] == "1",
            }

            suntech2g_alert_id = fields[15]

        
        # Mapeamento de IDs de Alerta
        universal_alert_id = settings.UNIVERSAL_ALERT_ID_DICTIONARY.get("suntech2g", {}).get(suntech2g_alert_id, 0)
        if universal_alert_id:
            packet_data["universal_alert_id"] = universal_alert_id

        # Lidando com mudanças no status da ignição
        alert_packet_data = handle_ignition_change(fields[1], 0, packet_data, raw_packet_hex=";".join(fields), original_protocol="suntech2g")
        if alert_packet_data and alert_packet_data.get("universal_alert_id"):
            send_to_main_server(fields[1], packet_data=alert_packet_data, serial=0, raw_packet_hex=";".join(fields), original_protocol="suntech2g", type="alert")

        # Normalizando dados para armazenamento em Redis
        timestamp_str = packet_data["timestamp"].strftime("%Y-%m-%dT%H:%M:%S")
        packet_data_redis = packet_data.copy()
        packet_data_redis["timestamp"] = timestamp_str

        redis_data = {
            "last_output_status": packet_data["output_status"],
            "last_voltage": packet_data["voltage"],
            "last_packet_data": json.dumps(packet_data_redis),
            "last_active_timestamp": datetime.now(timezone.utc).isoformat(),
            "last_event_type": "alert",
            "acc_status": packet_data.get('acc_status', 0),
            "power_status": 0 if packet_data.get('voltage', 0.0) > 0 else 1,
        }

        pipe = redis_client.pipeline()
        pipe.hincrby(fields[1], "total_packets_received", 1)
        pipe.hmset(fields[1], redis_data)

        pipe.execute()

        logger.info(f"ALT packet mapped data: {packet_data}")

        return packet_data
    except (ValueError, IndexError) as e:
        logger.error(f"Error parsing ALT packet: {e}")
        return {}

def handle_reply_packet(fields: list) -> dict:
    try:
        reply = fields[-1]

        packet_data_str = redis_client.hget(fields[2], "last_packet_data")
        packet_data = json.loads(packet_data_str) if packet_data_str else {}
        packet_data["timestamp"] = datetime.now(timezone.utc)

        if reply == "Disable1":
            packet_data["REPLY"] = "OUTPUT OFF"
        elif reply == "Enable1":
            packet_data["REPLY"] = "OUTPUT ON"
        else:
            logger.warning(f"Unknown reply command received: {reply}")

        return packet_data
    except Exception as e:
        logger.error(f"Error parsing CMD packet: {e}")
        return {}