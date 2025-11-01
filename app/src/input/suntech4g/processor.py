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
    ign_alert_packet_data = {}
    type = ""
    serial = 0
    if hdr == "STT":
        logger.info("Location packet (STT) received.")
        packet_data, ign_alert_packet_data, serial = mapper.handle_stt_packet(fields)
        type = "location"

    if hdr == "ALT":
        logger.info("Alert packet (ALT) received.")
        packet_data, ign_alert_packet_data = mapper.handle_alt_packet(fields)
        type = "alert"

    elif hdr == "RES":
        logger.info("Command response packet (CMD) received.")
        packet_data = mapper.handle_reply_packet(dev_id, fields)
        type = "command_reply"

    elif hdr == "ALV":
        logger.info("Keep-alive packet (ALV) received.")
        type = "heartbeat"
    
    if packet_data or type == "heartbeat":
        if packet_data:
            utils.log_mapped_packet(packet_data, "SUNTECH4G")
        
        if not serial:
            serial = redis_client.hget(f"tracker:{dev_id}", "last_serial") or 0
            serial = int(serial)

        if type == "heartbeat":
            send_to_main_server(dev_id, serial=serial, raw_packet_hex=packet_str, original_protocol="suntech4g", type=type)
        else:
            # Criando uma condição especial para o suntech4g: Quando tivermos pacotes do tipo de alerta, 
            # que geraram um pacote de "ign_alert_packet_data" com alerta 6533 ou 6534, encaramos ele como se fosse um pacote de localização.
            # Devido a regras internas de negócio.
            condition = not ign_alert_packet_data or not str(ign_alert_packet_data.get("universal_alert_id")) in ("6533", "6534") 
            send_to_main_server(dev_id, packet_data=packet_data, serial=serial, raw_packet_hex=packet_str, original_protocol="suntech4g", type=type if condition else "location")

    if ign_alert_packet_data and ign_alert_packet_data.get("universal_alert_id"):
        if not serial:
            serial = redis_client.hget(f"tracker:{dev_id}", "last_serial") or 0
            serial = int(serial)

        send_to_main_server(dev_id, packet_data=ign_alert_packet_data, serial=serial, raw_packet_hex=packet_str, original_protocol="suntech4g", type="alert")


    return dev_id