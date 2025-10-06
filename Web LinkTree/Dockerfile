# Usa una base leggera di Python
FROM python:3.12-slim

# Imposta la directory di lavoro dentro al container
WORKDIR /app

# Copia i file di progetto
COPY requirements.txt ./

# Installa le dipendenze (senza cache per ridurre peso immagine)
RUN pip install --no-cache-dir -r requirements.txt

# Copia tutto il codice sorgente
COPY . .

# Espone la porta usata da Flask
EXPOSE 8080

# Imposta variabili d'ambiente (disabilita il buffering di Python)
ENV PYTHONUNBUFFERED=1
ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0


CMD ["python3", "scr/main.py"]
