from app.src.session.input_sessions_manager import input_sessions_manager
from app.core.logger import get_logger

logger = get_logger(__name__)

def build_generic_response():
    return b"\x00"

def process_command(dev_id: str, _, universal_command: str):
    logger.info(f"Iniciando tradução de comando Universal para GP900M device_id={dev_id}, comando={universal_command}.")

    command_mapping = {
        "OUTPUT ON": "AT+XRLY=1",
        "OUTPUT OFF": "AT+XRLY=0",
    }

    gp900m_text_command = None
    if universal_command.startswith("HODOMETRO"):
        meters = universal_command.split(":")[-1]
        if not meters.isdigit():
            logger.info(f"Comando com metragem incorreta: {universal_command}.")
            return
        
        gp900m_text_command = f"AT+XVO={meters}"
    
    else:
        gp900m_text_command = command_mapping.get(universal_command)

    if not gp900m_text_command:
        logger.warning(f"Nenhum mapeamento GP900M encontrado para o comando Universal comando={universal_command}")
        return

    gp900m_binary_command = gp900m_text_command.encode("ASCII")

    tracker_socket = input_sessions_manager.get_tracker_client_socket(dev_id)
    if tracker_socket:
        try:
            tracker_socket.sendall(gp900m_binary_command)
            logger.info(f"Comando GP900M enviado com sucesso device_id={dev_id}, comando_hex={gp900m_binary_command.hex()}")
        except Exception:
            logger.exception(f"Falha ao enviar comando para o rastreador GP900M device_id={dev_id}")
    else:
        logger.warning(f"Rastreador GP900M não está conectado. Impossível enviar comando. device_id={dev_id}")
