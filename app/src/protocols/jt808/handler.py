import socket
import struct
from app.core.logger import get_logger
from .processor import process_packet, format_jt808_packet_for_display
from .utils import unescape_data, verify_checksum
from app.src.protocols.session_manager import tracker_sessions_manager
from app.services.redis_service import get_redis


logger = get_logger("jt808_handler")
redis_client = get_redis()

def handle_connection(conn: socket.socket, addr):
    """Lida com uma única conexão de cliente JT/T 808."""
    logger.info("Nova conexão JT/T 808", endereco=addr)
    buffer = b''
    dev_id_str = None
    try:
        while True:
            data = conn.recv(1024)
            if not data:
                break
            
            buffer += data
            
            while b'\x7e' in buffer:
                start_index = buffer.find(b'\x7e')
                end_index = buffer.find(b'\x7e', start_index + 1)
                if end_index == -1:
                    break

                raw_packet = buffer[start_index : end_index + 1]
                buffer = buffer[end_index + 1:]

                unescaped_packet = unescape_data(raw_packet[1:-1])
                if not verify_checksum(unescaped_packet):
                    logger.warning("Checksum JT/T 808 inválido", pacote=raw_packet.hex())
                    continue

                # Extrai o dev_id para registro e logging
                header_bytes = unescaped_packet[:12]
                _, _, terminal_phone_bcd, _ = struct.unpack('>HH6sH', header_bytes)
                dev_id_str = terminal_phone_bcd.hex()

                # Registra o cliente no gerenciador de sessão
                tracker_sessions_manager.register_client(dev_id_str, conn)
                redis_client.hset(dev_id_str, "protocol", "jt808")

                logger.info(f"Pacote Formatado Recebido de {addr}:\n{format_jt808_packet_for_display(unescaped_packet, dev_id_str)}")

                # Envia o pacote para o processador e recebe a resposta para o dispositivo
                response_to_device = process_packet(unescaped_packet)
                if response_to_device:
                    conn.sendall(response_to_device)

    except (ConnectionResetError, BrokenPipeError):
        logger.warning(f"Conexão JT/T 808 fechada abruptamente endereco={addr}, device_id={dev_id_str}")
    except Exception:
        logger.exception(f"Erro fatal na conexão JT/T 808 endereco={addr}, device_id={dev_id_str}")
    finally:
        if dev_id_str:
            tracker_sessions_manager.remove_client(dev_id_str)
        logger.info(f"Fechando conexão e thread JT/T 808 endereco={addr}, device_id={dev_id_str}")
        conn.close()