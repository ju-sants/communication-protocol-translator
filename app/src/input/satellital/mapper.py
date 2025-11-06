import json
from datetime import datetime
import copy
from dateutil import parser

from app.core.logger import get_logger
from app.services.redis_service import get_redis
from ..utils import handle_ignition_change, haversine
from . import utils
from app.src.session.input_sessions_manager import input_sessions_manager
from app.src.session.output_sessions_manager import output_sessions_manager


logger = get_logger(__name__)
redis_client = get_redis()


def handle_satelite_data(raw_satellite_data: bytes):
    """
    Maps satellital data to a structured python dict and sends it to the main server.
    """
    try:
        satellite_data = json.loads(raw_satellite_data)

        # Verificando se o campo ESN está presente.
        esn = satellite_data.get("ESN")
        if not esn:
            logger.info(f"Message received without ESN, dropping.")
            return None, None, None, None
        
        # Updating Satellite trackers set
        satellite_set = redis_client.smembers("satellite_trackers:set")
        if esn not in satellite_set:
            redis_client.sadd("satellite_trackers:set", esn)
            satellite_set = None

        # Verificando se o mesmo é híbrido.
        gsm_dev_id = redis_client.hget("SAT_GSM_MAPPING", esn)
        is_hybrid = bool(gsm_dev_id)

        output_dev_id = gsm_dev_id if is_hybrid else esn

        if satellite_data.get("message_type") == "heartbeat":
            logger.info(f"HeartBeat Message Received")

            # Apenas enviamos pacotes de heartbeat se não for híbrido, pois se for quem manda é o GSM.
            if not is_hybrid:
                return output_dev_id, satellite_data, None, 0        
            else: return None, None, None, None


        logger.info(f"Parsed Satellite Location data: {satellite_data}")

        last_serial = 0
        speed_filter = None

        pipe = redis_client.pipeline()
        
        if is_hybrid:
            logger.info("Satellite tracker with a GSM pair, initiating hybrid location.")
            pipe.hset(f"tracker:{esn}", "mode", "hybrid")

            last_serial, last_location_str, last_merged_location_str, speed_filter = redis_client.hmget(f"tracker:{gsm_dev_id}", "last_serial", "last_packet_data", "last_merged_location", "speed_filter")
            
            last_serial = int(last_serial) if last_serial else 0
            gsm_last_location = json.loads(last_location_str)

            # Obtendo a última localização GSM/SAT conhecida
            # Se o GSM está conectado e enviando pacotes em tempo real, usaremos o pacote do GSM. Caso o GSM não esteja conectado nem mandando pacotes em tempo real
            # Mas Ainda não temos um "last_merged_location" (que seria um pacote do SAT) também usaremos o pacote do GSM.
            gsm_connection_condition = input_sessions_manager.exists(gsm_dev_id) and output_sessions_manager.is_sending_realtime_location(gsm_dev_id)
            if gsm_connection_condition or not last_merged_location_str:
                last_location = gsm_last_location
            else:
                # Caso o GSM esteja offline ou sem mandar pacotes em tempo real, E, temos um pacote do SAT salvo "last_merged_location" usamos ele.
                last_location = json.loads(last_merged_location_str)

            # Caso o GSM não esteja conectado, ou não esteja enviando pacotes em tempo real
            # Calculemos o odometro a partir da diferença entre pares de LAT E LONG
            if not gsm_connection_condition:
                last_odometer = float(last_location.get("gps_odometer")) if last_location.get("gps_odometer") else 0.0

                last_lat, last_long = last_location.get("latitude"), last_location.get("longitude")
                new_lat, new_long = satellite_data.get("latitude"), satellite_data.get("longitude")
                
                to_add_odometer = haversine(last_lat, last_long, new_lat, new_long)

                new_odometer = last_odometer + (to_add_odometer * 1000)

                last_location["gps_odometer"] = new_odometer
                
        else:
            logger.info("Standalone satellital tracker, initiating standalone location.")
            mapping = {
                "mode": "solo",
                "last_output_status": 0,
            }
            pipe.hmset(f"tracker:{esn}", mapping)
            pipe.hset(f"tracker:{esn}", "protocol", "satellital")

            last_location_str, speed_filter = redis_client.hmget(f"tracker:{esn}", "last_merged_location", "speed_filter")
            if not last_location_str:
                # Não há um pacote salvo, iniciando com pacote padrão
                gps_odometer = utils.get_sat_odometer_from_previous_host(esn)
                last_location = {
                    "gps_fixed": 1,
                    "is_realtime": False,
                    "output_status": 0,
                    "gps_odometer": gps_odometer if gps_odometer else 0,
                }
                
            else:
                last_location = json.loads(last_location_str)
                last_lat, last_long = last_location.get("latitude"), last_location.get("longitude")
                new_lat, new_long = satellite_data.get("latitude"), satellite_data.get("longitude")

                if all([last_lat, new_lat, last_long, new_long]):
                    last_odometer = float(last_location.get("gps_odometer")) if last_location.get("gps_odometer") else 0.0
                    to_add_odometer = haversine(last_lat, last_long, new_lat, new_long)

                    odometer = last_odometer + (to_add_odometer * 1000)

                    last_location["gps_odometer"] = odometer
                

        last_merged_location = {**last_location, **satellite_data}
        last_merged_location["device_type"] = "satellital"
        
        last_merged_location["voltage"] = 2.22
        last_merged_location["satellites"] = 2
        last_merged_location["timestamp"] = parser.parse(satellite_data.get("timestamp"), ignoretz=True)
        last_merged_location["is_realtime"] = False

        # FIltro de velocidade para ALTAS velocidades
        if speed_filter and speed_filter.isdigit():
            speed_filter = int(speed_filter)
            actual_speed = int(last_merged_location.get("speed_kmh", 0))
            if actual_speed > speed_filter:
                last_merged_location["speed_kmh"] = 0
                last_merged_location["satellites"] = 1
                last_merged_location["voltage"] = 3.33

        # Filtro de velocidade para IGN DESLIGADA
        if last_merged_location["acc_status"] == 0 and last_merged_location["speed_kmh"] < 5:
            last_merged_location["speed_kmh"] = 0

        
        # Normalização para salvamento no redis
        redis_last_merged_location = copy.deepcopy(last_merged_location)
        redis_last_merged_location["timestamp"] = redis_last_merged_location["timestamp"].strftime("%Y-%m-%dT%H:%M:%S")

        redis_data = {
            "last_satellite_location": json.dumps(satellite_data),
            "last_satellite_active_timestamp": datetime.now().isoformat(),
            "last_merged_location": json.dumps(redis_last_merged_location)
        }


        ign_alert_packet_data = None
        # Lidando com o estado da ignição, muito preciso para veículos híbridos.
        last_altered_acc_str = redis_client.hget(f"tracker:{gsm_dev_id if is_hybrid else esn}", "last_altered_acc")
        if last_altered_acc_str:
            last_altered_acc_dt = parser.parse(last_altered_acc_str, ignoretz=True) 

        if not last_altered_acc_str or (last_merged_location.get("timestamp") and last_altered_acc_dt < last_merged_location.get("timestamp")):
            # Lidando com mudanças no status da ignição
            ign_alert_packet_data = handle_ignition_change(gsm_dev_id if is_hybrid else esn, copy.deepcopy(last_merged_location))

            redis_data["acc_status"] = last_merged_location.get("acc_status")
            redis_data["last_altered_acc"] = last_merged_location.get("timestamp").isoformat()

        actual_month = datetime.now().month

        pipe.rpush(f"payloads:{esn}", json.dumps(satellite_data))
        pipe.ltrim(f"payloads:{esn}", 0, 10000)
        pipe.hincrby(f"monthly_counts:{esn}", actual_month, 1)
        
        pipe.hmset(f"tracker:{gsm_dev_id}", redis_data)
        pipe.hmset(f"tracker:{esn}", redis_data)

        pipe.execute()

        return output_dev_id, last_merged_location, ign_alert_packet_data, last_serial 
    
    except json.JSONDecodeError as e:
        logger.error(f"Failed to decode JSON: {e}")
        return None, None, None, None
    except Exception as e:
        logger.error(f"Error mapping data: {e}")
        return None, None, None, None