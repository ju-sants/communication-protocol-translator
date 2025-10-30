def get_dinamic_field(packet: bytes, start: int):
    
    first_byte = packet[start]
    if first_byte < 224:
        field_length = 1
    else:
        field_length = 2

    end = start + field_length

    field_value = int.from_bytes(packet[start:end], "big")

    if field_length == 2:
        field_value &= 0x1FFF

    return field_value, end