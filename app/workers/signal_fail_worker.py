import json
import schedule
import time

from app.services.redis_service import get_redis
from app.utils.api_client import get_vehicle_data_from_tracker_id
from app.core.logger import get_logger
from app.src.output.utils import get_output_dev_id
from . import utils

logger = get_logger(__name__)
redis_client_gateway = get_redis()
redis_client_data = get_redis(db=3)

def signal_fail_worker():
    scheduled_work()

    schedule.every(2).hours.do(scheduled_work)

    while True:
        schedule.run_pending()
        time.sleep(60)

def scheduled_work():
    with logger.contextualize(log_label="SIGNAL FAIL WORKER"):
        try:            
            tracker_keys = list(redis_client_gateway.scan_iter("tracker:*", count=1000))
            
            failing_trackers_str = set(redis_client_data.smembers("translator_server:failing_trackers"))
            failing_trackers = [json.loads(fail) for fail in failing_trackers_str]
            
            to_add_to_failing = set()
            to_remove_from_failing = set()
            
            with redis_client_gateway.pipeline() as pipe:
                for key in tracker_keys:
                    pipe.hmget(key, "is_hybrid", "hybrid_id", "last_packet_data", "last_hybrid_location")
                
                all_trackers_data = pipe.execute()
                
            for i, tracker_data in enumerate(all_trackers_data):
                
                is_hybrid = tracker_data[0]
                hybrid_id = tracker_data[1]
                last_gsm_location_str = tracker_data[2]
                last_hybrid_location_str = tracker_data[3]

                # Se não for um veículo híbrido, dropamos
                if not is_hybrid and not hybrid_id:
                    continue

                if not last_gsm_location_str or not last_hybrid_location_str:
                    logger.error(f"Pacotes de dados inválidos! \n{last_hybrid_location_str}\n{last_gsm_location_str}")
                    continue

                last_gsm_location = json.loads(last_gsm_location_str)
                last_hybrid_location = json.loads(last_hybrid_location_str)
                
                gsm_last_timestamp = last_gsm_location.get("timestamp")
                satellite_last_timestamp = last_hybrid_location.get("timestamp")
                both_failed = all(
                                    (utils.is_signal_fail(gsm_last_timestamp), utils.is_signal_fail(satellite_last_timestamp))
                                )

                # Se temos uma falha em ambos os rastreadores, adicionamos apenas o registro do satelital (regras específicas de negócio)
                if both_failed:
                    packets_to_check = (last_hybrid_location,)
                else:
                    packets_to_check = (last_gsm_location, last_hybrid_location)

                for packet in packets_to_check:
                    if packet:
                        try:
                            timestamp_str = packet.get("timestamp")
                            
                            if timestamp_str:
                                key = tracker_keys[i]
                                if float(packet.get("voltage", 0.0)) == 2.22 and int(packet.get("satellites", 0)) == 2:
                                    key = "satellite|" + key

                                is_signal_fail = utils.is_signal_fail(timestamp_str)
                                if is_signal_fail and not any(key == fail.get("tracker_label") for fail in failing_trackers):
                                    to_add_to_failing.add(key)
                                    logger.info(f"Tracker {key} está a mais de 24horas sem comunicar. Marcando para adicionar aos registros de falha.")

                                elif not is_signal_fail:
                                    if any(key == fail.get("tracker_label") for fail in failing_trackers):
                                        to_remove_from_failing.add(key)
                                        logger.info(f"Tracker {key} voltou a comunicar. Marcando para retirar dos registros de falha.")
                                    

                        except (json.JSONDecodeError, KeyError, TypeError) as e:
                            logger.error(f"Error processing tracker data for key {tracker_keys[i]}: {e}")

            update_failing_trackers_list(to_add_to_failing, to_remove_from_failing)
                
            logger.info(f"Signal fail worker finished. Added: {len(to_add_to_failing)}, Removed: {len(to_remove_from_failing)}")

        except Exception as e:
            logger.error(f"An error occurred in the signal fail worker: {e}")


def update_failing_trackers_list(to_add_to_failing, to_remove_from_failing):

    if to_remove_from_failing:
        all_failing_trackers = redis_client_data.smembers("translator_server:failing_trackers")

        pipe = redis_client_data.pipeline()
        removed_count = 0
        for failing_tracker_str in all_failing_trackers:
            failing_tracker = json.loads(failing_tracker_str)

            tracker_label = failing_tracker.get("tracker_label")
            if tracker_label in to_remove_from_failing:
                pipe.srem("translator_server:failing_trackers", failing_tracker_str)
                removed_count += 1
        
        logger.info(f"Removidos {removed_count} de {len(to_remove_from_failing)} para remover.")
        
        pipe.execute()

    if to_add_to_failing:
        added_count = 0
        for tracker_label in to_add_to_failing:
            tracker_id = tracker_label.split(":")[-1]
            tracker_label_norm = tracker_label.replace("satellite|", "")

            output_protocol, is_hybrid, hybrid_id = redis_client_gateway.hmget(tracker_label_norm, "output_protocol", "is_hybrid", "hybrid_id")
            output_tracker_id = get_output_dev_id(tracker_id, output_protocol)

            vehicle_data = get_vehicle_data_from_tracker_id(output_tracker_id)

            if not vehicle_data:
                logger.error(f"Não foi possível adicionar o rastreador (dev_id={tracker_id}) aos registros de falha, não foi encontrado dados do veículo no sistema.")
                continue
            
            vehicle_details = vehicle_data.get("vehicle", {})
            last_position = vehicle_data.get("lastPosition", {})
            if not vehicle_details or not last_position:
                logger.error(f"Campo de dados importante para a operação não presente nos dados do veículo, dev_id={tracker_id} campo(s): {'vehicle' if not vehicle_details else 'lastPosition'}")
                continue
            
            owner_info = vehicle_details.get("owner", {})
            fail_register = {
                "id": vehicle_details.get("id"),
                "rastreador": vehicle_details.get("imei"),
                "fabricanteRastreador": vehicle_details.get("manufacturer_id"),
                "telefone": vehicle_details.get("chip_number"),
                "features": vehicle_details.get("features"),
                "placas": vehicle_details.get("license_plate"),
                "marca": vehicle_details.get("brand"),
                "model": vehicle_details.get("model"),
                "nome": owner_info.get("name"),
                "dataHora": last_position.get("datetime"),
                "latitude": last_position.get("latitude"),
                "longitude": last_position.get("longitude"),
                "satGps": last_position.get("satellites"),
                "ign": last_position.get("ignition"),
                "tensao": last_position.get("tension"),
                "vel": last_position.get("velocity"),
                "tracker_label": tracker_label,
                "fcel": owner_info.get("phone_number"),
                "fres": owner_info.get("residencial_number"), 
                "fcom": owner_info.get("comercial_number"),
                "hybridImei": hybrid_id,
                "hybridProtocolId": 10 if hybrid_id and is_hybrid else None,
                "isHybridVehicle": 1 if hybrid_id and is_hybrid else 0,
                "owner_id": owner_info.get("id"),
            }

            if "satellite|" in tracker_label:
                fail_register["isHybridPosition"] = True

            fail_register_str = json.dumps({k: v for k, v in fail_register.items() if v is not None})
            redis_client_data.sadd("translator_server:failing_trackers", fail_register_str)
            logger.info(f"Registro de falha adicionado ao set com sucesso! dev_id={tracker_id}, tracker_label={tracker_label}")
            added_count += 1
        
        logger.info(f"Adicionados {added_count} registros de falha nessa rodada.")