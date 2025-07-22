import struct
from datetime import datetime

from app.config.settings import settings
from app.src.suntech_utils import build_suntech_packet, build_suntech_alv_packet
from app.src.tcp_connection import send_to_main_server

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

        # 2. Decodificar os itens adicionais (após os 28 bytes)
        extra_body = body[28:]
        offset = 0
        while offset < len(extra_body):
            item_id = extra_body[offset]
            offset += 1
            item_len = extra_body[offset]
            offset += 1
            item_data = extra_body[offset : offset + item_len]
            offset += item_len

            if item_id == 0x01: # Odômetro/Quilometragem
                # Odômetro é DWORD, 1/10 km
                odometer_val = struct.unpack('>I', item_data)[0]
                data['gps_odometer'] = odometer_val * 100 # Suntech espera em metros

    except Exception as e:
        print(f"[!] Erro ao decodificar pacote de localização JT/T 808: {e}")
        return None
    return data


def process_jt808_packet(msg_id: int, body: bytes, dev_id_str: str):
    """Processa um pacote JT/T 808 decodificado e o traduz para o formato Suntech."""
    suntech_packet = None
    print(f"\n--- Processando Pacote JT/T 808 [ID: {hex(msg_id)}] de {dev_id_str} ---")

    if msg_id == 0x0100 or msg_id == 0x0102:
        print("  -> Tratado: Registro/Autenticação (Apenas para sessão)")

    elif msg_id == 0x0002:
        print("  -> Traduzindo: Heartbeat para Keep-Alive (ALV)")
        suntech_packet = build_suntech_alv_packet(dev_id_str)

    elif msg_id == 0x0200:
        location_data = decode_jt808_location_packet(body)
        if not location_data:
            return

        alert_triggered = False
        for bit_pos, alert_id in settings.JT808_TO_SUNTECH_ALERT_MAP.items():
            if (location_data['alert_mark'] >> bit_pos) & 1:
                print(f"  -> Traduzindo: Localização COM ALERTA (Bit {bit_pos}) para ALT (ID: {alert_id})")
                suntech_packet = build_suntech_packet("ALT", dev_id_str, location_data, is_realtime=True, alert_id=alert_id)
                alert_triggered = True
                break

        if not alert_triggered:
            print("  -> Traduzindo: Localização para Status (STT)")
            suntech_packet = build_suntech_packet("STT", dev_id_str, location_data, is_realtime=True)

    elif msg_id == 0x0704:
        print("  -> Traduzindo: Pacote de Dados de Área Cega (múltiplos STT/ALT)")
        total_reports = struct.unpack('>H', body[:2])[0]
        print(f"  -> Total de {total_reports} localizações históricas encontradas.")

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
                    print(f"    -> Encaminhando histórico {i+1}/{total_reports}: {historical_suntech_packet}")
                    send_to_main_server(historical_suntech_packet.encode('ascii'))
        suntech_packet = None # Já foram enviados

    else:
        print(f"  -> Ignorado: Pacote não mapeado.")

    if suntech_packet:
        print(f"  -> Pacote Suntech Gerado: {suntech_packet}")
        send_to_main_server(suntech_packet.encode('ascii'))