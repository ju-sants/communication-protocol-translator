import socket
from app.core.logger import get_logger
from .processor import process_packet

from app.src.session.input_sessions_manager import input_sessions_manager
from app.services.redis_service import get_redis
from app.src.session.output_sessions_manager import output_sessions_manager

logger = get_logger(__name__)
redis_client = get_redis()

def handle_connection(conn: socket.socket, addr):
    """
    Lida com uma única conexão de cliente NT40, gerenciando o estado da sessão.
    """
    logger.info(f"Nova conexão NT40 recebida endereco={addr}", log_label="SERVIDOR")
    buffer = b''
    dev_id_session = None
    
    try:
        while True:
            with logger.contextualize(log_label=dev_id_session):
                data = conn.recv(1024)
                if not data:
                    logger.info(f"Conexão NT40 fechada pelo cliente endereco={addr}")
                    break
                
                buffer += data
                
                while len(buffer) > 4:
                    if buffer.startswith(b'\x78\x78'):
                        packet_length = buffer[2]
                        # Tamanho total do pacote na stream: Start(2) + [Length(1) + Corpo(length-2)] + Stop(2)
                        full_packet_size = 2 + 1 + packet_length + 2
                        
                        if len(buffer) >= full_packet_size:
                            raw_packet = buffer[:full_packet_size]
                            buffer = buffer[full_packet_size:]

                            # Validação dos bits de parada
                            if not raw_packet.endswith(b'\x0d\x0a'):
                                logger.warning(f"Pacote NT40 com stop bits inválidos, descartando. pacote={raw_packet.hex()}")
                                continue
                            
                            # Corpo do pacote que vai para o processador: [Length(1) + Proto(1) + Conteúdo + Serial(2) + CRC(2)]
                            packet_body = raw_packet[2:-2]
                            logger.info(f"Recebido pacote NT40: {packet_body.hex()}")
                            
                            # Chama o processador, passando o ID da sessão
                            newly_logged_in_dev_id = process_packet(dev_id_session, packet_body, conn)
                            
                            if newly_logged_in_dev_id and newly_logged_in_dev_id != dev_id_session:
                                dev_id_session = newly_logged_in_dev_id

                            if dev_id_session and not input_sessions_manager.exists(dev_id_session):
                                input_sessions_manager.register_session(dev_id_session, conn)
                                redis_client.hset(f"tracker:{dev_id_session}", "protocol", "nt40")
                                logger.info(f"Dispositivo NT40 autenticado na sessão")

                        else:
                            break
                    else:
                        # Procuramos o próximo início de pacote válido para tentar nos recuperar.
                        next_start = buffer.find(b'\x78\x78', 1)
                        if next_start != -1:
                            dados_descartados = buffer[:next_start]
                            logger.warning(f"Dados desalinhados no buffer, descartando {len(dados_descartados)} bytes dados={dados_descartados.hex()}")
                            buffer = buffer[next_start:]
                        else:
                            # Nenhum início válido encontrado, limpa o buffer
                            buffer = b''
    
    except (ConnectionResetError, BrokenPipeError):
        logger.warning(f"Conexão NT40 fechada abruptamente endereco={addr}", log_label="SERVIDOR")
    except Exception:
        logger.exception(f"Erro fatal na conexão NT40 endereco={addr}", log_label="SERVIDOR")
    finally:
        logger.debug(f"[DIAGNOSTIC] Entering finally block for NT40 handler (addr={addr}).", log_label="SERVIDOR")
        if dev_id_session:
            with logger.contextualize(log_label=dev_id_session):
                logger.info(f"Deletando Sessões em ambos os lados para esse rastreador", log_label="SERVIDOR")
                output_sessions_manager.delete_session(dev_id_session)
                input_sessions_manager.remove_session(dev_id_session)
        
        logger.info(f"Fechando conexão e thread NT40 endereco={addr}", log_label="SERVIDOR")

        try:
            conn.shutdown(socket.SHUT_RDWR)
            conn.close()
            conn = None
        except Exception as e:
            logger.error(f"Impossível limpar conexão com rastreador: {e}", log_label="SERVIDOR")