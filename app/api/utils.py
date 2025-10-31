import json

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
