from datetime import datetime, timezone, timedelta
from dateutil import parser

from app.core.logger import get_logger
from app.services import extrernal_api_service

logger = get_logger(__name__)

def is_signal_fail(timestamp_str: str):
    timestamp = parser.parse(timestamp_str, yearfirst=True)
    timestamp = timestamp.replace(tzinfo=timezone.utc)

    if datetime.now(timezone.utc) - timestamp >= timedelta(hours=24):
        return True
    else:
        return False

def get_manufacturer_id(input_protocol: str):

    if input_protocol in ("nt40", "j16w", "j16x-j16", "j16x-j16", "vl01", "vl03"):
        manufacturer_id = 2
    elif input_protocol == "suntech2g":
        manufacturer_id = 1
    elif input_protocol == "suntech4g":
        manufacturer_id = 18
    elif input_protocol == "gp900m":
        manufacturer_id = 15
    elif input_protocol == "satellital":
        manufacturer_id = 10

    else: 
        logger.error(f"Erro ao tentar encontrar o manufacturer id para {input_protocol}")
        return None
    
    return manufacturer_id

def is_communicating_on_principal_server(tracker_id: str):
    """Função usada para verificar se o dispositivo está comunicando no servidor principal"""

    tracker_id_norm = str(tracker_id).lstrip("0")[-15:]

    vehicle_data = extrernal_api_service.get_vehicle_data_from_tracker_id(tracker_id_norm)
    if not vehicle_data:
        logger.warning(f"Não foi possível indicar se o {tracker_id} está comunicando no server principal pois não foram encontrados dados.")
        return False
    
    lastPosition = vehicle_data.get("lastPosition", {})
    if not lastPosition:
        logger.warning(f"Não foi possível indicar se o {tracker_id} está comunicando no server principal pois não há dados da última posição.")
        return False
    
    timestamp = lastPosition.get("datetime", "")
    if not timestamp:
        logger.warning(f"Não foi possível indicar se o {tracker_id} está comunicando no server principal não há timestamp nos dados da ultima localização")
        return False
    
    if not is_signal_fail(timestamp):
        logger.info(f"Rastreador {tracker_id} encontrado no servidor principal e comunicando: {timestamp}")
        return True
    
    logger.warning(f"Não foi possível indicar se o {tracker_id} está comunicando no server principal, pois a sua comunicação é de mais de um dia.")
    return None