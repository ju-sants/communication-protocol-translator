from app.core.logger import get_logger

logger = get_logger(__name__)

def build_suntech_packet(hdr: str, dev_id: str, location_data: dict, is_realtime: bool, alert_id: int = None, geo_fence_id: int = None) -> str:
    """Função central para construir pacotes Suntech STT e ALT, agora com suporte a ID de geocerca."""
    logger.debug(
        f"Construindo pacote Suntech: HDR={hdr}, DevID={dev_id}, Realtime={is_realtime}, "
        f"AlertID={alert_id}, GeoFenceID={geo_fence_id}, LocationData={location_data}"
    )
    
    # Campos básicos sempre presentes
    msg_type = "1" if is_realtime else "0"
    date = location_data['timestamp'].strftime('%Y%m%d')
    time = location_data['timestamp'].strftime('%H:%M:%S')
    lat = f"+{location_data['latitude']:.6f}" if location_data['latitude'] >= 0 else f"{location_data['latitude']:.6f}"
    lon = f"+{location_data['longitude']:.6f}" if location_data['longitude'] >= 0 else f"{location_data['longitude']:.6f}"
    spd = f"{location_data['speed_kmh']:.2f}"
    crs = f"{location_data['direction']:.2f}"
    satt = "10" # Valor padrão
    fix = "1" if (location_data['status_bits'] & 0b10) else "0"
    ign_on = (location_data['status_bits'] & 0b1)
    in_state = f"0000000{int(ign_on)}"
    
    fields = [hdr, dev_id]
    
    if hdr in ["STT", "ALT"]:
        fields.extend([msg_type, date, time, lat, lon, spd, crs, satt, fix, in_state])
        if hdr == "ALT":
            alert_mod = ""
            # Se for um alerta de geocerca e tivermos o ID, usamos como ALERT_MOD
            if alert_id in [5, 6] and geo_fence_id is not None:
                alert_mod = str(geo_fence_id)
            
            fields.append(str(alert_id)) # ALERT_ID
            fields.append(alert_mod)     # ALERT_MOD
            fields.append("")            # ALERT_DATA
    
    if 'gps_odometer' in location_data:
        gps_odom_meters = int(location_data['gps_odometer'])
        fields.append(str(gps_odom_meters))

    packet = ";".join(fields)
    logger.debug(f"Pacote Suntech construído: {packet}")
    return packet


def build_suntech_alv_packet(dev_id: str) -> str:
    """Constrói um pacote Keep-Alive (ALV) da Suntech."""
    packet = f"ALV;{dev_id}"
    logger.debug(f"Construído pacote Suntech ALV: {packet}")
    return packet

