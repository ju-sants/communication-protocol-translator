import threading
import socket

from app.core.logger import get_logger

logger = get_logger(__name__)

class TrackerSessionManager:
    _instance = None
    _lock = threading.Lock()

    active_trackers: dict[str, socket.socket]

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)

        return cls._instance
    
    def register_tracker(self, dev_id: str, conn: socket.socket):
        with self._lock:
            self._active_clients[dev_id] = conn
            logger.info(f"Rastreador registrado na sessão: dev_id={dev_id}")