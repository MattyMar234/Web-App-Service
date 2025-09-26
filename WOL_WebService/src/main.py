import platform
import subprocess
import threading
import time
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import json
import os
import uuid
from wakeonlan import send_magic_packet
import logging
from typing import Callable, Dict
import paramiko

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})
socketio = SocketIO(app, cors_allowed_origins="*")
DEVICES_FILE = 'devices.json'
paramiko.util.log_to_file("paramiko.log")
DEVICE_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), DEVICES_FILE)

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
    global DEVICE_FILE_PATH
    with open(DEVICE_FILE_PATH, 'r') as f:
        return json.load(f)

def save_devices(devices):
    global DEVICE_FILE_PATH
    with open(DEVICE_FILE_PATH, 'w') as f:
        json.dump(devices, f, indent=4)

def is_reachable(host: str, count: int = 1, timeout_ms: int = 1000) -> bool:
    system = platform.system().lower()

    # Costruisci il comando in base al sistema operativo
    cmd = ["ping", "-n", str(count), "-w", str(timeout_ms), host] if \
        system == "windows" else ["ping", "-c", str(count), host]
        
    proc_timeout = (timeout_ms / 1000.0) * count + 2.0

    try:
        # Nascondiamo output; ci interessa solo il returncode
        completed = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=proc_timeout
        )
        return completed.returncode == 0
    except subprocess.TimeoutExpired:
        # Il comando ha impiegato troppo tempo -> no risposta
        return False
    except FileNotFoundError:
        # "ping" non trovato sul sistema
        raise RuntimeError("Il comando 'ping' non è disponibile sul sistema.")
    except Exception as e:
        # Propaga altre eccezioni controllate dall'applicazione chiamante
        raise
    
def check_host_connectivity():
    global HOST_CONNECTED
    global DEVICES_LIST
    
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
                #logger.info(f"Checking connectivity for {device['name']} ({device['ip']})")
                reachable = is_reachable(device['ip'])
                #logger.info(f"Device {device['name']} is {'online' if reachable else 'offline'}")
                # Aggiorna lo stato del dispositivo
                device['status'] = 'online' if reachable else 'offline'
                
                # Invia aggiornamento via SocketIO
                socketio.emit('device_status_update', {
                    'device_id': device['id'],
                    'status': device['status']
                })
        
        time.sleep(15)

def ssh_shutdown(hostname, username, auth_method, password=None, key_file=None, key_passphrase=None):
    """Esegue lo shutdown remoto via SSH"""
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
       
        
        if auth_method == 'password':
            #logger.info(f"Connecting to {hostname} via SSH with password {password}")
            print("herreee1")
            ssh.connect(hostname, username=username, password=password, timeout=10, look_for_keys=False, allow_agent=False)
        else:  # key
            private_key = None
            if key_passphrase:
                private_key = paramiko.RSAKey.from_private_key_file(key_file, password=key_passphrase)
            else:
                private_key = paramiko.RSAKey.from_private_key_file(key_file)
            ssh.connect(hostname, username=username, pkey=private_key)
        
        # Comando di shutdown in base al sistema operativo
        print("herreee2")
        # if platform.system().lower() == "windows":
        #     command = "shutdown /s /t 0"
        # else:
        #     command = "sudo shutdown -h now"
        
        # stdin, stdout, stderr = ssh.exec_command(command)
        # exit_status = stdout.channel.recv_exit_status()
        #ssh.close()
        return 0
        # return exit_status == 0
    except Exception as e:
        logger.error(f"SSH shutdown error: {e}")
        return False
    finally:
        ssh.close()


@app.route('/')
def index():
    return render_template('index.html')

@synchronize_devices
@app.route('/api/devices', methods=['GET'])
def get_devices():
    global DEVICES_LIST
    return jsonify(DEVICES_LIST)

@synchronize_devices
@app.route('/api/devices/<device_id>', methods=['GET'])
def get_device(device_id: str):
    global DEVICES_DICT
    
    if device_id not in DEVICES_DICT:
        logger.error(f"Device not found: {device_id}")
        return jsonify({'error': 'Device not found'}), 404
    
    return jsonify(DEVICES_DICT[device_id])

@synchronize_devices
@app.route('/api/devices', methods=['POST'])
def add_or_update_device():
    global DEVICES_DICT
    global DEVICES_LIST
    global MAX_DEVICES
    
    # Controlliamo se c'è un ID nel corpo: se sì, è un aggiornamento
    device_id = request.json.get('id')
    
    if device_id:
        # Aggiornamento
        device_data = DEVICES_DICT.get(device_id)
        
        if device_data is None:
            logger.error(f"Device not found: {device_id}")
            return jsonify({'error': 'Device not found'}), 404
        
        device_data.update({
            'name': request.json['name'],
            'mac': request.json['mac'].lower(),
            'ip': request.json.get('ip', ''),
            'subnet': request.json.get('subnet', '255.255.255.0'),
            'port': int(request.json.get('port', 9)),
            'ssh': request.json.get('ssh', {'enabled': False})
        })
        
        save_devices(DEVICES_LIST)
        
        # Notifica i client connessi
        socketio.emit('devices_list', DEVICES_LIST)
        
        return jsonify(device_data)
    else:
        # Creazione
        if len(DEVICES_LIST) >= MAX_DEVICES:
            logger.error(f"Maximum number of devices reached")
            return jsonify({'error': 'Maximum number of devices reached'}), 400
            
        new_device = {
            'id': str(uuid.uuid4()),
            'name': request.json['name'],
            'mac': request.json['mac'].lower(),
            'ip': request.json.get('ip', ''),
            'subnet': request.json.get('subnet', '255.255.255.0'),
            'port': int(request.json.get('port', 9)),
            'status': 'unknown',  # Stato iniziale sconosciuto
            'ssh': request.json.get('ssh', {'enabled': False})
        }
        
        logging.info(f"Adding new device: {new_device}")
        DEVICES_DICT[new_device['id']] = new_device
        DEVICES_LIST.append(new_device)
        
        save_devices(DEVICES_LIST)
        
        # Notifica i client connessi
        socketio.emit('devices_list', DEVICES_LIST)
        
        return jsonify(new_device), 201

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
    
    # Notifica i client connessi
    socketio.emit('devices_list', DEVICES_LIST)
    
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

@synchronize_devices
@app.route('/api/shutdown/<device_id>', methods=['POST'])
def shutdown_device(device_id: str):
    global DEVICES_DICT
    
    if device_id not in DEVICES_DICT:
        return jsonify({'error': 'Device not found'}), 404
    
    device = DEVICES_DICT[device_id]
    
    if not device['ip']:
        return jsonify({'error': 'IP address required for shutdown'}), 400
    
    # Verifica se SSH è abilitato per questo dispositivo
    if not device.get('ssh', {}).get('enabled', False):
        return jsonify({'error': 'SSH not configured for this device'}), 400
    
    ssh_config = device['ssh']
    ssh_username = ssh_config.get('username', '')
    ssh_auth_method = ssh_config.get('authMethod', 'password')
    ssh_password = ssh_config.get('password', '') if ssh_auth_method == 'password' else None
    ssh_key_file = ssh_config.get('keyFile', '') if ssh_auth_method == 'key' else None
    ssh_key_passphrase = ssh_config.get('keyPassphrase', '') if ssh_auth_method == 'key' else None
    
    if not ssh_username:
        return jsonify({'error': 'SSH username required'}), 400
    
    if ssh_auth_method == 'password' and not ssh_password:
        return jsonify({'error': 'SSH password required'}), 400
    
    if ssh_auth_method == 'key' and not ssh_key_file:
        return jsonify({'error': 'SSH key file required'}), 400
    
    try:
        logger.info(f"Attempting to shutdown device {device_id} via SSH")
        success = ssh_shutdown(
            hostname=device['ip'],
            username=ssh_username,
            auth_method=ssh_auth_method,
            password=ssh_password,
            key_file=ssh_key_file,
            key_passphrase=ssh_key_passphrase
        )
        
        if success:
            logger.info(f"Shutdown command sent to device: {device_id}")
            return jsonify({'status': 'success'})
        else:
            logger.error(f"Failed to shutdown device: {device_id}")
            return jsonify({'error': 'Failed to execute shutdown command'}), 500
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")
        return jsonify({'error': str(e)}), 500


# Gestori eventi SocketIO
@socketio.on('connect')
def handle_connect():
    global HOST_CONNECTED
    with LOCK:
        HOST_CONNECTED += 1
    logger.info(f"Client connected. Total connected: {HOST_CONNECTED}")
    
    # Invia l'elenco corrente dei dispositivi
    emit('devices_list', DEVICES_LIST)

@socketio.on('disconnect')
def handle_disconnect():
    global HOST_CONNECTED
    with LOCK:
        HOST_CONNECTED -= 1
    logger.info(f"Client disconnected. Total connected: {HOST_CONNECTED}")

def main() -> None:
    global DEVICES_DICT
    global DEVICES_LIST
    
    # Inizializza file JSON se non esiste
    if not os.path.exists(DEVICE_FILE_PATH):
        with open(DEVICE_FILE_PATH, 'w') as f:
            json.dump([], f)
    else:  
        DEVICES_LIST = load_devices()
        DEVICES_DICT = {d['id']: d for d in DEVICES_LIST}
    
    print(f"Loaded devices:{DEVICES_LIST}")
    
    # Aggiungi stato iniziale ai dispositivi esistenti
    for device in DEVICES_LIST:
        if 'status' not in device:
            device['status'] = 'unknown'
        if 'ssh' not in device:
            device['ssh'] = {'enabled': False}
    
    # Avvia il thread per il controllo della connettività
    connectivity_thread = threading.Thread(target=check_host_connectivity, daemon=True)
    connectivity_thread.start()
    
    # Avvia il server
    socketio.run(app, debug=True, host='0.0.0.0', port=12345, allow_unsafe_werkzeug=True)

if __name__ == '__main__':
    main()