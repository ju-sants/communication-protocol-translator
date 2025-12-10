import threading
import socket
import importlib
import os
from simple_websocket_server import WebSocketServer
from dotenv import load_dotenv
load_dotenv()

from app.config.settings import settings
from app.core.logger import get_logger
from app.services import history_service

logger = get_logger(__name__)

def start_listener(port: int, handler_func):
    try:
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind(('', port))
        server_socket.listen(10000)
        logger.info(f"✅ Protocol listener iniciado com sucesso na porta {port}", log_label="SERVIDOR")

        while True:
            conn, addr = server_socket.accept()
            thread = threading.Thread(target=handler_func, args=(conn, addr), daemon=True)
            thread.start()
    except Exception as e:
        logger.critical(f"❌ Falha ao iniciar listener na porta {port} error={e}", log_label="SERVIDOR")

def run_flask_app():
    from app.api import create_app
    app = create_app()
    app.run(host='::', port=5000)

def run_ws_server():
    from app.websocket import ws
    server = WebSocketServer("0.0.0.0", 8575, ws.LogStreamer)
    server.serve_forever()

def run_workers():
    import importlib
    for item in os.listdir("app/workers"):
        if item.endswith(".py") and not "__" in item:
            module_name = item.removesuffix(".py")
            module = importlib.import_module(f"app.workers.{module_name}")
            for attr in dir(module):
                if "orchestrator" in attr:
                    worker_func = getattr(module, attr)
                    threading.Thread(target=worker_func, daemon=True).start()

def main():
    logger.info("Iniciando Servidor Tradutor...", log_label="SERVIDOR")

    # Iniciar API Flask em uma thread separada
    flask_thread = threading.Thread(target=run_flask_app, daemon=True)
    flask_thread.start()
    logger.info("✅ Servidor Flask iniciado em http://0.0.0.0:5000", log_label="SERVIDOR")
    
    # Iniciar servidor WebSocket para servir logs
    ws_thread = threading.Thread(target=run_ws_server, daemon=True)
    ws_thread.start()
    logger.info("✅ Servidor WebSocket iniciado em ws://0.0.0.0:8575", log_label="SERVIDOR")

    # Iniciar os workers (executam código arbitrário)
    workers_thread = threading.Thread(target=run_workers, daemon=True)
    workers_thread.start()
    logger.info("✅ Workers Iniciados!", log_label="SERVIDOR")

    # Inicializar worker de histórico
    # Trabalha em um PROCESSO dedicado
    history_service_process = history_service.start_history_service()

    for protocol_name, config in settings.INPUT_PROTOCOL_HANDLERS.items():
        try:
            port = config['port']
            module_path, func_name = config['handler_path'].rsplit('.', 1)
            logger.info(f"Config: port={port}, handler_path={config['handler_path']}, module_path={module_path}, func_name={func_name}", log_label="SERVIDOR")
            
            # Importa dinamicamente a função de handler
            module = importlib.import_module(module_path)
            handler_function = getattr(module, func_name)
            
            listener_thread = threading.Thread(
                target=start_listener,
                args=(port, handler_function),
                daemon=True
            )
            listener_thread.start()
            logger.info(f"Thread para protocolo '{protocol_name}' iniciada.", log_label="SERVIDOR")
            
        except (ImportError, AttributeError) as e:
            import traceback

            logger.error(f"Não foi possível carregar o handler para o protocolo '{protocol_name}' error={e}", log_label="SERVIDOR")
            logger.error(f"Traceback: \n{traceback.format_exc()}", log_label="SERVIDOR")
        except KeyError as e:
            logger.error(f"Configuração inválida para o protocolo '{protocol_name}' missing_key={str(e)}", log_label="SERVIDOR")

    # Mantém a thread principal viva
    try:
        while True:
            threading.Event().wait(60) # Espera para não consumir CPU
    except KeyboardInterrupt:
        logger.info("Servidor sendo desligado...", log_label="SERVIDOR")

if __name__ == "__main__":
    main()