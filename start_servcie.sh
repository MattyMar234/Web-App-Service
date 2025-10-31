#!/usr/bin/env bash
# start_all.sh
# Avvia più progetti Python in parallelo usando 'uv' per la gestione degli ambienti

set -e

# === CONFIGURAZIONE MANUALE ===
# Imposta qui i percorsi ai progetti, ai file .py e ai requirements.
# NOTA: Il percorso del venv non è più strettamente necessario con 'uv',
# ma lo manteniamo per chiarezza. 'uv' cercherà automaticamente .venv nella cartella del progetto.

# === PROGETTO 1 ===
PROJECT1_DIR="$HOME/Web-App-Service/WOL_WebService"
# VENV1="$PROJECT1_DIR/.venv" # Non più necessario specificarlo qui
SCRIPT1="$PROJECT1_DIR/src/main.py"
RQ_PATH1="$PROJECT1_DIR/requirements.txt"
ARGS1="--port 5001"

# === PROGETTO 2 ===
PROJECT2_DIR="$HOME/Web-App-Service/Web_LinkTree"
# VENV2="$PROJECT2_DIR/.venv" # Non più necessario specificarlo qui
SCRIPT2="$PROJECT2_DIR/V2/backend/flask_server.py"
RQ_PATH2="$PROJECT2_DIR/V2/backend/requirements.txt"
ARGS2="--port 5002"

# === PROGETTO 3 ===
PROJECT3_DIR="$HOME/Web-App-Service/Whisper_Web_Interface"
# VENV3="$PROJECT3_DIR/.venv" # Non più necessario specificarlo qui
SCRIPT3="$PROJECT3_DIR/server.py"
RQ_PATH3="$PROJECT3_DIR/V2/requirements.txt" # Controlla che questo percorso sia corretto
ARGS3="--port 5003"


# === FUNZIONE DI CONTROLLO DEGLI STRUMENTI DI SISTEMA ===
check_system_tools() {
    echo "🔍 Verifica strumenti di sistema..."

    # Controllo pip3 (necessario per installare uv se non presente)
    if ! command -v pip3 >/dev/null 2>&1; then
        echo "❌ pip3 non trovato! Installa python3-pip prima di procedere."
        exit 1
    else
        echo "✅ pip3 trovato."
    fi

    # Controllo uv
    if ! command -v uv >/dev/null 2>&1; then
        echo "⚠️  uv non installato. Installazione in corso..."
        pip3 install --break-system-packages uv
        echo "✅ uv installato correttamente."
    else
        echo "✅ uv è già installato."
    fi
}

# === FUNZIONE DI AVVIO CON UV ===
start_project() {
    local PROJECT_DIR="$1"
    local SCRIPT_PATH="$2"
    local RQ_PATH="$3"
    local ARGS="$4"

    echo "--------------------------------------------"
    echo "🔧 Avvio del progetto in $PROJECT_DIR"

    # Controlla esistenza progetto
    if [ ! -d "$PROJECT_DIR" ]; then
        echo "❌ Cartella progetto non trovata: $PROJECT_DIR"
        return 1 # Esce con un codice di errore
    fi

    cd "$PROJECT_DIR"

    # 'uv pip install' creerà automaticamente un ambiente virtuale (.venv) se non esiste
    # e installerà le dipendenze al suo interno. È un comando idempotente.
    if [ -f "$RQ_PATH" ]; then
        echo "📦 Installazione/Aggiornamento dipendenze da $RQ_PATH con 'uv'..."
        uv pip install -r "$RQ_PATH"
    else
        echo "⚠️  File requirements.txt non trovato in $RQ_PATH. Procedo senza installare dipendenze."
    fi

    # Avvia il server in background usando 'uv run'
    # 'uv run' trova e usa automaticamente l'ambiente virtuale del progetto.
    if [ -f "$SCRIPT_PATH" ]; then
        echo "🚀 Avvio di $SCRIPT_PATH con argomenti: $ARGS usando 'uv run'"
        # Usa 'uv run' per eseguire lo script nell'ambiente gestito da uv
        nohup uv run python "$SCRIPT_PATH" $ARGS > "$PROJECT_DIR/server.log" 2>&1 &
        echo "✅ Server avviato in background (log: $PROJECT_DIR/server.log)"
    else
        echo "❌ File script non trovato: $SCRIPT_PATH"
        return 1 # Esce con un codice di errore
    fi
}

# === ESECUZIONE ===
check_system_tools

echo "============================================"
echo "🚀 Avvio parallelo di tutti i progetti..."

# === AVVIO PARALLELO ===
# Nota: Ho rimosso il parametro VENV dalla chiamata alla funzione
start_project "$PROJECT1_DIR" "$SCRIPT1" "$RQ_PATH1" "$ARGS1" &
PID1=$!

start_project "$PROJECT2_DIR" "$SCRIPT2" "$RQ_PATH2" "$ARGS2" &
PID2=$!

#start_project "$PROJECT3_DIR" "$SCRIPT3" "$RQ_PATH3" "$ARGS3" &
PID3=$!

# Attende che tutti i processi in background siano stati avviati
# NOTA: 'wait' qui attende la terminazione dei processi, non solo il loro avvio.
# Per questo caso d'uso, va bene così perché lo script principale rimarrà in attesa.
# Se vuoi solo lanciarli e uscire, puoi rimuovere 'wait'.
wait

echo "============================================"
echo "🎉 Tutti i progetti sono stati avviati in background."
echo "📊 Puoi controllare i log nelle rispettive cartelle dei progetti (server.log)."
