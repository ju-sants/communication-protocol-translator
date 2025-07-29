import struct

from . import builder, mapper, utils
from app.core.logger import get_logger


logger = get_logger(__name__)

def process_packet(dev_id_str: str | None, packet_body: bytes) -> tuple[bytes | None, str | None]:
    """
    Processa o corpo de um pacote GT06, valida, disseca e delega a ação.
    Recebe o dev_id da sessão (se já conhecido).
    Retorna uma tupla: (pacote_de_resposta, dev_id_extraido_do_login)
    """
    # Validação Mínima de Tamanho
    if len(packet_body) < 6:
        logger.warning(f"Pacote GT06 recebido muito curto para processar: {packet_body.hex()}")
        return None, None

    # CRC
    data_to_check = packet_body[:-2]
    received_crc = struct.unpack('>H', packet_body[-2:])[0]
    calculated_crc = utils.crc_itu(data_to_check)

    if received_crc != calculated_crc:
        logger.warning(f"Checksum GT06 inválido! pacote={packet_body.hex()}, crc_recebido={hex(received_crc)}, crc_calculado={hex(calculated_crc)}")
        return None, None
    
    protocol_number = packet_body[1]
    serial_number = struct.unpack('>H', packet_body[-4:-2])[0]
    content_body = packet_body[2:-4]
    
    response_packet = None
    newly_logged_in_dev_id = None

    if protocol_number == 0x01: # Pacote de Login
        imei_bytes = content_body
        newly_logged_in_dev_id = imei_bytes.hex()
        response_packet = builder.build_generic_response(protocol_number, serial_number)
    
    elif protocol_number in [0x12, 0x22, 0xA0, 0x32]: # Pacotes de Localização
        if dev_id_str:
            mapper.handle_location_packet(dev_id_str, serial_number, content_body)
        else:
            logger.warning(f"Pacote de localização GT06 recebido antes do login. Ignorando. pacote={packet_body.hex()}")
        response_packet = None

    elif protocol_number == 0x13: # Pacote de Heartbeat/Status
        if dev_id_str:
            mapper.handle_heartbeat_packet(dev_id_str, serial_number, content_body)
        else:
            logger.warning(f"Pacote de heartbeat GT06 recebido antes do login. Ignorando. pacote={packet_body.hex()}")
        response_packet = builder.build_generic_response(protocol_number, serial_number)

    elif protocol_number == 0x16: # Pacote de Alarme
        if dev_id_str:
            mapper.handle_alarm_packet(dev_id_str, serial_number, content_body)
        else:
            logger.warning(f"Pacote de alarme GT06 recebido antes do login. Ignorando. pacote={packet_body.hex()}")
        response_packet = builder.build_generic_response(protocol_number, serial_number)
        
    else:
        logger.warning(f"Protocolo GT06 não mapeado: {hex(protocol_number)} device_id={dev_id_str}")
        response_packet = builder.build_generic_response(protocol_number, serial_number)

    return (response_packet, newly_logged_in_dev_id)