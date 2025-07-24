import struct
from . import builder, mapper

from app.core.logger import get_logger
from app.src.protocols.jt808.mapper import decode_location_packet

logger = get_logger(__name__)

def format_jt808_packet_for_display(unescaped_packet: bytes) -> str:
   """Formata um pacote JT/T 808 para exibição legível."""
   if len(unescaped_packet) < 13:
       return f"Pacote inválido (muito curto): {unescaped_packet.hex()}"

   try:
       # 1. Decodificar o Cabeçalho
       header_bytes = unescaped_packet[:12]
       msg_id, body_props, terminal_phone_bcd, serial = struct.unpack('>HH6sH', header_bytes)
       dev_id_str = terminal_phone_bcd.hex()

       # 2. Extrair Corpo e Checksum
       body = unescaped_packet[12:-1]
       checksum = unescaped_packet[-1]

       # 3. Construir a String de Saída
       display_str = [
           "--- Pacote JT/T 808 Recebido ---",
           f"  Device ID (Celular BCD): {dev_id_str}",
           f"  ID da Mensagem: {hex(msg_id)}",
           f"  Serial da Mensagem: {serial}",
           f"  Checksum: {hex(checksum)}",
           f"  Tamanho do Corpo: {len(body)} bytes",
           f"  Corpo (raw): {body.hex()}",
           "--- Detalhes do Corpo ---"
       ]

       # 4. Decodificar o Corpo com base no ID da Mensagem
       if msg_id == 0x0100:
           display_str.append("  Tipo: Registro de Terminal")
           try:
               province_id, city_id, manufacturer_id, terminal_model, terminal_id, color, plate = struct.unpack('>HH5s20s7sB', body[:37])
               display_str.append(f"    - ID Província: {province_id}")
               display_str.append(f"    - ID Cidade: {city_id}")
               display_str.append(f"    - Fabricante: {manufacturer_id.decode('ascii', errors='ignore').strip()}")
               display_str.append(f"    - Modelo: {terminal_model.decode('ascii', errors='ignore').strip()}")
               display_str.append(f"    - ID Terminal: {terminal_id.decode('ascii', errors='ignore').strip()}")
               display_str.append(f"    - Cor da Placa: {color}")
               # O restante é a placa, se houver
               if len(body) > 37:
                   display_str.append(f"    - Placa: {body[37:].decode('gbk', errors='ignore')}")
           except Exception as e:
               display_str.append(f"    - Erro ao decodificar corpo do registro: {e}")
       elif msg_id == 0x0102:
           display_str.append("  Tipo: Autenticação de Terminal")
           display_str.append(f"    - Token de Autenticação: {body.hex()}")
       elif msg_id == 0x0002:
           display_str.append("  Tipo: Heartbeat (Keep-Alive)")
       elif msg_id == 0x0200:
           display_str.append("  Tipo: Report de Localização")
           location_data = decode_location_packet(body)
           if location_data:
               for key, value in location_data.items():
                   display_str.append(f"    - {key}: {value}")
           else:
               display_str.append("    - Falha ao decodificar os dados de localização.")
       elif msg_id == 0x0704:
           display_str.append("  Tipo: Report de Localização em Lote (Área Cega)")
           try:
               total_reports = struct.unpack('>H', body[:2])[0]
               display_str.append(f"    - Total de Reports: {total_reports}")
               
               offset = 3 # Pula total e tipo de dados
               for i in range(total_reports):
                   if offset + 2 > len(body):
                       break
                   report_len = struct.unpack('>H', body[offset:offset+2])[0]
                   offset += 2
                   
                   if offset + report_len > len(body):
                       break
                   report_body = body[offset:offset+report_len]
                   offset += report_len
                   
                   display_str.append(f"    --- Report Histórico {i+1}/{total_reports} ---")
                   loc_data = decode_location_packet(report_body)
                   if loc_data:
                       for key, value in loc_data.items():
                           display_str.append(f"        - {key}: {value}")
                   else:
                       display_str.append("        - Falha ao decodificar o report.")

           except Exception as e:
               display_str.append(f"    - Erro ao decodificar o lote: {e}")
       else:
           display_str.append(f"  Tipo: Mensagem não mapeada ({hex(msg_id)})")
       
       display_str.append("---------------------------------")
       
       return "\n".join(display_str)

   except Exception as e:
       return f"Erro ao formatar pacote: {e}\nPacote (raw): {unescaped_packet.hex()}"

def process_packet(unescaped_packet: bytes) -> bytes | None:
    """Extrai dados do pacote, envia para o mapper e retorna a resposta do builder."""
    header_bytes = unescaped_packet[:12]
    msg_id, _, terminal_phone_bcd, serial = struct.unpack('>HH6sH', header_bytes)
    body = unescaped_packet[12:-1]
    dev_id_str = terminal_phone_bcd.hex()

    logger.debug("Processando pacote JT/T 808", device_id=dev_id_str, msg_id=hex(msg_id))

    # Envia os dados para o mapper, que fará a tradução e encaminhamento
    mapper.map_and_forward(dev_id_str, serial, msg_id, body)

    # Constrói e retorna a resposta ACK para o dispositivo
    return builder.build_ack_response(terminal_phone_bcd, serial, msg_id, result=0)