import socket
import threading
import time

from app.core.logger import get_logger
from app.services.redis_service import get_redis
from app.config.settings import settings
from app.src.suntech.utils import build_suntech_mnt_packet
from app.src.protocols.jt808.builder import process_suntech_command as process_suntech_command_to_jt808
from app.src.protocols.gt06.builder import process_suntech_command as process_suntech_command_to_gt06
from app.src.protocols.vl01.builder import process_suntech_command as process_suntech_command_to_vl01

logger = get_logger(__name__)
redis_client = get_redis()

COMMAND_PROCESSORS = {
    "jt808": process_suntech_command_to_jt808,
    "gt06": process_suntech_command_to_gt06,
    "vl01": process_suntech_command_to_vl01
    }
class MainServerSession:
    def __init__(self, dev_id: str, serial: str):
        self.dev_id = dev_id
        self.serial = serial
        self.sock: socket.socket = None
        self.lock = threading.Lock()
        self._is_connected = False
        self._conection_retries = 0
    
    def connect(self):
        with self.lock:
            if self._is_connected:
                return True

            try:
                logger.info(f"Iniciando nova conexão para {settings.MAIN_SERVER_HOST}:{settings.MAIN_SERVER_PORT}")
                self.sock = socket.create_connection((settings.MAIN_SERVER_HOST, settings.MAIN_SERVER_PORT), timeout=5)
                self._is_connected = True

                logger.info("Criando Thread para ouvir comandos do lado do server")
                self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
                self._reader_thread.start()

                logger.info("Enviando pacote MNT para apresentar a conexão")
                mnt_packet = build_suntech_mnt_packet(self.dev_id)

                self.sock.sendall(mnt_packet)
                logger.info(f"Conexão e thread de escuta iniciadas device_id={self.dev_id}")

                return True
            except Exception:
                logger.exception(f"Falha ao conectar ao servidor principal device_id={self.dev_id}")
                self._is_connected = False
                return False
    
    def _reader_loop(self):
        while self._is_connected:
            try:
                if not self.sock:
                    logger.warning(f"Socket is None, exiting reader loop for device_id={self.dev_id}")
                    break

                data = self.sock.recv(1024)
                if not data:
                    logger.warning(f"Conexão fechada pelo servidor Suntech (recv vazio) device_id={self.dev_id}")
                    self.disconnect()
                    break
                
                device_info = redis_client.hgetall(self.dev_id)
                protocol_type = device_info.get("protocol")

                if not protocol_type:
                    logger.error(f"Protocolo não encontrado no Redis para o device_id={self.dev_id}. Impossível traduzir comando.")
                    continue

                processor_func = COMMAND_PROCESSORS.get(protocol_type)

                if not processor_func:
                    logger.error(f"Processador de comando para o protocolo '{protocol_type}' não encontrado.")
                    continue

                logger.info(f"Roteando comando para o processador do protocolo: '{protocol_type}'")
                processor_func(data, self.dev_id, self.serial)


            except socket.timeout:
                continue
            
            except (ConnectionResetError, BrokenPipeError):
                logger.warning(f"Conexão com servidor Suntech resetada (reader) device_id={self.dev_id}")
                self.disconnect()
                break
            except OSError as e:
                if e.errno == 9:
                    logger.warning(f"Caught 'Bad file descriptor' for device_id={self.dev_id}. Socket was likely closed.")
                else:
                    logger.exception(f"Caught OSError in reader thread for device_id={self.dev_id}: {e}")
                self.disconnect()
                break
            except Exception as e:
                logger.exception(f"Unexpected error in reader thread for device_id={self.dev_id}: {e}")
                self.disconnect()
                break
    
    def send(self, packet: bytes):
        with self.lock:
            if not self._is_connected:
                logger.warning("Conexão perdida, tentando reconectar...")

                if not self.connect():
                    logger.error("Não foi possível conectar ao servidor principal. Pacote descartado.")
                    return
            
            try:
                logger.info(f"Encaminhando pacote de {len(packet)} bytes device_id={self.dev_id}")
                self.sock.sendall(packet + b'\r')
            except (ConnectionResetError, BrokenPipeError) as e:
                logger.warning(f"Conexão com servidor Suntech caiu ao enviar ({type(e).__name__}) device_id={self.dev_id}")

                if self._conection_retries < 5:
                    self._conection_retries += 1

                    if self.connect():
                        self.send(packet)
                        
                else:
                    logger.error("Número máximo de tentativas de conexão para essa sessão atingida")
                    self._conection_retries = 0
                    return

            except Exception:
                logger.exception(f"Erro inesperado ao enviar pacote device_id={self.dev_id}")
                self.disconnect()

    def disconnect(self):
        with self.lock:
            if self._is_connected:
                logger.info(f"Desconectando do server principal, dev_id={self.dev_id}")
                self._is_connected = False
                if self.sock:
                    try:
                        self.sock.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                    self.sock.close()
                self.sock = None

class MainServerSessionsManager:
    _lock = threading.Lock()
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._sessions = {}
                    cls._instance.lock = threading.Lock()

        return cls._instance

    def get_session(self, dev_id: str, serial: str):
        with self.lock:
            if dev_id not in self._sessions:
                logger.info(f"Nenhuma sessão encontrada no MainServerSessionsManager. Criando uma nova. dev_id={dev_id}")
                self._sessions[dev_id] = MainServerSession(dev_id, serial)
            
            session = self._sessions[dev_id]
            session.connect()

            return session
    
    def delete_session(self, dev_id: str):
        with self.lock:
            if dev_id in self._sessions:
                logger.info(f"Deletando sessão do MainServerSessionsManager para dev_id={dev_id}")
                session = self._sessions[dev_id]
                session.disconnect()
                del self._sessions[dev_id]
                logger.info(f"Sessão para dev_id={dev_id} deletada do MainServerSessionsManager.")

sessions_manager = MainServerSessionsManager()

def send_to_main_server(dev_id_str: str, serial: str, packet_data: bytes):
    session = sessions_manager.get_session(dev_id_str, serial)
    session.send(packet_data)