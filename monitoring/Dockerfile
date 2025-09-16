# Dockerfile pour monitoring avec API réelle
FROM nginx:alpine

# Installer docker CLI, jq et bash
RUN apk add --no-cache docker-cli jq bash curl

# Copier la configuration nginx
COPY nginx.conf /etc/nginx/nginx.conf

# Copier le script de mise à jour API
COPY update-api.sh /usr/local/bin/update-api.sh
RUN chmod +x /usr/local/bin/update-api.sh

# Créer le répertoire API
RUN mkdir -p /usr/share/nginx/html/api

# Script de démarrage qui lance nginx et le service API
COPY start-monitoring.sh /usr/local/bin/start-monitoring.sh
RUN chmod +x /usr/local/bin/start-monitoring.sh

# Exposer le port
EXPOSE 80

# Point d'entrée
CMD ["/usr/local/bin/start-monitoring.sh"]