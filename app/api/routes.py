import json
from flask import current_app as app, jsonify, request, make_response
from datetime import datetime
import os
import time
import zlib

from . import utils
from app.services.redis_service import get_redis
from app.core.logger import get_logger
from app.config.settings import settings
from app.src.session.input_sessions_manager import input_sessions_manager
from app.src.session.output_sessions_manager import output_sessions_manager
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
    "nt40": build_nt40_command,
    "j16w": build_j16w_command,
    "suntech2g": build_suntech2g_command,
    "suntech4g": build_suntech4g_command,
    # "jt808": build_jt808_command
}

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
        return jsonify(info)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@app.route('/trackers', methods=['GET'])
def get_trackers_data():
    try:
        args = request.args

        keys = list(redis_client.scan_iter('tracker:*', count=1000) )
        if not keys:
            return jsonify({"data": {}, "message": "Nenhum rastreador encontrado para esta página."})

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
                response.headers['Content-Type'] = 'application/json'

                return response
               
        return jsonify(all_data)

    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500

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
                })
            else:
                return jsonify({"error": "Tracker is not connected"}), 404
            
    except Exception as e:
        return jsonify({"error": f"Failed to send command: {str(e)}"}), 500

@app.route('/trackers/<string:dev_id>/history', methods=['GET'])
def get_tracker_history(dev_id):
    """
    Fetches the packet history for a specific tracker.
    """
    try:
        history = get_packet_history(dev_id)
        return jsonify(history)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/sessions/trackers', methods=['GET'])
def get_tracker_sessions():
    """
    Returns a list of device IDs with active socket connections to the translator.
    """
    active_sessions = list(input_sessions_manager.get_sessions())
    return jsonify(active_sessions)

@app.route('/sessions/main-server', methods=['GET'])
def get_main_server_sessions():
    """
    Returns a list of device IDs with active sessions to the main Suntech4G server.
    """
    active_sessions = list(output_sessions_manager.get_sessions())
    return jsonify(active_sessions)

@app.route('/trackers/<string:dev_id>/details', methods=['GET'])
def get_tracker_details(dev_id):
    """
    Returns comprehensive details for a specific tracker, including Redis data and connection status.
    """
    try:
        id_type = request.args.get("id_type")
        if id_type == "output":
            output_input_ids_0Padded = utils.get_mapping_cached("output_input_ids:mapping") or {}
            output_input_ids_notPadded = {k.lstrip("0"): v for k, v in output_input_ids_0Padded.items()}

            mapped_id = output_input_ids_0Padded.get(dev_id) or output_input_ids_notPadded.get(dev_id.lstrip("0"))
            if mapped_id:
                dev_id = mapped_id

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
        
        return jsonify(status_info)
    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500

@app.route("/satellite_trackers", methods=["GET"])
def get_satellite_trackers():
    """
    Obtem os IDs dos dispositivos satelitais conectados ao server
    """
    satellite_set = redis_client.smembers("satellite_trackers:set") or set()

    return jsonify(list(satellite_set))