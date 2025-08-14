import struct
from . import builder, mapper

from app.core.logger import get_logger

logger = get_logger(__name__)

def process_packet(unescaped_packet: bytes) -> bytes | None:
    """Extrai dados do pacote, envia para o mapper e retorna a resposta do builder."""
    header_bytes = unescaped_packet[:12]
    msg_id, _, terminal_phone_bcd, serial = struct.unpack('>HH6sH', header_bytes)
    body = unescaped_packet[12:-1]
    dev_id_str = terminal_phone_bcd.hex()

    logger.debug("Processando pacote JT/T 808", device_id=dev_id_str, msg_id=hex(msg_id))

    # Envia os dados para o mapper, que fará a tradução e encaminhamento
    mapper.map_and_forward(dev_id_str, serial, msg_id, body, unescaped_packet.hex())

    # Constrói e retorna a resposta ACK para o dispositivo
    return builder.build_ack_response(terminal_phone_bcd, serial, msg_id, result=0)