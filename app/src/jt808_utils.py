import struct

def unescape_data(data: bytes) -> bytes:
    """Remove o escape de bytes 0x7d e 0x7e de um pacote JT/T 808."""
    data = data.replace(b'\x7d\x01', b'\x7d')
    data = data.replace(b'\x7d\x02', b'\x7e')
    return data

def verify_checksum(raw_msg: bytes) -> bool:
    """Calcula e verifica o checksum (XOR) de uma mensagem JT/T 808."""
    message_data = raw_msg[:-1]
    expected_checksum = raw_msg[-1]
    
    calculated_checksum = 0
    for byte in message_data:
        calculated_checksum ^= byte
        
    return calculated_checksum == expected_checksum

def build_jt808_response(terminal_phone: bytes, terminal_serial: int, msg_id: int, result: int) -> bytes:
    """Constrói uma resposta padrão (0x8001) para o dispositivo JT/T 808."""
    msg_id_resp = 0x8001
    body_props = 5 # Corpo da resposta tem 5 bytes
    server_serial = terminal_serial # Ecoa o serial do terminal

    # Monta o cabeçalho e o corpo da resposta
    header = struct.pack('>HH', msg_id_resp, body_props) + terminal_phone + struct.pack('>H', server_serial)
    body = struct.pack('>HHB', terminal_serial, msg_id, result)
    
    raw_message = header + body
    
    # Calcula o checksum
    checksum = 0
    for byte in raw_message:
        checksum ^= byte
        
    final_message = raw_message + struct.pack('>B', checksum)
    
    # Realiza o escape de bytes
    final_message = final_message.replace(b'\x7d', b'\x7d\x01')
    final_message = final_message.replace(b'\x7e', b'\x7d\x02')
    
    # Delimita a mensagem com 0x7e
    return b'\x7e' + final_message + b'\x7e'