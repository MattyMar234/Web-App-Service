// API Base URL
const API_URL = '/api';

// State
let links = [];
let settings = { theme: 'light', buttonSize: 150 };
let isEditMode = false;
let editingLinkId = null;
let draggedElement = null;

// DOM Elements
const linksGrid = document.getElementById('linksGrid');
const addLinkBtn = document.getElementById('addLinkBtn');
const editModeBtn = document.getElementById('editModeBtn');
const linkModal = document.getElementById('linkModal');
const linkForm = document.getElementById('linkForm');
const closeModal = document.getElementById('closeModal');
const cancelBtn = document.getElementById('cancelBtn');
const modalTitle = document.getElementById('modalTitle');
const themeToggle = document.getElementById('themeToggle');
const buttonSizeSelect = document.getElementById('buttonSizeSelect');
const useGradientCheckbox = document.getElementById('useGradient');
const solidColorGroup = document.getElementById('solidColorGroup');
const gradientGroup = document.getElementById('gradientGroup');
const exportBtn = document.getElementById('exportBtn');
const importBtn = document.getElementById('importBtn');
const importFile = document.getElementById('importFile');

// Initialize
init();

async function init() {
    await loadSettings();
    await loadLinks();
    setupEventListeners();
}

// Load settings
async function loadSettings() {
    try {
        const response = await fetch(`${API_URL}/settings`);
        if (response.ok) {
            settings = await response.json();
            applySettings();
        }
    } catch (error) {
        console.error('Error loading settings:', error);
    }
}

// Apply settings
function applySettings() {
    // Apply theme
    document.documentElement.setAttribute('data-theme', settings.theme);
    
    // Apply button size
    document.documentElement.style.setProperty('--button-size', `${settings.buttonSize}px`);
    buttonSizeSelect.value = settings.buttonSize;
}

// Save settings
async function saveSettings() {
    try {
        await fetch(`${API_URL}/settings`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        });
    } catch (error) {
        console.error('Error saving settings:', error);
    }
}

// Load links
async function loadLinks() {
    try {
        const response = await fetch(`${API_URL}/links`);
        if (response.ok) {
            links = await response.json();
            renderLinks();
        }
    } catch (error) {
        console.error('Error loading links:', error);
    }
}

// Render links
function renderLinks() {
    linksGrid.innerHTML = '';
    
    links.forEach(link => {
        const linkElement = createLinkElement(link);
        linksGrid.appendChild(linkElement);
    });
    
    // Add "Add Link" button at the end
    if (!isEditMode) {
        const addBtn = document.createElement('div');
        addBtn.className = 'link-item add-link-btn';
        addBtn.innerHTML = '+';
        addBtn.setAttribute('data-testid', 'add-link-grid-btn');
        addBtn.onclick = () => openModal();
        linksGrid.appendChild(addBtn);
    }
}

// Create link element
function createLinkElement(link) {
    const div = document.createElement('div');
    div.className = 'link-item';
    div.setAttribute('data-link-id', link.id);
    div.setAttribute('data-testid', `link-item-${link.id}`);
    div.setAttribute('draggable', isEditMode);
    
    // Apply styles
    div.style.color = link.textColor;
    div.style.borderColor = link.borderColor;
    div.style.borderWidth = '3px';
    div.style.borderStyle = 'solid';
    div.style.fontFamily = link.fontFamily || 'Arial';
    
    if (link.useGradient) {
        div.style.background = `linear-gradient(${link.gradientAngle || 45}deg, ${link.gradientColor1}, ${link.gradientColor2})`;
    } else {
        div.style.backgroundColor = link.bgColor;
    }
    
    div.innerHTML = `
        <span>${link.name}</span>
        ${isEditMode ? `
            <div class="edit-controls">
                <button class="edit-btn" onclick="editLink('${link.id}')" data-testid="edit-link-${link.id}">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                        <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                    </svg>
                </button>
                <button class="edit-btn" onclick="deleteLink('${link.id}')" data-testid="delete-link-${link.id}">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="3 6 5 6 21 6"/>
                        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                    </svg>
                </button>
            </div>
        ` : ''}
    `;
    
    // Add click handler (only if not in edit mode)
    if (!isEditMode) {
        div.onclick = () => window.open(link.url, '_blank');
    }
    
    // Add drag handlers
    if (isEditMode) {
        div.ondragstart = handleDragStart;
        div.ondragover = handleDragOver;
        div.ondrop = handleDrop;
        div.ondragend = handleDragEnd;
    }
    
    return div;
}

// Drag and drop handlers
function handleDragStart(e) {
    draggedElement = e.target.closest('.link-item');
    draggedElement.classList.add('dragging');
    e.dataTransfer.effectAllowed = 'move';
}

function handleDragOver(e) {
    if (e.preventDefault) {
        e.preventDefault();
    }
    e.dataTransfer.dropEffect = 'move';
    return false;
}

function handleDrop(e) {
    if (e.stopPropagation) {
        e.stopPropagation();
    }
    
    const dropTarget = e.target.closest('.link-item');
    if (draggedElement !== dropTarget && dropTarget) {
        const draggedId = draggedElement.getAttribute('data-link-id');
        const targetId = dropTarget.getAttribute('data-link-id');
        
        // Reorder links array
        const draggedIndex = links.findIndex(l => l.id === draggedId);
        const targetIndex = links.findIndex(l => l.id === targetId);
        
        const [removed] = links.splice(draggedIndex, 1);
        links.splice(targetIndex, 0, removed);
        
        // Save new order
        saveLinksOrder();
        renderLinks();
    }
    
    return false;
}

function handleDragEnd() {
    if (draggedElement) {
        draggedElement.classList.remove('dragging');
    }
}

// Save links order
async function saveLinksOrder() {
    try {
        await fetch(`${API_URL}/links/reorder`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ links })
        });
    } catch (error) {
        console.error('Error saving links order:', error);
    }
}

// Open modal
function openModal(link = null) {
    editingLinkId = link ? link.id : null;
    modalTitle.textContent = link ? 'Modifica Link' : 'Aggiungi Link';
    
    if (link) {
        document.getElementById('linkName').value = link.name;
        document.getElementById('linkUrl').value = link.url;
        document.getElementById('textColor').value = link.textColor;
        document.getElementById('borderColor').value = link.borderColor;
        document.getElementById('fontFamily').value = link.fontFamily || 'Arial';
        
        if (link.useGradient) {
            useGradientCheckbox.checked = true;
            document.getElementById('gradientColor1').value = link.gradientColor1;
            document.getElementById('gradientColor2').value = link.gradientColor2;
            document.getElementById('gradientAngle').value = link.gradientAngle || 45;
            solidColorGroup.style.display = 'none';
            gradientGroup.style.display = 'block';
        } else {
            useGradientCheckbox.checked = false;
            document.getElementById('bgColor').value = link.bgColor;
            solidColorGroup.style.display = 'block';
            gradientGroup.style.display = 'none';
        }
    } else {
        linkForm.reset();
        useGradientCheckbox.checked = false;
        solidColorGroup.style.display = 'block';
        gradientGroup.style.display = 'none';
    }
    
    linkModal.classList.add('active');
}

// Close modal
function closeModalFn() {
    linkModal.classList.remove('active');
    editingLinkId = null;
}

// Submit form
async function submitForm(e) {
    e.preventDefault();
    
    const formData = {
        name: document.getElementById('linkName').value,
        url: document.getElementById('linkUrl').value,
        textColor: document.getElementById('textColor').value,
        borderColor: document.getElementById('borderColor').value,
        fontFamily: document.getElementById('fontFamily').value,
        useGradient: useGradientCheckbox.checked
    };
    
    if (formData.useGradient) {
        formData.gradientColor1 = document.getElementById('gradientColor1').value;
        formData.gradientColor2 = document.getElementById('gradientColor2').value;
        formData.gradientAngle = parseInt(document.getElementById('gradientAngle').value);
    } else {
        formData.bgColor = document.getElementById('bgColor').value;
    }
    
    try {
        let response;
        if (editingLinkId) {
            response = await fetch(`${API_URL}/links/${editingLinkId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(formData)
            });
        } else {
            response = await fetch(`${API_URL}/links`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(formData)
            });
        }
        
        if (response.ok) {
            await loadLinks();
            closeModalFn();
        }
    } catch (error) {
        console.error('Error saving link:', error);
    }
}

// Edit link
function editLink(linkId) {
    const link = links.find(l => l.id === linkId);
    if (link) {
        openModal(link);
    }
}

// Delete link
async function deleteLink(linkId) {
    if (!confirm('Sei sicuro di voler eliminare questo link?')) {
        return;
    }
    
    try {
        const response = await fetch(`${API_URL}/links/${linkId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            await loadLinks();
        }
    } catch (error) {
        console.error('Error deleting link:', error);
    }
}

// Toggle edit mode
function toggleEditMode() {
    isEditMode = !isEditMode;
    editModeBtn.textContent = isEditMode ? 'Esci da Modifica' : 'Modalità Modifica';
    editModeBtn.classList.toggle('btn-primary', isEditMode);
    linksGrid.classList.toggle('edit-mode', isEditMode);
    renderLinks();
}

// Toggle theme
function toggleTheme() {
    settings.theme = settings.theme === 'light' ? 'dark' : 'light';
    applySettings();
    saveSettings();
}

// Change button size
function changeButtonSize(e) {
    settings.buttonSize = parseInt(e.target.value);
    applySettings();
    saveSettings();
}

// Toggle gradient
function toggleGradient() {
    if (useGradientCheckbox.checked) {
        solidColorGroup.style.display = 'none';
        gradientGroup.style.display = 'block';
    } else {
        solidColorGroup.style.display = 'block';
        gradientGroup.style.display = 'none';
    }
}

// Export data
async function exportData() {
    try {
        const response = await fetch(`${API_URL}/export`);
        if (response.ok) {
            const data = await response.json();
            const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `link-manager-export-${Date.now()}.json`;
            a.click();
            URL.revokeObjectURL(url);
        }
    } catch (error) {
        console.error('Error exporting data:', error);
    }
}

// Import data
function triggerImport() {
    importFile.click();
}

async function importData(e) {
    const file = e.target.files[0];
    if (!file) return;
    
    try {
        const text = await file.text();
        const data = JSON.parse(text);
        
        const response = await fetch(`${API_URL}/import`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        
        if (response.ok) {
            await loadSettings();
            await loadLinks();
            alert('Dati importati con successo!');
        }
    } catch (error) {
        console.error('Error importing data:', error);
        alert('Errore durante l\'importazione dei dati');
    }
    
    importFile.value = '';
}

// Event listeners
function setupEventListeners() {
    addLinkBtn.onclick = () => openModal();
    editModeBtn.onclick = toggleEditMode;
    closeModal.onclick = closeModalFn;
    cancelBtn.onclick = closeModalFn;
    linkForm.onsubmit = submitForm;
    themeToggle.onclick = toggleTheme;
    buttonSizeSelect.onchange = changeButtonSize;
    useGradientCheckbox.onchange = toggleGradient;
    exportBtn.onclick = exportData;
    importBtn.onclick = triggerImport;
    importFile.onchange = importData;
    
    // Close modal on background click
    linkModal.onclick = (e) => {
        if (e.target === linkModal) {
            closeModalFn();
        }
    };
}
