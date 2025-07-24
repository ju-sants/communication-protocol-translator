# main.py
import threading
import socket
import importlib
from app.config.settings import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

def start_listener(port: int, handler_func):
    try:
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind(('', port))
        server_socket.listen(10)
        logger.info(f"✅ Protocol listener iniciado com sucesso na porta {port}")

        while True:
            conn, addr = server_socket.accept()
            thread = threading.Thread(target=handler_func, args=(conn, addr), daemon=True)
            thread.start()
    except Exception as e:
        logger.critical(f"❌ Falha ao iniciar listener na porta {port}", error=e)


def main():
    logger.info("Iniciando Servidor Tradutor...")
    
    for protocol_name, config in settings.PROTOCOLS.items():
        try:
            port = config['port']
            module_path, func_name = config['handler_path'].rsplit('.', 1)
            
            # Importa dinamicamente a função de handler
            module = importlib.import_module(module_path)
            handler_function = getattr(module, func_name)
            
            listener_thread = threading.Thread(
                target=start_listener,
                args=(port, handler_function),
                daemon=True
            )
            listener_thread.start()
            logger.info(f"Thread para protocolo '{protocol_name}' iniciada.")
            
        except (ImportError, AttributeError) as e:
            logger.error(f"Não foi possível carregar o handler para o protocolo '{protocol_name}'", error=e)
        except KeyError as e:
            logger.error(f"Configuração inválida para o protocolo '{protocol_name}'", missing_key=str(e))

    # Mantém a thread principal viva
    try:
        while True:
            threading.Event().wait(60) # Espera para não consumir CPU
    except KeyboardInterrupt:
        logger.info("Servidor sendo desligado...")

if __name__ == "__main__":
    main()