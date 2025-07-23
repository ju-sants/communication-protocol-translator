import socket
import threading
import time

from app.core.logger import get_logger
from app.config.settings import settings
from app.src.suntech_utils import build_suntech_mnt_packet

logger = get_logger(__name__)


class MainServerSession:
    def __init__(self, dev_id: str):
        self.dev_id = dev_id
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
                logger.info("Conexão e thread de escuta iniciadas", device_id=self.dev_id)

                return True
            except Exception:
                logger.exception("Falha ao conectar ao servidor principal", device_id=self.dev_id)
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
                logger.info("Recebido comando {command} do server iniciando processamento.")
                process_suntech_command(command, self.dev_id)

            except socket.timeout:
                continue
            
            except (ConnectionResetError, BrokenPipeError):
                logger.warning("Conexão com servidor Suntech resetada (reader)", device_id=self.dev_id)
                self.disconnect()
                break
            except Exception:
                logger.exception("Erro inesperado na thread de escuta", device_id=self.dev_id)
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
                logger.info(f"Encaminhando pacote de {len(packet)} bytes", device_id=self.dev_id)
                self.sock.sendall(packet + b'\r')
            except (ConnectionResetError, BrokenPipeError) as e:
                logger.warning(f"Conexão com servidor Suntech caiu ao enviar ({type(e).__name__})", device_id=self.dev_id)

                if self._conection_retries < 5:
                    if self.connect():
                        self.send(packet)
                else:
                    logger.error("Número máximo de tentativas de conexão para essa sessão atingida")
                    self._conection_retries = 0
                    return

            except Exception:
                logger.exception("Erro inesperado ao enviar pacote", device_id=self.dev_id)
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

    def get_session(self, dev_id: str):
        with self.lock:
            if dev_id not in self._sessions:
                logger.info(f"Nenhuma sessão encontrada. Criando Sessão, dev_id={dev_id}")
                self._sessions[dev_id] = MainServerSession()
            
            session = self._sessions[dev_id]
            session.connect()

            return session
        
# active_connections = {}
# connection_lock = threading.Lock()

# def send_to_main_server(dev_id_str: str, packet_data: bytes):
#     """Envia os dados convertidos para o servidor principal."""
#     host = settings.MAIN_SERVER_HOST
#     port = settings.MAIN_SERVER_PORT
#     print(f"Enviando pacote de {len(packet_data)} bytes para {host}:{port}")
#     logger.info(f"Encaminhando pacote de {len(packet_data)} bytes para o servidor principal em {host}:{port}")
    
#     # # Linha temporária para desativar o envio
#     # logger.info("Temporariamente desativado o envio para o servidor principal")
#     # return

#     s = None
#     is_new_connection = False
#     packet_data = packet_data + b'\r'

#     with connection_lock:
#         if dev_id_str in active_connections:
#             s = active_connections[dev_id_str]
#             logger.debug(f"Reutilizando conexão existente para {host}:{port}")
    
#     if s is None:
#         logger.info(f"Criando nova conexão para {host}:{port}")
#         try:
#             s = socket.create_connection((host, port), timeout=5)
#             is_new_connection = True
#             with connection_lock:
#                 active_connections[dev_id_str] = s
#             logger.debug(f"Nova conexão criada para {host}:{port}")
#         except Exception:
#             logger.exception("Falha ao criar nova conexão com o servidor principal", device_id=dev_id_str)
#             return

#     try:
#         if is_new_connection:
#             # Envia o pacote de monitoramento para o servidor principal
#             monitor_packet = build_suntech_mnt_packet(dev_id_str)
#             s.sendall(monitor_packet)
#             logger.info(f"Pacote de monitoramento enviado para {host}:{port}")

#         logger.info(f"Enviando pacote de {len(packet_data)} bytes para {host}:{port}")
#         s.sendall(packet_data)

#         resposta = None
#         try:
#             resposta = s.recv(1024)
#         except TimeoutError:
#             logger.warning(f"Nenhuma resposta recebida do servidor Suntech.")
        
#         if resposta:
#             logger.info(f"RESPOSTA RECEBIDA DO SERVIDOR SUNTECH resposta_raw={resposta}, resposta_texto={resposta.decode('ascii', errors='ignore')}")
    
#     except Exception:
#         logger.exception(f"Falha ao enviar dados para o servidor principal para {dev_id_str} em {host}:{port}")

#         with connection_lock:
#             if dev_id_str in active_connections:
#                 del active_connections[dev_id_str]