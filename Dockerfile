# Dockerfile robuste pour QNAP avec toutes les optimisations
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

# Variables d'environnement optimisées
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONOPTIMIZE=1 \
    DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1

# Répertoire de travail
WORKDIR /app

# Copier requirements et installer
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code
COPY . .

# Créer dossiers et permissions
RUN mkdir -p logs data cache config && \
    chmod 777 logs data cache config

# Script d'entrée
RUN chmod +x docker-entrypoint.sh

# Variables d'environnement configurables via .env (pas de valeurs par défaut hardcodées)

# Volumes pour persistance
VOLUME ["/app/logs", "/app/data", "/app/cache"]

# Point d'entrée
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["python", "main.py", "--continuous"]