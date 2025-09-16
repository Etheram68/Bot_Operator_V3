# Dockerfile ultra-simple pour Bot Opérateur 112 - QNAP
FROM python:3.11-slim

# Variables d'environnement
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV DEBIAN_FRONTEND=noninteractive

# Installation des dépendances système pour Playwright
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    ca-certificates \
    xvfb \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libxss1 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# Répertoire de travail
WORKDIR /app

# Copier requirements et installer Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Installer Playwright (sans install-deps car déjà installé manuellement)
RUN playwright install chromium

# Copier tout le code
COPY . .

# Créer dossiers avec bonnes permissions
RUN mkdir -p /app/logs /app/data /app/cache /app/config
RUN chmod 777 /app/logs /app/data /app/cache /app/config

# Script d'entrée
RUN chmod +x docker-entrypoint.sh

# Volumes
VOLUME ["/app/logs", "/app/data", "/app/cache"]

# Port
EXPOSE 8080

# Point d'entrée
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["python", "main.py", "--continuous"]