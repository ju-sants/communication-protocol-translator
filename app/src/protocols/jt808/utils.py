import struct

def unescape_data(data: bytes) -> bytes:
    """Remove o escape de bytes 0x7d e 0x7e de um pacote JT/T 808."""
    data = data.replace(b'\x7d\x01', b'\x7d')
    data = data.replace(b'\x7d\x02', b'\x7e')
    return data

def escape_data(data: bytes) -> bytes:
    data = data.replace(b"\x7d", b"\x7d\x01")
    data = data.replace(b"\x7e", b"\x7d\x02")

    return data

def verify_checksum(raw_msg: bytes) -> bool:
    """Calcula e verifica o checksum (XOR) de uma mensagem JT/T 808."""
    message_data = raw_msg[:-1]
    expected_checksum = raw_msg[-1]
    
    calculated_checksum = 0
    for byte in message_data:
        calculated_checksum ^= byte
        
    return calculated_checksum == expected_checksum

def calculate_checksum(raw_message: bytes):
    checksum = 0
    for byte in raw_message:
        checksum ^= byte

    return struct.pack(">B", checksum)