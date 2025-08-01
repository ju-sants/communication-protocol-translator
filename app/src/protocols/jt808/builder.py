import struct
import socket

from app.config.settings import settings
from app.core.logger import get_logger
from app.src.protocols.jt808.utils import calculate_checksum, escape_data
from app.src.protocols.session_manager import tracker_sessions_manager

logger = get_logger(__name__)

def build_generic_response(terminal_phone: bytes, terminal_serial: int, msg_id: int, result: int) -> bytes:
    """Constrói uma resposta padrão (0x8001) para o dispositivo JT/T 808."""
    msg_id_resp = 0x8001
    body_props = 5 # Corpo da resposta tem 5 bytes
    server_serial = terminal_serial # Ecoa o serial do terminal

    # Monta o cabeçalho e o corpo da resposta
    header = struct.pack('>HH', msg_id_resp, body_props) + terminal_phone + struct.pack('>H', server_serial)
    body = struct.pack('>HHB', terminal_serial, msg_id, result)
    
    raw_message = header + body
    
    # Calcula o checksum
    checksum = 0
    for byte in raw_message:
        checksum ^= byte
        
    final_message = raw_message + struct.pack('>B', checksum)
    
    # Realiza o escape de bytes
    final_message = final_message.replace(b'\x7d', b'\x7d\x01')
    final_message = final_message.replace(b'\x7e', b'\x7d\x02')
    
    # Delimita a mensagem com 0x7e
    return b'\x7e' + final_message + b'\x7e'

def build_command(dev_id: str, serial: int, msg_id: int, msg_body: bytes) -> bytes:
    dev_id_bcd = bytes.fromhex(dev_id[-12:])
    msg_body_properties = len(msg_body) & 0x03FF

    header = struct.pack(">HH6sH", msg_id, msg_body_properties, dev_id_bcd, serial)
    raw_message = header + msg_body
    checksum = calculate_checksum(raw_message)
    message_w_checksum = raw_message + checksum
    escaped_message = escape_data(message_w_checksum)
    command = b"\x7e" + escaped_message + b"\x7e"
    return command


def process_suntech_command(data: bytes, dev_id: str, serial: str):
    logger.info(f"Processando comando suntech, dev_id={dev_id}")

    command = data.decode("ascii", errors="ignore").strip()

    parts = command.split(';')

    command_key = f"{parts[0]};{parts[2]};{parts[3]}"

    command_mapping = {
        "CMD;04;01": (0x8105, b"\x64"),
        "CMD;04;02": (0x8105, b"\x65"),
        "CMD;03;01": (0x8201, b""),
    }

    jt808_command = None
    if command_key in command_mapping:
        params = command_mapping[command_key]
        jt808_command = build_command(dev_id, int(serial), *params)

    if jt808_command:

        if tracker_sessions_manager.exists(dev_id):
            tracker_socket: socket.socket = tracker_sessions_manager.get_tracker_client_socket[dev_id]

            if tracker_socket:
                try:
                    tracker_socket.sendall(jt808_command)
                    logger.info(f"Comando JT/T 808 enviado para o rastreador device_id={dev_id}")
                except Exception:
                    logger.exception(f"Falha ao enviar comando para o rastreador device_id={dev_id}")
            else:
                logger.warning(f"Conexão do dispositivo dev_id={dev_id} foi encontrada mas já foi fechada")
        else:
            logger.warning(f"Dispositivo não registrado na sessão: dev_id={dev_id}")