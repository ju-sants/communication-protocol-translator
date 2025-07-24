import threading
import socket

from app.core.logger import get_logger

logger = get_logger(__name__)

class TrackerSessionsManager:
    _instance = None
    _lock = threading.Lock()

    active_trackers: dict[str, socket.socket]

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)

        return cls._instance
    
    def register_tracker_client(self, dev_id: str, conn: socket.socket):
        with self._lock:
            self._active_clients[dev_id] = conn
            logger.info(f"Rastreador registrado na sessão: dev_id={dev_id}")

    def remove_tracker_client(self, dev_id: str):
        with self._lock:
            if dev_id in self.active_trackers:
                del self.active_trackers[dev_id]

                logger.info(f"Rastreador removido de sua sessão: dev_id={dev_id}")
    
    def get_tracker_client_socket(self, dev_id: str):
        with self._lock:
            return self.active_trackers.get(dev_id)

tracker_sessions_manager = TrackerSessionsManager()