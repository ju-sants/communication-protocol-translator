from . import mapper
from app.src.session.output_sessions_manager import send_to_main_server

def process_packet(data: bytes):
    hybrid_gsm_dev_id, last_hybrid_location, last_serial = mapper.handle_satelite_data(data)

    send_to_main_server(hybrid_gsm_dev_id, last_hybrid_location, last_serial, data.decode("utf-8"), "SATELLITAL")
