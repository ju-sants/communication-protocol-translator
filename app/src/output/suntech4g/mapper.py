from app.core.logger import get_logger

logger = get_logger(__name__)

def map_to_universal_command(dev_id: str, command: bytes):
    logger.info(f"Iniciando tradução de comando Suntech para Comando Universal device_id={dev_id}, comando={command.hex()}")

    command_str = command.decode("ascii", errors="ignore")
    parts = command_str.split(';')

    if len(parts) < 4:
        logger.warning(f"Comando Suntech mal formatado, ignorando. comando={command}")
        return

    command_key = f"{parts[0]};{';'.join(parts[2:])}"

    command_mapping = {
        "CMD;04;01": "OUTPUT ON",
        "CMD;04;02": "OUTPUT OFF",
        "CMD;03;01": "PING",
    }

    if command_key.startswith("CMD;05;03"):
        meters = command_key.split(";")[-1]
        if not meters.isdigit():
            logger.info(f"Comando com metragem incorreta: {command_key}")
            return
        
        return f"HODOMETRO:{meters}"

    return command_mapping.get(command_key)