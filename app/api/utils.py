import json
from typing import Tuple

from app.services.redis_service import get_redis
from app.services.cache_service import get_cache
from app.core.logger import get_logger

redis_client = get_redis()
logger = get_logger(__name__)
cache = get_cache()

def get_mapping_cached(mapping):
    cached_data = cache.get(mapping)

    if not cached_data:
        data = redis_client.hgetall(mapping)
        cache.set(mapping, json.dumps(data), expire=3600 * 6)
    else:
        data = json.loads(cached_data)

    return data

def parse_json_safe(json_str: str):
    """Parse a json string with error handling"""

    try:
        return json.loads(json_str)
    
    except Exception as e:
        logger.error(f"Não foi possível parsear a string json: {e}\n{json_str}")

def get_output_input_ids_map() -> Tuple[dict]:
    """
    Obtém o mapeamento de ids de entrada e saída com 0s a esquerda
    e sem 0s a esquerda.
    
    :return: Description
    :rtype: Tuple[dict]
    """

    try:
        output_input_ids_0Padded = redis_client.hgetall("output_input_ids:mapping")
        output_input_ids_notPadded = {str(k).lstrip("0"): v for k, v in output_input_ids_0Padded.items()}

        return output_input_ids_0Padded, output_input_ids_notPadded
    except Exception as e:
        logger.error(f"Houve um erro ao tentar obter o mapeamento de ids. {e}")