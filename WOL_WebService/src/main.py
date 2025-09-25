import platform
import subprocess
import threading
import time
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
import json
import os
import uuid
from wakeonlan import send_magic_packet
import logging
from typing import Callable, Dict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
DEVICES_FILE = 'devices.json'

DEVICES_DICT: Dict[str, dict] = {}
DEVICES_LIST: list = []
MAX_DEVICES = 128
LOCK = threading.Lock()
HOST_CONNECTED: int = 0

def synchronize_devices(func: Callable) -> Callable:
    global LOCK
    def wrapper(*args, **kwargs):
        with LOCK:
            return func(*args, **kwargs)
    return wrapper

def load_devices() -> list:
    global DEVICES_FILE
    with open(DEVICES_FILE, 'r') as f:
        return json.load(f)

def save_devices(devices):
    global DEVICES_FILE
    with open(DEVICES_FILE, 'w') as f:
        json.dump(devices, f, indent=4)

def is_reachable(ip):
    # Comando diverso tra Windows e Linux/macOS
    param = "-n" if platform.system().lower()=="windows" else "-c"
    try:
        subprocess.check_output(["ping", param, "1", ip], stderr=subprocess.DEVNULL)
        return True
    except subprocess.CalledProcessError:
        return False
    
def check_host_connectivity():
    
    global HOST_CONNECTED
    global DEVICES_LIST
    numerber = 0
    
    while True:
        with LOCK:
            numerber = HOST_CONNECTED
        
        if numerber == 0:
            time.sleep(5) 
            continue
        
        with LOCK:
            device_list = DEVICES_LIST[::]
            
        for device in device_list:
            if device['ip']:
                reachable = is_reachable(device['ip'])
                pass
            
        time.sleep(15)

@app.route('/')
def index():
    return render_template('index.html')

@synchronize_devices
@app.route('/api/devices', methods=['GET'])
def get_devices():
    global DEVICES_LIST
    return jsonify(DEVICES_LIST)

@synchronize_devices
@app.route('/api/devices', methods=['POST'])
def add_device():
    
    global DEVICES_DICT
    global DEVICES_LIST
    global MAX_DEVICES
    
    if len(DEVICES_LIST) >= MAX_DEVICES:
        logger.error(f"Maximum number of devices reached")
        return jsonify({'error': 'Maximum number of devices reached'}), 400
        
    new_device = {
        'id': str(uuid.uuid4()),
        'name': request.json['name'],
        'mac': request.json['mac'].lower(),
        'ip': request.json.get('ip', ''),
        'subnet': request.json.get('subnet', '255.255.255.0'),
        'port': int(request.json.get('port', 9))
    }
    
    logging.info(f"Adding new device: {new_device}")
    DEVICES_DICT[new_device['id']] = new_device
    DEVICES_LIST.append(new_device)
    
    save_devices(DEVICES_LIST)
    return jsonify(new_device), 201

@synchronize_devices
@app.route('/api/devices/<device_id>', methods=['PUT'])
def update_device(device_id: str):
    global DEVICES_DICT
    global DEVICES_LIST
    
    device_data = DEVICES_DICT.get(device_id)
    
    if device_data is None:
        logger.error(f"Device not found: {device_id}")
        return jsonify({'error': 'Device not found'}), 404
    
    device_data.update({
        'name': request.json['name'],
        'mac': request.json['mac'].lower(),
        'ip': request.json.get('ip', ''),
        'subnet': request.json.get('subnet', '255.255.255.0'),
        'port': int(request.json.get('port', 9))
    })
    
    save_devices(DEVICES_LIST)
    return jsonify(device_data)
    

@synchronize_devices
@app.route('/api/devices/<device_id>', methods=['DELETE'])
def delete_device(device_id: str):
    global DEVICES_DICT
    global DEVICES_LIST
    
    if device_id not in DEVICES_DICT:
        logger.error(f"Device not found: {device_id}")
        return jsonify({'error': 'Device not found'}), 404
    
    DEVICES_DICT.pop(device_id)
    DEVICES_LIST = [d for d in DEVICES_LIST if d['id'] != device_id]
    save_devices(DEVICES_LIST)
    logger.info(f"Deleted device: {device_id}")
    return '', 204

@synchronize_devices
@app.route('/api/wake/<device_id>', methods=['POST'])
def wake_device(device_id:str):
    
    if device_id not in DEVICES_DICT and DEVICES_DICT.get(device_id) is None:
        return jsonify({'error': 'Device not found'}), 404
    
    device = DEVICES_DICT[device_id]
    logger.info(f"Waking device: {device}")
    try:
        # Calcolo broadcast address se IP e subnet sono presenti
        if device['ip'] and device['subnet']:
            ip_parts = device['ip'].split('.')
            subnet_parts = device['subnet'].split('.')
            broadcast = '.'.join([
                str(int(ip_parts[i]) | (255 ^ int(subnet_parts[i])))
                for i in range(4)
            ])
            
            logger.info("Sending magic packet to %s via broadcast %s on port %d", device['mac'], broadcast, device['port'])
            send_magic_packet(device['mac'], ip_address=broadcast, port=device['port'])
            send_magic_packet(device['mac'], ip_address="255.255.255.255", port=device['port'])
        else:
            logger.info("Sending magic packet to %s on port %d", device['mac'], device['port'])
            send_magic_packet(device['mac'], port=device['port'])
        return jsonify({'status': 'success'})
    except Exception as e:
        logger.error(f"Error sending magic packet: {e}")
        return jsonify({'error': str(e)}), 500



def main() -> None:
    
    global DEVICES_DICT
    global DEVICES_LIST
    
    # Inizializza file JSON se non esiste
    if not os.path.exists(DEVICES_FILE):
        with open(DEVICES_FILE, 'w') as f:
            json.dump([], f)
    else:  
        DEVICES_LIST = load_devices()
        DEVICES_DICT = {d['id']: d for d in DEVICES_LIST}
    
    socketio = SocketIO(app, cors_allowed_origins="*")
    socketio.run(app, debug=True,  host='0.0.0.0', port=12345, allow_unsafe_werkzeug=True)



if __name__ == '__main__':
    main()