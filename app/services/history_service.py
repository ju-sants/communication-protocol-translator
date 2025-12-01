import json
import zlib
from app.services.redis_service import get_redis

redis_client = get_redis(decode_responses=False)
HISTORY_LIMIT = 10000  # Limite de entradas no histórico por dispositivo

def add_packet_to_history(dev_id: str, raw_packet_hex: str, translated_packet: str):
    """
    Adiciona um par de pacotes (raw e traduzido) ao histórico de um dispositivo no Redis.
    O histórico é armazenado como uma lista JSON comprimida com zlib.
    """
    try:
        history_key = f"history:{dev_id}"
        packet_pair = {
            "raw_packet": raw_packet_hex,
            "translated_packet": translated_packet
        }

        # Recupera o histórico existente
        compressed_history = redis_client.get(history_key)
        if compressed_history:
            decompressed_history = zlib.decompress(compressed_history)
            history = json.loads(decompressed_history.decode('utf-8'))
        else:
            history = []

        # Adiciona o novo pacote e mantém o limite
        history.insert(0, packet_pair)
        history = history[:HISTORY_LIMIT]

        # Comprime e armazena o histórico atualizado
        updated_history_json = json.dumps(history).encode('utf-8')
        compressed_updated_history = zlib.compress(updated_history_json)
        redis_client.set(history_key, compressed_updated_history)

    except Exception as e:
        print(f"Erro ao adicionar pacote ao histórico para {dev_id}: {e}")

def get_packet_history(dev_id: str, return_compressed: bool = False) -> list:
    """
    Recupera o histórico de pacotes para um dispositivo do Redis,
    descomprimindo-o de zlib.
    """
    try:
        history_key = f"history:{dev_id}"
        compressed_history = redis_client.get(history_key)
        if compressed_history:
            if return_compressed:
                return compressed_history
            
            decompressed_history = zlib.decompress(compressed_history)
            history = json.loads(decompressed_history.decode('utf-8'))
            return history
        return []
    except Exception as e:
        print(f"Erro ao recuperar histórico para {dev_id}: {e}")
        return []
