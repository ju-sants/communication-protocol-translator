
import redis

from app.core.logger import get_logger
from app.config.settings import settings
from functools import lru_cache

logger = get_logger(__name__)

@lru_cache(maxsize=1)
def get_redis(db: int | None = None, host: str | None = None, port: int | None = None, password: str | None = None, decode_responses: bool = True):
    redis_conn = None

    db = db if db is not None else settings.REDIS_DB_MAIN
    host = host if host is not None else settings.REDIS_HOST
    port = port if port is not None else settings.REDIS_PORT
    password = password if password is not None else settings.REDIS_PASSWORD
    logger.info(f"Connecting to Redis DB {db} at {host}:{port} with ConnectionPool", log_label="SERVIDOR")

    try:
        connection_pool = redis.ConnectionPool(max_connections=50, db=db, host=host, port=port, password=password, decode_responses=decode_responses)
        redis_conn = redis.Redis(connection_pool=connection_pool)
        redis_conn.ping()
        logger.info(f"Successfully connected to Redis DB {db} at {host}:{port}", log_label="SERVIDOR")
    except redis.ConnectionError as e:
        import traceback
        import inspect

        frame = inspect.currentframe()
        caller_frame = frame.f_back
        
        filename = caller_frame.f_code.co_filename
        line_number = caller_frame.f_lineno
        function_name = caller_frame.f_code.co_name
        
        logger.info(f"Chamada de: {filename}:{line_number} na função '{function_name}'", log_label="SERVIDOR")

        logger.error(f"Failed to connect to Redis DB {db} at {host}:{port}; {e}", log_label="SERVIDOR")
        logger.info(traceback.format_exc(), log_label="SERVIDOR")
        exit(1)

    return redis_conn