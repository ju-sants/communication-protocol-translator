# app/services/history_service.py
import json
from app.services.redis_service import get_redis

redis_client = get_redis()
HISTORY_LIMIT = 50  # Limite de entradas no histórico por dispositivo

def add_packet_to_history(dev_id: str, raw_packet_hex: str, suntech_packet: str):
    """
    Adiciona um par de pacotes (raw e suntech) ao histórico de um dispositivo no Redis.
    Usa uma lista do Redis (LPUSH) e apara para manter um tamanho fixo (LTRIM).
    """
    try:
        history_key = f"history:{dev_id}"
        packet_pair = {
            "raw_packet": raw_packet_hex,
            "suntech_packet": suntech_packet
        }
        # Adiciona o novo par no início da lista
        redis_client.lpush(history_key, json.dumps(packet_pair))
        # Mantém a lista com no máximo HISTORY_LIMIT itens
        redis_client.ltrim(history_key, 0, HISTORY_LIMIT - 1)
    except Exception as e:
        # Logar o erro seria ideal aqui
        print(f"Erro ao adicionar pacote ao histórico para {dev_id}: {e}")

def get_packet_history(dev_id: str) -> list:
    """
    Recupera o histórico de pacotes para um dispositivo do Redis.
    """
    try:
        history_key = f"history:{dev_id}"
        # Pega todos os itens da lista
        history_json = redis_client.lrange(history_key, 0, -1)
        # Decodifica de JSON string para dict
        history = [json.loads(item) for item in history_json]
        return history
    except Exception as e:
        print(f"Erro ao recuperar histórico para {dev_id}: {e}")
        return []
