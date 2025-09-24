from crc import Calculator, Configuration

from app.services.redis_service import get_redis
from app.core.logger import get_logger

redis_client = get_redis()
logger = get_logger(__name__)

# IDs de Alerta Suntech4G que são INFERIDOS, não traduzidos diretamente
IGNITION_ON_UNIVERSAL_ALERT_ID: int = 6533
IGNITION_OFF_UNIVERSAL_ALERT_ID: int = 6534

def log_mapped_packet(mapped_data: dict, protocol_name: str):
    """
    Recebe um dicionário de dados mapeados e formata uma string de log legível.
    """
    header = f"--- Pacote {protocol_name.upper()} Mapeado ---"
    footer = "-" * len(header)
    
    log_parts = [header]
    for key, value in mapped_data.items():
        log_parts.append(f"  - {key}: {value}")
    log_parts.append(footer)
    
    logger.info("\n" + "\n".join(log_parts))

def crc_itu(data_bytes: bytes) -> int:
    config = Configuration(
        width=16,
        polynomial=0x1021,
        init_value=0xFFFF,
        final_xor_value=0xFFFF,
        reverse_input=True,
        reverse_output=True,
    )

    calculator = Calculator(config)
    crc_value = calculator.checksum(data_bytes)
    return crc_value

def handle_ignition_change(dev_id_str: str, packet_data: dict):
    """
    Verifica se houve mudança no status da ignição e envia o alerta correspondente.
    """
    try:
        current_acc_status = packet_data['acc_status'] # 1 se ON, 0 se OFF
        
        # Busca o estado anterior no Redis
        previous_acc_status_str = redis_client.hget(f"tracker:{dev_id_str}", "acc_status")
        
        # Converte o estado anterior para inteiro se existir
        previous_acc_status = int(previous_acc_status_str) if previous_acc_status_str is not None else None

        # Se o estado mudou, gera um alerta
        if previous_acc_status is not None and previous_acc_status != current_acc_status:

            packet_data["hdr"] = "ALT"
            packet_data["is_realtime"] = True
            if current_acc_status == 1:
                # Mudou de OFF para ON
                alert_id = IGNITION_ON_UNIVERSAL_ALERT_ID
                logger.info(f"EVENTO DETECTADO: Ignição Ligada para device_id={dev_id_str}")

                packet_data["universal_alert_id"] = alert_id

            else:
                # Mudou de ON para OFF
                alert_id = IGNITION_OFF_UNIVERSAL_ALERT_ID
                logger.info(f"EVENTO DETECTADO: Ignição Desligada para device_id={dev_id_str}")

                packet_data["universal_alert_id"] = alert_id

        # Atualiza o estado no Redis para a próxima verificação
        redis_client.hset(f"tracker:{dev_id_str}", 'acc_status', current_acc_status)

        return packet_data

    except Exception:
        logger.exception(f"Erro ao processar mudança de ignição para device_id={dev_id_str}")


# DEPRECATED, MANTEINED BY SUPPORT TO JT808 PROTOCOL
def handle_power_change(dev_id_str: str, serial, packet_data: dict):
    """Verifica se houve mudança no status da alimentação e envia o alerta correspondente."""
    try:
        # Bit 11: 0 = normal, 1 = desconectado
        current_power_disconnected = (packet_data['DEPRECATED'] >> 11) & 1
        
        previous_state = redis_client.hgetall(f"tracker:{dev_id_str}")
        previous_power_disconnected_str = previous_state.get('power_status')
        previous_power_disconnected = int(previous_power_disconnected_str) if previous_power_disconnected_str is not None else None

        if previous_power_disconnected is not None and previous_power_disconnected != current_power_disconnected:
            power_alert_packet = None
            if current_power_disconnected == 1:
                # Mudou de Conectado (0) para Desconectado (1)
                # alert_id = SUNTECH_POWER_DISCONNECTED_ALERT_ID # Alerta 41
                logger.info(f"EVENTO DETECTADO: Alimentação Principal Desconectada para device_id={dev_id_str}")
                # power_alert_packet = build_suntech_packet(
                #     "ALT", dev_id_str, packet_data, serial, is_realtime=True, alert_id=alert_id
                # )
            else:
                # Mudou de Desconectado (1) para Conectado (0)
                # alert_id = SUNTECH_POWER_CONNECTED_ALERT_ID # Alerta 40
                logger.info(f"EVENTO DETECTADO: Alimentação Principal Conectada para device_id={dev_id_str}")
                # power_alert_packet = build_suntech_packet(
                #     "ALT", dev_id_str, packet_data, serial, is_realtime=True, alert_id=alert_id
                # )
            
            # if power_alert_packet:
            #     send_to_main_server(dev_id_str, serial, power_alert_packet.encode('ascii'))

        redis_client.hset(f"tracker:{dev_id_str}", 'power_status', current_power_disconnected)
    except Exception:
        logger.exception(f"Erro ao processar mudança de alimentação para device_id={dev_id_str}")