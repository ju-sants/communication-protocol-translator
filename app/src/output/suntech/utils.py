from datetime import datetime

from app.core.logger import get_logger
from app.services.redis_service import get_redis

logger = get_logger(__name__)
redis_client = get_redis()

def build_login_packet(dev_id_str: str) -> bytes:
    """Constrói um pacote de Manutenção (MNT) para 'apresentar' o dispositivo."""

    device_info = redis_client.hgetall(dev_id_str)

    sw_ver = "Poliglot"
    if device_info and device_info.get("protocol"):
        sw_ver = str(device_info.get("protocol", "")).upper()
    
    sw_ver += "_Translator_2.0"

    packet_str = f"MNT;{dev_id_str};{sw_ver}"
    logger.info(f"Construído pacote de apresentação MNT, pacote={packet_str}")
    return packet_str.encode('ascii')

def build_location_packet(dev_id: str, packet_data: dict, serial: int) -> bytes:
    """Função central para construir pacotes Suntech STT e ALT, agora com suporte a ID de geocerca."""
    
    hdr = packet_data.get("hdr")
    is_realtime = packet_data.get("is_realtime")
    alert_id = packet_data.get("alert_id")
    geo_fence_id = packet_data.get("geo_fence_id")
    voltage_stored = packet_data.get("voltage_stored")

    logger.debug(
        f"Construindo pacote Suntech: HDR={hdr}, DevID={dev_id}, Realtime={is_realtime}, "
        f"AlertID={alert_id}, GeoFenceID={geo_fence_id}, LocationData={packet_data}"
    )
    
    dev_id_normalized = ''.join(filter(str.isdigit, dev_id))

    # Campos básicos (comuns a todos)
    base_fields = [
        hdr,
        dev_id_normalized[-10:],
        "FFF83F",
        "218",
        "1.0.12",
        "1" if is_realtime else "0",
        packet_data['timestamp'].strftime('%Y%m%d'),
        packet_data['timestamp'].strftime('%H:%M:%S'),
        f"+{packet_data['latitude']:.6f}" if packet_data['latitude'] >= 0 else f"{packet_data['latitude']:.6f}",
        f"+{packet_data['longitude']:.6f}" if packet_data['longitude'] >= 0 else f"{packet_data['longitude']:.6f}",
        f"{packet_data['speed_kmh']:.2f}",
        f"{packet_data['direction']:.2f}",
        str(packet_data.get('satellites', 15)),
        "1" if packet_data.get('gps_fixed') else "0",
        f"0000000{int(packet_data.get('acc_status', 0))}",
        f"0000000{redis_client.hget(dev_id, 'last_output_status') if redis_client.hget(dev_id, 'last_output_status') else '0'}"
    ]

    # Campos de telemetria extra (Assign Headers)
    assign_map = "00028003"
    
    voltage = None
    if not voltage_stored:
        voltage = str(packet_data.get("voltage", "1.11"))
    elif voltage_stored and not is_realtime:
        voltage = str(packet_data.get("voltage", "1.11"))
    elif voltage_stored and is_realtime:
        voltage = redis_client.hget(dev_id, "last_voltage")
        
    telemetry_fields = [
        assign_map,
        voltage if voltage else "1.11", # PWR_VOLT
        "0.0",   # BCK_VOLT
        str(int(packet_data.get('gps_odometer', 0))), # GPS_ODOM
        "1"  # H_METER
    ]

    # Montagem    
    fields = base_fields

    if hdr == "STT":
        mode = "0" if redis_client.hget(dev_id, 'last_output_status') else "1"
        stt_rpt_type = "1"

        suntech_serial = serial % 10000
        msg_num = f"{suntech_serial:04d}"
        reserved = ""
        
        fields.extend([mode, stt_rpt_type, msg_num, reserved])
        fields.extend(telemetry_fields)
    
    elif hdr == "ALT":
        alert_mod = str(geo_fence_id) if alert_id in [5, 6] and geo_fence_id is not None else ""
        
        fields.extend([str(alert_id), alert_mod, "", ""]) # ALERT_ID, ALERT_MOD, ALERT_DATA, RESERVED
        fields.extend(telemetry_fields)
    
    packet = ";".join(fields)
    logger.debug(f"Pacote Suntech final construído: {packet}")
    return packet.encode("ascii")


def build_heartbeat_packet(dev_id: str, *args) -> str:
    """Constrói um pacote Keep-Alive (ALV) da Suntech."""
    dev_id_normalized = ''.join(filter(str.isdigit, dev_id))
    cutted_dev_id = dev_id_normalized[-10:]

    packet = f"ALV;{cutted_dev_id}"
    logger.debug(f"Construído pacote Suntech ALV: {packet}")
    return packet.encode("ascii")

def build_reply_packet(dev_id: str, packet_data: dict) -> str:
    """
    Constrói um pacote de Resposta (RES) rico em dados, como o observado nos logs.
    """
    cmd_group = command_parts[2]
    cmd_action = command_parts[3]

    # O formato de timestamp no RES é diferente do STT
    ts = packet_data.get('timestamp', datetime.now())
    date_fields = [ts.strftime('%Y'), ts.strftime('%m'), ts.strftime('%d'), ts.strftime('%H:%M:%S')]

    mode = "0" if redis_client.hget(dev_id, 'last_output_status') else "1"

    dev_id_normalized = ''.join(filter(str.isdigit, dev_id))

    packet_fields = [
        "RES",
        dev_id_normalized[-10:],
        cmd_group,
        cmd_action,
        *date_fields,
        packet_data.get('cell_id', '0'),
        f"{packet_data.get('latitude', 0.0):.6f}",
        f"{packet_data.get('longitude', 0.0):.6f}",
        f"{packet_data.get('speed_kmh', 0.0):.2f}",
        f"{packet_data.get('direction', 0.0):.2f}",
        str(packet_data.get('satellites', 0)),
        "1" if packet_data.get('gps_fixed', 0) else "0",
        str(int(packet_data.get('gps_odometer', 0))),
        str(packet_data.get('power_voltage', 0.0)),
        f"0000000{int(packet_data.get('acc_status', 0))}",
        f"0000000{redis_client.hget(dev_id, 'last_output_status') if redis_client.hget(dev_id, 'last_output_status') else '0'}",
        mode,
        "0"  # ERR_CODE
    ]
    
    packet = ";".join(packet_fields)
    logger.info(f"Construído pacote de Resposta (RES): {packet}")
    return packet
