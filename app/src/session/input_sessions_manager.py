import threading
import socket
from datetime import datetime
from dateutil.relativedelta import relativedelta
import time
import errno

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


    def register_session(self, dev_id: str, conn: socket.socket, ex: int = -1):
        with self._lock:
            self.active_trackers[str(dev_id)] = conn
            redis_client.sadd("input_sessions:active_trackers", dev_id)

            if ex != -1 and isinstance(ex, int):
                self.to_expire_keys[dev_id] = (ex, datetime.now())

            logger.info(f"Rastreador registrado na sessão: dev_id={dev_id}")
            

    def remove_session(self, dev_id: str):
        with self._lock:
            dev_id_str = str(dev_id)
            if dev_id_str in self.active_trackers:
                del self.active_trackers[dev_id_str]
                logger.info(f"Rastreador removido de sua sessão: dev_id={dev_id_str}")
                redis_client.srem("input_sessions:active_trackers", dev_id_str)

    def get_session(self, dev_id: str) -> socket.socket:
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
                # Tenta verificar o descritor de arquivo
                if socket_obj.fileno() == -1:
                    return False

                data = socket_obj.recv(16, socket.MSG_PEEK | socket.MSG_DONTWAIT)
                
                if data == b'':
                    if dev_id in self.active_trackers:
                        del self.active_trackers[dev_id]

                    logger.info(f"Tracker {dev_id} fechou a conexão de forma elegante (recv(0) retornou b'').")
                    return False 
                
                return True 
                
            except BlockingIOError:
                # Não havia dados para ler, mas o socket está aberto e não houve erro
                return True
                
            except ConnectionResetError:
                # Conexão resetada de forma abrupta (RST)
                if dev_id in self.active_trackers:
                    del self.active_trackers[dev_id]

                logger.info(f"Tracker {dev_id} sofreu um ConnectionResetError.")
                return False
                
            except BrokenPipeError:
                # Tentativa de escrita em um socket fechado
                if dev_id in self.active_trackers:
                    del self.active_trackers[dev_id]

                logger.info(f"Tracker {dev_id} sofreu um BrokenPipeError.")
                return False

            except OSError as e:
                # Outros erros de SO, como o socket ter sido fechado (errno.EBADF, etc.)
                if e.errno == errno.EBADF: # Bad file descriptor
                    return False
                
                if dev_id in self.active_trackers:
                    del self.active_trackers[dev_id]

                logger.info(f"Tracker {dev_id} sofreu um OSError: {e}.")
                return False
    
    def get_sessions(self, use_redis: bool = False):
        if use_redis:
            return redis_client.smembers("input_sessions:active_trackers")
        
        else: return self.active_trackers.keys()

input_sessions_manager = InputSessionsManager()