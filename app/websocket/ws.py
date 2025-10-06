import subprocess
import threading
from simple_websocket_server import WebSocket

from app.core.logger import get_logger

logger = get_logger(__name__)

class LogStreamer(WebSocket):
    def __init__(self, server, sock, address):
        super().__init__(server, sock, address)
        
        self.tracker_id = None
        self.n_lines = None
        self.log_process = None

    def connected(self):
        logger.info(f"Cliente conectado: {self.address}", log_label="SERVIDOR - WEBSOCKET SERVER")

    def handle(self):
        if self.tracker_id is None:
            tracker_id_n_lines = self.data
            self.tracker_id = tracker_id_n_lines.split("|")[0]
            self.n_lines = tracker_id_n_lines.split("|")[-1]

            logger.info(f"Cliente {self.address} solicitou monitoramento para o rastreador: {self.tracker_id}", tracker_id="SERVIDOR - WEBSOCKET SERVER")
            
            streaming_thread = threading.Thread(target=self._stream_logs)
            streaming_thread.daemon = True 
            streaming_thread.start()
        else:
            logger.info(f"Mensagem subsequente de {self.address} ignorada: {self.data}", log_label="SERVIDOR - WEBSOCKET SERVER")

    def handle_close(self):
        logger.info(f"Cliente desconectado: {self.address}", log_label="SERVIDOR - WEBSOCKET SERVER")
        
        if self.log_process:
            logger.info(f"Encerrando o processo journalctl para o cliente {self.address}...", log_label="SERVIDOR - WEBSOCKET SERVER")
            self.log_process.terminate()
            self.log_process.wait()
            logger.info("Processo encerrado.", log_label="SERVIDOR - WEBSOCKET SERVER")

    def _stream_logs(self):
        if not self.tracker_id:
            return

        cmd = [
            "sudo",
            "journalctl", 
            "-f", 
            "-u", "gateway-rastreadores.service",
            "--output=cat",
            "--all"
        ]

        # Número de linhas
        n_lines = self.n_lines if self.n_lines else 100
        cmd += ["-n", str(n_lines)]

        try:
            self.log_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

            for line in iter(self.log_process.stdout.readline, ''):
                if self.tracker_id in line:
                    try:
                        self.send_message(line.strip())
                    except Exception as e:
                        logger.info(f"Erro ao enviar para o cliente {self.address}: {e}", log_label="SERVIDOR - WEBSOCKET SERVER")
                        break
            
            self.log_process.stdout.close()
            return_code = self.log_process.wait()
            if return_code:
                stderr_output = self.log_process.stderr.read()
                logger.info(f"Subprocesso journalctl terminou com erro. código {return_code}: {stderr_output}", log_label="SERVIDOR - WEBSOCKET SERVER")

        except Exception as e:
            logger.info(f"Ocorreu um erro na thread de streaming para {self.address}: {e}", log_label="SERVIDOR - WEBSOCKET SERVER")
        finally:
            if self.log_process and self.log_process.poll() is None:
                self.log_process.terminate()