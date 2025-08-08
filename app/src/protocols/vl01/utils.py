from crc import Calculator, Configuration
import struct


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

def _format_location_content(content_body: bytes) -> list[str]:
    """Função auxiliar para formatar os campos de um pacote de localização/alarme."""
    try:
        parts = []
        # Data/Hora
        year, month, day, hour, min, sec = struct.unpack('>BBBBBB', content_body[0:6])
        parts.append(f"    - Data/Hora: 20{year:02d}-{month:02d}-{day:02d} {hour:02d}:{min:02d}:{sec:02d}")

        # GPS Info
        sats_byte = content_body[6]
        sats_count = sats_byte & 0x0F
        parts.append(f"    - Satélites: {sats_count}")

        # Coordenadas
        lat_raw, lon_raw = struct.unpack('>II', content_body[7:15])
        lat = lat_raw / 1800000.0
        lon = lon_raw / 1800000.0

        # Status do Curso
        course_status = struct.unpack('>H', content_body[16:18])[0]
        if not (course_status >> 10) & 1: lat = -lat
        if (course_status >> 11) & 1: lon = -lon
        
        gps_fixed = "Sim" if (course_status >> 12) & 1 else "Não"
        direction = course_status & 0x03FF
        
        parts.append(f"    - Latitude: {lat:.6f}")
        parts.append(f"    - Longitude: {lon:.6f}")
        parts.append(f"    - GPS Válido: {gps_fixed}")
        parts.append(f"    - Direção (Curso): {direction}°")
        
        # Velocidade
        speed = content_body[15]
        parts.append(f"    - Velocidade: {speed} km/h")

        # ACC (se for um pacote V3 '0x22' ou superior)
        if len(content_body) >= 27:
            mcc = struct.unpack(">H", content_body[18:20])[0]

            mnc_length = 1
            if (mcc >> 15) & 1:
                mnc_length = 2

            acc_at = 20 + mnc_length + 4 + 8
            acc_status = "Ligado" if content_body[acc_at] & 1 else "Desligado"
            parts.append(f"    - Ignição (ACC): {acc_status}")

        return parts
    except Exception as e:
        return [f"    - Erro ao formatar conteúdo de localização: {e}"]


def _format_status_content(content_body: bytes) -> list[str]:
    """Função auxiliar para formatar os campos de um pacote de status/heartbeat."""
    try:
        parts = []
        term_info, voltage_level, gsm_signal, alarm_lang = struct.unpack('>BBBH', content_body[:5])
        
        # Terminal Info Byte
        acc = "Ligada" if (term_info >> 1) & 1 else "Desligada"
        parts.append(f"    - [Terminal Info] Ignição: {acc}")
        
        # Voltage Level
        VOLTAGE_LEVELS = {0:"Sem Bateria", 1:"Extremamente Baixa", 2:"Muito Baixa (Alarme)", 3:"Baixa", 4:"Média", 5:"Alta", 6:"Muito Alta"}
        parts.append(f"    - Nível de Bateria: {voltage_level} ({VOLTAGE_LEVELS.get(voltage_level, 'Desconhecido')})")
        
        # GSM Signal
        GSM_LEVELS = {0:"Sem Sinal", 1:"Extremamente Fraco", 2:"Muito Fraco", 3:"Bom", 4:"Forte"}
        parts.append(f"    - Sinal GSM: {gsm_signal} ({GSM_LEVELS.get(gsm_signal, 'Desconhecido')})")

        # Alarm
        alarm_code = alarm_lang >> 8
        ALARM_CODES = {0x01: "SOS", 0x02: "Corte de Energia", 0x06: "Excesso de Velocidade"}
        if alarm_code != 0:
            parts.append(f"    - Alarme Ativo: {ALARM_CODES.get(alarm_code, f'Código {hex(alarm_code)}')}")

        return parts
    except Exception as e:
        return [f"    - Erro ao formatar conteúdo de status: {e}"]


def format_vl01_packet_for_display(packet_body: bytes) -> str:
   """
   Formata o corpo de um pacote VL01 para exibição legível em logs.
   """
   try:
       length = packet_body[0]
       protocol = packet_body[1]
       serial = struct.unpack('>H', packet_body[-4:-2])[0]
       crc = struct.unpack('>H', packet_body[-2:])[0]
       content_body = packet_body[2:-4]

       display_str = [
           "--- Pacote VL01 Recebido ---",
           f"  Protocolo: {hex(protocol)}",
           f"  Tamanho Declarado: {length}",
           f"  Serial: {serial}",
           f"  CRC: {hex(crc)}",
           f"  Corpo (raw): {content_body.hex()}",
           "--- Detalhes do Conteúdo ---"
       ]

       if protocol == 0x01: # Login
           display_str.append("  Tipo: Pacote de Login")
           display_str.append(f"    - IMEI: {content_body.hex()}")
       
       elif protocol in [0x12, 0x22, 0xA0, 0x32]: # Localização
           display_str.append(f"  Tipo: Pacote de Localização ({hex(protocol)})")
           display_str.extend(_format_location_content(content_body))

       elif protocol == 0x13: # Heartbeat
           display_str.append("  Tipo: Pacote de Heartbeat (Status)")
           display_str.extend(_format_status_content(content_body))

       elif protocol == 0x95: # Alarme
           display_str.append("  Tipo: Pacote de Alarme")
           location_part = content_body[:32]
           status_part = content_body[32:]
           display_str.append("  [Dados de Localização do Alarme]")
           display_str.extend(_format_location_content(location_part))
           display_str.append("  [Dados de Status do Alarme]")
           display_str.extend(_format_status_content(status_part))

       else:
           display_str.append(f"  Tipo: Desconhecido ({hex(protocol)})")
       
       display_str.append("-----------------------------")
       return "\n".join(display_str)

   except Exception as e:
       return f"!!! Erro ao formatar pacote VL01: {e} | Pacote (raw): {packet_body.hex()} !!!"