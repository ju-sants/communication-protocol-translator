import struct

from app.core.logger import get_logger
from .. import utils
from app.src.session.input_sessions_manager import input_sessions_manager

logger = get_logger(__name__)

def build_generic_response(protocol_number: str, serial_number: int):
    """
    Constrói uma resposta genérica (ACK) para o dispositivo J16X-J16.
    """

    # Conteúdo
    packet_content = struct.pack(">BH", protocol_number, serial_number)

    packet_length = len(packet_content) + 2

    data_for_crc = struct.pack(">B", packet_length) + packet_content

    crc = utils.crc_itu(data_for_crc)

    response_packet = (
        b"\x78\x78" +
        data_for_crc + 
        struct.pack(">H", crc) +
        b"\x0d\x0a"
    )

    logger.debug(f"Construido pacote de resposta GTO6: {response_packet.hex()}")

    return response_packet

def build_command(command_content_str: str, serial_number: int):
    """
    Cria comandos no padrão J16X-J16 para envio ao dispositivo
    """

    protocol_number = 0x80

    server_flag = b'\x00\x00\x00\x01'
    command_bytes = command_content_str.encode("ascii")

    command_body = server_flag + command_bytes

    command_length = len(command_body)

    packet_length = 1 + 1 + command_length + 2 + 2

    data_for_crc = (
        struct.pack(">B", packet_length) +
        struct.pack(">B", protocol_number) +
        struct.pack(">B", command_length) +
        command_body + 
        struct.pack(">H", serial_number)
    )

    crc = utils.crc_itu(data_for_crc)

    command_packet = (
        b'\x78\x78' +
        data_for_crc + 
        struct.pack(">H", crc) +
        b'\x0d\x0a'
        )
    
    logger.info(f"Construído comando J16X-J16: {command_packet.hex()}")

    return command_packet

def process_command(dev_id: str, serial: int, universal_command: str):
    logger.info(f"Iniciando tradução de comando Universal para J16X-J16 device_id={dev_id}, comando={universal_command}")

    command_mapping = {
        "OUTPUT ON": "RELAY,1#",
        "OUTPUT OFF": "RELAY,0#",
        "PING": "GPRS,GET,LOCATION#",
    }

    j16x_text_command = None
    if universal_command.startswith("HODOMETRO"):
        meters = universal_command.split(":")[-1]
        if not meters.isdigit():
            logger.info(f"Comando com metragem incorreta: {universal_command}")
            return
        
        kilometers = int(meters) / 1000

        j16x_text_command = f"MILEAGE={kilometers}#"
    
    else:
        j16x_text_command = command_mapping.get(universal_command)

    if not j16x_text_command:
        logger.warning(f"Nenhum mapeamento J16X-J16 encontrado para o comando Universal comando={universal_command}")
        return

    j16x_binary_command = build_command(j16x_text_command, serial)

    tracker_socket = input_sessions_manager.get_tracker_client_socket(dev_id)
    if tracker_socket:
        try:
            tracker_socket.sendall(j16x_binary_command)
            logger.info(f"Comando J16X-J16 enviado com sucesso device_id={dev_id}, comando_hex={j16x_binary_command.hex()}")
        except Exception:
            logger.exception(f"Falha ao enviar comando para o rastreador J16X-J16 device_id={dev_id}")
    else:
        logger.warning(f"Rastreador J16X-J16 não está conectado. Impossível enviar comando. device_id={dev_id}")
