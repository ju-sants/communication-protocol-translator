import socket
from app.core.logger import get_logger, set_log_context
from app.services.redis_service import get_redis
from .processor import process_packet
from app.src.session.input_sessions_manager import input_sessions_manager
from app.src.session.output_sessions_manager import output_sessions_manager

logger = get_logger(__name__)
redis_client = get_redis()

def handle_connection(conn: socket.socket, addr):
    logger.info(f"New connection from {addr}")
    buffer = b''
    dev_id = None

    set_log_context(f"addr:{addr[0]}:{addr[1]}")

    try:
        while True:
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
                logger.debug(f"Packet string (before processing): '{packet_str}'")

                new_dev_id = process_packet(packet_str)
                if new_dev_id and new_dev_id != dev_id:
                    dev_id = new_dev_id
                    set_log_context(dev_id)
                    
                if dev_id and not input_sessions_manager.exists(dev_id):
                    input_sessions_manager.register_tracker_client(dev_id, conn)
                    redis_client.hset(f"tracker:{dev_id}", "protocol", "suntech2g")


    except ConnectionResetError:
        logger.warning(f"Connection with {addr} was reset.")
    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.error(f"Error in connection with {addr}: {e}")
    finally:
        if dev_id:
            logger.info(f"Deletando Sessões em ambos os lados para esse rastreador dev_id={dev_id}")
            input_sessions_manager.remove_tracker_client(dev_id)
            output_sessions_manager.delete_session(dev_id)

        set_log_context(None)

        try:
            conn.shutdown(socket.SHUT_RDWR)
            conn.close()
            conn = None
        except Exception as e:
            logger.error(f"Impossible to shutdown connection with {addr}: {e}")