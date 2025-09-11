import socket
from app.core.logger import get_logger
from app.src.protocols.session_manager import tracker_sessions_manager
from app.services.redis_service import get_redis
from app.src.connection.main_server_connection import sessions_manager
from . import mapper

logger = get_logger(__name__)
redis_client = get_redis()

START_BIT = b'\xff'
STOP_BIT = b'\xfe'

def handle_connection(conn: socket.socket, addr):
    """
    Handles a single satellite client connection, managing the session state.
    """
    logger.info(f"New Satellite connection received address={addr}")
    buffer = b''
    dev_id_session = None

    try:
        while True:
            data = conn.recv(1024)
            if not data:
                logger.info(f"Satellite connection closed by client address={addr}, device_id={dev_id_session}")
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
                logger.info(f"Satellite data received: {data}")
                try:
                    mapper.map_data(data)
                except Exception as e:
                    logger.error(f"Error processing data: {e}")
                buffer = b''
            else:
                logger.debug("No complete data packet yet.")

    except (ConnectionResetError, BrokenPipeError):
        logger.warning(f"Satellite connection closed abruptly address={addr}, device_id={dev_id_session}")
    except Exception:
        logger.exception(f"Fatal error in Satellite connection address={addr}, device_id={dev_id_session}")
    finally:
        logger.debug(f"[DIAGNOSTIC] Entering finally block for Satellite handler (addr={addr}, dev_id={dev_id_session}).")
        if dev_id_session:
            logger.info(f"Deleting Sessions on both sides for this tracker dev_id={dev_id_session}")
            sessions_manager.delete_session(dev_id_session)
            tracker_sessions_manager.remove_tracker_client(dev_id_session)

        logger.info(f"Closing connection and Satellite thread address={addr}, device_id={dev_id_session}")

        try:
            conn.shutdown(socket.SHUT_RDWR)
            conn.close()
            conn = None
        except Exception as e:
            logger.error(f"Impossible to clean connection with tracker dev_id={dev_id_session}")