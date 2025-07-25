import struct
from datetime import datetime, timezone, timedelta
from app.config.settings import settings
from app.src.suntech.utils import build_suntech_packet, build_suntech_alv_packet
from app.src.connection.main_server_connection import send_to_main_server
from app.services.redis_service import get_redis
from app.core.logger import get_logger
from app.src.protocols.utils import handle_ignition_change, handle_power_change

logger = get_logger(__name__)
redis_client = get_redis()


JT808_TO_SUNTECH_ALERT_MAP = {
    0: 42,  # Bit 0 (SOS) -> Alert 42 (Panic Button)
    1: 1,   # Bit 1 (Over-speed) -> Alert 1 (Over Speed)
    5: 3,   # Bit 5 (GNSS Antenna not connected) -> Alert 3 (GPS Antenna Disconnected)
    8: 41,  # Bit 8 (Main power cut off) -> Alert 41 (Power Disconnected)
    27: 73, # Bit 27 (Illegal fire) -> Alert 73 (Anti-Theft)
    20: 5,  # Bit 20 (in/out area) -> Usaremos 5 (Exit) ou 6 (Enter)
    21: 5,  # Bit 21 (in/out routine) -> Usaremos 5 (Exit) ou 6 (Enter)
}

def decode_location_packet(body: bytes) -> dict:
    """Decodifica o corpo da mensagem de localização (0x0200), incluindo itens adicionais."""
    data = {}
    try:
        # 1. Decodificar a parte básica (28 bytes)
        alert_mark, status, lat, lon, height, speed, direction, time_bcd = struct.unpack('>IIIIHHH6s', body[:28])
        time_str = time_bcd.hex()

        longitude = lon / 1_000_000.0
        latitude = lat / 1_000_000.0

        if (status >> 2) & 1:
            latitude = -latitude
        if (status >> 3) & 1:
            longitude = -longitude

        time_str = time_bcd.hex()
        naive_dt = datetime.strptime(time_str, '%y%m%d%H%M%S')
        timezone_tracker = timezone(timedelta(hours=-3))
        localized_dt = naive_dt.replace(tzinfo=timezone_tracker)
        utc_dt = localized_dt.astimezone(timezone.utc)

        data.update({
            "alert_mark": alert_mark, "status_bits": status,
            "latitude": latitude, "longitude": longitude,
            "altitude": height, "speed_kmh": speed / 10.0, "direction": direction,
            "timestamp": utc_dt
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

def map_and_forward(dev_id_str: str, serial: int, msg_id: int, body: bytes):
    """Processa um pacote JT/T 808 decodificado e o traduz para o formato Suntech."""
    suntech_packet = None  # Usar um nome de variável genérico
    logger.info(f"Processando pacote JT/T 808: msg_id={hex(msg_id)}, device_id={dev_id_str}")

    if msg_id == 0x0100 or msg_id == 0x0102:
        logger.info(f"Pacote de Registro/Autenticação tratado (apenas para sessão) para device_id={dev_id_str}")

    elif msg_id == 0x0002:
        logger.info(f"Traduzindo Heartbeat para Keep-Alive (ALV) para device_id={dev_id_str}")
        suntech_packet = build_suntech_alv_packet(dev_id_str)

    elif msg_id == 0x0200:
        location_data = decode_location_packet(body)
        if not location_data:
            return
        
        # Funções que geram eventos adicionais (enviam seus próprios pacotes)
        handle_ignition_change(dev_id_str, serial, location_data)
        handle_power_change(dev_id_str, serial, location_data)

        # Agora, gera o pacote principal para a localização/alerta atual
        alert_triggered = False
        jt808_alert_mark = location_data.get('alert_mark', 0)

        # Verifica se é um alerta de Geocerca (bit 20 ou 21)
        if ((jt808_alert_mark >> 20) & 1 or (jt808_alert_mark >> 21) & 1) and 'geo_fence_id' in location_data:
            direction = location_data['geo_fence_direction']
            geo_id = location_data['geo_fence_id']
            alert_id = settings.SUNTECH_GEOFENCE_ENTER_ALERT_ID if direction == 0 else settings.SUNTECH_GEOFENCE_EXIT_ALERT_ID
            
            logger.info(f"Tradução: Localização COM ALERTA de Geocerca para device_id={dev_id_str}, suntech_alert_id={alert_id}, geo_id={geo_id}")
            suntech_packet = build_suntech_packet("ALT", dev_id_str, location_data, serial, is_realtime=True, alert_id=alert_id, geo_fence_id=geo_id)
            alert_triggered = True

        if not alert_triggered:
            for bit_pos, alert_id in JT808_TO_SUNTECH_ALERT_MAP.items():
                if (jt808_alert_mark >> bit_pos) & 1:
                    logger.info(f"Tradução: Localização COM ALERTA para device_id={dev_id_str}, bit_pos={bit_pos}, suntech_alert_id={alert_id}")
                    suntech_packet = build_suntech_packet("ALT", dev_id_str, location_data, serial, is_realtime=True, alert_id=alert_id)
                    alert_triggered = True
                    break
        
        if not alert_triggered:
            logger.info(f"Tradução: Localização para Status (STT) para device_id={dev_id_str}")
            suntech_packet = build_suntech_packet("STT", dev_id_str, location_data, serial, is_realtime=True)

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

            loc_data = decode_location_packet(report_body)
            if loc_data:
                # Trata como não-tempo-real
                historical_suntech_packet = build_suntech_packet("STT", dev_id_str, loc_data, serial, is_realtime=False)
                if historical_suntech_packet:
                    logger.debug(f"Encaminhando pacote histórico {i+1}/{total_reports} para device_id={dev_id_str}: {historical_suntech_packet}")
                    send_to_main_server(dev_id_str, serial, historical_suntech_packet.encode('ascii'))
        suntech_packet = None # Garante que nada extra seja enviado no final

    else:
        logger.warning(f"Pacote ignorado: ID de mensagem não mapeado {hex(msg_id)} para device_id={dev_id_str}")

    if suntech_packet:
        logger.info(f"Pacote Suntech gerado para encaminhamento para device_id={dev_id_str}: {suntech_packet}")
        send_to_main_server(dev_id_str, serial, suntech_packet.encode('ascii'))