import socket
from app.core.logger import get_logger
from .processor import process_packet
import struct

from app.src.session.input_sessions_manager import input_sessions_manager
from app.services.redis_service import get_redis
from app.src.session.output_sessions_manager import output_sessions_manager

logger = get_logger(__name__)
redis_client = get_redis()

def handle_connection(conn: socket.socket, addr):
    """
    Lida com uma única conexão de cliente J16X-J16, gerenciando o estado da sessão.
    """
    logger.info(f"Nova conexão J16X-J16 recebida endereco={addr}", log_label="SERVIDOR")
    buffer = b''
    dev_id_session = None

    try:
        while True:
            with logger.contextualize(log_label=dev_id_session):
                data = conn.recv(1024)
                if not data:
                    logger.info(f"Conexão J16X-J16 fechada pelo cliente endereco={addr}")
                    break
                
                buffer += data
                
                while len(buffer) > 4:
                    if buffer.startswith(b'\x78\x78') or buffer.startswith(b"\x79\x79"):

                        packet_length = buffer[2] if buffer.startswith(b"\x78\x78") else struct.unpack(">H", buffer[2:4])[0]

                        is_x79 = False
                        if buffer.startswith(b'\x78\x78'):
                            # Tamanho total do pacote na stream: Start(2) + [Length(1) + Corpo(length-2)] + Stop(2)
                            full_packet_size = 2 + 1 + packet_length + 2
                        else:
                            is_x79 = True
                            full_packet_size = 2 + 2 + packet_length + 2
                        
                        if len(buffer) >= full_packet_size:
                            raw_packet = buffer[:full_packet_size]
                            buffer = buffer[full_packet_size:]

                            # Validação dos bits de parada
                            if not raw_packet.endswith(b'\x0d\x0a'):
                                logger.warning(f"Pacote J16X-J16 com stop bits inválidos, descartando. pacote={raw_packet.hex()}")
                                continue
                            
                            # Corpo do pacote que vai para o processador: [Length(1) + Proto(1) + Conteúdo + Serial(2) + CRC(2)]
                            packet_body = raw_packet[2:-2]

                            logger.info(f"Recebido pacote J16X-J16 (x79: {is_x79}): {packet_body.hex()}")
                            
                            # Chama o processador, passando o ID da sessão
                            new_dev_id = process_packet(dev_id_session, packet_body, conn, is_x79)
                            
                            if new_dev_id and new_dev_id != dev_id_session:
                                dev_id_session = new_dev_id

                            if dev_id_session:
                                # Verificando se já existe um registro desse device id com um socket
                                if input_sessions_manager.exists(dev_id_session):
                                    old_conn = input_sessions_manager.get_session(dev_id_session)

                                    if old_conn and old_conn != conn:
                                        logger.warning(f"Conexão Duplicada. Fechando conexão antiga: {old_conn.getpeername()}", log_label="SERVIDOR")
                                        try:
                                            old_conn.shutdown(socket.SHUT_RDWR)
                                            old_conn.close()
                                        except Exception:
                                            pass
                                        
                                        # Removendo o registro antigo
                                        input_sessions_manager.remove_session(dev_id_session)

                                        # Criando o novo
                                        input_sessions_manager.register_session(dev_id_session, conn)
                                        redis_client.hset(f"tracker:{dev_id_session}", "protocol", "j16x_j16")
                                        logger.info(f"Dispositivo J16X-J16 autenticado na sessão device_id={dev_id_session}, endereco={addr}")

                                else:     
                                    # Caso não exista, o registramos
                                    input_sessions_manager.register_session(dev_id_session, conn)
                                    redis_client.hset(f"tracker:{dev_id_session}", "protocol", "j16x_j16")
                                    logger.info(f"Dispositivo J16X-J16 autenticado na sessão device_id={dev_id_session}, endereco={addr}")

                        else:
                            break
                    else:
                        # Procuramos o próximo início de pacote válido para tentar nos recuperar.
                        next_start_78 = buffer.find(b'\x78\x78', 1)
                        next_start_79 = buffer.find(b"\x79\x79", 1)

                        next_start = next_start_78
                        if next_start_79 != -1 and next_start_78 != -1 and next_start_79 < next_start_78:
                            next_start = next_start_79

                        if next_start != -1:
                            dados_descartados = buffer[:next_start]
                            logger.warning(f"Dados desalinhados no buffer, descartando {len(dados_descartados)} bytes dados={dados_descartados.hex()}")
                            buffer = buffer[next_start:]
                        else:
                            # Nenhum início válido encontrado, limpa o buffer
                            buffer = b''
    
    except (ConnectionResetError, BrokenPipeError):
        logger.warning(f"Conexão J16X-J16 fechada abruptamente endereco={addr}, device_id={dev_id_session}", log_label="SERVIDOR")
    except Exception:
        logger.exception(f"Erro fatal na conexão J16X-J16 endereco={addr}, device_id={dev_id_session}", log_label="SERVIDOR")
    finally:
        logger.debug(f"[DIAGNOSTIC] Entering finally block for J16X-J16 handler (addr={addr}, dev_id={dev_id_session}", log_label="SERVIDOR")
        if dev_id_session:
            with logger.contextualize(log_label=dev_id_session):
                logger.info(f"Deletando Sessões em ambos os lados para esse rastreador dev_id={dev_id_session}", log_label="SERVIDOR")
                output_sessions_manager.delete_session(dev_id_session)
                input_sessions_manager.remove_session(dev_id_session)
        
        logger.info(f"Fechando conexão e thread J16X-J16 endereco={addr}, device_id={dev_id_session}", log_label="SERVIDOR")

        try:
            conn.shutdown(socket.SHUT_RDWR)
            conn.close()
            conn = None
        except Exception as e:
            logger.error(f"Impossível limpar conexão com rastreador dev_id={dev_id_session}", log_label="SERVIDOR")