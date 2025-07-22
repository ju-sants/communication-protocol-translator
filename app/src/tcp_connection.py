import socket
from app.config.settings import settings

def send_to_main_server(packet_data: bytes):
    """Envia os dados convertidos para o servidor principal."""
    print(f"[*] Encaminhando {len(packet_data)} bytes para {settings.MAIN_SERVER_HOST}:{settings.MAIN_SERVER_PORT}")
    try:
        with socket.create_connection((settings.MAIN_SERVER_HOST, settings.MAIN_SERVER_PORT), timeout=5) as s:
            s.sendall(packet_data)
    except Exception as e:
        print(f"[!] Falha ao encaminhar dados para o servidor principal: {e}")