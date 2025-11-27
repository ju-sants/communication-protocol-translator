import requests

from app.config.settings import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

HEADERS = {
    'accept': 'application/json, text/plain, */*',
    'accept-language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
    "origin": settings.API_ORIGIN,
    'priority': 'u=1, i',
    "referer": settings.API_REFERER,
    'sec-ch-ua': '"Not(A:Brand";v="99", "Opera GX";v="118", "Chromium";v="133"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-site',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 OPR/118.0.0.0',
    "x-token": settings.API_X_TOKEN

}

def search_vehicles(search_term):
        
        URL = f"{settings.API_BASE_URL}/manager/vehicles"
        PARAMS = {
            "items_per_page": 50,
            "paginate": 1,
            "current_page": 1,
            "sort_by_field": "owner_name",
            "sort_direction": "asc",
            "all": search_term,
        }

        try:
            response = requests.get(URL, headers=HEADERS, params=PARAMS, timeout=60)
            response.raise_for_status()
            data = response.json()

            data_v = data.get('data', [])
            return data_v
                    
        except requests.exceptions.HTTPError as http_err:
            logger.error(f"Erro HTTP ao buscar dados: {http_err}")
            logger.error(f"Detalhes: {response.text}")
            return []
        
        except requests.exceptions.RequestException as req_err:
            logger.error(f"Erro de requisição ao buscar dados: {req_err}")
            return []
        
        except ValueError as json_err: # Trata erro de decodificação do JSON
            logger.error(f"Erro ao decodificar JSON da resposta da API: {json_err}")
            logger.error(f"Conteúdo da resposta: {response.text if 'response' in locals() else 'Não disponível'}")
            return []

def get_vehicle_data(vehicle_id):
    url = f"{settings.API_BASE_URL}/position/last"
    params = {
        "vehicle_id": vehicle_id
    }

    response = requests.get(url, headers=HEADERS, params=params)

    if response.status_code == 200:
        return response.json()
    else:
       return {}
    

def get_vehicle_data_from_tracker_id(dev_id: str):
    dev_id_norm = str(dev_id).lstrip("0")

    search = search_vehicles(dev_id_norm)
    if not search:
        logger.error(f"Não foi possível realizar uma busca com o dev_id={dev_id}")
        return {}
        
    vehicle_id = None
    if len(search) == 1: vehicle_id = search[0].get("id")
    else:
        for item in search:
            imei = str(item.get("imei")).lstrip("0")
            if imei == dev_id_norm:
                vehicle_id = item.get("id")
    
    if not vehicle_id:
        logger.error(f"As buscas não tiveram nenhum resultado compatível com o dev_id={dev_id}, search={search}")
        return {}

    vehicle_data = get_vehicle_data(vehicle_id)

    if not vehicle_data:
        logger.error(f"Foi encontrado um resultado na busca, porém ao tentar obter os dados do veículo houve falha o dev_id={dev_id}")
        return {}

    return vehicle_data
