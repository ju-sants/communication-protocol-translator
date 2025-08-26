import json
from app.core.logger import get_logger
from app.services.redis_service import get_redis
from app.src.suntech.utils import build_suntech_packet
from app.src.connection.main_server_connection import send_to_main_server

logger = get_logger(__name__)
redis_client = get_redis()


def map_data(raw_data: str):
    """
    Maps satellite data to a Suntech packet and sends it to the main server.
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

    except json.JSONDecodeError as e:
        logger.error(f"Failed to decode JSON: {e}")
    except Exception as e:
        logger.error(f"Error mapping data: {e}")