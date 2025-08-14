import threading
import socket

from app.core.logger import get_logger
from app.services.redis_service import get_redis

logger = get_logger(__name__)
redis_client = get_redis()
class TrackerSessionsManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance.active_trackers = {}

        return cls._instance
    
    def register_tracker_client(self, dev_id: str, conn: socket.socket):
        with self._lock:
            self.active_trackers[str(dev_id)] = conn
            logger.info(f"Rastreador registrado na sessão: dev_id={dev_id}")
            redis_client.sadd("active_trackers", dev_id)
    def remove_tracker_client(self, dev_id: str):
        with self._lock:
            dev_id_str = str(dev_id)
            if dev_id_str in self.active_trackers:
                del self.active_trackers[dev_id_str]
                logger.info(f"Rastreador removido de sua sessão: dev_id={dev_id_str}")
                redis_client.srem("active_trackers", dev_id_str)

    def get_tracker_client_socket(self, dev_id: str):
        with self._lock:
            return self.active_trackers.get(dev_id)

    def exists(self, dev_id: str, use_redis: bool = False) -> bool:
        with self._lock:
            if use_redis:
                return redis_client.sismember("active_trackers", str(dev_id))
            
            socket_obj = self.active_trackers.get(str(dev_id))
            if socket_obj is None:
                return False
            
            try:
                return socket_obj.fileno() != -1
            except OSError:
                return False

tracker_sessions_manager = TrackerSessionsManager()