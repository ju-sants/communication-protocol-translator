import socket
import json

from app.core.logger import get_logger
from app.services.redis_service import get_redis
from . import processor
from app.src.session.input_sessions_manager import input_sessions_manager

logger = get_logger(__name__)
redis_client = get_redis()

START_BIT = b'\xff'
STOP_BIT = b'\xfe'

def handle_connection(conn: socket.socket, addr):
    """
    Handles a single satellite client connection, managing the session state.
    """
    logger.info(f"New Satellite connection received address={addr}", log_label="SERVIDOR")
    buffer = b''
    esn_id = None

    try:
        while True:
            data = conn.recv(1024)
            if not data:
                logger.info(f"Satellite connection closed by client address={addr}, esn_id={esn_id}", log_label="SERVIDOR")
                break

            buffer += data

            start_index = buffer.find(START_BIT)
            if start_index == -1:
                return None

            stop_index = buffer.find(STOP_BIT, start_index + len(START_BIT))
            if stop_index == -1:
                return None

            data = buffer[start_index + len(START_BIT):stop_index]

            data_json = json.loads(data)
            esn_id = data_json.get("ESN")

            with logger.contextualize(log_label=esn_id):

                if esn_id and not input_sessions_manager.exists(esn_id):
                    input_sessions_manager.register_tracker_client(esn_id, conn, ex=3600 * 24)
                    logger.info(f"Rastreador satelital {esn_id}, registrado na seção.")

                if data:
                    try:
                        processor.process_packet(data)
                    except Exception as e:
                        logger.error(f"Error processing data: {e}")
                    buffer = b''
                else:
                    logger.debug("No complete data packet yet.")

    except (ConnectionResetError, BrokenPipeError):
        logger.warning(f"Satellite connection closed abruptly address={addr}, esn_id={esn_id}", log_label="SERVIDOR")
    except Exception:
        logger.exception(f"Fatal error in Satellite connection address={addr}, esn_id={esn_id}", log_label="SERVIDOR")
    finally:
        logger.info(f"Closing connection and Satellite thread address={addr}, esn_id={esn_id}", log_label="SERVIDOR")

        try:
            conn.shutdown(socket.SHUT_RDWR)
            conn.close()
            conn = None
        except Exception as e:
            logger.error(f"Impossible to clean connection with tracker esn_id={esn_id}", log_label="SERVIDOR")