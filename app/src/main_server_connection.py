import socket
import threading

from app.core.logger import get_logger
from app.config.settings import settings
from app.src.suntech_utils import build_suntech_mnt_packet

logger = get_logger(__name__)

active_connections = {}
connection_lock = threading.Lock()

def send_to_main_server(dev_id_str: str, packet_data: bytes):
    """Envia os dados convertidos para o servidor principal."""
    host = settings.MAIN_SERVER_HOST
    port = settings.MAIN_SERVER_PORT
    print(f"Enviando pacote de {len(packet_data)} bytes para {host}:{port}")
    logger.info(f"Encaminhando pacote de {len(packet_data)} bytes para o servidor principal em {host}:{port}")
    
    # # Linha temporária para desativar o envio
    # logger.info("Temporariamente desativado o envio para o servidor principal")
    # return

    s = None
    is_new_connection = False
    packet_data = packet_data + b'\r'

    with connection_lock:
        if dev_id_str in active_connections:
            s = active_connections[dev_id_str]
            logger.debug(f"Reutilizando conexão existente para {host}:{port}")
    
    if s is None:
        logger.info(f"Criando nova conexão para {host}:{port}")
        try:
            s = socket.create_connection((host, port), timeout=5)
            is_new_connection = True
            with connection_lock:
                active_connections[dev_id_str] = s
            logger.debug(f"Nova conexão criada para {host}:{port}")
        except Exception:
            logger.exception("Falha ao criar nova conexão com o servidor principal", device_id=dev_id_str)
            return

    try:
        if is_new_connection:
            # Envia o pacote de monitoramento para o servidor principal
            monitor_packet = build_suntech_mnt_packet(dev_id_str)
            s.sendall(monitor_packet)
            logger.info(f"Pacote de monitoramento enviado para {host}:{port}")

        logger.info(f"Enviando pacote de {len(packet_data)} bytes para {host}:{port}")
        s.sendall(packet_data)

        resposta = None
        try:
            resposta = s.recv(1024)
        except TimeoutError:
            logger.warning(f"Nenhuma resposta recebida do servidor Suntech.")
        
        if resposta:
            logger.info(f"RESPOSTA RECEBIDA DO SERVIDOR SUNTECH resposta_raw={resposta}, resposta_texto={resposta.decode('ascii', errors='ignore')}")
    
    except Exception:
        logger.exception(f"Falha ao enviar dados para o servidor principal para {dev_id_str} em {host}:{port}")

        with connection_lock:
            if dev_id_str in active_connections:
                del active_connections[dev_id_str]