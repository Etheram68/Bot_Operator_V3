#!/bin/bash
# Script pour créer un fichier trigger de reset
# Ce script sera appelé depuis nginx via un CGI ou exec

TRIGGER_FILE="/usr/share/nginx/html/api/reset-trigger"

# Créer le fichier trigger
touch "$TRIGGER_FILE"

# Retourner une réponse JSON
echo '{"success":true,"message":"Demande de reset enregistrée"}'
