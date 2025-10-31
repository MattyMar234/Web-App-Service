// Global variables
let socket;
let devices = [];
let draggedElement = null;
let currentTheme = localStorage.getItem('theme') || 'light';

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    initSocketIO();
    initEventListeners();
    loadDevices();
});

// Theme Management
function initTheme() {
    document.documentElement.setAttribute('data-theme', currentTheme);
    updateThemeIcon();
}

function toggleTheme() {
    currentTheme = currentTheme === 'light' ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', currentTheme);
    localStorage.setItem('theme', currentTheme);
    updateThemeIcon();
}

function updateThemeIcon() {
    const icon = document.querySelector('#themeToggle i');
    icon.className = currentTheme === 'light' ? 'fas fa-moon' : 'fas fa-sun';
}

// SocketIO
function initSocketIO() {
    socket = io();
    
    socket.on('connect', () => {
        console.log('Connected to server');
    });
    
    socket.on('devices_list', (devicesList) => {
        devices = devicesList;
        renderDevices();
    });
    
    socket.on('device_status_update', (data) => {
        const device = devices.find(d => d.id === data.device_id);
        if (device) {
            device.status = data.status;
            updateDeviceStatus(data.device_id, data.status);
        }
    });
    
    socket.on('disconnect', () => {
        console.log('Disconnected from server');
    });
}

// Event Listeners
function initEventListeners() {
    document.getElementById('themeToggle').addEventListener('click', toggleTheme);
    document.getElementById('addDeviceBtn').addEventListener('click', openAddDeviceModal);
    document.getElementById('deviceForm').addEventListener('submit', handleDeviceSubmit);
    document.getElementById('sshEnabled').addEventListener('change', toggleSSHConfig);
    document.getElementById('sshAuthMethod').addEventListener('change', toggleSSHAuthMethod);
    
    // Close modal on backdrop click
    document.getElementById('deviceModal').addEventListener('click', (e) => {
        if (e.target.id === 'deviceModal') {
            closeDeviceModal();
        }
    });
}

// API Calls
async function loadDevices() {
    try {
        const response = await fetch('/api/devices');
        devices = await response.json();
        renderDevices();
    } catch (error) {
        console.error('Error loading devices:', error);
        showNotification('Errore nel caricamento dei dispositivi', 'error');
    }
}

async function saveDevice(deviceData) {
    try {
        const url = '/api/devices';
        const method = 'POST';
        
        const response = await fetch(url, {
            method: method,
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(deviceData),
        });
        
        if (response.ok) {
            showNotification('Dispositivo salvato con successo', 'success');
            closeDeviceModal();
            loadDevices();
        } else {
            const error = await response.json();
            showNotification(error.error || 'Errore nel salvataggio', 'error');
        }
    } catch (error) {
        console.error('Error saving device:', error);
        showNotification('Errore nel salvataggio del dispositivo', 'error');
    }
}

async function deleteDevice(deviceId) {
    if (!confirm('Sei sicuro di voler eliminare questo dispositivo?')) {
        return;
    }
    
    try {
        const response = await fetch(`/api/devices/${deviceId}`, {
            method: 'DELETE',
        });
        
        if (response.ok) {
            showNotification('Dispositivo eliminato', 'success');
            loadDevices();
        } else {
            showNotification('Errore nell\'eliminazione', 'error');
        }
    } catch (error) {
        console.error('Error deleting device:', error);
        showNotification('Errore nell\'eliminazione del dispositivo', 'error');
    }
}

async function wakeDevice(deviceId) {
    try {
        const response = await fetch(`/api/wake/${deviceId}`, {
            method: 'POST',
        });
        
        if (response.ok) {
            showNotification('Pacchetto Wake-on-LAN inviato', 'success');
        } else {
            const error = await response.json();
            showNotification(error.error || 'Errore nell\'invio del pacchetto', 'error');
        }
    } catch (error) {
        console.error('Error waking device:', error);
        showNotification('Errore nell\'invio del pacchetto Wake-on-LAN', 'error');
    }
}

async function shutdownDevice(deviceId) {
    if (!confirm('Sei sicuro di voler spegnere questo dispositivo?')) {
        return;
    }
    
    try {
        const response = await fetch(`/api/shutdown/${deviceId}`, {
            method: 'POST',
        });
        
        if (response.ok) {
            showNotification('Comando di spegnimento inviato', 'success');
        } else {
            const error = await response.json();
            showNotification(error.error || 'Errore nello spegnimento', 'error');
        }
    } catch (error) {
        console.error('Error shutting down device:', error);
        showNotification('Errore nello spegnimento del dispositivo', 'error');
    }
}

async function reorderDevices(newOrder) {
    try {
        const response = await fetch('/api/devices/reorder', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ order: newOrder }),
        });
        
        if (!response.ok) {
            showNotification('Errore nel riordino', 'error');
        }
    } catch (error) {
        console.error('Error reordering devices:', error);
        showNotification('Errore nel riordino dei dispositivi', 'error');
    }
}

// UI Rendering
function renderDevices() {
    const tbody = document.getElementById('devicesTableBody');
    const emptyState = document.getElementById('emptyState');
    const table = document.getElementById('devicesTable');
    
    if (devices.length === 0) {
        table.style.display = 'none';
        emptyState.style.display = 'block';
        return;
    }
    
    table.style.display = 'table';
    emptyState.style.display = 'none';
    
    tbody.innerHTML = devices.map(device => `
        <tr data-device-id="${device.id}" draggable="true">
            <td class="drag-handle">
                <i class="fas fa-grip-vertical"></i>
            </td>
            <td>${escapeHtml(device.name)}</td>
            <td><code>${escapeHtml(device.mac)}</code></td>
            <td>${device.ip ? escapeHtml(device.ip) : '-'}</td>
            <td>${escapeHtml(device.subnet)}</td>
            <td>${device.port}</td>
            <td><span class="os-badge">${escapeHtml(device.os_type || 'linux')}</span></td>
            <td>
                <span class="status-badge status-${device.status}">
                    <span class="status-indicator"></span>
                    ${device.status === 'online' ? 'Online' : device.status === 'offline' ? 'Offline' : 'Sconosciuto'}
                </span>
            </td>
            <td>
                <div class="actions">
                    <button class="action-btn edit" onclick="editDevice('${device.id}')" title="Modifica">
                        <i class="fas fa-edit"></i>
                    </button>
                    <button class="action-btn power" onclick="wakeDevice('${device.id}')" title="Accendi">
                        <i class="fas fa-power-off"></i>
                    </button>
                    ${device.ssh && device.ssh.enabled ? `
                        <button class="action-btn shutdown" onclick="shutdownDevice('${device.id}')" title="Spegni">
                            <i class="fas fa-stop-circle"></i>
                        </button>
                    ` : ''}
                    <button class="action-btn delete" onclick="deleteDevice('${device.id}')" title="Elimina">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </td>
        </tr>
    `).join('');
    
    // Initialize drag and drop
    initDragAndDrop();
}



function updateDeviceStatus(deviceId, status) {
    const row = document.querySelector(`tr[data-device-id="${deviceId}"]`);
    if (row) {
        const statusBadge = row.querySelector('.status-badge');
        statusBadge.className = `status-badge status-${status}`;
        statusBadge.innerHTML = `
            <span class="status-indicator"></span>
            ${status === 'online' ? 'Online' : status === 'offline' ? 'Offline' : 'Sconosciuto'}
        `;
    }
}

// Drag and Drop
function initDragAndDrop() {
    const rows = document.querySelectorAll('#devicesTableBody tr');
    
    rows.forEach(row => {
        row.addEventListener('dragstart', handleDragStart);
        row.addEventListener('dragover', handleDragOver);
        row.addEventListener('drop', handleDrop);
        row.addEventListener('dragend', handleDragEnd);
    });
}

function handleDragStart(e) {
    draggedElement = this;
    this.classList.add('dragging');
    e.dataTransfer.effectAllowed = 'move';
}

function handleDragOver(e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    
    const afterElement = getDragAfterElement(this.parentElement, e.clientY);
    if (afterElement == null) {
        this.parentElement.appendChild(draggedElement);
    } else {
        this.parentElement.insertBefore(draggedElement, afterElement);
    }
}

function handleDrop(e) {
    e.preventDefault();
}

function handleDragEnd(e) {
    this.classList.remove('dragging');
    
    // Get new order
    const rows = document.querySelectorAll('#devicesTableBody tr');
    const newOrder = Array.from(rows).map(row => row.dataset.deviceId);
    
    // Update devices array
    const reorderedDevices = [];
    newOrder.forEach(id => {
        const device = devices.find(d => d.id === id);
        if (device) {
            reorderedDevices.push(device);
        }
    });
    devices = reorderedDevices;
    
    // Send to server
    reorderDevices(newOrder);
}

function getDragAfterElement(container, y) {
    const draggableElements = [...container.querySelectorAll('tr:not(.dragging)')];
    
    return draggableElements.reduce((closest, child) => {
        const box = child.getBoundingClientRect();
        const offset = y - box.top - box.height / 2;
        
        if (offset < 0 && offset > closest.offset) {
            return { offset: offset, element: child };
        } else {
            return closest;
        }
    }, { offset: Number.NEGATIVE_INFINITY }).element;
}

// Modal Management
function openAddDeviceModal() {
    document.getElementById('modalTitle').textContent = 'Aggiungi Dispositivo';
    document.getElementById('deviceForm').reset();
    document.getElementById('deviceId').value = '';
    document.getElementById('sshConfig').style.display = 'none';
    document.getElementById('deviceModal').classList.add('active');
}

function editDevice(deviceId) {
    const device = devices.find(d => d.id === deviceId);
    if (!device) return;
    
    document.getElementById('modalTitle').textContent = 'Modifica Dispositivo';
    document.getElementById('deviceId').value = device.id;
    document.getElementById('deviceName').value = device.name;
    document.getElementById('deviceMac').value = device.mac;
    document.getElementById('deviceIp').value = device.ip || '';
    document.getElementById('deviceSubnet').value = device.subnet || '255.255.255.0';
    document.getElementById('devicePort').value = device.port || 9;
    document.getElementById('deviceOsType').value = device.os_type || 'linux';
    
    // SSH Config
    const sshEnabled = device.ssh && device.ssh.enabled;
    document.getElementById('sshEnabled').checked = sshEnabled;
    
    if (sshEnabled) {
        document.getElementById('sshConfig').style.display = 'block';
        document.getElementById('sshUsername').value = device.ssh.username || '';
        document.getElementById('sshAuthMethod').value = device.ssh.authMethod || 'password';
        
        if (device.ssh.authMethod === 'password') {
            document.getElementById('sshPasswordGroup').style.display = 'block';
            document.getElementById('sshKeyGroup').style.display = 'none';
            document.getElementById('sshKeyPassphraseGroup').style.display = 'none';
            document.getElementById('sshPassword').value = device.ssh.password || '';
        } else {
            document.getElementById('sshPasswordGroup').style.display = 'none';
            document.getElementById('sshKeyGroup').style.display = 'block';
            document.getElementById('sshKeyPassphraseGroup').style.display = 'block';
            document.getElementById('sshKey').value = device.ssh.sshKey || '';
            document.getElementById('sshKeyPassphrase').value = device.ssh.keyPassphrase || '';
        }
    } else {
        document.getElementById('sshConfig').style.display = 'none';
    }
    
    document.getElementById('deviceModal').classList.add('active');
}

function closeDeviceModal() {
    document.getElementById('deviceModal').classList.remove('active');
}

function toggleSSHConfig() {
    const enabled = document.getElementById('sshEnabled').checked;
    document.getElementById('sshConfig').style.display = enabled ? 'block' : 'none';
}

function toggleSSHAuthMethod() {
    const method = document.getElementById('sshAuthMethod').value;
    
    if (method === 'password') {
        document.getElementById('sshPasswordGroup').style.display = 'block';
        document.getElementById('sshKeyGroup').style.display = 'none';
        document.getElementById('sshKeyPassphraseGroup').style.display = 'none';
    } else {
        document.getElementById('sshPasswordGroup').style.display = 'none';
        document.getElementById('sshKeyGroup').style.display = 'block';
        document.getElementById('sshKeyPassphraseGroup').style.display = 'block';
    }
}

function handleDeviceSubmit(e) {
    e.preventDefault();
    
    const formData = new FormData(e.target);
    const deviceData = {
        id: formData.get('id') || undefined,
        name: formData.get('name'),
        mac: formData.get('mac'),
        ip: formData.get('ip'),
        subnet: formData.get('subnet'),
        port: parseInt(formData.get('port')),
        os_type: formData.get('os_type'),
        ssh: {
            enabled: document.getElementById('sshEnabled').checked,
        }
    };
    
    if (deviceData.ssh.enabled) {
        deviceData.ssh.username = formData.get('ssh_username');
        deviceData.ssh.authMethod = formData.get('ssh_auth_method');
        
        if (deviceData.ssh.authMethod === 'password') {
            deviceData.ssh.password = formData.get('ssh_password');
        } else {
            deviceData.ssh.sshKey = formData.get('ssh_key');
            deviceData.ssh.keyPassphrase = formData.get('ssh_key_passphrase');
        }
    }
    
    saveDevice(deviceData);
}

// Utility Functions
function escapeHtml(text) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return text.replace(/[&<>"']/g, m => map[m]);
}

function showNotification(message, type = 'info') {
    // Simple notification using alert for now
    // You can implement a more sophisticated notification system
    if (type === 'error') {
        alert('❌ ' + message);
    } else if (type === 'success') {
        alert('✅ ' + message);
    } else {
        alert('ℹ️ ' + message);
    }
}

