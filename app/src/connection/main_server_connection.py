import socket
import threading
import time

from app.core.logger import get_logger
from app.config.settings import settings
from app.src.suntech_utils import build_suntech_mnt_packet, process_suntech_command

logger = get_logger(__name__)


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
                data = self.sock.recv(1024)
                if not data:
                    logger.warning(f"Conexão fechada pelo servidor Suntech (recv vazio) device_id={self.dev_id}")
                    self.disconnect()
                    break
                
                command = data.decode("ascii", errors="ignore").strip()
                logger.info(f"Recebido comando {command} do server iniciando processamento.")
                process_suntech_command(command, self.dev_id, self.serial)

            except socket.timeout:
                continue
            
            except (ConnectionResetError, BrokenPipeError):
                logger.warning(f"Conexão com servidor Suntech resetada (reader) device_id={self.dev_id}")
                self.disconnect()
                break
            except Exception:
                logger.exception(f"Erro inesperado na thread de escuta device_id={self.dev_id}")
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
                    self.sock.close()

                self.sock = None

class MainServerSessionsManager:
    def __init__(self):
        self._sessions: dict[str, MainServerSession] = {}
        self.lock = threading.Lock()

    def get_session(self, dev_id: str, serial: str):
        with self.lock:
            if dev_id not in self._sessions:
                logger.info(f"Nenhuma sessão encontrada. Criando Sessão, dev_id={dev_id}")
                self._sessions[dev_id] = MainServerSession(dev_id, serial)
            
            session = self._sessions[dev_id]
            session.connect()

            return session

sessions_manager = MainServerSessionsManager()

def send_to_main_server(dev_id_str: str, serial: str, packet_data: bytes):
    session = sessions_manager.get_session(dev_id_str, serial)
    session.send(packet_data)