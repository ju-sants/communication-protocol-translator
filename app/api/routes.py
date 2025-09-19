import json
from flask import current_app as app, jsonify, request
from datetime import datetime, timezone
import os

from app.services.redis_service import get_redis
from app.config.settings import settings
from app.src.session.input_sessions_manager import input_sessions_manager
from app.src.session.output_sessions_manager import output_sessions_manager
from app.services.history_service import get_packet_history
from app.src.input.j16x.builder import build_command as build_j16x_command
from app.src.input.vl01.builder import build_command as build_vl01_command
from app.src.input.nt40.builder import build_command as build_nt40_command
# from app.src.input.jt808.builder import build_command as build_jt808_command

redis_client = get_redis()

COMMAND_BUILDERS = {
    "j16x": build_j16x_command,
    "vl01": build_vl01_command,
    "nt40": build_nt40_command
    # "jt808": build_jt808_command
}

@app.route('/gateway_info', methods=['GET'])
def get_gateway_info():
    """
    Retorna informações básicas sobre o gateway.
    """
    try:
        info = {
            "input_protocols": [dir.upper() for dir in os.listdir('app/src/input') if os.path.isdir(os.path.join('app/src/input', dir)) and not dir.startswith('__')],
            "output_protocols": [dir.upper() for dir in os.listdir('app/src/output') if os.path.isdir(os.path.join('app/src/output', dir)) and not dir.startswith('__')],
        }

        port_protocol_mapping = {
            protocol: settings.INPUT_PROTOCOL_HANDLERS[protocol]["port"] for protocol in settings.INPUT_PROTOCOL_HANDLERS
        }

        info["port_protocol_mapping"] = port_protocol_mapping
        
        return jsonify(info)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
@app.route('/trackers', methods=['GET'])
def get_trackers_data_efficiently():
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 100))
        offset = (page - 1) * limit

        ignored_keys = {"global_data", "universal_data", "SAT_GSM_MAPPING"}
        
        keys_to_fetch = []
        scanner = redis_client.scan_iter('tracker:*', count=1000) 
        
        processed_count = 0
        for key in scanner:
            if key in ignored_keys:
                continue
            
            if processed_count >= offset:
                keys_to_fetch.append(key)
                if len(keys_to_fetch) == limit:
                    break 

            processed_count += 1

        if not keys_to_fetch:
            return jsonify({"data": {}, "message": "Nenhum rastreador encontrado para esta página."})

        pipe = redis_client.pipeline()
        for key in keys_to_fetch:
            pipe.hgetall(key)
        
        results = pipe.execute()

        all_data = {}
        for i, key in enumerate(keys_to_fetch):
            device_data = results[i]
            
            device_data['is_connected'] = input_sessions_manager.exists(key)
            device_data["output_protocol"] = device_data.get("output_protocol") or "suntech4g"
            all_data[key] = device_data
            
        return jsonify(all_data)

    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@app.route('/trackers/summary', methods=['GET'])
def get_trackers_summary():
    """
    Returns high-level statistics for all trackers.
    """
    try:
        all_tracker_keys = [key for key in redis_client.keys('*') if redis_client.type(key) == 'hash']
        
        total_registered_trackers = len(all_tracker_keys)
        total_active_translator_sessions = len(input_sessions_manager.active_trackers)
        total_active_main_server_sessions = len(output_sessions_manager._sessions)

        protocol_distribution = {}
        last_active_trackers = []

        for dev_id in all_tracker_keys:
            protocol, last_active_timestamp = redis_client.hmget(f"tracker:{dev_id}", 'protocol', 'last_active_timestamp')
            if protocol:
                protocol_distribution[protocol] = protocol_distribution.get(protocol, 0) + 1
            
            if last_active_timestamp:
                last_active_trackers.append({
                    "device_id": dev_id,
                    "last_active_timestamp": last_active_timestamp
                })
        
        # Sort last active trackers by timestamp (most recent first)
        last_active_trackers.sort(key=lambda x: x['last_active_timestamp'], reverse=True)
        
        # Calculate total packets in history
        total_packets_in_history = 0
        history_keys = [key for key in redis_client.keys('history:*')]
        for history_key in history_keys:
            total_packets_in_history += redis_client.llen(history_key)

        summary = {
            "total_registered_trackers": total_registered_trackers,
            "total_active_translator_sessions": total_active_translator_sessions,
            "total_active_main_server_sessions": total_active_main_server_sessions,
            "protocol_distribution": protocol_distribution,
            "total_packets_in_history": total_packets_in_history,
            "most_recent_active_trackers": last_active_trackers[:10] # Top 10 most recent
        }
        return jsonify(summary)
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
        command_packet = builder_func(command_str, serial)
        
        tracker_socket = input_sessions_manager.get_tracker_client_socket(dev_id)
        if tracker_socket:
            tracker_socket.sendall(command_packet)
            # Store command sent in Redis
            redis_client.hset(f"tracker:{dev_id}", "last_command_sent", json.dumps({
                "command": command_str,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "packet_hex": command_packet.hex()
            }))
            redis_client.hincrby(f"tracker:{dev_id}", "total_commands_sent", 1)

            return jsonify({
                "status": "Command sent successfully",
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
    active_sessions = list(input_sessions_manager.active_trackers.keys())
    return jsonify(active_sessions)

@app.route('/sessions/main-server', methods=['GET'])
def get_main_server_sessions():
    """
    Returns a list of device IDs with active sessions to the main Suntech4G server.
    """
    active_sessions = list(output_sessions_manager._sessions.keys())
    return jsonify(active_sessions)

@app.route('/trackers/<string:dev_id>/details', methods=['GET'])
def get_tracker_details(dev_id):
    """
    Returns comprehensive details for a specific tracker, including Redis data and connection status.
    """
    try:
        device_data = redis_client.hgetall(f"tracker:{dev_id}")
        if not device_data:
            return jsonify({"error": "Device not found in Redis"}), 404

        status_info = {
            "device_id": dev_id,
            "imei": device_data.get('imei', dev_id),
            "protocol": device_data.get('protocol'),
            "output_protocol": device_data.get("output_protocol") or "suntech4g",
            "is_connected_translator": input_sessions_manager.exists(dev_id, use_redis=True),
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