document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('downloadForm');
    const progressContainer = document.getElementById('progressContainer');
    const progressBar = document.getElementById('progressBar');
    const statusMessage = document.getElementById('statusMessage');
    const downloadLink = document.getElementById('downloadLink');
    const downloadFileBtn = document.getElementById('downloadFileBtn');
    const downloadBtn = document.getElementById('downloadBtn');
    const scaleInput = document.getElementById('scale');
    const scaleValue = document.getElementById('scaleValue');
    const sharpenInput = document.getElementById('sharpen_count');
    const sharpenValue = document.getElementById('sharpenValue');
    
    let currentTaskId = null;
    let statusCheckInterval = null;
    
    // Aggiorna i valori visualizzati per gli slider
    scaleInput.addEventListener('input', function() {
        scaleValue.textContent = this.value + 'x';
    });
    
    sharpenInput.addEventListener('input', function() {
        sharpenValue.textContent = this.value;
    });
    
    form.addEventListener('submit', function(e) {
        e.preventDefault();
        
        const url = document.getElementById('url').value;
        const scale = scaleInput.value;
        const sharpen_count = sharpenInput.value;
        
        // Disabilita il pulsante di download
        downloadBtn.disabled = true;
        downloadBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Elaborazione in corso...';
        
        // Mostra il contenitore di progresso
        progressContainer.style.display = 'block';
        downloadLink.style.display = 'none';
        
        // Invia la richiesta di download
        fetch('/download', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                url: url,
                scale: scale,
                sharpen_count: sharpen_count
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                throw new Error(data.error);
            }
            
            currentTaskId = data.task_id;
            
            // Avvia il controllo dello stato
            statusCheckInterval = setInterval(checkStatus, 1000);
        })
        .catch(error => {
            console.error('Error:', error);
            statusMessage.textContent = 'Errore: ' + error.message;
            statusMessage.className = 'alert alert-danger';
            
            // Riabilita il pulsante di download
            downloadBtn.disabled = false;
            downloadBtn.innerHTML = '<i class="bi bi-download"></i> Scarica Spartito';
        });
    });
    
    function checkStatus() {
        if (!currentTaskId) return;
        
        fetch(`/status/${currentTaskId}`)
        .then(response => response.json())
        .then(data => {
            if (data.status === 'not_found') {
                clearInterval(statusCheckInterval);
                statusMessage.textContent = 'Errore: Stato del task non trovato';
                statusMessage.className = 'alert alert-danger';
                
                // Riabilita il pulsante di download
                downloadBtn.disabled = false;
                downloadBtn.innerHTML = '<i class="bi bi-download"></i> Scarica Spartito';
                return;
            }
            
            // Aggiorna la barra di progresso
            progressBar.style.width = data.progress + '%';
            progressBar.setAttribute('aria-valuenow', data.progress);
            progressBar.textContent = Math.round(data.progress) + '%';
            
            // Aggiorna il messaggio di stato
            statusMessage.textContent = data.message;
            
            // Gestisci i diversi stati
            if (data.status === 'error') {
                clearInterval(statusCheckInterval);
                statusMessage.className = 'alert alert-danger';
                
                // Riabilita il pulsante di download
                downloadBtn.disabled = false;
                downloadBtn.innerHTML = '<i class="bi bi-download"></i> Scarica Spartito';
            } else if (data.status === 'completed') {
                clearInterval(statusCheckInterval);
                statusMessage.className = 'alert alert-success';
                
                // Mostra il link di download
                downloadFileBtn.href = data.download_url;
                downloadLink.style.display = 'block';
                
                // Riabilita il pulsante di download
                downloadBtn.disabled = false;
                downloadBtn.innerHTML = '<i class="bi bi-download"></i> Scarica Spartito';
            }
        })
        .catch(error => {
            console.error('Error checking status:', error);
            clearInterval(statusCheckInterval);
            statusMessage.textContent = 'Errore durante il controllo dello stato: ' + error.message;
            statusMessage.className = 'alert alert-danger';
            
            // Riabilita il pulsante di download
            downloadBtn.disabled = false;
            downloadBtn.innerHTML = '<i class="bi bi-download"></i> Scarica Spartito';
        });
    }
});