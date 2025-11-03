import json

from app.core.logger import get_logger
from app.services.redis_service import get_redis

logger = get_logger(__name__)
redis_client = get_redis()

def process_command(dev_id, _, universal_command):
    if not universal_command.startswith("HODOMETRO"):
        logger.warning(f"Comando incompatível com rastreador satelital, dropando. Universal command: {universal_command}")
        return
    
    meters = universal_command.split(":")[-1]
    if not meters.isdigit():
        logger.error(f"Comando com metragem incorreta: {universal_command}")
        return

    last_location_str = redis_client.hget(f"tracker:{dev_id}", "last_merged_location")

    if not last_location_str:
        logger.warning(f"Não existe um pacote prévio de localização para editar o hodometro.")
        return
    
    last_location_data = json.loads(last_location_str)
    last_location_data["gps_odometer"] = int(meters)

    redis_client.hset(f"tracker:{dev_id}", "last_merged_location", json.dumps(last_location_data))

    logger.success(f"Hodometro atualizado com sucesso para: {int(meters) / 1000} KM.")