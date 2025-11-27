import requests

from app.core.logger import get_logger
from app.services.extrernal_api_service import get_vehicle_data_from_tracker_id

logger = get_logger(__name__)

def get_odometer_from_previous_host(esn):
    """
    Função que performa uma ação de negócio, onde obtemos o valor de hodometro do antigo host do dispositivo.
    """

    vehicle_data = get_vehicle_data_from_tracker_id(esn)
    if not vehicle_data:
        logger.error("Erro ao obter os dados do veículo, a fim de obter seu hodômetro.")
        return
    
    lastPosition = vehicle_data.get("lastPosition")
    if not lastPosition:
        logger.error("Dados do veículo sem informações da última posição, retornando.")
        return
    
    odometer = lastPosition.get("odometer")

    return odometer
