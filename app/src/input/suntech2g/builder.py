from app.core.logger import get_logger
from app.services.redis_service import get_redis
from app.src.session.input_sessions_manager import input_sessions_manager

logger = get_logger(__name__)
redis_client = get_redis()
def process_command(dev_id: str, serial: str, universal_command: str):
    logger.info(f"Iniciando tradução de comando Universal para NT40 device_id={dev_id}, comando={universal_command}")

    command_mapping = {
        "OUTPUT ON": "Enable1",
        "OUTPUT OFF": "Disable1",
        "PING": "StatusReq",
    }

    suntech2g_command = None
    if universal_command.startswith("HODOMETRO"):
        meters = universal_command.split(":")[-1]
        if not meters.isdigit():
            logger.info(f"Comando com metragem incorreta: {universal_command}")
            return
        
        suntech2g_command = f"SetOdometer={meters}"
    
    else:
        suntech2g_command = command_mapping.get(universal_command)

    if len(dev_id) <= 6:
        prefix = "SA200"
    else:
        prefix = "ST300"

    if len(dev_id) <= 6:
        fill = 6
    else:
        fill = 9

    suntech2g_complete_command = f"{prefix}CMD;{dev_id.zfill(fill)};02;{suntech2g_command}"

    if not suntech2g_command:
        logger.warning(f"Nenhum mapeamento Suntech2g encontrado para o comando Universal comando={universal_command}")
        return

    logger.info(f"Comando Suntech2g gerado com sucesso: {suntech2g_complete_command}")

    tracker_socket = input_sessions_manager.get_tracker_client_socket(dev_id)
    if tracker_socket:
        try:
            tracker_socket.sendall(suntech2g_complete_command.encode('ascii') + b"\r")
            logger.info(f"Comando Suntech2g enviado com sucesso device_id={dev_id}, comando='{suntech2g_complete_command}'")
        except Exception as e:
            logger.error(f"Erro ao enviar comando Suntech2g device_id={dev_id}, comando='{suntech2g_complete_command}': {e}")
    else:
        logger.warning(f"Nenhum socket encontrado para o dispositivo Suntech2g device_id={dev_id}. Comando não enviado.")