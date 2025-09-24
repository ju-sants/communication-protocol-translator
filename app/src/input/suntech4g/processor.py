from app.core.logger import get_logger
from app.services.redis_service import get_redis
from . import mapper
from .. import utils
from app.src.session.output_sessions_manager import send_to_main_server

logger = get_logger(__name__)
redis_client = get_redis()

def process_packet(packet_str: str):
    """
    Processes a raw packet string from a Suntech device.
    """
    fields = packet_str.split(';')
    if not fields:
        logger.warning("Received an empty packet.")
        return None
        
    hdr = fields[0]
    
    dev_id = fields[2] if "Res" in packet_str and len(fields) >= 3 else fields[1] if len(fields) >= 2 else None
    if not dev_id or not dev_id.isdigit:
        logger.warning(f"Dev id {dev_id} encontrado no pacote {packet_str} não é um ID válido.")

    logger.info(f"Processing Suntech packet: {packet_str} dev_id={dev_id}")

    if not dev_id:
        logger.warning(f"Could not extract dev_id from packet: {packet_str}")
        return None
        
    logger.info(f"Processing packet from device: {dev_id}")

    packet_data = {}
    type = ""
    serial = 0
    if hdr == "STT":
        logger.info("Location packet (STT) received.")
        packet_data, serial = mapper.handle_stt_packet(fields)
        type = "location"
    else:
        print(packet_str)
        return
    
    if hdr == "ALT":
        logger.info("Alert packet (ALT) received.")
        packet_data = mapper.handle_alt_packet(fields)
        type = "alert"

    elif hdr == "EMG":
        logger.info("Emergency packet (EMG) received.")
        packet_data = mapper.handle_emg_packet(fields)
        type = "location"

    elif hdr == "EVT":
        logger.info("Event packet (EVT) received.")
        packet_data = mapper.handle_evt_packet(fields)
        type = "alert"

    elif hdr == "CMD":
        logger.info("Command response packet (CMD) received.")
        packet_data = mapper.handle_reply_packet(fields)
        type = "command_reply"

    elif hdr == "ALV":
        logger.info("Keep-alive packet (ALV) received.")
        type = "heartbeat"
    
    if packet_data or type == "heartbeat":
        if packet_data:
            utils.log_mapped_packet(packet_data, "SUNTECH2G")
        
        if not serial:
            serial = redis_client.hget(f"tracker:{dev_id}", "last_serial") or 0
            serial = int(serial)

        if type == "heartbeat":
            send_to_main_server(dev_id, serial=serial, raw_packet_hex=packet_str, original_protocol="suntech2g", type=type)
        else:
            send_to_main_server(dev_id, packet_data=packet_data, serial=serial, raw_packet_hex=packet_str, original_protocol="suntech2g", type=type)

    return dev_id