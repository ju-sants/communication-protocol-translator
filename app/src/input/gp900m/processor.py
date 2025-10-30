import struct
import socket

from . import builder, mapper, utils as protocol_utils
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
    event, _ = protocol_utils.get_dinamic_field(header, 15)
        
    # ============================================
    
    # Payload Decodification
    # ======================================
    # Processor-Scope
    payload_type, payload_type_end = protocol_utils.get_dinamic_field(payload, 0)

    _, payload_length_end = protocol_utils.get_dinamic_field(payload, payload_type_end)

    # =========================================
    
    response_to_device = None

    if payload_type == 0x00: # General Report
        packet_data, alarm_packet_data, ign_alarm_packet_data = mapper.handle_general_report(dev_id_str, serial_number, payload, event, payload_length_end)
        if packet_data:
            utils.log_mapped_packet(packet_data, "GP900M")

            send_to_main_server(dev_id_str, packet_data, serial_number, packet_body.hex(), "GP900M")

        last_alarm = None
        if alarm_packet_data:
            last_alarm = alarm_packet_data.get("universal_alert_id")
            send_to_main_server(dev_id_str, alarm_packet_data, serial_number, packet_body.hex(), "GP900M", "alert" if isinstance(last_alarm, int) else "command_reply")
        
        if ign_alarm_packet_data and not last_alarm or ign_alarm_packet_data and last_alarm != ign_alarm_packet_data.get("universal_alert_id"):
            send_to_main_server(dev_id_str, ign_alarm_packet_data, serial_number, packet_body.hex(), "GP900M", "alert")

        if needs_response: 
            response_to_device = builder.build_generic_response(payload_type, serial_number)
            
    elif payload_type == 0x41:
        packet_data = mapper.handle_odometer_read(dev_id_str, serial_number, payload, event, payload_length_end)
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