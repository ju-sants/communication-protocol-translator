import socket
from app.core.logger import get_logger
from app.services.redis_service import get_redis
from . import processor
from app.src.session.input_sessions_manager import input_sessions_manager
from app.src.session.output_sessions_manager import output_sessions_manager

logger = get_logger(__name__)
redis_client = get_redis()

def handle_connection(conn: socket.socket, addr):
    logger.info(f"New connection from {addr}", log_label="SERVIDOR")
    buffer = b''
    dev_id_session = None

    try:
        while True:
            with logger.contextualize(log_label=dev_id_session):
                data = conn.recv(1024)
                if not data:
                    logger.info(f"Connection with {addr} closed by client.")
                    break

                logger.debug(f"Raw data received: {data}")
                buffer += data

                while b'\r' in buffer:
                    packet_end_index = buffer.find(b'\r')
                    raw_packet = buffer[:packet_end_index]
                    buffer = buffer[packet_end_index:].lstrip(b'\r\n')
                    
                    packet_str = raw_packet.decode('ascii', errors='ignore')
                    logger.info(f"Recebido pacote SUNTECH2G: {packet_str}")

                    new_dev_id = processor.process_packet(packet_str)

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
                                redis_client.hset(f"tracker:{dev_id_session}", "protocol", "suntech2g")
                                logger.info(f"Dispositivo SUNTECH2G autenticado na sessão")
                        else:
                            # Caso não exista, o registramos
                            input_sessions_manager.register_session(dev_id_session, conn)
                            redis_client.hset(f"tracker:{dev_id_session}", "protocol", "suntech2g")
                            logger.info(f"Dispositivo SUNTECH2G autenticado na sessão")


    except ConnectionResetError:
        logger.warning(f"Connection with {addr} was reset.", log_label="SERVIDOR")
    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.error(f"Error in connection with {addr}: {e}", log_label="SERVIDOR")
    finally:
        if dev_id_session:
            with logger.contextualize(log_label=dev_id_session):
                logger.info(f"Deletando Sessões em ambos os lados para esse rastreador dev_id_session={dev_id_session}", log_label="SERVIDOR")
                input_sessions_manager.remove_session(dev_id_session)
                output_sessions_manager.delete_session(dev_id_session)

        try:
            conn.shutdown(socket.SHUT_RDWR)
            conn.close()
            conn = None
        except Exception as e:
            logger.error(f"Impossible to shutdown connection with {addr}: {e}", log_label="SERVIDOR")