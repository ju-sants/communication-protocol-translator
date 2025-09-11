import struct

from app.core.logger import get_logger
from . import utils
from app.src.protocols.session_manager import tracker_sessions_manager
from app.services.redis_service import get_redis

redis_client = get_redis()
logger = get_logger(__name__)


def build_generic_response(protocol_number: str, serial_number: int):
    """
    Constrói uma resposta genérica (ACK) para o dispositivo VL01.
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
    Cria comandos no padrão VL01 para envio ao dispositivo
    """

    protocol_number = 0x80
    server_flag = b'\x00\x00\x00\x01'
    command_bytes = command_content_str.encode("ascii")
    language = b'\x00\x02'

    m_len = len(command_bytes)

    command_length = 4 + m_len + 2

    packet_length = m_len + 12

    # Data for CRC is from Packet Length field to Serial Number field inclusive
    data_for_crc = (
        struct.pack(">B", packet_length) +
        struct.pack(">B", protocol_number) +
        struct.pack(">B", command_length) +
        server_flag +
        command_bytes +
        language +
        struct.pack(">H", serial_number)
    )

    crc = utils.crc_itu(data_for_crc)

    command_packet = (
        b'\x78\x78' +
        data_for_crc +
        struct.pack(">H", crc) +
        b'\x0d\x0a'
        )

    logger.info(f"Construído comando VL01: {command_packet.hex()}")

    return command_packet

def process_suntech_command(command: bytes, dev_id: str, serial: int):
    logger.info(f"Iniciando tradução de comando Suntech para VL01 device_id={dev_id}, comando={command}")

    command_str = command.decode("ascii", errors="ignore")
    parts = command_str.split(';')

    if len(parts) < 4:
        logger.warning(f"Comando Suntech mal formatado, ignorando. comando={command}")
        return

    command_key = f"{parts[0]};{';'.join(parts[2:])}"

    command_mapping = {
        "CMD;04;01": "RELAY,1#",
        "CMD;04;02": "RELAY,0#",
        "CMD;03;01": "GPRS,GET,LOCATION#",
    }

    vl01_text_command = None
    if command_key.startswith("CMD;05;03"):
        meters = command_key.split(";")[-1]
        if not meters.isdigit():
            logger.info(f"Comando com metragem incorreta: {command_key}")
            return
        
        # kilometers = int(meters) / 1000

        # vl01_text_command = f"MILEAGE,ON,{kilometers}#"

        # NO MOMENTO ESTAMOS USANDO HODOMETRO GERENCIADO PELO PRÓPRIO SERVIDOR
        redis_client.hset(dev_id, "odometer", meters)

    else:
        vl01_text_command = command_mapping.get(command_key)

    if not vl01_text_command:
        logger.warning(f"Nenhum mapeamento VL01 encontrado para o comando Suntech comando={command_key}")
        return

    vl01_binary_command = build_command(vl01_text_command, serial)

    tracker_socket = tracker_sessions_manager.get_tracker_client_socket(dev_id)
    if tracker_socket:
        try:
            tracker_socket.sendall(vl01_binary_command)
            logger.info(f"Comando VL01 enviado com sucesso device_id={dev_id}, comando_hex={vl01_binary_command.hex()}")
        except Exception:
            logger.exception(f"Falha ao enviar comando para o rastreador VL01 device_id={dev_id}")
    else:
        logger.warning(f"Rastreador VL01 não está conectado. Impossível enviar comando. device_id={dev_id}")
