#!/bin/bash
# Script pour remettre à zéro le fichier unmatched_labels.jsonl

PATTERNS_FILE="/usr/share/nginx/html/data/unmatched_labels.jsonl"

# Vérifier si le fichier existe
if [ -f "$PATTERNS_FILE" ]; then
    # Faire une sauvegarde avant suppression
    BACKUP_FILE="/usr/share/nginx/html/data/unmatched_labels_backup_$(date +%Y%m%d_%H%M%S).jsonl"
    cp "$PATTERNS_FILE" "$BACKUP_FILE" 2>/dev/null || true

    # Vider le fichier
    > "$PATTERNS_FILE"

    echo '{"success":true,"message":"Labels non reconnus remis à zéro","backup":"'$BACKUP_FILE'"}'
else
    echo '{"success":true,"message":"Fichier déjà vide ou inexistant"}'
fi
