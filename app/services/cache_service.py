import diskcache
import os
from functools import lru_cache

from app.config.settings import settings

@lru_cache(maxsize=1)
def get_cache():
    os.makedirs(settings.CACHE_DIR, exist_ok=True)

    cache = diskcache.Cache(settings.CACHE_DIR)

    return cache