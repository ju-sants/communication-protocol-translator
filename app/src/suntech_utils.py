import socket

from app.core.logger import get_logger
from app.config.settings import settings

logger = get_logger(__name__)


def build_suntech_mnt_packet(dev_id_str: str) -> bytes:
    """Constrói um pacote de Manutenção (MNT) para 'apresentar' o dispositivo."""
    sw_ver = "JT808_Translator_1.0"
    packet_str = f"MNT;{dev_id_str};{sw_ver}"
    logger.info(f"Construído pacote de apresentação MNT, pacote={packet_str}")
    return packet_str.encode('ascii')

def build_suntech_packet(hdr: str, dev_id: str, location_data: dict, serial: int, is_realtime: bool, alert_id: int = None, geo_fence_id: int = None) -> str:
    """Função central para construir pacotes Suntech STT e ALT, agora com suporte a ID de geocerca."""
    logger.debug(
        f"Construindo pacote Suntech: HDR={hdr}, DevID={dev_id}, Realtime={is_realtime}, "
        f"AlertID={alert_id}, GeoFenceID={geo_fence_id}, LocationData={location_data}"
    )
    
    # Campos básicos (comuns a todos)
    base_fields = [
        hdr,
        dev_id[-10:],
        "FFF83F",
        "218",
        "1.0.12",
        "1" if is_realtime else "0",
        location_data['timestamp'].strftime('%Y%m%d'),
        location_data['timestamp'].strftime('%H:%M:%S'),
        f"{location_data['latitude']:.6f}",
        f"{location_data['longitude']:.6f}",
        f"{location_data['speed_kmh']:.2f}",
        f"{location_data['direction']:.2f}",
        str(location_data.get('satellites', 15)),
        "1" if (location_data.get('status_bits', 0) & 0b10) else "0",
        f"0000000{int(location_data.get('status_bits', 0) & 0b1)}",
        f"0000000{int((location_data.get('status_bits', 0) >> 10) & 1)}"
    ]
    
    # Campos de telemetria extra (Assign Headers)
    assign_map = "00028003"
    
    telemetry_fields = [
        assign_map,
        "12.43", # PWR_VOLT
        "0.0",   # BCK_VOLT
        str(int(location_data.get('gps_odometer', 0))), # GPS_ODOM
        "69647"  # H_METER
    ]

    # Montagem    
    fields = base_fields

    if hdr == "STT":
        ign_on = (location_data.get('status_bits', 0) & 0b1)
        mode = "1" if ign_on else "0"
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
    return packet


def build_suntech_alv_packet(dev_id: str) -> str:
    """Constrói um pacote Keep-Alive (ALV) da Suntech."""
    cutted_dev_id = dev_id[-10:]

    packet = f"ALV;{cutted_dev_id}"
    logger.debug(f"Construído pacote Suntech ALV: {packet}")
    return packet



def process_suntech_command(command: str, dev_id: str, serial: str):
    from app.src.jt808_utils import build_jt808_command

    logger.info(f"Processando comando suntech, dev_id={dev_id}")

    parts = command.split(';')

    command_key = f"{parts[0]};{parts[2]};{parts[3]}"

    command_mapping = {
        "CMD;04;01": (0x8105, b"\x64"),
        "CMD;04;02": (0x8105, b"\x65"),
        "CMD;03;01": (0x8201, b""),
    }

    jt808_command = None
    if command_key in command_mapping:
        params = command_mapping[command_key]
        jt808_command = build_jt808_command(dev_id, int(serial), *params)

    if jt808_command:
        with settings.jt808_clients_lock:
            if dev_id in settings.jt808_clients:
                tracker_socket: socket.socket = settings.jt808_clients[dev_id]

                try:
                    tracker_socket.sendall(jt808_command)
                    logger.info(f"Comando JT/T 808 enviado para o rastreador device_id={dev_id}")
                except Exception:
                    logger.exception(f"Falha ao enviar comando para o rastreador device_id={dev_id}")
            else:
                logger.warning(f"Rastreador não está conectado, não foi possível enviar comando device_id={dev_id}")
