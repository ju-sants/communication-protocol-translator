from app.core.logger import get_logger
from app.src.session.input_sessions_manager import input_sessions_manager

logger = get_logger(__name__)

def process_command(dev_id: str, serial: str, universal_command: str):
    logger.info(f"Iniciando tradução de comando Universal para NT40 device_id={dev_id}, comando={universal_command}")

    command_mapping = {
        "OUTPUT ON": f"CMD;{dev_id};04;01",
        "OUTPUT OFF": f"CMD;{dev_id};04;02",
        "PING": f"CMD;{dev_id};03;01",
    }

    suntech4g_command = None
    if universal_command.startswith("HODOMETRO"):
        meters = universal_command.split(":")[-1]
        if not meters.isdigit():
            logger.info(f"Comando com metragem incorreta: {universal_command}")
            return
        
        suntech4g_command = f"CMD;{dev_id};05;03;{meters}"
    
    else:
        suntech4g_command = command_mapping.get(universal_command)

    if not suntech4g_command:
        logger.warning(f"Nenhum mapeamento Suntech4g encontrado para o comando Universal comando={universal_command}")
        return

    tracker_socket = input_sessions_manager.get_tracker_client_socket(dev_id)
    if tracker_socket:
        try:
            tracker_socket.sendall(suntech4g_command.encode('ascii'))
            logger.info(f"Comando Suntech4g enviado com sucesso device_id={dev_id}, comando='{suntech4g_command}'")
        except Exception as e:
            logger.error(f"Erro ao enviar comando Suntech4g device_id={dev_id}, comando='{suntech4g_command}': {e}")
    else:
        logger.warning(f"Nenhum socket encontrado para o dispositivo Suntech4g device_id={dev_id}. Comando não enviado.")