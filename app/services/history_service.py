import json
import zlib
import time
import multiprocessing
from diskcache import Cache

from app.services.redis_service import get_redis
from app.core.logger import get_logger
from app.config.settings import settings

logger = get_logger(__name__)
redis_client = get_redis()

def add_packet_to_history(dev_id: str, raw_packet_hex: str, translated_packet: str):
    """
    Função leve: Apenas coloca os dados na fila para processamento assíncrono.
    O retorno é imediato, liberando a API/Thread principal.
    """
    try:
        payload = {
            "dev_id": dev_id,
            "packet": {
                "raw_packet": raw_packet_hex,
                "translated_packet": translated_packet,
                "timestamp": time.time()
            }
        }
        redis_client.rpush(settings.HISTORY_SERVICE_QUEUE, json.dumps(payload))

    except Exception as e:
        logger.info(f"Erro ao enfileirar pacote para {dev_id}: {e}")

def get_packet_history(dev_id: str, return_compressed: bool = False) -> list:
    """
    Mantém a funcionalidade de leitura.
    Nota: Dados que ainda estão no buffer de disco (diskcache) e não foram para o Redis
    não aparecerão aqui. Se consistência em tempo real for crítica,
    seria necessário ler do Redis E do Diskcache e mesclar na leitura.
    """
    try:
        # Fazendo merge dos possíveis pacotes salvos no disco
        _merge_disk_to_redis(dev_id)

        # Obtendo histórico salvo no redis
        redis_client = get_redis(decode_responses=False)
        history_key = f"history:{dev_id}"
        compressed_history = redis_client.get(history_key)
        
        # Retornando os dados comprimidos ou descomprimidos
        if compressed_history:
            if return_compressed:
                return compressed_history
            
            try:
                decompressed_history = zlib.decompress(compressed_history)
                history = json.loads(decompressed_history.decode('utf-8'))
            except Exception as e:
                logger.error(f"Houve um erro ao tentar descomprimir. Descartando histórico.")
                history = []

            return history
        
        return []
    
    except Exception as e:
        logger.info(f"Erro ao recuperar histórico para {dev_id}: {e}")
        return []

def _merge_disk_to_redis(dev_id: str, new_packets: list = None) -> bool:
    """
    Faz o merge dos dados em disco para o redis, lida com dados não enviados nos parâmetros
    """

    history_key = f"history:{dev_id}"
    
    try:
        # Recupera histórico atual do Redis
        redis_client = get_redis(decode_responses=False)
        compressed_history = redis_client.get(history_key)
        if compressed_history:
            try:
                decompressed_history = zlib.decompress(compressed_history)
                current_history = json.loads(decompressed_history.decode('utf-8'))

            except Exception as e:
                logger.error(f"Houve um erro ao tentar descomprimir. Descartando histórico.")
                current_history = []

        else:
            current_history = []

        # Verificando presença de new_packets
        if not new_packets:
            cache = Cache(settings.CACHE_DIR)

            buffer_key = f"buffer:{dev_id}"
            new_packets = cache.get(buffer_key, default=[])

            if not new_packets:
                logger.warning("Não a pacotes no disco para serem mesclados.")
                return False
            
            cache.delete(buffer_key)

        # Merging
        new_packets.reverse() 
        full_history = new_packets + current_history
        
        # Aplica o limite
        full_history = full_history[:settings.HISTORY_LIMIT]

        # Comprime e Salva no Redis
        updated_history_json = json.dumps(full_history).encode('utf-8')
        compressed_updated_history = zlib.compress(updated_history_json)
        redis_client.set(history_key, compressed_updated_history)
        
        return True
    except Exception as e:
        logger.error(f"Erro no merge Redis para {dev_id}: {e}")
        return False

def history_worker_process():

    with logger.contextualize(log_label="HISTORY WORKER"):
        logger.info("--- Iniciando Processo Worker de Histórico ---")
        
        cache = Cache(settings.CACHE_DIR)
        redis_client = get_redis(decode_responses=False)
        
        while True:
            try:
                item = redis_client.blpop(settings.HISTORY_SERVICE_QUEUE, timeout=5)
                
                if item:
                    item = json.loads(item[1])
                    dev_id = item['dev_id']
                    packet_data = item['packet']

                    # Obtendo os pacotes já salvos em disco, ou criando uma nova lista
                    buffer_key = f"buffer:{dev_id}"
                    
                    current_buffer = cache.get(buffer_key, default=[])
                    current_buffer.append(packet_data)
                    
                    # Verifica se atingiu o limite
                    if len(current_buffer) >= settings.DISK_BATCH_SIZE:
                        logger.info(f"Batch atingido para {dev_id} ({len(current_buffer)} itens). Iniciando merge...")
                        
                        success = _merge_disk_to_redis(dev_id, current_buffer)
                        
                        if success:
                            cache.delete(buffer_key)
                        else:
                            # se houve erros salvamos o buffer e tentamos novamente depois
                            cache.set(buffer_key, current_buffer)
                    else:
                        # Caso não atingiu o limite, salvamos o buffer
                        cache.set(buffer_key, current_buffer)

            except Exception as e:
                import traceback
                traceback.print_exc()
                logger.info(f"Erro crítico no loop: {e}")
                time.sleep(1) 

def start_history_service():
    p = multiprocessing.Process(target=history_worker_process)
    p.daemon = True
    p.start()
    return p