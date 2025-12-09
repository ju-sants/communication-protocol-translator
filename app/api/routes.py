import json
from flask import current_app as app, jsonify, request, make_response
from datetime import datetime
from dateutil import parser
import os
import time
import zlib

from . import utils
from app.services.redis_service import get_redis
from app.core.logger import get_logger
from app.config.settings import settings
from app.src.session.input_sessions_manager import input_sessions_manager
from app.src.session.output_sessions_manager import output_sessions_manager, send_to_main_server
from app.src.output.utils import get_output_dev_id
from app.services.history_service import get_packet_history
from app.src.input.j16x_j16.builder import build_command as build_j16x_j16_command
from app.src.input.j16w.builder import build_command as build_j16w_command
from app.src.input.vl01.builder import build_command as build_vl01_command
from app.src.input.vl03.builder import build_command as build_vl03_command
from app.src.input.nt40.builder import build_command as build_nt40_command
from app.src.input.suntech2g.builder import build_command as build_suntech2g_command
from app.src.input.suntech4g.builder import build_command as build_suntech4g_command
from app.src.input.gp900m.builder import build_command as build_gp900m_command
# from app.src.input.jt808.builder import build_command as build_jt808_command

redis_client = get_redis()
logger = get_logger(__name__)

COMMAND_BUILDERS = {
    "j16x_j16": build_j16x_j16_command,
    "vl01": build_vl01_command,
    "vl03": build_vl03_command,
    "nt40": build_nt40_command,
    "j16w": build_j16w_command,
    "gp900m": build_gp900m_command,
    "suntech2g": build_suntech2g_command,
    "suntech4g": build_suntech4g_command,
    # "jt808": build_jt808_command
}

# ==================================================================================================
# GATEWAY INFO, STATS AND TECHNICAL DATA
# ==================================================================================================

@app.route('/gateway_info', methods=['GET'])
def get_gateway_info():
    """
    Retorna informações técnicas sobre o gateway.
    """
    try:
        info = {
            "gateway_info": {
                "input_protocols": [dir.upper() for dir in os.listdir('app/src/input') if os.path.isdir(os.path.join('app/src/input', dir)) and not dir.startswith('__')],
                "output_protocols": [dir.upper() for dir in os.listdir('app/src/output') if os.path.isdir(os.path.join('app/src/output', dir)) and not dir.startswith('__')],
                "port_protocol_mapping": {
                    protocol: settings.INPUT_PROTOCOL_HANDLERS[protocol]["port"] for protocol in settings.INPUT_PROTOCOL_HANDLERS
                },
                "total_active_translator_sessions": len(input_sessions_manager.get_sessions()),
                "total_active_main_server_sessions": len(output_sessions_manager.get_sessions()),
            }
        }
    
        return jsonify(info), 200
    
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/sessions/trackers', methods=['GET'])
def get_tracker_sessions():
    """
    Returns a list of device IDs with active socket connections to the translator.
    """
    active_sessions = list(input_sessions_manager.get_sessions())
    return jsonify(active_sessions), 200

@app.route('/sessions/main-server', methods=['GET'])
def get_main_server_sessions():
    """
    Returns a list of device IDs with active sessions to the main Suntech4G server.
    """
    active_sessions = list(output_sessions_manager.get_sessions())
    return jsonify(active_sessions), 200


# ==================================================================================================
# GATEWAY TRACKERS INFORMATION
# ==================================================================================================
  
@app.route('/trackers', methods=['GET'])
def get_trackers_data():
    try:
        args = request.args

        keys = list(redis_client.scan_iter('tracker:*', count=1000) )
        if not keys:
            return jsonify({"data": {}, "message": "Nenhum rastreador encontrado."}), 204

        pipe = redis_client.pipeline()
        for key in keys:
            pipe.hgetall(key)
        
        results = pipe.execute()

        all_data = {}
        for i, key in enumerate(keys):
            device_data = results[i]
            
            key_normalized = key.split("tracker:")[-1]
            device_data['is_connected'] = input_sessions_manager.exists(key_normalized)
            device_data["output_protocol"] = device_data.get("output_protocol") or "suntech4g"
            all_data[key_normalized] = device_data

        if args:
            if args.get("zlib_compress"):
                json_bytes = json.dumps(all_data).encode("utf-8")
                zlib_compressed = zlib.compress(json_bytes)

                response = make_response(zlib_compressed)
                response.headers["Content-Encoding"] = "deflate"
                response.headers["Content-Type"] = "application/json"

                return response, 200
               
        return jsonify(all_data), 200

    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500

@app.route("/satellite_trackers", methods=["GET"])
def get_satellite_trackers():
    """
    Obtem os IDs dos dispositivos satelitais conectados ao server
    """
    satellite_set = redis_client.smembers("satellite_trackers:set") or set()

    return jsonify(list(satellite_set)), 200

@app.route('/trackers/<string:dev_id>/history', methods=['GET'])
def get_tracker_history(dev_id):
    """
    Fetches the packet history for a specific tracker.
    """
    try:
        compress = request.args.get("zlib_compress")
        history = get_packet_history(dev_id, return_compressed=True if compress else False)

        if compress:
            response = make_response(history)
            response.headers["Content-Encoding"] = "deflate"
            response.headers["Content-Type"] = "application/json"

            return response, 200
        
        return jsonify(history), 200
    
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/trackers/<string:dev_id>/details', methods=['GET'])
def get_tracker_details(dev_id):
    """
    Returns comprehensive details for a specific tracker, including Redis data and connection status.
    """
    try:
        id_type = request.args.get("id_type")
        if id_type == "output":
            output_input_ids_0Padded, output_input_ids_notPadded = utils.get_output_input_ids_map()

            dev_id = output_input_ids_0Padded.get(dev_id) or output_input_ids_notPadded.get(dev_id.lstrip("0"))

        device_data = redis_client.hgetall(f"tracker:{dev_id}")
        if not device_data:
            return jsonify({"error": "Device not found in Redis"}), 404

        status_info = {
            "device_id": dev_id,
            "imei": device_data.get('imei', dev_id),
            "protocol": device_data.get('protocol'),
            "output_protocol": device_data.get("output_protocol") or "suntech4g",
            "is_connected_translator": input_sessions_manager.exists(dev_id),
            "is_connected_main_server": dev_id in output_sessions_manager._sessions,
            "last_active_timestamp": device_data.get('last_active_timestamp'),
            "last_event_type": device_data.get('last_event_type'),
            "total_packets_received": int(device_data.get('total_packets_received', 0)),
            "last_packet_data": json.loads(device_data.get('last_packet_data', '{}')),
            "last_full_location": json.loads(device_data.get('last_full_location', '{}')),
            "odometer": float(device_data.get('odometer', 0.0)),
            "acc_status": int(device_data.get('acc_status', 0)),
            "power_status": int(device_data.get('power_status', 0)),
            "last_voltage": float(device_data.get('last_voltage', 0.0)),
            "last_command_sent": json.loads(device_data.get('last_command_sent', '{}')),
            "last_command_response": json.loads(device_data.get('last_command_response', '{}'))
        }

        status_info = {**device_data, **status_info}

        # Determine a more descriptive device_status
        if status_info["is_connected_translator"]:
            if status_info["acc_status"] == 1:
                if status_info["last_full_location"].get("speed_kmh", 0) > 0:
                    status_info["device_status"] = "Moving (Ignition On)"
                else:
                    status_info["device_status"] = "Stopped (Ignition On)"
            else:
                status_info["device_status"] = "Parked (Ignition Off)"
        else:
            status_info["device_status"] = "Offline"
        
        return jsonify(status_info), 200
    
    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


# ==================================================================================================
# GATEWAY TRACKERS ACTIONS
# ==================================================================================================

@app.route('/trackers/<string:dev_id>/command', methods=['POST'])
def send_tracker_command(dev_id):
    """
    Sends a command to a specific tracker through its active socket.
    Sends a native command directly to a specific tracker.
    """
    
    data = request.get_json()
    if not data or 'command' not in data:
        return jsonify({"error": "Command not specified in request body"}), 400

    command_str = data['command']
    
    device_info = redis_client.hgetall(f"tracker:{dev_id}")
    if not device_info:
        return jsonify({"error": "Device not found in Redis"}), 404
    
    protocol_type = device_info.get('protocol')
    serial = int(device_info.get('last_serial', 0))

    if not protocol_type:
        return jsonify({"error": f"Protocol not set for device {dev_id}"}), 500

    builder_func = COMMAND_BUILDERS.get(protocol_type)
    if not builder_func:
        return jsonify({"error": f"No command builder found for protocol '{protocol_type}'"}), 500

    try:
        with logger.contextualize(log_label=dev_id):
            command_packet = builder_func(dev_id, serial, command_str)
            
            tracker_socket = input_sessions_manager.get_session(dev_id)
            if tracker_socket:
                # Limpando estado da variável "last_command_reply" antes de enviar o comando 
                redis_client.hdel(f"tracker:{dev_id}", "last_command_reply")

                tracker_socket.sendall(command_packet)

                device_response = None
                max_retries = 5
                tries = 0
                while True:
                    if tries > max_retries:
                        break

                    device_response = redis_client.hget(f"tracker:{dev_id}", "last_command_reply")
                    if device_response:
                        redis_client.hdel(f"tracker:{dev_id}", "last_command_reply")
                        break

                    tries += 1

                    time.sleep(1)

                # Store command sent in Redis
                redis_client.hset(f"tracker:{dev_id}", "last_command_sent", json.dumps({
                    "command": command_str,
                    "timestamp": datetime.now().isoformat(),
                    "packet_hex": command_packet.hex()
                }))
                redis_client.hincrby(f"tracker:{dev_id}", "total_commands_sent", 1)

                return jsonify({
                    "status": "Command sent successfully",
                    "device_response": device_response,
                    "device_id": dev_id,
                    "command": command_str,
                    "packet_hex": command_packet.hex()
                }), 200
            
            else:
                return jsonify({"error": "Tracker is not connected"}), 503
            
    except Exception as e:
        return jsonify({"error": f"Failed to send command: {str(e)}"}), 500
    
@app.route("/trackers/<string:dev_id>/resend_last", methods=["GET"])
def resend_last_packet(dev_id: str):
    """Resends the last location packet to main server"""
    args = request.args

    if not dev_id:
        logger.error("Device id empty in resend last packet request.", log_label="API")
        return jsonify({"status": "error", "message": "please provide a valid device id."}), 400
    
    with logger.contextualize(log_label=dev_id):
        tracker_key = f"tracker:{dev_id}"
        if not redis_client.exists(tracker_key):
            logger.error(f"Device not found in Database for {dev_id}. Cannot send last packet.")
            return jsonify({"status": "error", "message": "device not found in Database."}), 404
        
        # Obtaining data
        last_packet_data_str, last_merged_location_str, input_protocol = redis_client.hmget(tracker_key, "last_packet_data", "last_merged_location", "protocol")
        last_packet_data, last_merged_location = utils.parse_json_safe(last_packet_data_str), utils.parse_json_safe(last_merged_location_str)
        
        # Date parsing
        if last_packet_data:
            last_packet_data["timestamp"] = parser.parse(last_packet_data.get("timestamp"))
        if last_merged_location:
            last_merged_location["timestamp"] = parser.parse(last_merged_location.get("timestamp"))


        # Logic to know what packet to send
        packet_to_send = args.get("packet_to_send") or "last"
        packet = None

        if packet_to_send == "last":
            if packet is None or (last_packet_data and last_packet_data["timestamp"] > packet["timestamp"]):
                packet = last_packet_data


            if packet is None or (last_merged_location and last_merged_location["timestamp"] > packet["timestamp"]):
                packet = last_merged_location
        
        elif packet_to_send == "gsm":
            packet = last_packet_data
        
        elif packet_to_send == "sat":
            packet = last_merged_location
        
        
        # Sending packet if it exists
        if packet:
            packet["timestamp"] = datetime.now()
            send_to_main_server(dev_id, packet, 00, "API SENT REQUEST", input_protocol)

            return jsonify({"status": "ok", "message": "sent"}), 200
        
        return jsonify({"status": "ok", "message": "no packet available"}), 204

@app.route("/trackers/<string:dev_id>/get_info", methods=["POST"])
def get_info(dev_id: str):
    """EP to serve specific field data from the device stored data on redis."""
    
    if not dev_id:
        logger.error("Device id empty in resend last packet request.", log_label="API")
        return jsonify({"status": "error", "message": "please provide a valid device id."})
    
    with logger.contextualize(log_label=dev_id):
        data = request.get_json()
        if not data or not data.get("fields", []):
            logger.error(f"No field was requested in the 'get_info' request for {dev_id}.")
            return jsonify({"status": "ok", "message": "no data field was requested"})
                
        tracker_key = f"tracker:{dev_id}"
        if not redis_client.exists(tracker_key):
            logger.error(f"Device not found in Database for {dev_id}. Cannot retrieve data for {dev_id}.")
            return jsonify({"status": "error", "message": "device not found in Database."})
        
        fields_requested = data["fields"]

        device_data = redis_client.hmget(tracker_key, fields_requested)

        logger.success("Success! Device data retrieved from redis.")
        return jsonify({"values": device_data}), 200
    
# ==================================================================================================
# OTHER GATEWAY FEATURES
# ==================================================================================================

@app.route("/turn_hybrid", methods=["POST"])
def turn_hybrid():
    """
    Turns a tracker hybrid (with a satellite tracker communicating using its connection)
    by adding the fields "is_hybrid" and "hybrid_id" to the tracker Hash in redis
    And updating the "SAT_GSM:MAPPING" Hash.
    """

    request_data = request.get_json()
    args = request.args
    if not request_data:
        logger.error(f"Request with no data received.")
        return jsonify({"status": "error", "message": "request with no data received."}), 400
    
    # Obtendo os dados iniciais
    base_tracker = str(request_data.get("base_tracker"))
    sat_tracker = str(request_data.get("sat_tracker"))

    if not base_tracker or not sat_tracker:
        logger.error("Request without the necessary fields.")
        return jsonify({"status": "error", "message": "Please provide all the necessary data to perform the action. 'base_tracker' or 'sat_tracker' field missing"}), 400
    
    # Verificando se o satelital já não está atrelado a outro registro de rastreador
    sat_gsm_mapping = redis_client.hgetall("SAT_GSM_MAPPING") or {}
    if sat_tracker in sat_gsm_mapping:
        logger.error(f"Satellite tracker already attached to another device.")
        return jsonify({"status": "ok", "message": "Satellite tracker already attached to another device."}), 409

    # Se o cliente fez essa requisição e enviou um ID de saída para "base_tracker"
    # Precisamos obter o ID de entrada do dispositivo.
    # Muitas vezes os IDs de saída vez com 0s a esquerda, por isso precisamos lidar com isso.
    input_id = base_tracker
    if args.get("id_type") == "output":
        # Robustez na verificação do ID do rastreador base, para lidar com IDs com 0s a esquerda e sem 0s a esquerda
        output_input_ids_0Padded, output_input_ids_notPadded = utils.get_output_input_ids_map()

        input_id = output_input_ids_0Padded.get(base_tracker) or output_input_ids_notPadded.get(base_tracker.lstrip("0"))
    
    tracker_key = f"tracker:{input_id}"

    if not input_id or not redis_client.exists(tracker_key):
        logger.error(f"{base_tracker} device not found in database.")
        return jsonify({"status": "ok", "message": "base tracker device not found."}), 404
    
    # Obtendo o novo ID de saída do dispositivo
    new_output_id = get_output_dev_id(input_id, settings.STANDARD_HYBRID_OUTPUT_PROTOCOL)
    
    # Criando mapeamento de dados para salvar no redis.
    mapp = {
        "is_hybrid": "1",
        "hybrid_id": sat_tracker,
        "output_protocol": settings.STANDARD_HYBRID_OUTPUT_PROTOCOL,
        "output_id": new_output_id
    }
    pipe = redis_client.pipeline()

    pipe.hmset(tracker_key, mapp)
    pipe.set("SAT_GSM_MAPPING", sat_tracker, base_tracker)

    logger.success("Hybrid Created!")
    return jsonify({"status": "ok", "message": "created.", "return_data": {"new_output_id": new_output_id}}), 200
