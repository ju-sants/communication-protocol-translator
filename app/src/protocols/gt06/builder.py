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