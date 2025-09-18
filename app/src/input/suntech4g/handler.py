import socket
from app.core.logger import get_logger
from . import processor
from app.src.session.input_sessions_manager import input_sessions_manager

logger = get_logger(__name__)

def handle_connection(conn: socket.socket, addr):
    logger.info(f"New connection from {addr}")
    buffer = b''
    dev_id = None
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

                dev_id = processor.process_packet(packet_str)
                if dev_id:
                    input_sessions_manager.register_tracker_client(dev_id, conn)

    except ConnectionResetError:
        logger.warning(f"Connection with {addr} was reset.")
    except Exception as e:
        logger.error(f"Error in connection with {addr}: {e}")
    finally:
        if dev_id:
            input_sessions_manager.remove_tracker_client(dev_id)
            logger.info(f"Device {dev_id} session removed.")
        logger.info(f"Closing connection with {addr}.")
        conn.close()