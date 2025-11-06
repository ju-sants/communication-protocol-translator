import socket
import threading
import time
import importlib
from typing import Literal
import json

from app.core.logger import get_logger
from app.services.redis_service import get_redis
from app.services.history_service import add_packet_to_history
from app.config.output_protocol_settings import output_protocol_settings
from app.src.output.suntech4g.builder import build_login_packet as build_suntech_login_packet
from app.src.output.gt06.builder import build_login_packet as build_gt06_login_packet, build_voltage_info_packet as build_gt06_voltage_info_packet
from .input_sessions_manager import input_sessions_manager

logger = get_logger(__name__)
redis_client = get_redis()

class MainServerSession:
    def __init__(self, dev_id: str, serial: str, input_protocol: str, output_protocol: str):
        self.input_protocol = input_protocol
        self.output_protocol = output_protocol
        self.dev_id = dev_id
        self.serial = serial
        self.device_type = "GSM"
        self.pending_odometer_command = {}

        self.sock: socket.socket = None
        self.lock = threading.RLock()

        self._is_connected = False
        self._conection_retries = 0
        self._is_gt06_login_step = False
        self._is_realtime = False
        self._is_sending_realtime_location = False
    
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

    def handle_pending_odometer_command(self, actual_odometer: int):
        if self.pending_odometer_command:
            if self._is_realtime and self.device_type == "GSM":
                
                # Verificação do hodometro atual
                if not actual_odometer or not isinstance(actual_odometer, int):
                    logger.error(f"Comando de hodometro pendente; o hodometro atual provido não é um inteiro: {actual_odometer} class: {type(actual_odometer).__name__}")
                    return
                
                # Verificação do hodometro enviado no comando
                command = str(self.pending_odometer_command.get("command"))
                target_odometer_str = command.split(":")[-1]
                if not target_odometer_str or not target_odometer_str.isdigit():
                    logger.error(f"Comando de hodometro pendente; o hodometro enviado no comando de hodometro não é um inteiro: {target_odometer_str}")
                    return
                target_odometer = int(target_odometer_str)
                
                # Verificação do hodometro salvo no momento em que o comando foi recebido
                last_odometer_str = str(self.pending_odometer_command.get("last_odometer"))
                if not last_odometer_str or not last_odometer_str.isdigit():
                    logger.error(f"Comando de hodometro pendente; o último hodometro salvo não é um inteiro: {last_odometer_str}")
                    return
                last_odometer = int(last_odometer_str)
                
                logger.info("Comando de hodometro pendente; Valores checados, criando comando.")
                # =============================================================================
                # Criando novo comando
                difference = actual_odometer - last_odometer

                new_odometer = target_odometer + difference

                new_command = f"HODOMETRO:{new_odometer}"
                
                # ============================================================================

                logger.info("Comando de hodometro pendente; Comando criando, roteando para o dispositivo.")

                # Enviando comando para o processor do dispositivo
                protocol_type = redis_client.hget(f"tracker:{self.dev_id}", "protocol")
                if not protocol_type:
                    logger.error(f"Comando de hodometro pendente; Erro ao obter o protocolo de entrada do dispositivo, para rotear ao seu process_command, retornando.")
                    return
                
                target_module = importlib.import_module(f"app.src.input.{protocol_type}.builder")
                processor_func = getattr(target_module, "process_command")

                if not processor_func:
                    logger.error(f"Processador de comando para o protocolo '{str(protocol_type).upper()}' não encontrado.")
                    return

                logger.info(f"Comando de hodometro pendente; Roteando comando para o processador do protocolo: '{str(protocol_type).upper()}'.")
                processor_func(self.dev_id, self.serial, new_command)

                self.pending_odometer_command = {}

    def _reader_loop(self):
        while self._is_connected:
            with logger.contextualize(log_label=self.dev_id):
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
                    
                    if not self.input_protocol:
                        logger.error(f"Protocolo não disponível para o device_id={self.dev_id}. Impossível traduzir comando. dev_id={self.dev_id}")
                        continue

                    mapper_func = output_protocol_settings.OUTPUT_PROTOCOL_COMMAND_MAPPERS.get(self.output_protocol)
                    if not mapper_func:
                        logger.error(f"Mapeador de comandos universais para o protocolo de saida '{str(self.output_protocol).upper()}' não encontrado. dev_id={self.dev_id}")
                        return
                    
                    universal_command = mapper_func(self.dev_id, data)
                    if not universal_command:
                        logger.error(f"Comando universal não encontrado, output_protocol={self.output_protocol}, dev_id={self.dev_id}")
                        return
                    
                    redis_client.hset(f"tracker:{self.dev_id}", "last_command", universal_command)
                    
                    # Se for um comando de hodometro e o rastreador não estiver conectado no momento (estiver fora de área)
                    # Salvamos alguns dados importantes para que esse comando seja enviado novamente assim que o rastreador conectar novamente
                    if str(universal_command).startswith("HODOMETRO:") and not input_sessions_manager.exists(self.dev_id):
                        last_location_str, last_merged_location_str = redis_client.hmget(f"tracker:{self.dev_id}", "last_packet_data", "last_merged_location")
                        last_location = json.loads(last_location_str) if last_location_str else {}
                        last_merged_location = json.loads(last_merged_location_str) if last_merged_location_str else {}

                        last_odometer = last_location.get("gps_odometer", 0)

                        self.pending_odometer_command["command"] = universal_command
                        self.pending_odometer_command["last_odometer"] = last_odometer

                        # Atualizando GPS Hodometer de last_packet_data
                        meters = str(universal_command).split(":")[-1]
                        if not meters or not meters.isdigit():
                            logger.error(f"Não foi possível atualizar o hodometro de 'last_packet_data' e 'last_merged_location' no redis.")
                            continue

                        last_location["gps_odometer"] = meters
                        last_merged_location["gps_odometer"] = meters

                        mapping = {
                            "last_packet_data": json.dumps(last_location),
                            "last_merged_location": json.dumps(last_merged_location)
                        }
                        redis_client.hmset(f"tracker:{self.dev_id}", mapping)

                        logger.success(f"Hodometro de 'last_packet_data' e 'last_merged_location' no redis alterado com sucesso!")

                        continue

                    target_module = importlib.import_module(f"app.src.input.{self.input_protocol}.builder")
                    processor_func = getattr(target_module, "process_command")

                    if not processor_func:
                        logger.error(f"Processador de comando para o protocolo '{str(self.input_protocol).upper()}' não encontrado.")
                        continue

                    logger.info(f"Roteando comando para o processador do protocolo: '{str(self.input_protocol).upper()}'")
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
            
            # Atualizando variáveis de instância
            is_realtime = packet_data.get("is_realtime") if packet_data else None
            if is_realtime is not None:
                self._is_realtime = is_realtime

            device_type = packet_data.get("device_type") if packet_data else None
            if device_type and device_type == "satellital":
                self.device_type = "SAT"
            else:
                self.device_type = "GSM"

            packet_type = packet_data.get("packet_type") if packet_data else None
            if packet_type is not None and packet_type == "location" and self._is_realtime and self.device_type == "GSM":
                self._is_sending_realtime_location = True
            
            # Lógica para lidar com comandos de hodometro pendentes para dispositivos GSM
            # Que saem de área (disconectam-se do server, consequentemente não tem mais uma sessão em input_sessions_manager)
            # mas essa instância ainda está recebendo comandos, o salvamos e então o roteamos novamente ao aparelho
            self.handle_pending_odometer_command(int(packet_data.get("gps_odometer", 0) if packet_data else 0))
            
            # Atualizando protocolo de saída da instância
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

                # Apenas para GT06:
                # Enviando pacote de info de voltagem antes de qualquer pacote de localização/alerta em tempo real
                if self.output_protocol == "gt06" and packet_data and packet_data.get("packet_type") in ("location", "alert"):
                    if packet_data.get("voltage"): # Prioridade 1: é GSM/SAT e possui voltagem no pacote
                        voltage = packet_data.get("voltage")
                    elif not self._is_realtime: # Prioridade 2: Estamos enviando pacotes de memória de protocolos que não enviam voltagem nos pacotes, envia voltagem específica.
                        voltage = 1.11
                    else: # Prioridade 4: estamos em tempo real, o protocolo em questão não envia dados de voltagem no pacote, mas o conseguimos de outra forma, e se não o conseguirmos, enviamos 1.11.
                        voltage = packet_data.get("last_voltage") or "1.11" 
                        voltage = float(voltage)

                    voltage_packet = build_gt06_voltage_info_packet({"voltage": voltage}, int(self.serial))
                    logger.info(f"Enviando pacote de voltagem antes do pacote de localização/alerta em tempo real. dev_id={self.dev_id} voltage={voltage}V")
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

    def get_session(self, dev_id: str, input_protocol: str, output_protocol: str, serial: str) -> MainServerSession:
        with self.lock:
            if dev_id not in self._sessions:
                logger.info(f"Nenhuma sessão encontrada no MainServerSessionsManager. Criando uma nova. dev_id={dev_id}")
                self._sessions[dev_id] = MainServerSession(dev_id, input_protocol, output_protocol, serial)
                redis_client.sadd("output_sessions:active_trackers", dev_id)
            
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
                redis_client.srem("output_sessions:active_trackers", dev_id)

                logger.info(f"Sessão para dev_id={dev_id} deletada do MainServerSessionsManager.")
    
    def exists(self, dev_id, use_redis: bool = False):
        with self._lock:
            if use_redis:
                return redis_client.sismember("output_sessions:active_trackers", str(dev_id))
            
            socket_obj = self._sessions.get(str(dev_id))
            if socket_obj is None:
                return False
            
            try:
                return socket_obj.fileno() != -1
            except OSError:
                return False
    
    def get_sessions(self, use_redis: bool = False):
        if use_redis:
            return redis_client.smembers("output_sessions:active_trackers")
        
        else: return self._sessions.keys()
    
    def is_sending_realtime_location(self, dev_id: str):

        if dev_id in self._sessions:
            session = self._sessions[dev_id]

            return session._is_sending_realtime_location
        
        return False



output_sessions_manager = OutputSessionsManager()

def send_to_main_server(
        dev_id: str, packet_data: dict = None, serial: str = None, 
        raw_packet_hex: str = None, original_protocol: str = None, 
        type: Literal["location", "heartbeat", "alert", "command_reply"] = "location",
        managed_alert: bool = False
    ):
    """
    Executa lógica de construção de pacotes com base no protocolo de saída do dispositivo e o tipo de pacote especificado.
    """

    # Obtendo dados necessários do redis
    output_protocol, protocol, is_hybrid = redis_client.hmget(f"tracker:{dev_id}", "output_protocol", "protocol", "is_hybrid")
    
    # Verificação de protocolo de saída + setagem de valores padrão
    if not output_protocol:  # VL01 apenas se comunicará como GT06
        if is_hybrid or (protocol and protocol in ("vl01", "gp900m")):
            output_protocol = "gt06"
        else:
            output_protocol = "suntech4g"
        
        redis_client.hset(f"tracker:{dev_id}", "output_protocol", output_protocol)
    
    # Construção do pacote de saída, de acordo com o protocolo especificado
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

        logger.info(f"Pacote de {type.upper()} {output_protocol.upper()} traduzido de pacote {str(original_protocol).upper()}:")
        logger.info(f"{str_output_packet}")

        add_packet_to_history(dev_id, raw_packet_hex, str_output_packet)
        
        session = output_sessions_manager.get_session(dev_id, original_protocol.lower(), output_protocol, serial)
        session.send(output_packet, output_protocol, packet_data)

        # Heartbeats para GT06
        if output_protocol == 'gt06':
            heartbeat_packet_builder = output_protocol_settings.OUTPUT_PROTOCOL_PACKET_BUILDERS.get(output_protocol).get('heartbeat')
            heartbeat_packet = heartbeat_packet_builder(dev_id, packet_data, serial)

            session.send(heartbeat_packet, output_protocol, None)