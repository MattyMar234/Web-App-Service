import argparse
import platform
import subprocess
import threading
import time
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import json
import os
import uuid
from wakeonlan import send_magic_packet
import logging
from typing import Callable, Dict
import paramiko
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding
import base64
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

#app = Flask(__name__, static_folder='static', template_folder='templates')
app = Flask(__name__, static_folder='../frontend/public', static_url_path='')
CORS(app, resources={r"/api/*": {"origins": "*"}})
socketio = SocketIO(app, cors_allowed_origins="*")

DEVICES_FILE = 'devices.json'
#paramiko.util.log_to_file("paramiko.log")
DEVICE_FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), DEVICES_FILE)

DEVICES_DICT: Dict[str, dict] = {}
DEVICES_LIST: list = []
MAX_DEVICES = 128
LOCK = threading.Lock()
HOST_CONNECTED: int = 0

# AES-256 Encryption key (should be in .env)
ENCRYPTION_KEY = os.environ.get('AES_ENCRYPTION_KEY', 'default-32-byte-key-change-me!!')
if len(ENCRYPTION_KEY) < 32:
    ENCRYPTION_KEY = ENCRYPTION_KEY.ljust(32, '0')[:32]
ENCRYPTION_KEY = ENCRYPTION_KEY.encode('utf-8')[:32]

def encrypt_data(data: str) -> str:
    """Encrypt data using AES-256"""
    try:
        # Generate random IV
        iv = os.urandom(16)
        cipher = Cipher(algorithms.AES(ENCRYPTION_KEY), modes.CBC(iv), backend=default_backend())
        encryptor = cipher.encryptor()
        
        # Pad data
        padder = padding.PKCS7(128).padder()
        padded_data = padder.update(data.encode('utf-8')) + padder.finalize()
        
        # Encrypt
        encrypted = encryptor.update(padded_data) + encryptor.finalize()
        
        # Combine IV + encrypted data and encode to base64
        return base64.b64encode(iv + encrypted).decode('utf-8')
    except Exception as e:
        logger.error(f"Encryption error: {e}")
        return data

def decrypt_data(encrypted_data: str) -> str:
    """Decrypt data using AES-256"""
    try:
        # Decode from base64
        encrypted_bytes = base64.b64decode(encrypted_data.encode('utf-8'))
        
        # Extract IV and encrypted data
        iv = encrypted_bytes[:16]
        encrypted = encrypted_bytes[16:]
        
        # Decrypt
        cipher = Cipher(algorithms.AES(ENCRYPTION_KEY), modes.CBC(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        padded_data = decryptor.update(encrypted) + decryptor.finalize()
        
        # Unpad
        unpadder = padding.PKCS7(128).unpadder()
        data = unpadder.update(padded_data) + unpadder.finalize()
        
        return data.decode('utf-8')
    except Exception as e:
        logger.error(f"Decryption error: {e}")
        return encrypted_data

def synchronize_devices(func: Callable) -> Callable:
    global LOCK
    def wrapper(*args, **kwargs):
        with LOCK:
            return func(*args, **kwargs)
    return wrapper

def load_devices() -> list:
    """Load and decrypt devices from JSON file"""
    global DEVICE_FILE_PATH
    try:
        with open(DEVICE_FILE_PATH, 'r') as f:
            encrypted_devices = json.load(f)
            
        # Decrypt sensitive fields
        devices = []
        for device in encrypted_devices:
            decrypted_device = device.copy()
            
            # Decrypt SSH password and key if present
            if 'ssh' in device and device['ssh'].get('enabled'):
                if 'password' in device['ssh'] and device['ssh']['password']:
                    decrypted_device['ssh']['password'] = decrypt_data(device['ssh']['password'])
                if 'sshKey' in device['ssh'] and device['ssh']['sshKey']:
                    decrypted_device['ssh']['sshKey'] = decrypt_data(device['ssh']['sshKey'])
                if 'keyPassphrase' in device['ssh'] and device['ssh']['keyPassphrase']:
                    decrypted_device['ssh']['keyPassphrase'] = decrypt_data(device['ssh']['keyPassphrase'])
            
            devices.append(decrypted_device)
        
        return devices
    except FileNotFoundError:
        return []
    except Exception as e:
        logger.error(f"Error loading devices: {e}")
        return []

def save_devices(devices):
    """Encrypt and save devices to JSON file"""
    global DEVICE_FILE_PATH
    try:
        # Encrypt sensitive fields
        encrypted_devices = []
        for device in devices:
            encrypted_device = device.copy()
            
            # Encrypt SSH password and key if present
            if 'ssh' in device and device['ssh'].get('enabled'):
                encrypted_device['ssh'] = device['ssh'].copy()
                if 'password' in device['ssh'] and device['ssh']['password']:
                    encrypted_device['ssh']['password'] = encrypt_data(device['ssh']['password'])
                if 'sshKey' in device['ssh'] and device['ssh']['sshKey']:
                    encrypted_device['ssh']['sshKey'] = encrypt_data(device['ssh']['sshKey'])
                if 'keyPassphrase' in device['ssh'] and device['ssh']['keyPassphrase']:
                    encrypted_device['ssh']['keyPassphrase'] = encrypt_data(device['ssh']['keyPassphrase'])
            
            encrypted_devices.append(encrypted_device)
        
        with open(DEVICE_FILE_PATH, 'w') as f:
            json.dump(encrypted_devices, f, indent=4)
    except Exception as e:
        logger.error(f"Error saving devices: {e}")

def is_reachable(host: str, count: int = 1, timeout_ms: int = 1000) -> bool:
    system = platform.system().lower()

    cmd = ["ping", "-n", str(count), "-w", str(timeout_ms), host] if \
        system == "windows" else ["ping", "-c", str(count), "-W", "1", host]
        
    proc_timeout = (timeout_ms / 1000.0) * count + 2.0

    try:
        completed = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=proc_timeout
        )
        return completed.returncode == 0
    except subprocess.TimeoutExpired:
        return False
    except FileNotFoundError:
        raise RuntimeError("Il comando 'ping' non è disponibile sul sistema.")
    except Exception as e:
        logger.error(f"Error checking reachability: {e}")
        return False
    
def check_host_connectivity():
    global HOST_CONNECTED
    global DEVICES_LIST
    
    while True:
        with LOCK:
            number = HOST_CONNECTED
        
        if number == 0:
            time.sleep(5) 
            continue
        
        with LOCK:
            device_list = DEVICES_LIST[::]
            
        for device in device_list:
            if device.get('ip'):
                reachable = is_reachable(device['ip'])
                device['status'] = 'online' if reachable else 'offline'
                
                socketio.emit('device_status_update', {
                    'device_id': device['id'],
                    'status': device['status']
                })
        
        time.sleep(10)

def detect_os_via_ssh(hostname, username, auth_method, password=None, ssh_key=None, key_passphrase=None):
    """Detect OS type via SSH connection"""
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        if auth_method == 'password':
            ssh.connect(hostname, username=username, password=password, timeout=10, look_for_keys=False, allow_agent=False)
        else:
            # Load key from string
            from io import StringIO
            key_file = StringIO(ssh_key)
            try:
                if key_passphrase:
                    private_key = paramiko.RSAKey.from_private_key(key_file, password=key_passphrase)
                else:
                    private_key = paramiko.RSAKey.from_private_key(key_file)
            except:
                # Try other key types
                key_file.seek(0)
                try:
                    if key_passphrase:
                        private_key = paramiko.Ed25519Key.from_private_key(key_file, password=key_passphrase)
                    else:
                        private_key = paramiko.Ed25519Key.from_private_key(key_file)
                except:
                    key_file.seek(0)
                    if key_passphrase:
                        private_key = paramiko.ECDSAKey.from_private_key(key_file, password=key_passphrase)
                    else:
                        private_key = paramiko.ECDSAKey.from_private_key(key_file)
            
            ssh.connect(hostname, username=username, pkey=private_key, timeout=10)
        
        # Detect OS
        stdin, stdout, stderr = ssh.exec_command('uname -s')
        os_type = stdout.read().decode().strip().lower()
        
        if 'linux' in os_type:
            return 'linux'
        elif 'darwin' in os_type:
            return 'macos'
        else:
            # Try Windows command
            stdin, stdout, stderr = ssh.exec_command('ver')
            result = stdout.read().decode().strip()
            if 'Windows' in result or 'Microsoft' in result:
                return 'windows'
        
        return 'linux'  # Default
    except Exception as e:
        logger.error(f"OS detection error: {e}")
        return None
    finally:
        ssh.close()

def ssh_shutdown(hostname, username, auth_method, os_type='linux', password=None, ssh_key=None, key_passphrase=None):
    """Execute remote shutdown via SSH"""
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        if auth_method == 'password':
            ssh.connect(hostname, username=username, password=password, timeout=10, look_for_keys=False, allow_agent=False)
        else:
            # Load key from string
            from io import StringIO
            key_file = StringIO(ssh_key)
            try:
                if key_passphrase:
                    private_key = paramiko.RSAKey.from_private_key(key_file, password=key_passphrase)
                else:
                    private_key = paramiko.RSAKey.from_private_key(key_file)
            except:
                # Try other key types
                key_file.seek(0)
                try:
                    if key_passphrase:
                        private_key = paramiko.Ed25519Key.from_private_key(key_file, password=key_passphrase)
                    else:
                        private_key = paramiko.Ed25519Key.from_private_key(key_file)
                except:
                    key_file.seek(0)
                    if key_passphrase:
                        private_key = paramiko.ECDSAKey.from_private_key(key_file, password=key_passphrase)
                    else:
                        private_key = paramiko.ECDSAKey.from_private_key(key_file)
            
            ssh.connect(hostname, username=username, pkey=private_key, timeout=10)
        
        # Choose shutdown command based on OS
        if os_type == 'windows':
            command = "shutdown /s /t 0"
        else:  # linux or macos
            command = "sudo shutdown -h now"
        
        stdin, stdout, stderr = ssh.exec_command(command)
        exit_status = stdout.channel.recv_exit_status()
        
        return exit_status == 0
    except Exception as e:
        logger.error(f"SSH shutdown error: {e}")
        return False
    finally:
        ssh.close()


@app.route('/')
def index():
    assert app.static_folder is not None
    return send_from_directory(app.static_folder, 'index.html')

# @app.route('/static/<path:path>')
# def send_static(path):
#     return send_from_directory('static', path)

@app.route('/<path:path>')
def serve_static(path):
    assert app.static_folder is not None
    return send_from_directory(app.static_folder, path)

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
    
    device_id = request.json.get('id')
    
    if device_id:
        # Update
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
            'os_type': request.json.get('os_type', 'linux'),
            'ssh': request.json.get('ssh', {'enabled': False})
        })
        
        save_devices(DEVICES_LIST)
        socketio.emit('devices_list', DEVICES_LIST)
        
        return jsonify(device_data)
    else:
        # Create
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
            'os_type': request.json.get('os_type', 'linux'),
            'status': 'unknown',
            'ssh': request.json.get('ssh', {'enabled': False})
        }
        
        logging.info(f"Adding new device: {new_device}")
        DEVICES_DICT[new_device['id']] = new_device
        DEVICES_LIST.append(new_device)
        
        save_devices(DEVICES_LIST)
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
    
    socketio.emit('devices_list', DEVICES_LIST)
    
    return '', 204

@synchronize_devices
@app.route('/api/devices/reorder', methods=['POST'])
def reorder_devices():
    """Reorder devices based on provided order"""
    global DEVICES_LIST
    global DEVICES_DICT
    
    try:
        new_order = request.json.get('order', [])
        
        if len(new_order) != len(DEVICES_LIST):
            return jsonify({'error': 'Invalid order array'}), 400
        
        # Reorder the list
        reordered = []
        for device_id in new_order:
            device = DEVICES_DICT.get(device_id)
            if device:
                reordered.append(device)
        
        DEVICES_LIST = reordered
        save_devices(DEVICES_LIST)
        
        socketio.emit('devices_list', DEVICES_LIST)
        
        return jsonify({'status': 'success'})
    except Exception as e:
        logger.error(f"Error reordering devices: {e}")
        return jsonify({'error': str(e)}), 500

@synchronize_devices
@app.route('/api/wake/<device_id>', methods=['POST'])
def wake_device(device_id:str):
    if device_id not in DEVICES_DICT and DEVICES_DICT.get(device_id) is None:
        return jsonify({'error': 'Device not found'}), 404
    
    device = DEVICES_DICT[device_id]
    logger.info(f"Waking device: {device}")
    try:
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
    
    if not device.get('ssh', {}).get('enabled', False):
        return jsonify({'error': 'SSH not configured for this device'}), 400
    
    ssh_config = device['ssh']
    ssh_username = ssh_config.get('username', '')
    ssh_auth_method = ssh_config.get('authMethod', 'password')
    ssh_password = ssh_config.get('password', '') if ssh_auth_method == 'password' else None
    ssh_key = ssh_config.get('sshKey', '') if ssh_auth_method == 'key' else None
    ssh_key_passphrase = ssh_config.get('keyPassphrase', '') if ssh_auth_method == 'key' else None
    os_type = device.get('os_type', 'linux')
    
    if not ssh_username:
        return jsonify({'error': 'SSH username required'}), 400
    
    if ssh_auth_method == 'password' and not ssh_password:
        return jsonify({'error': 'SSH password required'}), 400
    
    if ssh_auth_method == 'key' and not ssh_key:
        return jsonify({'error': 'SSH key required'}), 400
    
    try:
        logger.info(f"Attempting to shutdown device {device_id} via SSH (OS: {os_type})")
        success = ssh_shutdown(
            hostname=device['ip'],
            username=ssh_username,
            auth_method=ssh_auth_method,
            os_type=os_type,
            password=ssh_password,
            ssh_key=ssh_key,
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


# SocketIO event handlers
@socketio.on('connect')
def handle_connect():
    global HOST_CONNECTED
    with LOCK:
        HOST_CONNECTED += 1
    logger.info(f"Client connected. Total connected: {HOST_CONNECTED}")
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
    
    parser = argparse.ArgumentParser(description='Avvia il server Wake-on-LAN.')
    parser.add_argument('--host', type=str, default='0.0.0.0', help="Indirizzo IP su cui il server è in ascolto. Default: '0.0.0.0'")
    parser.add_argument('--port', type=int, default=8080, help='Porta su cui il server è in ascolto. Default: 8080')
    args = parser.parse_args()

    # Initialize JSON file if not exists
    if not os.path.exists(DEVICE_FILE_PATH):
        with open(DEVICE_FILE_PATH, 'w') as f:
            json.dump([], f)
    else:  
        DEVICES_LIST = load_devices()
        DEVICES_DICT = {d['id']: d for d in DEVICES_LIST}
    
    logger.info(f"Loaded devices: {len(DEVICES_LIST)}")
    
    # Add initial status to existing devices
    for device in DEVICES_LIST:
        if 'status' not in device:
            device['status'] = 'unknown'
        if 'ssh' not in device:
            device['ssh'] = {'enabled': False}
        if 'os_type' not in device:
            device['os_type'] = 'linux'
    
    # Start connectivity check thread
    connectivity_thread = threading.Thread(target=check_host_connectivity, daemon=True)
    connectivity_thread.start()
    
    # Start server
    logger.info(f"Starting server on http://localhost:{args.port}")
    logger.info(f"Allowed IP: {{args.host}}")
    socketio.run(app, debug=False, host=args.host, port=args.port, allow_unsafe_werkzeug=True)

if __name__ == '__main__':
    main()
