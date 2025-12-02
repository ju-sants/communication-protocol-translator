import struct
import socket

from . import builder, mapper
from .. import utils
from app.src.session.output_sessions_manager import send_to_main_server
from app.core.logger import get_logger
from app.services.redis_service import get_redis

redis_client = get_redis()
logger = get_logger(__name__)

def process_packet(dev_id_str: str | None, packet_body: bytes, conn: socket.socket, is_x79: bool = False) -> tuple[bytes | None, str | None]:
    """
    Processa o corpo de um pacote VL03, valida, disseca e delega a ação.
    Recebe o dev_id da sessão (se já conhecido).
    Retorna uma tupla: (pacote_de_resposta, dev_id_extraido_do_login)
    """
    # Validação Mínima de Tamanho
    if len(packet_body) < 6:
        logger.warning(f"Pacote VL03 recebido muito curto para processar: {packet_body.hex()}")
        return None, None
    
    # CRC
    data_to_check = packet_body[:-2]
    received_crc = struct.unpack('>H', packet_body[-2:])[0]
    calculated_crc = utils.crc_itu(data_to_check)

    if received_crc != calculated_crc:
        logger.warning(f"Checksum VL03 inválido! pacote={packet_body.hex()}, crc_recebido={hex(received_crc)}, crc_calculado={hex(calculated_crc)}")
        return None, None
    
    protocol_number = packet_body[1] if not is_x79 else packet_body[2]
    serial_number = struct.unpack('>H', packet_body[-4:-2])[0]
    content_body = packet_body[2:-4] if not is_x79 else packet_body[3:-4]
    
    response_to_device = None
    newly_logged_in_dev_id = None

    if protocol_number == 0x01: # Pacote de Login
        imei_bytes = content_body
        newly_logged_in_dev_id = imei_bytes.hex()
        response_to_device = builder.build_generic_response(protocol_number, serial_number)
    

    elif protocol_number in (0xA0, 0x22): # Location Packet
        if dev_id_str:
            location_packet_data, ign_alert_packet_data = mapper.handle_location_packet(dev_id_str, serial_number, content_body, protocol_number)
            if location_packet_data:
                utils.log_mapped_packet(location_packet_data, "VL03")
                send_to_main_server(dev_id_str, location_packet_data, serial_number, packet_body.hex(), "VL03")

            if ign_alert_packet_data and ign_alert_packet_data.get("universal_alert_id"):
                send_to_main_server(dev_id_str, ign_alert_packet_data, serial_number, packet_body.hex(), "VL03", "alert", True)

        else:
            logger.warning(f"Pacote de localização/alarme VL03 recebido antes do login. Ignorando. pacote={packet_body.hex()}")

        response_to_device = builder.build_generic_response(protocol_number, serial_number)


    elif protocol_number in (0x26, 0xA4): # Alarm Packet
        if dev_id_str:
            alarm_packet_data = mapper.handle_alarm_packet(dev_id_str, content_body)
            if alarm_packet_data:
                utils.log_mapped_packet(alarm_packet_data, "VL03")
                send_to_main_server(dev_id_str, alarm_packet_data, serial_number, packet_body.hex(), original_protocol="VL03", type="alert")

        else:
            logger.warning(f"Pacote de localização/alarme VL03 recebido antes do login. Ignorando. pacote={packet_body.hex()}")

        response_to_device = builder.build_generic_response(protocol_number, serial_number)


    elif protocol_number == 0x94: # Information Packet
        if dev_id_str:
            mapper.handle_information_packet(dev_id_str, content_body)
        else:
            logger.warning(f"Pacote de information VL03 recebido antes do login. Ignorando. pacote={packet_body.hex()}")

        response_to_device = builder.build_generic_response(protocol_number, serial_number)


    elif protocol_number == 0x13: # Pacote de Heartbeat/Status
        if dev_id_str:
            mapper.handle_heartbeat_packet(dev_id_str, serial_number, content_body)
            send_to_main_server(dev_id_str, serial=serial_number, raw_packet_hex=packet_body.hex(), original_protocol="VL03", type="heartbeat")

        else:
            logger.warning(f"Pacote de heartbeat VL03 recebido antes do login. Ignorando. pacote={packet_body.hex()}")

        response_to_device = builder.build_generic_response(protocol_number, serial_number)
    
    elif protocol_number == 0x21:
        if dev_id_str:
            reply_command_packet_data = mapper.handle_reply_command_packet(dev_id_str, content_body)
            if reply_command_packet_data:
                utils.log_mapped_packet(reply_command_packet_data, "VL03")
                send_to_main_server(dev_id_str, reply_command_packet_data, serial_number, packet_body.hex(), original_protocol="VL03", type="command_reply")

        else:
            logger.warning(f"Pacote de reply command VL03 recebido antes do login. Ignorando. pacote={packet_body.hex()}")
    else:
        logger.warning(f"Protocolo VL03 não mapeado: {hex(protocol_number)} device_id={dev_id_str}")
        response_to_device = builder.build_generic_response(protocol_number, serial_number)

    if response_to_device:
        conn.sendall(response_to_device)

    return newly_logged_in_dev_id