from app.core.logger import get_logger

logger = get_logger(__name__)

def map_to_universal_command(dev_id: str, command: bytes):
    logger.info(f"Iniciando tradução de comando GT06 para Comando Universal device_id={dev_id}, comando={command.hex()}")

    command_content = command[8:-8]
    command_key = command_content.decode("ascii", errors="ignore")

    logger.info(f"Comando GT06 traduzido para ASCII. command_bytes={command_content.hex()} command_ascii={command_key}")

    command_mapping = {
        "RELAY,1#": "OUTPUT ON",
        "DYD,000": "OUTPUT ON",
        "RELAY,0#": "OUTPUT OFF",
        "HFYD,000": "OUTPUT OFF",
        "GPRS,GET,LOCATION#": "PING",
    }

    if command_key.startswith("MILEAGE"):
        kilometers = command_key.split("ON,")[-1].replace("#", "")
        if not kilometers.isdigit():
            logger.info(f"Comando com metragem incorreta: {command_key}")
            return
        
        meters = int(kilometers) * 1000
        return f"HODOMETRO:{meters}"

    return command_mapping.get(command_key)