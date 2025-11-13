# Usa una base leggera di Python
FROM python:3.12-slim

WORKDIR /app


RUN apt-get update
RUN apt-get install -y gcc
RUN apt-get install -y libcairo2-dev
RUN apt-get install -y pkg-config
RUN apt-get install -y libfreetype6-dev
RUN apt-get install -y libffi-dev
RUN apt-get install -y libjpeg-dev
RUN apt-get install -y zlib1g-dev

RUN apt-get install -y libnss3
#RUN apt-get install -y libgconf-2-4
RUN apt-get install -y libfontconfig1
RUN apt-get install -y chromium
RUN apt-get install -y chromium
RUN rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN pwd && ls -la

CMD ["python3", "/app/src/main.py"]
