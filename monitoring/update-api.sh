#!/bin/bash
# Script pour mettre à jour les données d'API en continu

API_DIR="/usr/share/nginx/html/api"
CONTAINER_NAME="bot-operateur-112"
UPDATE_INTERVAL=5

echo "🔄 Démarrage du service de mise à jour API"
echo "📁 Répertoire API: $API_DIR"
echo "🐳 Container surveillé: $CONTAINER_NAME"
echo "⏱️  Intervalle: ${UPDATE_INTERVAL}s"

# Créer le répertoire API
mkdir -p "$API_DIR"

# Fonction pour générer les stats
generate_stats() {
    local output_file="$API_DIR/stats.json"
    local temp_file="${output_file}.tmp"
    
    # Vérifier si le container existe et est en cours d'exécution
    if ! docker ps --format "table {{.Names}}" | grep -q "$CONTAINER_NAME"; then
        cat > "$temp_file" << EOF
{
    "status": "stopped",
    "error": "Container not running",
    "timestamp": "$(date -Iseconds)"
}
EOF
        mv "$temp_file" "$output_file"
        return
    fi
    
    # Récupérer les stats
    local stats=$(docker stats --no-stream --format "table {{.Container}}\\t{{.CPUPerc}}\\t{{.MemUsage}}\\t{{.NetIO}}\\t{{.BlockIO}}" "$CONTAINER_NAME" 2>/dev/null | tail -n 1)
    local inspect=$(docker inspect "$CONTAINER_NAME" 2>/dev/null)
    
    if [ -z "$stats" ]; then
        cat > "$temp_file" << EOF
{
    "status": "error",
    "error": "Cannot get stats",
    "timestamp": "$(date -Iseconds)"
}
EOF
        mv "$temp_file" "$output_file"
        return
    fi
    
    # Parser les stats CPU avec normalisation simple
    local cpu_raw=$(echo "$stats" | awk '{print $2}' | sed 's/%//')
    local cpu="$cpu_raw"
    
    # Si CPU > 100%, c'est probablement du multi-core
    # Normaliser pour affichage (diviser par le nombre de cores alloués)
    if [ -n "$cpu_raw" ] && (( $(echo "$cpu_raw > 100" | bc -l 2>/dev/null || echo 0) )); then
        # Le container a 2.0 cores max selon docker-compose.yml
        # Donc 200% max théorique, normalisons sur 100%
        cpu=$(echo "scale=1; $cpu_raw / 2" | bc 2>/dev/null || echo "$cpu_raw")
        
        # Limiter à 100% pour l'affichage
        if (( $(echo "$cpu > 100" | bc -l 2>/dev/null || echo 0) )); then
            cpu="99.9"
        fi
    fi
    
    # Validation du format numérique
    if ! echo "$cpu" | grep -q '^[0-9]\+\(\.[0-9]\+\)\?$'; then
        cpu="0.0"
    fi
    
    # Parser la mémoire correctement
    local memory_raw=$(docker stats --no-stream --format "{{.MemUsage}}" "$CONTAINER_NAME" 2>/dev/null)
    local memory_usage=""
    local memory_limit=""
    
    if [ -n "$memory_raw" ]; then
        # Gérer différents formats (MiB, GiB, MB, GB)
        if echo "$memory_raw" | grep -q "MiB"; then
            memory_usage=$(echo "$memory_raw" | cut -d'/' -f1 | sed 's/MiB/MB/g' | tr -d ' ')
            memory_limit=$(echo "$memory_raw" | cut -d'/' -f2 | sed 's/MiB/MB/g' | tr -d ' ')
        elif echo "$memory_raw" | grep -q "GiB"; then
            memory_usage=$(echo "$memory_raw" | cut -d'/' -f1 | sed 's/GiB/GB/g' | tr -d ' ')
            memory_limit=$(echo "$memory_raw" | cut -d'/' -f2 | sed 's/GiB/GB/g' | tr -d ' ')
        elif echo "$memory_raw" | grep -q "MB"; then
            memory_usage=$(echo "$memory_raw" | cut -d'/' -f1 | tr -d ' ')
            memory_limit=$(echo "$memory_raw" | cut -d'/' -f2 | tr -d ' ')
        elif echo "$memory_raw" | grep -q "GB"; then
            memory_usage=$(echo "$memory_raw" | cut -d'/' -f1 | tr -d ' ')
            memory_limit=$(echo "$memory_raw" | cut -d'/' -f2 | tr -d ' ')
        else
            # Fallback sur l'ancienne méthode
            local memory=$(echo "$stats" | awk '{print $3}')
            memory_usage=$(echo "$memory" | cut -d'/' -f1 | sed 's/MiB/MB/g' | tr -d ' ')
            memory_limit=$(echo "$memory" | cut -d'/' -f2 | sed 's/MiB/MB/g' | tr -d ' ')
        fi
    else
        # Fallback si docker stats échoue
        memory_usage="unknown"
        memory_limit="unknown"
    fi
    
    # Obtenir l'uptime - méthode robuste
    local uptime_seconds=""
    local uptime_formatted="unknown"
    
    # Méthode 1: via jq si disponible
    if command -v jq >/dev/null 2>&1; then
        local started_at=$(echo "$inspect" | jq -r '.[0].State.StartedAt' 2>/dev/null || echo "")
        if [ -n "$started_at" ] && [ "$started_at" != "null" ] && [ "$started_at" != "" ]; then
            local start_timestamp=$(date -d "$started_at" +%s 2>/dev/null || echo "")
            local current_timestamp=$(date +%s)
            if [ -n "$start_timestamp" ] && [ "$start_timestamp" != "" ]; then
                uptime_seconds=$((current_timestamp - start_timestamp))
            fi
        fi
    fi
    
    # Méthode 2: si jq échoue, utiliser grep/sed
    if [ -z "$uptime_seconds" ] || [ "$uptime_seconds" = "" ]; then
        local started_at=$(echo "$inspect" | grep -o '"StartedAt":"[^"]*"' | sed 's/"StartedAt":"//' | sed 's/"//' | head -n1)
        if [ -n "$started_at" ]; then
            # Convertir le format ISO en timestamp
            local start_timestamp=$(date -d "$started_at" +%s 2>/dev/null || echo "")
            local current_timestamp=$(date +%s)
            if [ -n "$start_timestamp" ] && [ "$start_timestamp" != "" ]; then
                uptime_seconds=$((current_timestamp - start_timestamp))
            fi
        fi
    fi
    
    # Méthode 3: fallback - utiliser docker stats directement
    if [ -z "$uptime_seconds" ] || [ "$uptime_seconds" = "" ]; then
        # Extraire l'uptime depuis la colonne Status de docker ps
        local container_status=$(docker ps --filter "name=$CONTAINER_NAME" --format "{{.Status}}" 2>/dev/null)
        if echo "$container_status" | grep -q "Up"; then
            # Essayer d'extraire le temps depuis "Up X hours" ou "Up X minutes"
            if echo "$container_status" | grep -q "hour"; then
                local hours=$(echo "$container_status" | grep -o '[0-9]\+ hour' | grep -o '[0-9]\+')
                local minutes=$(echo "$container_status" | grep -o '[0-9]\+ minute' | grep -o '[0-9]\+' || echo "0")
                uptime_seconds=$(( (hours * 3600) + (minutes * 60) ))
            elif echo "$container_status" | grep -q "minute"; then
                local minutes=$(echo "$container_status" | grep -o '[0-9]\+ minute' | grep -o '[0-9]\+')
                uptime_seconds=$((minutes * 60))
            fi
        fi
    fi
    
    # Formater l'uptime
    if [ -n "$uptime_seconds" ] && [ "$uptime_seconds" != "" ] && [ "$uptime_seconds" -gt 0 ]; then
        local hours=$((uptime_seconds / 3600))
        local minutes=$(((uptime_seconds % 3600) / 60))
        uptime_formatted="${hours}h ${minutes}m"
    else
        # Si impossible de calculer, essayer une dernière méthode simple
        local container_status=$(docker ps --filter "name=$CONTAINER_NAME" --format "{{.Status}}" 2>/dev/null)
        if echo "$container_status" | grep -q "Up.*second"; then
            uptime_formatted="<1m"
            uptime_seconds=30
        elif echo "$container_status" | grep -q "Up"; then
            # Container actif mais uptime indéterminé
            uptime_formatted="actif"
            uptime_seconds=1
        else
            uptime_formatted="unknown"
            uptime_seconds=0
        fi
    fi
    
    # Générer le JSON
    cat > "$temp_file" << EOF
{
    "status": "running",
    "uptime": "$uptime_formatted",
    "uptime_seconds": $uptime_seconds,
    "cpu_percent": "$cpu",
    "memory_usage": "$memory_usage",
    "memory_limit": "$memory_limit",
    "timestamp": "$(date -Iseconds)"
}
EOF
    
    # Remplacer atomiquement le fichier
    mv "$temp_file" "$output_file"
}

# Fonction pour générer les logs
generate_logs() {
    local output_file="$API_DIR/logs.txt"
    local temp_file="${output_file}.tmp"

    if ! docker ps --format "table {{.Names}}" | grep -q "$CONTAINER_NAME"; then
        echo "Container $CONTAINER_NAME not running at $(date)" > "$temp_file"
        mv "$temp_file" "$output_file"
        return
    fi

    # Récupérer les logs (100 dernières lignes)
    docker logs --tail 100 "$CONTAINER_NAME" 2>&1 > "$temp_file"
    mv "$temp_file" "$output_file"
}

# Fonction pour générer les statistiques du bot
generate_bot_stats() {
    /usr/local/bin/extract-bot-stats.sh > /dev/null 2>&1
}

# Fonction pour générer les missions actives
generate_active_missions() {
    /usr/local/bin/extract-active-missions.sh > /dev/null 2>&1
}

# Génération initiale
echo "📊 Génération initiale des données..."
generate_stats
echo "✅ Stats générées: $(ls -la $API_DIR/stats.json 2>/dev/null || echo 'ERREUR')"
generate_logs
echo "✅ Logs générés: $(ls -la $API_DIR/logs.txt 2>/dev/null || echo 'ERREUR')"
generate_bot_stats
echo "✅ Bot stats générées: $(ls -la $API_DIR/bot-stats.json 2>/dev/null || echo 'ERREUR')"
generate_active_missions
echo "✅ Missions actives générées: $(ls -la $API_DIR/active-missions.json 2>/dev/null || echo 'ERREUR')"

# Fonction pour gérer la remise à zéro des patterns
handle_reset_trigger() {
    local trigger_file="$API_DIR/reset-trigger"
    local patterns_file="/usr/share/nginx/html/data/unrecognized_vehicle_patterns.jsonl"

    if [ -f "$trigger_file" ]; then
        echo "🗑️  Remise à zéro des patterns détectée..."

        # Faire une sauvegarde si le fichier existe
        if [ -f "$patterns_file" ]; then
            local backup_file="/usr/share/nginx/html/data/unrecognized_vehicle_patterns_backup_$(date +%Y%m%d_%H%M%S).jsonl"
            cp "$patterns_file" "$backup_file" 2>/dev/null || true
            echo "💾 Backup créé: $backup_file"
        fi

        # Vider le fichier
        > "$patterns_file"

        # Supprimer le trigger
        rm -f "$trigger_file"

        echo "✅ Patterns remis à zéro"
    fi
}

# Fonction pour gérer le redémarrage du bot
handle_restart_trigger() {
    local trigger_file="$API_DIR/restart-trigger"

    if [ -f "$trigger_file" ]; then
        echo "🔄 Redémarrage du bot détecté..."

        # Exécuter le script de redémarrage
        /usr/local/bin/restart-bot.sh

        # Supprimer le trigger
        rm -f "$trigger_file"

        echo "✅ Commande de redémarrage envoyée"
    fi
}

# Boucle de mise à jour
echo "🔄 Démarrage de la boucle de mise à jour..."
while true; do
    generate_stats
    generate_logs
    generate_bot_stats
    generate_active_missions
    handle_reset_trigger
    handle_restart_trigger
    sleep "$UPDATE_INTERVAL"
done