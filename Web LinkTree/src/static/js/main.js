document.addEventListener('DOMContentLoaded', function() {
    // Elementi DOM
    const entriesContainer = document.getElementById('entries-container');
    const addEntryBtn = document.getElementById('add-entry-btn');
    const editModeBtn = document.getElementById('edit-mode-btn');
    const entryModal = document.getElementById('entry-modal');
    const modalTitle = document.getElementById('modal-title');
    const entryForm = document.getElementById('entry-form');
    const entryIdInput = document.getElementById('entry-id');
    const entryTitleInput = document.getElementById('entry-title');
    const entryUrlInput = document.getElementById('entry-url');
    const entryIconInput = document.getElementById('entry-icon');
    const entryTemplateSelect = document.getElementById('entry-template');
    const templatePreview = document.getElementById('template-preview');
    const customOptions = document.getElementById('custom-options');
    
    // Nuovi elementi per i colori personalizzati
    const customBgColorInput = document.getElementById('custom-bg-color');
    const customBorderColorInput = document.getElementById('custom-border-color');
    const customTextColorInput = document.getElementById('custom-text-color');

    const iconPreview = document.getElementById('icon-preview');
    const closeModalBtn = document.querySelector('.close');
    const cancelBtn = document.getElementById('cancel-btn');
    
    // --- Controllo di robustezza per evitare errori ---
    const requiredElements = [
        { el: entriesContainer, name: 'entries-container' },
        { el: addEntryBtn, name: 'add-entry-btn' },
        { el: editModeBtn, name: 'edit-mode-btn' },
        { el: entryModal, name: 'entry-modal' },
        { el: entryForm, name: 'entry-form' },
        { el: entryTitleInput, name: 'entry-title' },
        { el: entryUrlInput, name: 'entry-url' },
        { el: entryTemplateSelect, name: 'entry-template' },
        { el: templatePreview, name: 'template-preview' },
        { el: customOptions, name: 'custom-options' },
        { el: customBgColorInput, name: 'custom-bg-color' },
        { el: customBorderColorInput, name: 'custom-border-color' },
        { el: customTextColorInput, name: 'custom-text-color' },
        { el: closeModalBtn, name: '.close' },
        { el: cancelBtn, name: 'cancel-btn' }
    ];

    for (const item of requiredElements) {
        if (!item.el) {
            console.error(`ERRORE: Elemento non trovato nel DOM: ${item.name}. Assicurati che l'HTML e il JS siano sincronizzati.`);
            // Interrompi l'esecuzione se mancano elementi critici
            return; 
        }
    }
    // --- Fine controllo ---

    let isEditMode = false;
    let entries = [];
    
    // Carica le entry dal server
    function loadEntries() {
        fetch('/api/entries')
            .then(response => response.json())
            .then(data => {
                entries = data;
                renderEntries();
            })
            .catch(error => console.error('Errore nel caricamento delle entry:', error));
    }
    
    // Renderizza le entry
    function renderEntries() {
        entriesContainer.innerHTML = '';
        
        entries.forEach(entry => {
            const entryElement = document.createElement('div');
            entryElement.className = 'entry';
            
            let buttonClass = 'button';
            let buttonStyle = '';

            if (entry.template === 'custom') {
                buttonClass += ' button-custom';
                const bgColor = entry.custom_color || '#000000';
                const borderColor = entry.custom_border_color || '#FFFFFF';
                const textColor = entry.custom_text_color || '#FFFFFF';
                buttonStyle = `--button-background: ${bgColor}; --button-border: 1px solid ${borderColor}; --button-text: ${textColor};`;
            } else if (entry.template) {
                buttonClass += ` button-${entry.template}`;
            } else {
                buttonClass += ' button-default';
            }
            
            entryElement.innerHTML = `
                ${entry.icon ? `<img src="/static/${entry.icon}" alt="${entry.title}" class="entry-icon">` : ''}
                <div class="entry-content">
                    <a href="${entry.url}" target="_blank" class="${buttonClass}" style="${buttonStyle}">${entry.title}</a>
                </div>
                <div class="entry-actions">
                    <button class="action-btn edit" data-id="${entry.id}">
                        <i class="fas fa-edit"></i>
                    </button>
                    <button class="action-btn delete" data-id="${entry.id}">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            `;
            
            entriesContainer.appendChild(entryElement);
        });
        
        // Aggiungi event listener per i pulsanti di azione
        document.querySelectorAll('.action-btn.edit').forEach(btn => {
            btn.addEventListener('click', function() {
                const entryId = this.getAttribute('data-id');
                openEditModal(entryId);
            });
        });
        
        document.querySelectorAll('.action-btn.delete').forEach(btn => {
            btn.addEventListener('click', function() {
                const entryId = this.getAttribute('data-id');
                if (confirm('Sei sicuro di voler eliminare questa entry?')) {
                    deleteEntry(entryId);
                }
            });
        });
    }
    
    // Apri il modal per aggiungere una nuova entry
    function openAddModal() {
        modalTitle.textContent = 'Aggiungi Nuovo Link';
        entryForm.reset();
        entryIdInput.value = '';
        iconPreview.innerHTML = '';
        updateTemplatePreview();
        entryModal.style.display = 'block';
    }
    
    // Apri il modal per modificare una entry esistente
    function openEditModal(entryId) {
        const entry = entries.find(e => e.id == entryId);
        if (!entry) return;
        
        modalTitle.textContent = 'Modifica Link';
        entryIdInput.value = entry.id;
        entryTitleInput.value = entry.title;
        entryUrlInput.value = entry.url;
        entryTemplateSelect.value = entry.template || 'default';
        
        if (entry.icon) {
            iconPreview.innerHTML = `<img src="/static/${entry.icon}" alt="Icona">`;
        } else {
            iconPreview.innerHTML = '';
        }
        
        if (entry.template === 'custom') {
            customOptions.style.display = 'block';
            customBgColorInput.value = entry.custom_color || '#000000';
            customBorderColorInput.value = entry.custom_border_color || '#FFFFFF';
            customTextColorInput.value = entry.custom_text_color || '#FFFFFF';
        } else {
            customOptions.style.display = 'none';
        }
        
        updateTemplatePreview();
        entryModal.style.display = 'block';
    }
    
    // Chiudi il modal
    function closeModal() {
        entryModal.style.display = 'none';
    }
    
    // Aggiorna l'anteprima del template in tempo reale
    function updateTemplatePreview() {
        const template = entryTemplateSelect.value;
        const title = entryTitleInput.value || 'Anteprima';
        
        let buttonClass = 'button';
        let buttonStyle = '';

        if (template === 'custom') {
            buttonClass += ' button-custom';
            customOptions.style.display = 'block';
            
            const bgColor = customBgColorInput.value;
            const borderColor = customBorderColorInput.value;
            const textColor = customTextColorInput.value;
            
            buttonStyle = `--button-background: ${bgColor}; --button-border: 1px solid ${borderColor}; --button-text: ${textColor};`;
        } else {
            buttonClass += ` button-${template}`;
            customOptions.style.display = 'none';
        }
        
        templatePreview.innerHTML = `
            <button class="${buttonClass}" style="${buttonStyle}">
                ${title}
            </button>
        `;
    }
    
    // Salva una entry (nuova o modificata)
    function saveEntry() {
        const entryId = entryIdInput.value;
        const title = entryTitleInput.value;
        const url = entryUrlInput.value;
        const template = entryTemplateSelect.value;
        
        if (!title || !url) {
            alert('Per favore, compila tutti i campi obbligatori.');
            return;
        }
        
        const formData = new FormData();
        formData.append('title', title);
        formData.append('url', url);
        formData.append('template', template);
        
        if (template === 'custom') {
            formData.append('custom_color', customBgColorInput.value);
            formData.append('custom_border_color', customBorderColorInput.value);
            formData.append('custom_text_color', customTextColorInput.value);
        }
        
        if (entryIconInput.files[0]) {
            formData.append('icon', entryIconInput.files[0]);
        }
        
        const apiCall = entryId ? 
            fetch(`/api/entries/${entryId}`, { method: 'PUT', body: formData }) :
            fetch('/api/entries', { method: 'POST', body: formData });
        
        apiCall
            .then(response => response.json())
            .then(data => {
                console.log(data.message);
                loadEntries();
                closeModal();
            })
            .catch(error => console.error('Errore nel salvataggio della entry:', error));
    }
    
    // Elimina una entry
    function deleteEntry(entryId) {
        fetch(`/api/entries/${entryId}`, { method: 'DELETE' })
            .then(response => response.json())
            .then(data => {
                console.log(data.message);
                loadEntries();
            })
            .catch(error => console.error('Errore nell\'eliminazione della entry:', error));
    }
    
    // Event Listeners
    addEntryBtn.addEventListener('click', openAddModal);
    
    editModeBtn.addEventListener('click', function() {
        isEditMode = !isEditMode;
        document.body.classList.toggle('edit-mode', isEditMode);
        this.innerHTML = isEditMode ? 
            '<i class="fas fa-times"></i> Fine Modifica' : 
            '<i class="fas fa-edit"></i> Modifica';
    });
    
    closeModalBtn.addEventListener('click', closeModal);
    cancelBtn.addEventListener('click', closeModal);
    
    entryForm.addEventListener('submit', function(e) {
        e.preventDefault();
        saveEntry();
    });
    
    // Event listener per l'anteprima in tempo reale
    entryTemplateSelect.addEventListener('change', updateTemplatePreview);
    entryTitleInput.addEventListener('input', updateTemplatePreview);
    customBgColorInput.addEventListener('input', updateTemplatePreview);
    customBorderColorInput.addEventListener('input', updateTemplatePreview);
    customTextColorInput.addEventListener('input', updateTemplatePreview);
    
    entryIconInput.addEventListener('change', function() {
        const file = this.files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = function(e) {
                iconPreview.innerHTML = `<img src="${e.target.result}" alt="Icona">`;
            };
            reader.readAsDataURL(file);
        }
    });
    
    // Chiudi il modal quando si clicca fuori di esso
    window.addEventListener('click', function(event) {
        if (event.target === entryModal) {
            closeModal();
        }
    });
    
    // Carica le entry all'avvio
    loadEntries();
});