import socket
from app.core.logger import get_logger
from app.services.redis_service import get_redis
from . import processor

logger = get_logger(__name__)
redis_client = get_redis()

START_BIT = b'\xff'
STOP_BIT = b'\xfe'

def handle_connection(conn: socket.socket, addr):
    """
    Handles a single satellite client connection, managing the session state.
    """
    with logger.contextualize(tracker_id="SATELLITE"):
        logger.info(f"New Satellite connection received address={addr}")
        buffer = b''
        esn_id = None

        try:
            while True:
                data = conn.recv(1024)
                if not data:
                    logger.info(f"Satellite connection closed by client address={addr}, esn_id={esn_id}")
                    break

                buffer += data

                start_index = buffer.find(START_BIT)
                if start_index == -1:
                    return None

                stop_index = buffer.find(STOP_BIT, start_index + len(START_BIT))
                if stop_index == -1:
                    return None

                data = buffer[start_index + len(START_BIT):stop_index]

                if data:
                    try:
                        processor.process_packet(data)
                    except Exception as e:
                        logger.error(f"Error processing data: {e}")
                    buffer = b''
                else:
                    logger.debug("No complete data packet yet.")

        except (ConnectionResetError, BrokenPipeError):
            logger.warning(f"Satellite connection closed abruptly address={addr}, esn_id={esn_id}")
        except Exception:
            logger.exception(f"Fatal error in Satellite connection address={addr}, esn_id={esn_id}")
        finally:
            logger.info(f"Closing connection and Satellite thread address={addr}, esn_id={esn_id}")

            try:
                conn.shutdown(socket.SHUT_RDWR)
                conn.close()
                conn = None
            except Exception as e:
                logger.error(f"Impossible to clean connection with tracker esn_id={esn_id}")