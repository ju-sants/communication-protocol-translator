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