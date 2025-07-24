import struct

from . import builder, mapper
from app.core.logger import get_logger


logger = get_logger(__name__)

CRC_TABLE = []

def precompute_crc_table():
    global CRC_TABLE

    if len(CRC_TABLE) == 256:
        return
    
    polynomial = 0x1021
    for i in range(256):
        crc = 0
        c = i << 8

        for j in range(8):
            if (crc ^ c) & 0x8000:
                crc = (crc << 1) ^ polynomial
            else:
                crc = crc << 1
            
            c = c << 1
        CRC_TABLE.append(crc & 0xFFFF)

precompute_crc_table()


def crc16_itu(data: bytes) -> int:
    crc = 0
    for byte in data:
        crc = ((crc << 8) & 0xFF00) ^ CRC_TABLE[((crc >> 8) & 0xFF) ^ byte]
    return crc & 0xFFFF