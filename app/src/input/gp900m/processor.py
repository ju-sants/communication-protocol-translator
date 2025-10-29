import struct
import socket

from . import builder, mapper
from .. import utils
from app.src.session.output_sessions_manager import send_to_main_server
from app.core.logger import get_logger
from app.services.redis_service import get_redis


logger = get_logger(__name__)
redis_client = get_redis()

def process_packet(payload_starts_at: int, packet_body: bytes, conn: socket.socket) -> tuple[bytes | None, str | None]:
    """
    Processa o corpo de um pacote GP900M, valida, disseca e delega a ação.
    Recebe o dev_id da sessão (se já conhecido).
    """
    # Validação Mínima de Tamanho
    if len(packet_body) < 20:
        logger.warning(f"Pacote GP900M recebido muito curto para processar: {packet_body.hex()}")
        return None, None

    header = packet_body[:payload_starts_at]
    payload = packet_body[payload_starts_at:]

    # Header Decodification
    # ====================================
    # Processor-Scope
    tag = header[0]
    needs_response = tag & 0b11 != 0 # Verificamos se os dois primeiros bits são diferentes de 0, em caso positivo o dipositivo precisa de resposta (ACK)
    dev_id_str = header[1:9].hex()
    serial_number = int.from_bytes(header[9:11], "big")
    # Mapper-Scope
    event = header[15]
    # ============================================
    
    # Payload Decodification
    # ======================================
    # Processor-Scope
    first_byte_payload_type = payload[0]
    if not first_byte_payload_type >= 224:
        payload_type_field_len = 1
        payload_type = first_byte_payload_type
    else:
        payload_type_field_len = 2

        payload_type = payload[:2] & 0x1FFF
    
    first_byte_payload_length = payload[payload_type_field_len]
    if not first_byte_payload_length >= 224:
        payload_length_field_len = 1
    else:
        payload_length_field_len = 2

    # =========================================
    
    response_to_device = None
    payload_value_starts_at = payload_type_field_len + payload_length_field_len

    if payload_type == 0x00: # General Report
        packet_data = mapper.handle_general_report(dev_id_str, serial_number, payload, event, payload_value_starts_at)
        if packet_data:
            utils.log_mapped_packet(packet_data, "GP900M")

            send_to_main_server(...)

        if needs_response: 
            response_to_device = builder.build_generic_response(payload_type, serial_number)
            
    elif payload_type == 0x41:
        packet_data = mapper.handle_odometer_read(dev_id_str, serial_number, payload, event, payload_type_field_len)
        if packet_data:
            send_to_main_server(...)

        if needs_response: 
            response_to_device = builder.build_generic_response(payload_type, serial_number)
            
    else:
        logger.warning(f"Protocolo GP900M não mapeado: {hex(payload_type)} device_id={dev_id_str}")
        if needs_response: 
            response_to_device = builder.build_generic_response(payload_type, serial_number)

    if response_to_device:
        conn.sendall(response_to_device)

    return dev_id_str