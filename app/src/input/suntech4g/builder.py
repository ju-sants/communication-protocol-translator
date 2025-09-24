from app.core.logger import get_logger

logger = get_logger(__name__)

def build_command(dev_id: str, command: str) -> bytes:
    """
    Builds a command string to be sent to a Suntech device.
    """
    logger.info(f"Building command for dev_id={dev_id}, command={command}")

    command_mapping = {
        "OUTPUT ON": f"CMD;{dev_id};04;01",
        "OUTPUT OFF": f"CMD;{dev_id};04;02",
        "PING": f"CMD;{dev_id};03;01",
    }

    command_str = command_mapping.get(command)
    
    if command and command.startswith("HODOMETRO"):
        try:
            hodometro_value = command.split(":")[1]
            command_str = f"CMD;{dev_id};05;03;{hodometro_value}"
        except IndexError:
            logger.error("HODOMETRO command is not correctly formatted")
            return None


    if command_str:
        logger.info(f"Built command: {command_str}")
        return command_str.encode('ascii') + b'\r'
    else:
        logger.warning(f"Unknown command: {command}")
        return None