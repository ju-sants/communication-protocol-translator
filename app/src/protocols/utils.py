from app.services.redis_service import get_redis
from app.core.logger import get_logger
from app.src.output.suntech.utils import build_suntech_packet
from app.src.connection.main_server_connection import send_to_main_server

redis_client = get_redis()
logger = get_logger(__name__)

# IDs de Alerta Suntech que são INFERIDOS, não traduzidos diretamente
SUNTECH_IGNITION_ON_ALERT_ID: int = 33
SUNTECH_IGNITION_OFF_ALERT_ID: int = 34
SUNTECH_POWER_CONNECTED_ALERT_ID: int = 40
SUNTECH_POWER_DISCONNECTED_ALERT_ID: int = 41

# IDs de Alerta Suntech para Geocerca (baseado na direção)
SUNTECH_GEOFENCE_ENTER_ALERT_ID: int = 6
SUNTECH_GEOFENCE_EXIT_ALERT_ID: int = 5


def handle_ignition_change(dev_id_str: str, serial, location_data: dict, raw_packet_hex: str):
    """
    Verifica se houve mudança no status da ignição e envia o alerta correspondente.
    """
    try:
        current_acc_status = location_data['acc_status'] # 1 se ON, 0 se OFF
        
        # Busca o estado anterior no Redis
        previous_acc_status_str = redis_client.hget(dev_id_str, "acc_status")
        
        # Converte o estado anterior para inteiro se existir
        previous_acc_status = int(previous_acc_status_str) if previous_acc_status_str is not None else None

        # Se o estado mudou, gera um alerta
        if previous_acc_status is not None and previous_acc_status != current_acc_status:
            ignition_alert_packet = None
            if current_acc_status == 1:
                # Mudou de OFF para ON
                alert_id = SUNTECH_IGNITION_ON_ALERT_ID
                logger.info(f"EVENTO DETECTADO: Ignição Ligada para device_id={dev_id_str}")
                ignition_alert_packet = build_suntech_packet(
                    "ALT", dev_id_str, location_data, serial, is_realtime=True, alert_id=alert_id
                )

            else:
                # Mudou de ON para OFF
                alert_id = SUNTECH_IGNITION_OFF_ALERT_ID
                logger.info(f"EVENTO DETECTADO: Ignição Desligada para device_id={dev_id_str}")
                ignition_alert_packet = build_suntech_packet(
                    "ALT", dev_id_str, location_data, serial, is_realtime=True, alert_id=alert_id
                )
            
            # Envia o pacote de alerta de ignição para o servidor principal
            if ignition_alert_packet:
                send_to_main_server(dev_id_str, serial, ignition_alert_packet.encode('ascii'), raw_packet_hex)

        # Atualiza o estado no Redis para a próxima verificação
        redis_client.hset(dev_id_str, 'acc_status', current_acc_status)

    except Exception:
        logger.exception(f"Erro ao processar mudança de ignição para device_id={dev_id_str}")


# DEPRECATED
def handle_power_change(dev_id_str: str, serial, location_data: dict):
    """Verifica se houve mudança no status da alimentação e envia o alerta correspondente."""
    try:
        # Bit 11: 0 = normal, 1 = desconectado
        current_power_disconnected = (location_data['DEPRECATED'] >> 11) & 1
        
        previous_state = redis_client.hgetall(dev_id_str)
        previous_power_disconnected_str = previous_state.get('power_status')
        previous_power_disconnected = int(previous_power_disconnected_str) if previous_power_disconnected_str is not None else None

        if previous_power_disconnected is not None and previous_power_disconnected != current_power_disconnected:
            power_alert_packet = None
            if current_power_disconnected == 1:
                # Mudou de Conectado (0) para Desconectado (1)
                alert_id = SUNTECH_POWER_DISCONNECTED_ALERT_ID # Alerta 41
                logger.info(f"EVENTO DETECTADO: Alimentação Principal Desconectada para device_id={dev_id_str}")
                power_alert_packet = build_suntech_packet(
                    "ALT", dev_id_str, location_data, serial, is_realtime=True, alert_id=alert_id
                )
            else:
                # Mudou de Desconectado (1) para Conectado (0)
                alert_id = SUNTECH_POWER_CONNECTED_ALERT_ID # Alerta 40
                logger.info(f"EVENTO DETECTADO: Alimentação Principal Conectada para device_id={dev_id_str}")
                power_alert_packet = build_suntech_packet(
                    "ALT", dev_id_str, location_data, serial, is_realtime=True, alert_id=alert_id
                )
            
            if power_alert_packet:
                send_to_main_server(dev_id_str, serial, power_alert_packet.encode('ascii'))

        redis_client.hset(dev_id_str, 'power_status', current_power_disconnected)
    except Exception:
        logger.exception(f"Erro ao processar mudança de alimentação para device_id={dev_id_str}")