import socket
import threading
import time
import importlib

from app.core.logger import get_logger
from app.services.redis_service import get_redis
from app.services.history_service import add_packet_to_history
from app.config.output_protocol_settings import output_protocol_settings
from app.src.output.suntech4g.builder import build_login_packet as build_suntech_login_packet
from app.src.output.gt06.builder import build_login_packet as build_gt06_login_packet, build_voltage_info_packet as build_gt06_voltage_info_packet

logger = get_logger(__name__)
redis_client = get_redis()

class MainServerSession:
    def __init__(self, dev_id: str, serial: str, output_protocol: str):
        self.output_protocol = output_protocol
        self.dev_id = dev_id
        self.serial = serial
        self.sock: socket.socket = None
        self.lock = threading.RLock()
        self._is_connected = False
        self._conection_retries = 0
        
        self._is_gt06_login_step = False
        self._is_realtime = False
    
    def connect(self):
        with self.lock:
            if self._is_connected:
                return True

            try:
                if not self.output_protocol:
                    logger.info(f"Impossível iniciar conexão com server principal, tipo de protocolo de saída não especificado. dev_id={self.dev_id}")
                    return
                
                address = output_protocol_settings.OUTPUT_PROTOCOL_HOST_ADRESSES.get(self.output_protocol)

                if not address:
                    logger.info(f"Impossível iniciar conexão com server principal, tipo de protocolo de saída não mapeado. dev_id={self.dev_id}, output_protocol={self.output_protocol}")
                    return


                logger.info(f"Iniciando nova conexão para {address[0]}:{address[1]}")
                self.sock = socket.create_connection(address, timeout=5)
                self._is_connected = True

                logger.info(f"Criando Thread para ouvir comandos do lado do server. dev_id={self.dev_id}")
                self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
                self._reader_thread.start()

                self.present_connection()

                logger.info(f"Conexão e thread de escuta iniciadas device_id={self.dev_id}")

                return True
            except Exception:
                logger.exception(f"Falha ao conectar ao servidor principal device_id={self.dev_id}")
                self._is_connected = False
                return False
    
    def present_connection(self):

        if self.output_protocol == "suntech4g":
            logger.info(f"Enviando pacote MNT para apresentar a conexão dev_id={self.dev_id}")
            mnt_packet = build_suntech_login_packet(self.dev_id)

            self.sock.sendall(mnt_packet)
            logger.info(f"Pacote de apresentação MNT enviado. dev_id={self.dev_id}")
        
        elif self.output_protocol == "gt06":
            logger.info(f"Iniciando login... dev_id={self.dev_id}")
            self._is_gt06_login_step = True

            login_packet = build_gt06_login_packet(self.dev_id, self.serial)

            self.sock.sendall(login_packet)

            logger.info(f"Pacote de Login enviado. dev_id={self.dev_id}")

    def handle_gt06_login(self, data):
        self._is_gt06_login_step = False
        logger.info(f"The server replyed the login data packet, dev_id={self.dev_id} data={data.hex()}")

    def _reader_loop(self):
        while self._is_connected:
            try:
                if not self.sock:
                    logger.warning(f"Socket is None, exiting reader loop for device_id={self.dev_id}")
                    break

                data = self.sock.recv(1024)
                if not data:
                    logger.warning(f"Conexão fechada pelo servidor principal (recv vazio) device_id={self.dev_id}")
                    self.disconnect()
                    break
                
                # Lida com resposta do servidor para pacotes de login
                if self._is_gt06_login_step:
                    self.handle_gt06_login(data)
                    continue
                
                device_info = redis_client.hgetall(f"tracker:{self.dev_id}")
                protocol_type = device_info.get("protocol")
                output_protocol = device_info.get("output_protocol")

                if not protocol_type:
                    logger.error(f"Protocolo não encontrado no Redis para o device_id={self.dev_id}. Impossível traduzir comando. dev_id={self.dev_id}")
                    continue

                mapper_func = output_protocol_settings.OUTPUT_PROTOCOL_COMMAND_MAPPERS.get(output_protocol)
                if not mapper_func:
                    logger.error(f"Mapeador de comandos universais para o protocolo de saida '{str(output_protocol).upper()}' não encontrado. dev_id={self.dev_id}")
                    return
                
                universal_command = mapper_func(self.dev_id, data)
                if not universal_command:
                    logger.error(f"Comando universal não encontrado, output_protocol={self.output_protocol}, dev_id={self.dev_id}")
                    return
                
                target_module = importlib.import_module(f"app.src.input.{protocol_type}.builder")
                processor_func = getattr(target_module, "process_command")

                if not processor_func:
                    logger.error(f"Processador de comando para o protocolo '{str(protocol_type).upper()}' com o protocolo de saida '{str(output_protocol).upper()}' não encontrado.")
                    continue

                logger.info(f"Roteando comando para o processador do protocolo: '{str(protocol_type).upper()}' com protocolo de saida '{str(output_protocol).upper()}'")
                processor_func(self.dev_id, self.serial, universal_command)


            except socket.timeout:
                continue
            
            except (ConnectionResetError, BrokenPipeError):
                logger.warning(f"Conexão com servidor principal resetada (reader) device_id={self.dev_id}")
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
    
    def send(self, packet: bytes, current_output_protocol: str = None, packet_data: dict = None):
        with self.lock:
            if not self._is_connected:
                logger.warning(f"Conexão perdida, tentando reconectar... dev_id={self.dev_id}")

                if not self.connect():
                    logger.error(f"Não foi possível conectar ao servidor principal. Pacote descartado. dev_id={self.dev_id}")
                    return
            
            is_realtime = packet_data.get("is_realtime") if packet_data else None
            if is_realtime is not None:
                self._is_realtime = is_realtime

            if current_output_protocol and current_output_protocol.lower() != self.output_protocol:
                logger.warning(f"Protocolo de saída mudou de {self.output_protocol} para {current_output_protocol}, desconectando sessão atual e criando uma nova.")
                
                self.disconnect()
                self.output_protocol = current_output_protocol
                if not self.connect():
                    logger.error(f"Não foi possível conectar ao servidor principal com o novo protocolo. Pacote descartado. dev_id={self.dev_id}")
                    return
                
            try:
                if self._is_gt06_login_step:
                    logger.info(f"Aguardadndo resposta do server principal sobre o pacote de login. dev_id={self.dev_id}")

                    while self._is_gt06_login_step:
                        time.sleep(1)
                    
                    logger.info(f"Resposta do server principal recebida, continuando a entrega de pacotes. dev_id={self.dev_id}")

                # Enviando pacote de info de voltagem antes de qualquer pacote de localização em tempo real
                if self.output_protocol == "gt06" and packet_data and packet_data.get("packet_type") == "location":
                    if packet_data.get("device_type") == "satellital": # Prioridade 1: é um satelital? mande a voltagem específica.
                        voltage = 2.22
                    elif packet_data.get("voltage"): # Prioridade 2: é GSM e possui voltagem no pacote
                        voltage = packet_data.get("voltage")
                    elif not self._is_realtime and current_output_protocol.lower() in ("vl01"): # Prioridade 3: Estamos enviando pacotes de memória de protocolos que não enviam voltagem nos pacotes, envia voltagem específica.
                        voltage = 1.11
                    else: # Prioridade 4: estamos em tempo real, o protocolo em questão não envia dados de voltagem no pacote, mas o conseguimos de outra forma, e se não o conseguirmos, enviamos 1.11.
                        voltage = packet_data.get("last_voltage") or "1.11" 
                        voltage = float(voltage)

                    voltage_packet = build_gt06_voltage_info_packet({"voltage": voltage}, int(self.serial))
                    logger.info(f"Enviando pacote de voltagem antes do pacote de localização em tempo real. dev_id={self.dev_id} voltage={voltage}V")
                    self.sock.sendall(voltage_packet)

                logger.info(f"Encaminhando pacote de {len(packet)} bytes device_id={self.dev_id}")

                if self.output_protocol == "suntech4g":
                    packet += b'\r'

                self.sock.sendall(packet)
            except (ConnectionResetError, BrokenPipeError) as e:
                logger.warning(f"Conexão com servidor Principal caiu ao enviar ({type(e).__name__}) device_id={self.dev_id}")

                if self._conection_retries < 5:
                    self._conection_retries += 1

                    if self.connect():
                        self.send(packet)
                        
                else:
                    logger.error(f"Número máximo de tentativas de conexão para essa sessão atingida dev_id={self.dev_id}")
                    self._conection_retries = 0
                    self.disconnect()
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

class OutputSessionsManager:
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

    def get_session(self, dev_id: str, serial: str, output_protocol) -> MainServerSession:
        with self.lock:
            if dev_id not in self._sessions:
                logger.info(f"Nenhuma sessão encontrada no MainServerSessionsManager. Criando uma nova. dev_id={dev_id}")
                self._sessions[dev_id] = MainServerSession(dev_id, serial, output_protocol)
            
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

output_sessions_manager = OutputSessionsManager()

def send_to_main_server(
        dev_id: str, packet_data: dict = None, serial: str = None, 
        raw_packet_hex: str = None, original_protocol: str = None, 
        type: str = "location",
        managed_alert: bool = False
    ):
    """
    Executa lógica de construção de pacotes se o mesmo não for fornecido, com base no protocolo de saída do dispositivo e o tipo de pacote especificado.
    """

    output_protocol, protocol, is_hybrid = redis_client.hmget(f"tracker:{dev_id}", "output_protocol", "protocol", "is_hybrid")
    
    if not output_protocol:  # VL01 apenas se comunicará como GT06
        if is_hybrid or (protocol and protocol == "vl01"):
            output_protocol = "gt06"
        else:
            output_protocol = "suntech4g"
        
        redis_client.hset(f"tracker:{dev_id}", "output_protocol", output_protocol)
    
    
    output_packet_builder = output_protocol_settings.OUTPUT_PROTOCOL_PACKET_BUILDERS.get(output_protocol).get(type)

    if not managed_alert:
        output_packet = output_packet_builder(dev_id, packet_data, serial, type)
    else:
        output_packet = output_packet_builder(dev_id, packet_data, serial, type, managed_alert=managed_alert)

    # Lógica de envios
    if output_packet:
        if output_protocol == "suntech4g":
            str_output_packet = output_packet.decode("ascii")
        else:
            str_output_packet = output_packet.hex()

        if packet_data is not None:
            packet_data["packet_type"] = type

            if not packet_data.get("voltage"):
                last_voltage = redis_client.hget(f"tracker:{dev_id}", "last_voltage")
                packet_data["last_voltage"] = last_voltage if last_voltage else "1.11"

        logger.info(f"Pacote de {type.upper()} {output_protocol.upper()} traduzido de pacote {str(original_protocol).upper()}:\n{str_output_packet}")

        add_packet_to_history(dev_id, raw_packet_hex, str_output_packet)
        
        session = output_sessions_manager.get_session(dev_id, serial, output_protocol)
        session.send(output_packet, output_protocol, packet_data)