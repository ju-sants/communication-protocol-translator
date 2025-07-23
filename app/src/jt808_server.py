import socket
import threading
import struct

from app.config.settings import settings
from app.src.jt808_utils import unescape_data, verify_checksum, build_jt808_response, format_jt808_packet_for_display
from app.src.jt808_processors import process_jt808_packet
from app.core.logger import get_logger

logger = get_logger(__name__)

jt808_clients = {}
jt808_clients_lock = threading.Lock()

def handle_jt808_connection(conn: socket.socket, addr):
    """Lida com uma única conexão de cliente JT/T 808."""
    logger.info(f"Conexão aceita de {addr}")
    buffer = b''
    dev_id_str = "desconhecido"
    try:
        while True:
            data = conn.recv(1024)
            if not data:
                break

            logger.debug(f"Dados brutos recebidos de {addr}: {data.hex()}")
            buffer += data
            
            while b'\x7e' in buffer:
                start_index = buffer.find(b'\x7e')
                end_index = buffer.find(b'\x7e', start_index + 1)
                if end_index == -1:
                    break

                raw_packet = buffer[start_index : end_index + 1]
                packet = buffer[start_index + 1 : end_index]
                buffer = buffer[end_index + 1:]

                logger.debug(f"Processando pacote de {addr}: {raw_packet.hex()}")

                unescaped_packet = unescape_data(packet)
                if not verify_checksum(unescaped_packet):
                    logger.warning(f"Checksum inválido para pacote de {addr}: {raw_packet.hex()}")
                    continue
                
                display_output = format_jt808_packet_for_display(unescaped_packet)
                logger.info(f"Pacote Formatado Recebido de {addr}:\n{display_output}")

                header_bytes = unescaped_packet[:12]
                msg_id, _, terminal_phone_bcd, serial = struct.unpack('>HH6sH', header_bytes)
                body = unescaped_packet[12:-1]
                dev_id_str = terminal_phone_bcd.hex()

                with jt808_clients_lock:
                    jt808_clients[dev_id_str] = conn
                    
                response_to_device = build_jt808_response(terminal_phone_bcd, serial, msg_id, 0)
                conn.sendall(response_to_device)
                logger.debug(f"ACK enviado ao dispositivo {dev_id_str}: {response_to_device.hex()}")

                process_jt808_packet(msg_id, body, serial, dev_id_str)

    except (ConnectionResetError, BrokenPipeError, TimeoutError):
        logger.warning(f"Conexão fechada abruptamente por {addr} (Device: {dev_id_str})")
    except Exception:
        logger.exception(f"Erro fatal na conexão de {addr} (Device: {dev_id_str})")
    finally:
        with jt808_clients_lock:
            if dev_id_str in jt808_clients:
                del jt808_clients[dev_id_str]

        logger.info(f"Fechando conexão e thread, dev_id={dev_id_str}, addr={addr}")
        conn.close()

def start_translator_server():
    """Inicia o servidor tradutor de protocolo."""
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(('', settings.JT808_LISTENER_PORT))
    server_socket.listen(10)
    logger.info(f"[*] Servidor Tradutor de Protocolo escutando em *:{settings.JT808_LISTENER_PORT}")
    
    while True:
        conn, addr = server_socket.accept()
        handler_thread = threading.Thread(target=handle_jt808_connection, args=(conn, addr))
        handler_thread.start()