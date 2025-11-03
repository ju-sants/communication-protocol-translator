import threading
import socket
from datetime import datetime
from dateutil.relativedelta import relativedelta
import time

from app.core.logger import get_logger
from app.services.redis_service import get_redis

logger = get_logger(__name__)
redis_client = get_redis()

class InputSessionsManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance.active_trackers = {}
                    cls._instance.to_expire_keys = {}
                    threading.Thread(target=cls._instance.expire_keys, daemon=True).start()

        return cls._instance
    
    def expire_keys(self):
        while True:
            for k in self.to_expire_keys:
                now = datetime.now()
                
                ex, start_time = self.to_expire_keys[k]
                complete_time = start_time + relativedelta(seconds=ex)
                
                if complete_time < now:
                    del self._instance.active_trackers[k]
                    redis_client.srem("input_sessions:active_trackers", k)
            
            time.sleep(5)


    def register_tracker_client(self, dev_id: str, conn: socket.socket, ex: int = -1):
        with self._lock:
            self.active_trackers[str(dev_id)] = conn
            redis_client.sadd("input_sessions:active_trackers", dev_id)

            if ex != -1 and isinstance(ex, int):
                self.to_expire_keys[dev_id] = (ex, datetime.now())

            logger.info(f"Rastreador registrado na sessão: dev_id={dev_id}")
            

    def remove_tracker_client(self, dev_id: str):
        with self._lock:
            dev_id_str = str(dev_id)
            if dev_id_str in self.active_trackers:
                del self.active_trackers[dev_id_str]
                logger.info(f"Rastreador removido de sua sessão: dev_id={dev_id_str}")
                redis_client.srem("input_sessions:active_trackers", dev_id_str)

    def get_tracker_client_socket(self, dev_id: str):
        with self._lock:
            return self.active_trackers.get(dev_id)

    def exists(self, dev_id: str, use_redis: bool = False) -> bool:
        with self._lock:
            if use_redis:
                return redis_client.sismember("input_sessions:active_trackers", str(dev_id))
            
            socket_obj = self.active_trackers.get(str(dev_id))
            if socket_obj is None:
                return False
            
            try:
                return socket_obj.fileno() != -1
            except OSError:
                return False
    
    def get_active_trackers(self, use_redis: bool = False):
        if use_redis:
            return redis_client.smembers("input_sessions:active_trackers")
        
        else: return self.active_trackers

input_sessions_manager = InputSessionsManager()