from . import mapper
from .. import utils
from app.src.session.output_sessions_manager import send_to_main_server

def process_packet(data: bytes):
    output_dev_id, last_merged_location, ign_alert_packet_data, last_serial = mapper.handle_satelite_data(data)

    if last_merged_location:
        utils.log_mapped_packet(last_merged_location, "SATELLITAL")
        send_to_main_server(output_dev_id, last_merged_location, last_serial, data.decode("utf-8"), "SATELLITAL")
        
    if ign_alert_packet_data and ign_alert_packet_data.get("universal_alert_id"):
        send_to_main_server(output_dev_id, ign_alert_packet_data, last_serial, data.decode("utf-8"), "SATELLITAL", "alert", True)