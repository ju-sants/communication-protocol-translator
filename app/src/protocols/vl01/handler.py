import socket
import struct

from app.core.logger import get_logger
from .processor import process_packet
from .utils import format_vl01_packet_for_display 
from app.src.protocols.session_manager import tracker_sessions_manager
from app.services.redis_service import get_redis
from app.src.connection.main_server_connection import sessions_manager


logger = get_logger(__name__)
redis_client = get_redis()

def handle_connection(conn: socket.socket, addr):
    """
    Lida com uma única conexão de cliente VL01, gerenciando o estado da sessão.
    """
    logger.info(f"Nova conexão VL01 recebida endereco={addr}")
    buffer = b''
    dev_id_session = None

    try:
        while True:
            data = conn.recv(1024)
            if not data:
                logger.info(f"Conexão VL01 fechada pelo cliente endereco={addr}, device_id={dev_id_session}")
                break
            
            buffer += data
            
            while len(buffer) > 4:
                if buffer.startswith(b'\x78\x78') or buffer.startswith(b"\x79\x79"):
                    packet_length = buffer[2] if buffer.startswith(b"\x78\x78") else struct.unpack(">H", buffer[2:4])
                    
                    if buffer.startswith(b'\x78\x78'):
                        # Tamanho total do pacote na stream: Start(2) + [Length(1) + Corpo(length-2)] + Stop(2)
                        full_packet_size = 2 + 1 + packet_length + 2
                    else:
                        full_packet_size = 2 + 2 + packet_length + 2
                    
                    if len(buffer) >= full_packet_size:
                        raw_packet = buffer[:full_packet_size]
                        buffer = buffer[full_packet_size:]

                        # Validação dos bits de parada
                        if not raw_packet.endswith(b'\x0d\x0a'):
                            logger.warning(f"Pacote VL01 com stop bits inválidos, descartando. pacote={raw_packet.hex()}")
                            continue
                        
                        # Corpo do pacote que vai para o processador: [Length(1) + Proto(1) + Conteúdo + Serial(2) + CRC(2)]
                        packet_body = raw_packet[2:-2]
                        
                        # Formatando pacote para display
                        logger.info(f"Pacote Formatado Recebido de {addr}:\n{format_vl01_packet_for_display(packet_body)}")

                        # Chama o processador, passando o ID da sessão
                        response_packet, newly_logged_in_dev_id = process_packet(dev_id_session, packet_body)
                        
                        if newly_logged_in_dev_id:
                            dev_id_session = newly_logged_in_dev_id

                        if dev_id_session and not tracker_sessions_manager.exists(dev_id_session):
                            tracker_sessions_manager.register_tracker_client(dev_id_session, conn)
                            redis_client.hset(dev_id_session, "protocol", "vl01")
                            logger.info(f"Dispositivo VL01 autenticado na sessão device_id={dev_id_session}, endereco={addr}")

                        if response_packet:
                            conn.sendall(response_packet)

                    else:
                        break
                else:
                    # Procuramos o próximo início de pacote válido para tentar nos recuperar.
                    next_start_78 = buffer.find(b'\x78\x78', 1)
                    next_start_79 = buffer.find(b"\x79\x79", 1)

                    next_start = next_start_78
                    if next_start_79 != -1 and next_start_78 != -1 and next_start_79 < next_start_78:
                        next_start = next_start_79

                    if next_start != -1:
                        dados_descartados = buffer[:next_start]
                        logger.warning(f"Dados desalinhados no buffer, descartando {len(dados_descartados)} bytes dados={dados_descartados.hex()}")
                        buffer = buffer[next_start:]
                    else:
                        # Nenhum início válido encontrado, limpa o buffer
                        buffer = b''
    
    except (ConnectionResetError, BrokenPipeError):
        logger.warning(f"Conexão VL01 fechada abruptamente endereco={addr}, device_id={dev_id_session}")
    except Exception:
        logger.exception(f"Erro fatal na conexão VL01 endereco={addr}, device_id={dev_id_session}")
    finally:
        if dev_id_session:
            logger.info(f"Deletando Sessões em ambos os lados para esse rastreador dev_id={dev_id_session}")
            tracker_sessions_manager.remove_tracker_client(dev_id_session)
            sessions_manager.delete_session(dev_id_session)

        logger.info(f"Fechando conexão e thread VL01 endereco={addr}, device_id={dev_id_session}")
        try:
            conn.shutdown(socket.SHUT_RDWR)
            conn.close()
            conn = None
        except Exception as e:
            logger.error(f"Impossível limpar conexão com rastreador dev_id={dev_id_session if dev_id_session in locals() else 'None'}")