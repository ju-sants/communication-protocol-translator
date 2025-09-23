import json
from datetime import datetime

from app.core.logger import get_logger
from app.services.redis_service import get_redis
from app.src.session.output_sessions_manager import send_to_main_server

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
            return
        
        esn = data.get("ESN")
        if not esn:
            logger.info(f"Message received without ESN, dropping.")
            return
        
        logger.info(f"Parsed JSON data: {data}")

        hybrid_gsm = redis_client.hget("SAT_GSM_MAPPING", esn)

        if not hybrid_gsm:
            logger.info("Satellite tracker without a GSM pair, dropping.")
            return

        last_serial, last_gsm_location_str = redis_client.hmget(hybrid_gsm, "last_serial", "last_packet_data")

        last_serial = int(last_serial) if last_serial else 0
        last_gsm_location = json.loads(last_gsm_location_str) if last_gsm_location_str else {}

        last_hybrid_location = {**last_gsm_location, **data}
        last_hybrid_location["voltage"] = 2.22
        last_hybrid_location["satellites"] = 2
        last_hybrid_location["timestamp"] = datetime.fromisoformat(data.get("timestamp"))
        last_gsm_location["is_realtime"] = False
        last_hybrid_location["device_type"] = "satellital"

        return hybrid_gsm, last_hybrid_location, last_serial 
    
    except json.JSONDecodeError as e:
        logger.error(f"Failed to decode JSON: {e}")
    except Exception as e:
        logger.error(f"Error mapping data: {e}")