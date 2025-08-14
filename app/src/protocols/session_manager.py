import threading
import socket

from app.core.logger import get_logger

logger = get_logger(__name__)

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
            self.active_trackers[dev_id] = conn
            logger.info(f"Rastreador registrado na sessão: dev_id={dev_id}")

    def remove_tracker_client(self, dev_id: str):
        with self._lock:
            if dev_id in self.active_trackers:
                del self.active_trackers[dev_id]

                logger.info(f"Rastreador removido de sua sessão: dev_id={dev_id}")
    
    def get_tracker_client_socket(self, dev_id: str):
        with self._lock:
            return self.active_trackers.get(dev_id)

    def exists(self, dev_id: str) -> bool:
        with self._lock:
            # Try the key as-is first (string)
            socket_obj = self.active_trackers.get(dev_id)
            
            # If not found, try decoding if it's bytes, or encoding if it's string
            if socket_obj is None:
                try:
                    # If dev_id is a string, try finding a bytes version
                    if isinstance(dev_id, str):
                        bytes_key = bytes.fromhex(dev_id)
                        socket_obj = self.active_trackers.get(bytes_key)
                    # If dev_id is bytes, try finding a string version
                    elif isinstance(dev_id, bytes):
                        str_key = dev_id.hex()
                        socket_obj = self.active_trackers.get(str_key)
                except (ValueError, TypeError):
                    pass # Ignore errors if conversion fails

            if socket_obj is None:
                return False
            
            try:
                return socket_obj.fileno() != -1 
            except OSError:
                return False

tracker_sessions_manager = TrackerSessionsManager()