# Dockerfile pour monitoring avec API réelle
FROM nginx:alpine

# Installer docker CLI, jq, bash, curl, bc et Python pour l'API Flask
RUN apk add --no-cache docker-cli jq bash curl bc python3 py3-pip

# Copier la configuration nginx
COPY nginx.conf /etc/nginx/nginx.conf

# Copier l'interface HTML
COPY index.html /usr/share/nginx/html/index.html

# Copier l'API Flask et installer les dépendances
COPY api-server.py /usr/local/bin/api-server.py
COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --break-system-packages --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt
RUN chmod +x /usr/local/bin/api-server.py

# Copier le script de mise à jour API
COPY update-api.sh /usr/local/bin/update-api.sh
RUN chmod +x /usr/local/bin/update-api.sh

# Copier le script de reset des patterns
COPY reset-patterns.sh /usr/local/bin/reset-patterns.sh
RUN chmod +x /usr/local/bin/reset-patterns.sh

# Copier le script de redémarrage du bot
COPY restart-bot.sh /usr/local/bin/restart-bot.sh
RUN chmod +x /usr/local/bin/restart-bot.sh

# Copier le script d'extraction des statistiques du bot
COPY extract-bot-stats.sh /usr/local/bin/extract-bot-stats.sh
RUN chmod +x /usr/local/bin/extract-bot-stats.sh

# Copier le script d'extraction des missions actives
COPY extract-active-missions.sh /usr/local/bin/extract-active-missions.sh
RUN chmod +x /usr/local/bin/extract-active-missions.sh

# Copier les scripts d'actions rapides
COPY stop-bot.sh /usr/local/bin/stop-bot.sh
COPY clear-cache.sh /usr/local/bin/clear-cache.sh
COPY toggle-debug.sh /usr/local/bin/toggle-debug.sh
RUN chmod +x /usr/local/bin/stop-bot.sh /usr/local/bin/clear-cache.sh /usr/local/bin/toggle-debug.sh

# Créer le répertoire API
RUN mkdir -p /usr/share/nginx/html/api

# Script de démarrage qui lance nginx et le service API
COPY start-monitoring.sh /usr/local/bin/start-monitoring.sh
RUN chmod +x /usr/local/bin/start-monitoring.sh

# Exposer le port
EXPOSE 80

# Sauvegarder l'entrypoint nginx original pour plus tard si nécessaire
RUN cp /docker-entrypoint.sh /docker-entrypoint-nginx.sh || true

# Utiliser notre propre script comme entrypoint principal
ENTRYPOINT ["/usr/local/bin/start-monitoring.sh"]