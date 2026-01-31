#!/bin/bash
# Script pour créer un fichier trigger de redémarrage du bot

TRIGGER_FILE="/usr/share/nginx/html/api/restart-trigger"

# Créer le fichier trigger
touch "$TRIGGER_FILE"

# Retourner une réponse JSON
echo '{"success":true,"message":"Redémarrage du bot en cours..."}'
