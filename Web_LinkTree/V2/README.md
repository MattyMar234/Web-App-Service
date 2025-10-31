# Link Manager

Una web app moderna per gestire una matrice di link personalizzabili.

## 🚀 Caratteristiche

### Gestione Link
- **Matrice adattiva**: I pulsanti si adattano automaticamente alla larghezza della pagina
- **Personalizzazione completa**: Ogni link può avere colori personalizzati per testo, sfondo e bordo
- **Supporto gradiente**: Possibilità di usare gradienti lineari per lo sfondo con angolo personalizzabile
- **Font personalizzati**: Selezione tra diversi font per ogni pulsante
- **Nome personalizzato**: Il pulsante mostra un nome a scelta, non l'URL

### Modalità Modifica
- **Drag & Drop**: Riordina i pulsanti trascinandoli
- **Modifica inline**: Pulsanti per modificare ed eliminare i link direttamente dalla griglia
- **Pulsante "+"**: Aggiungi nuovi link sia dall'header che dalla griglia

### Temi e Dimensioni
- **Tema chiaro/scuro**: Switch rapido tra modalità chiaro e scuro
- **Dimensioni selezionabili**: Scegli tra 120px, 150px, 180px e 200px

### Import/Export
- **Esportazione JSON**: Scarica tutti i tuoi link e impostazioni
- **Importazione JSON**: Ripristina o condividi le tue configurazioni

## 🏗️ Architettura

### Backend (Flask + Python)
- **Factory Pattern**: Sistema modulare per la gestione dati
- **Storage Types supportati**:
  - ✅ JSON (file locale) - implementato
  - 🔄 PostgreSQL - placeholder
  - 🔄 MongoDB - placeholder

### Frontend (Vanilla HTML/CSS/JS)
- Nessun framework, solo HTML, CSS e JavaScript puro
- Design moderno con animazioni fluide
- Completamente responsive

## 📁 Struttura File

```
/app/
├── backend/
│   ├── flask_server.py      # Server Flask principale
│   ├── data_manager.py       # Factory pattern per gestione dati
│   ├── data.json             # File dati (generato automaticamente)
│   └── .env                  # Configurazione (STORAGE_TYPE=JSON)
└── frontend/
    └── public/
        ├── index.html        # Interfaccia utente
        ├── styles.css        # Stili moderni
        └── app.js            # Logica applicazione
```

## 🔧 API Endpoints

- `GET /api/links` - Ottieni tutti i link
- `POST /api/links` - Crea nuovo link
- `PUT /api/links/<id>` - Aggiorna link
- `DELETE /api/links/<id>` - Elimina link
- `PUT /api/links/reorder` - Riordina link
- `GET /api/export` - Esporta dati in JSON
- `POST /api/import` - Importa dati da JSON
- `GET /api/settings` - Ottieni impostazioni
- `PUT /api/settings` - Aggiorna impostazioni

## 🚀 Utilizzo

L'applicazione è accessibile su `http://localhost:8001`

### Aggiungere un Link
1. Clicca su "+ Aggiungi Link" nell'header o sul pulsante "+" nella griglia
2. Compila il form con:
   - Nome del pulsante
   - URL
   - Colori (testo, sfondo, bordo)
   - Opzionale: Abilita gradiente e configura i colori
   - Seleziona il font
3. Clicca "Salva"

### Modificare i Link
1. Clicca su "Modalità Modifica"
2. Trascina i pulsanti per riordinarli
3. Usa le icone su ogni pulsante per modificare o eliminare

### Cambiare Tema/Dimensioni
- **Tema**: Clicca l'icona sole/luna nell'header
- **Dimensione**: Seleziona dal menu a tendina nell'header

### Import/Export
- **Export**: Clicca l'icona download per scaricare il file JSON
- **Import**: Clicca l'icona upload e seleziona un file JSON

## 🔄 Cambiare Storage Backend

Per cambiare il tipo di archiviazione, modifica il file `/app/backend/.env`:

```env
STORAGE_TYPE=JSON      # o POSTGRES o MONGODB
```

Nota: PostgreSQL e MongoDB richiedono l'implementazione dei rispettivi DataManager.

## 🎨 Personalizzazione

### Colori Tema
Modifica le variabili CSS in `styles.css`:

```css
:root {
    --primary: #4f46e5;
    --bg-primary: #ffffff;
    /* ... altri colori ... */
}
```

### Font Disponibili
- Arial
- Space Grotesk
- Inter
- Courier New
- Georgia
- Trebuchet MS
- Verdana
- Times New Roman

## 🛠️ Tecnologie Utilizzate

- **Backend**: Flask, Python 3.11
- **Frontend**: HTML5, CSS3, JavaScript (ES6+)
- **Storage**: JSON (file system)
- **Pattern**: Factory Pattern per estensibilità

## 📝 Note

- I dati sono salvati in `/app/backend/data.json`
- L'applicazione usa il factory pattern per facilitare il cambio di database in futuro
- Design responsive e accessibile
- Nessuna autenticazione (uso personale)

---

# Welcome to emergent!
