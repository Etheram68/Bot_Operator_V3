# Dockerfile robuste pour QNAP avec toutes les optimisations
FROM python:3.13-slim-bookworm

# Variables d'environnement optimisées
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONOPTIMIZE=1 \
    DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1

# Installer les dépendances système requises par Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libxkbcommon0 \
    libatspi2.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libwayland-client0 \
    && rm -rf /var/lib/apt/lists/*

# Répertoire de travail
WORKDIR /app

# Copier requirements et installer
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Installer les navigateurs Playwright
RUN playwright install chromium

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