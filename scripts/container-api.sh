#!/bin/bash
# API simple pour récupérer les stats réelles du container bot

# Fonction pour obtenir les stats du container
get_container_stats() {
    local container_name="bot-operateur-112"
    
    # Vérifier si le container existe et est en cours d'exécution
    if ! docker ps --format "table {{.Names}}" | grep -q "$container_name"; then
        echo '{"status":"stopped","error":"Container not running"}'
        return
    fi
    
    # Récupérer les stats
    local stats=$(docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.BlockIO}}" $container_name 2>/dev/null | tail -n 1)
    local inspect=$(docker inspect $container_name 2>/dev/null)
    
    if [ -z "$stats" ]; then
        echo '{"status":"error","error":"Cannot get stats"}'
        return
    fi
    
    # Parser les stats
    local cpu=$(echo "$stats" | awk '{print $2}' | sed 's/%//')
    local memory=$(echo "$stats" | awk '{print $3}')
    local memory_usage=$(echo "$memory" | cut -d'/' -f1 | sed 's/MiB/MB/g')
    local memory_limit=$(echo "$memory" | cut -d'/' -f2 | sed 's/MiB/MB/g')
    
    # Obtenir l'uptime
    local started_at=$(echo "$inspect" | jq -r '.[0].State.StartedAt' 2>/dev/null || echo "")
    local uptime_seconds=""
    if [ -n "$started_at" ] && [ "$started_at" != "null" ]; then
        local start_timestamp=$(date -d "$started_at" +%s 2>/dev/null || echo "")
        local current_timestamp=$(date +%s)
        if [ -n "$start_timestamp" ]; then
            uptime_seconds=$((current_timestamp - start_timestamp))
        fi
    fi
    
    # Formater l'uptime
    local uptime_formatted=""
    if [ -n "$uptime_seconds" ]; then
        local hours=$((uptime_seconds / 3600))
        local minutes=$(((uptime_seconds % 3600) / 60))
        uptime_formatted="${hours}h ${minutes}m"
    else
        uptime_formatted="unknown"
    fi
    
    # Retourner le JSON
    cat << EOF
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
}

# Fonction pour obtenir les logs du container
get_container_logs() {
    local container_name="bot-operateur-112"
    local lines=${1:-50}  # Par défaut 50 lignes
    
    if ! docker ps --format "table {{.Names}}" | grep -q "$container_name"; then
        echo "Container $container_name not running"
        return
    fi
    
    docker logs --tail "$lines" "$container_name" 2>&1
}

# Point d'entrée principal
case "${1:-stats}" in
    "stats")
        get_container_stats
        ;;
    "logs")
        get_container_logs "${2:-50}"
        ;;
    "help")
        echo "Usage: $0 [stats|logs|help] [lines_for_logs]"
        echo "  stats: Get container statistics (default)"
        echo "  logs [N]: Get last N lines of container logs (default 50)"
        echo "  help: Show this help"
        ;;
    *)
        echo "Unknown command: $1"
        echo "Use '$0 help' for usage information"
        exit 1
        ;;
esac