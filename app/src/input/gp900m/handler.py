import socket
import struct

from app.core.logger import get_logger
from .processor import process_packet
from app.src.session.input_sessions_manager import input_sessions_manager
from app.services.redis_service import get_redis
from app.src.session.output_sessions_manager import output_sessions_manager

logger = get_logger(__name__)
redis_client = get_redis()

def handle_connection(conn: socket.socket, addr):
    """
    Lida com uma única conexão de cliente GP900M, gerenciando o estado da sessão.
    """
    logger.info(f"Nova conexão GP900M recebida endereco={addr}", log_label="SERVIDOR")
    buffer = b''
    dev_id_session = None

    try:
        while True:
            with logger.contextualize(log_label=dev_id_session):
                data = conn.recv(1024)
                if not data:
                    logger.info(f"Conexão GP900M fechada pelo cliente endereco={addr}, device_id={dev_id_session}")
                    break
                
                buffer += data
                
                while len(buffer) > 4:
                    if buffer.startswith(b'\x7d'):
                        
                        first_event_field_byte = buffer[16]
                        if not first_event_field_byte >= 224:
                            event_field_len = 1

                        else:
                            event_field_len = 2

                        first_length_field_byte = buffer[16 + event_field_len]
                        if not first_length_field_byte >= 224:
                            length_field_len = 1

                            length_body = first_length_field_byte
                        else:
                            length_field_len = 2

                            full_length_bytes = buffer[16 + event_field_len:16 + length_field_len + length_field_len]
                            length_body = full_length_bytes & 0x1FFF # Usamos apenas os 13 LSBs

                        # Tamanho total do pacote na stream: Start(1) + Ack(1) + DevID(8) + Serial(2) + Timestamp(4) + Event + LengthByteLen + LengthBody
                        payload_starts_at = 1 + 1 + 8 + 2 + 4 + event_field_len + length_field_len
                        full_packet_size = payload_starts_at + length_body
                        
                        if len(buffer) >= full_packet_size:
                            raw_packet = buffer[:full_packet_size]
                            buffer = buffer[full_packet_size:]

                            # Corpo do pacote que vai para o processador: Ack(1) + DevID(8) + Serial(2) + Timestamp(4) + Event + LengthByteLen + LengthBody
                            packet_body = raw_packet[1:]
                            logger.info(f"Recebido pacote GP900M: {packet_body.hex()}")

                            # Chama o processador, passando o ID da sessão
                            payload_starts_at -= 1 # Retirando um pois passaremos o pacote depois do Byte de start packet_body[1:]
                            newly_logged_in_dev_id = process_packet(payload_starts_at, packet_body, conn)
                            
                            if newly_logged_in_dev_id and newly_logged_in_dev_id != dev_id_session:
                                dev_id_session = newly_logged_in_dev_id

                            if dev_id_session and not input_sessions_manager.exists(dev_id_session):
                                input_sessions_manager.register_tracker_client(dev_id_session, conn)
                                redis_client.hset(f"tracker:{dev_id_session}", "protocol", "gp900m")
                                logger.info(f"Dispositivo GP900M autenticado na sessão device_id={dev_id_session}, endereco={addr}")

                        else:
                            break
                    else:
                        # Procuramos o próximo início de pacote válido para tentar nos recuperar.
                        next_start = buffer.find(b'\x7d', 1)

                        if next_start != -1:
                            dados_descartados = buffer[:next_start]
                            logger.warning(f"Dados desalinhados no buffer, descartando {len(dados_descartados)} bytes dados={dados_descartados.hex()}")
                            buffer = buffer[next_start:]
                        else:
                            # Nenhum início válido encontrado, limpa o buffer
                            buffer = b''
    
    except (ConnectionResetError, BrokenPipeError):
        logger.warning(f"Conexão GP900M fechada abruptamente endereco={addr}, device_id={dev_id_session}", log_label="SERVIDOR")
    except Exception:
        logger.exception(f"Erro fatal na conexão GP900M endereco={addr}, device_id={dev_id_session}", log_label="SERVIDOR")
    finally:
        logger.debug(f"[DIAGNOSTIC] Entering finally block for GP900M handler (addr={addr}, dev_id={dev_id_session}", log_label="SERVIDOR")
        if dev_id_session:
            with logger.contextualize(log_label=dev_id_session):
                logger.info(f"Deletando Sessões em ambos os lados para esse rastreador dev_id={dev_id_session}", log_label="SERVIDOR")
                output_sessions_manager.delete_session(dev_id_session)
                input_sessions_manager.remove_tracker_client(dev_id_session)
        
        logger.info(f"Fechando conexão e thread GP900M endereco={addr}, device_id={dev_id_session}", log_label="SERVIDOR")

        try:
            conn.shutdown(socket.SHUT_RDWR)
            conn.close()
            conn = None
        except Exception as e:
            logger.error(f"Impossível limpar conexão com rastreador dev_id={dev_id_session}", log_label="SERVIDOR")