import struct
from app.core.logger import get_logger

from .processor import crc16_itu


logger = get_logger(__name__)


def build_generic_response(protocol_number: str, serial_number: int):
    """
    Constrói uma resposta genérica (ACK) para o dispositivo GT06.
    """

    # Conteúdo
    packet_content = struct.pack(">BH", protocol_number, serial_number)

    packet_length = len(packet_content) + 2

    data_for_crc = struct.pack(">B", packet_length) + packet_content

    crc = crc16_itu(data_for_crc)

    response_packet = (
        b"\x78\x78" +
        data_for_crc + 
        struct.pack(">B", crc) +
        b"\x0d\x0a"
    )

    logger.debug(f"Construido pacote de resposta GTO6: {response_packet.hex()}")

    return response_packet

def build_command(command_content_str: str, serial_number: int):
    """
    Cria comandos no padrão GT06 para envio ao dispositivo
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

    crc = crc16_itu(data_for_crc)

    command_packet = (
        b'\x78\x78' +
        data_for_crc + 
        struct.pack(">H", crc) +
        b'\x0d\x0a'
        )
    
    logger.info(f"Construído comando GT06: {command_packet.hex()}")

    return command_packet