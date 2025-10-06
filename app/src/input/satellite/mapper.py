import json
from datetime import datetime, timezone
import copy

from app.core.logger import get_logger
from app.services.redis_service import get_redis
from ..utils import handle_ignition_change

logger = get_logger(__name__)
redis_client = get_redis()


def handle_satelite_data(raw_data: bytes):
    """
    Maps satellite data to a structured python dict and sends it to the main server.
    """
    try:
        data = json.loads(raw_data)

        if data.get("message_type") == "heartbeat":
            logger.info(f"HeartBeat Message Received")
            return None, None, None, None
        
        esn = data.get("ESN")
        if not esn:
            logger.info(f"Message received without ESN, dropping.")
            return None, None, None, None
        
        logger.info(f"Parsed JSON data: {data}")

        hybrid_gsm_dev_id = redis_client.hget("SAT_GSM_MAPPING", esn)

        if not hybrid_gsm_dev_id:
            logger.info("Satellite tracker without a GSM pair, dropping.")
            return None, None, None, None

        last_serial, last_gsm_location_str = redis_client.hmget(f"tracker:{hybrid_gsm_dev_id}", "last_serial", "last_packet_data")

        last_serial = int(last_serial) if last_serial else 0
        last_gsm_location = json.loads(last_gsm_location_str) if last_gsm_location_str else {}

        last_hybrid_location = {**last_gsm_location, **data}
        last_hybrid_location["voltage"] = 2.22
        last_hybrid_location["satellites"] = 2
        last_hybrid_location["timestamp"] = datetime.fromisoformat(data.get("timestamp"))
        last_hybrid_location["is_realtime"] = False
        last_hybrid_location["device_type"] = "satellital"

        redis_data = {
            "last_satellite_location": json.dumps(data),
            "last_satellite_active_timestamp": datetime.now(timezone.utc).isoformat(),
            "last_hybrid_location": last_hybrid_location
        }


        ign_alert_packet_data = None
        # Lidando com o estado da ignição, muito preciso para veículos híbridos.
        last_altered_acc_str = redis_client.hget(f"tracker:{hybrid_gsm_dev_id}", "last_altered_acc")
        if last_altered_acc_str:
            last_altered_acc_dt = datetime.fromisoformat(last_altered_acc_str)

        if not last_altered_acc_str or (last_hybrid_location.get("timestamp") and last_altered_acc_dt < last_hybrid_location.get("timestamp")):
            # Lidando com mudanças no status da ignição
            ign_alert_packet_data = handle_ignition_change(hybrid_gsm_dev_id, copy.deepcopy(last_hybrid_location))

            redis_data["acc_status"] = last_hybrid_location.get("acc_status")
            redis_data["last_altered_acc"] = last_hybrid_location.get("timestamp").isoformat()

        actual_month = datetime.now().month

        pipe = redis_client.pipeline()
        pipe.rpush(f"payloads:{esn}", json.dumps(data))
        pipe.ltrim(f"payloads:{esn}", 0, 10000)
        pipe.hmset(f"tracker:{hybrid_gsm_dev_id}", redis_data)
        pipe.hincrby(f"monthly_counts:{esn}", actual_month, 1)
        pipe.execute()

        return hybrid_gsm_dev_id, last_hybrid_location, ign_alert_packet_data, last_serial 
    
    except json.JSONDecodeError as e:
        logger.error(f"Failed to decode JSON: {e}")
        return None, None, None, None
    except Exception as e:
        logger.error(f"Error mapping data: {e}")
        return None, None, None, None