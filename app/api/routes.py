import json
from flask import current_app as app, jsonify, request
from app.services.redis_service import get_redis
from app.src.protocols.session_manager import tracker_sessions_manager
from app.src.connection.main_server_connection import COMMAND_PROCESSORS
from app.services.history_service import get_packet_history

redis_client = get_redis()

@app.route('/trackers', methods=['GET'])
def get_all_trackers_data():
    """
    Fetches all tracker data from all keys in Redis.
    """
    try:
        keys = redis_client.keys('*')
        all_data = {}
        for key in keys:
            device_data = redis_client.hgetall(key)
            device_data['is_connected'] = tracker_sessions_manager.exists(key)
            all_data[key] = device_data
        return jsonify(all_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/trackers/<string:dev_id>/command', methods=['POST'])
def send_tracker_command(dev_id):
    """
    Sends a command to a specific tracker through its active socket.
    The command is sent in the original Suntech format and will be translated.
    """
    data = request.get_json()
    if not data or 'command' not in data:
        return jsonify({"error": "Command not specified in request body"}), 400

    command_str = data['command']
    
    device_info = redis_client.hgetall(dev_id)
    if not device_info:
        return jsonify({"error": "Device not found in Redis"}), 404

    protocol_type = device_info.get('protocol')
    serial = device_info.get('last_serial', '0')

    if not protocol_type:
        return jsonify({"error": f"Protocol not set for device {dev_id}"}), 500

    processor_func = COMMAND_PROCESSORS.get(protocol_type)
    if not processor_func:
        return jsonify({"error": f"No command processor found for protocol '{protocol_type}'"}), 500

    # The command must be in Suntech format, so we encode it to ascii
    command_bytes = command_str.encode('ascii')

    try:
        # The processor function handles the sending logic via the tracker's socket
        processor_func(command_bytes, dev_id, serial)
        return jsonify({"status": "Command sent for processing", "device_id": dev_id, "command": command_str})
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