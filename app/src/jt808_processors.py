import struct
from datetime import datetime

from app.config.settings import settings
from app.src.suntech_utils import build_suntech_packet, build_suntech_alv_packet
from app.src.main_server_connection import send_to_main_server
from app.core.logger import get_logger
from app.services.redis_service import get_redis

logger = get_logger(__name__)
redis_client = get_redis()

def handle_ignition_change(dev_id_str: str, location_data: dict):
    """
    Verifica se houve mudança no status da ignição e envia o alerta correspondente.
    """
    try:
        current_acc_status = (location_data['status_bits'] & 0b1) # 1 se ON, 0 se OFF
        
        # Busca o estado anterior no Redis
        previous_state = redis_client.hgetall(dev_id_str)
        previous_acc_status_str = previous_state.get('acc_status')
        
        # Converte o estado anterior para inteiro se existir
        previous_acc_status = int(previous_acc_status_str) if previous_acc_status_str is not None else None

        # Se o estado mudou, gera um alerta
        if previous_acc_status is not None and previous_acc_status != current_acc_status:
            ignition_alert_packet = None
            if current_acc_status == 1:
                # Mudou de OFF para ON
                alert_id = settings.SUNTECH_IGNITION_ON_ALERT_ID
                logger.info(f"EVENTO DETECTADO: Ignição Ligada para device_id={dev_id_str}")
                ignition_alert_packet = build_suntech_packet(
                    "ALT", dev_id_str, location_data, is_realtime=True, alert_id=alert_id
                )

            else:
                # Mudou de ON para OFF
                alert_id = settings.SUNTECH_IGNITION_OFF_ALERT_ID
                logger.info(f"EVENTO DETECTADO: Ignição Desligada para device_id={dev_id_str}")
                ignition_alert_packet = build_suntech_packet(
                    "ALT", dev_id_str, location_data, is_realtime=True, alert_id=alert_id
                )
            
            # Envia o pacote de alerta de ignição para o servidor principal
            if ignition_alert_packet:
                send_to_main_server(dev_id_str, ignition_alert_packet.encode('ascii'))

        # Atualiza o estado no Redis para a próxima verificação
        redis_client.hset(dev_id_str, 'acc_status', current_acc_status)

    except Exception:
        logger.exception(f"Erro ao processar mudança de ignição para device_id={dev_id_str}")

def handle_power_change(dev_id_str: str, location_data: dict):
    """Verifica se houve mudança no status da alimentação e envia o alerta correspondente."""
    try:
        # Bit 11: 0 = normal, 1 = desconectado
        current_power_disconnected = (location_data['status_bits'] >> 11) & 1
        
        previous_state = redis_client.hgetall(dev_id_str)
        previous_power_disconnected_str = previous_state.get('power_status')
        previous_power_disconnected = int(previous_power_disconnected_str) if previous_power_disconnected_str is not None else None

        if previous_power_disconnected is not None and previous_power_disconnected != current_power_disconnected:
            power_alert_packet = None
            if current_power_disconnected == 1:
                # Mudou de Conectado (0) para Desconectado (1)
                alert_id = settings.SUNTECH_POWER_DISCONNECTED_ALERT_ID # Alerta 41
                logger.info(f"EVENTO DETECTADO: Alimentação Principal Desconectada para device_id={dev_id_str}")
                power_alert_packet = build_suntech_packet(
                    "ALT", dev_id_str, location_data, is_realtime=True, alert_id=alert_id
                )
            else:
                # Mudou de Desconectado (1) para Conectado (0)
                alert_id = settings.SUNTECH_POWER_CONNECTED_ALERT_ID # Alerta 40
                logger.info(f"EVENTO DETECTADO: Alimentação Principal Conectada para device_id={dev_id_str}")
                power_alert_packet = build_suntech_packet(
                    "ALT", dev_id_str, location_data, is_realtime=True, alert_id=alert_id
                )
            
            if power_alert_packet:
                send_to_main_server(dev_id_str, power_alert_packet.encode('ascii'))

        redis_client.hset(dev_id_str, 'power_status', current_power_disconnected)
    except Exception:
        logger.exception(f"Erro ao processar mudança de alimentação para device_id={dev_id_str}")


def decode_jt808_location_packet(body: bytes) -> dict:
    """Decodifica o corpo da mensagem de localização (0x0200), incluindo itens adicionais."""
    data = {}
    try:
        # 1. Decodificar a parte básica (28 bytes)
        alert_mark, status, lat, lon, height, speed, direction, time_bcd = struct.unpack('>IIIIHHH6s', body[:28])
        time_str = time_bcd.hex()
        data.update({
            "alert_mark": alert_mark, "status_bits": status,
            "latitude": lat / 1_000_000.0, "longitude": lon / 1_000_000.0,
            "altitude": height, "speed_kmh": speed / 10.0, "direction": direction,
            "timestamp": datetime.strptime(time_str, '%y%m%d%H%M%S')
        })
        logger.debug(f"Decodificação básica do pacote de localização bem-sucedida: {data}")

        # 2. Decodificar os itens adicionais
        extra_body = body[28:]
        offset = 0
        while offset < len(extra_body):
            item_id = extra_body[offset]
            offset += 1
            item_len = extra_body[offset]
            offset += 1
            item_data = extra_body[offset : offset + item_len]
            offset += item_len

            if item_id == 0x01: # Odômetro
                odometer_val = struct.unpack('>I', item_data)[0]
                data['gps_odometer'] = odometer_val * 100
                logger.debug(f"Decodificado item adicional: Odômetro, valor={data['gps_odometer']}")

            # --- NOVA LÓGICA PARA ITEM DE GEOCERCA ---
            elif item_id == 0x12 and item_len == 6: # Alerta de In/Out Area 
                # Formato: Tipo (B), ID da Área (I), Direção (B) 
                _, area_id, direction = struct.unpack('>BIB', item_data)
                data['geo_fence_id'] = area_id
                data['geo_fence_direction'] = direction # 0: in, 1: out 
                logger.debug(f"Decodificado item adicional: Geocerca, id={area_id}, direcao={direction}")

    except Exception:
        logger.exception(f"Erro ao decodificar pacote de localização JT/T 808: {body.hex()}")
        return None
    return data


def process_jt808_packet(msg_id: int, body: bytes, dev_id_str: str):
    """Processa um pacote JT/T 808 decodificado e o traduz para o formato Suntech."""
    suntech_packet = None  # Usar um nome de variável genérico
    logger.info(f"Processando pacote JT/T 808: msg_id={hex(msg_id)}, device_id={dev_id_str}")

    if msg_id == 0x0100 or msg_id == 0x0102:
        logger.info(f"Pacote de Registro/Autenticação tratado (apenas para sessão) para device_id={dev_id_str}")

    elif msg_id == 0x0002:
        logger.info(f"Traduzindo Heartbeat para Keep-Alive (ALV) para device_id={dev_id_str}")
        suntech_packet = build_suntech_alv_packet(dev_id_str)

    elif msg_id == 0x0200:
        location_data = decode_jt808_location_packet(body)
        if not location_data:
            return
        
        # Funções que geram eventos adicionais (enviam seus próprios pacotes)
        handle_ignition_change(dev_id_str, location_data)
        handle_power_change(dev_id_str, location_data)

        # Agora, gera o pacote principal para a localização/alerta atual
        alert_triggered = False
        jt808_alert_mark = location_data.get('alert_mark', 0)

        # Verifica se é um alerta de Geocerca (bit 20 ou 21)
        if ((jt808_alert_mark >> 20) & 1 or (jt808_alert_mark >> 21) & 1) and 'geo_fence_id' in location_data:
            direction = location_data['geo_fence_direction']
            geo_id = location_data['geo_fence_id']
            alert_id = settings.SUNTECH_GEOFENCE_ENTER_ALERT_ID if direction == 0 else settings.SUNTECH_GEOFENCE_EXIT_ALERT_ID
            
            logger.info(f"Tradução: Localização COM ALERTA de Geocerca para device_id={dev_id_str}, suntech_alert_id={alert_id}, geo_id={geo_id}")
            suntech_packet = build_suntech_packet("ALT", dev_id_str, location_data, is_realtime=True, alert_id=alert_id, geo_fence_id=geo_id)
            alert_triggered = True

        if not alert_triggered:
            for bit_pos, alert_id in settings.JT808_TO_SUNTECH_ALERT_MAP.items():
                if (jt808_alert_mark >> bit_pos) & 1:
                    logger.info(f"Tradução: Localização COM ALERTA para device_id={dev_id_str}, bit_pos={bit_pos}, suntech_alert_id={alert_id}")
                    suntech_packet = build_suntech_packet("ALT", dev_id_str, location_data, is_realtime=True, alert_id=alert_id)
                    alert_triggered = True
                    break
        
        if not alert_triggered:
            logger.info(f"Tradução: Localização para Status (STT) para device_id={dev_id_str}")
            suntech_packet = build_suntech_packet("STT", dev_id_str, location_data, is_realtime=True)

    elif msg_id == 0x0704:
        logger.info(f"Tradução: Pacote de Dados de Área Cega (múltiplos STT/ALT) para device_id={dev_id_str}")
        total_reports = struct.unpack('>H', body[:2])[0]
        logger.info(f"Total de {total_reports} localizações históricas encontradas para device_id={dev_id_str}")

        offset = 3 # Pula total e tipo
        for i in range(total_reports):
            report_len = struct.unpack('>H', body[offset:offset+2])[0]
            offset += 2
            report_body = body[offset:offset+report_len]
            offset += report_len

            loc_data = decode_jt808_location_packet(report_body)
            if loc_data:
                # Trata como não-tempo-real
                historical_suntech_packet = build_suntech_packet("STT", dev_id_str, loc_data, is_realtime=False)
                if historical_suntech_packet:
                    logger.debug(f"Encaminhando pacote histórico {i+1}/{total_reports} para device_id={dev_id_str}: {historical_suntech_packet}")
                    send_to_main_server(dev_id_str, historical_suntech_packet.encode('ascii'))
        suntech_packet = None # Garante que nada extra seja enviado no final

    else:
        logger.warning(f"Pacote ignorado: ID de mensagem não mapeado {hex(msg_id)} para device_id={dev_id_str}")

    if suntech_packet:
        logger.info(f"Pacote Suntech gerado para encaminhamento para device_id={dev_id_str}: {suntech_packet}")
        send_to_main_server(dev_id_str, suntech_packet.encode('ascii'))

    