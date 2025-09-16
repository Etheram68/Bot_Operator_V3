#!/bin/bash
# Test rapide de l'uptime pour identifier le problème

echo "🕒 Test de l'uptime pour corriger l'affichage"
echo "============================================"

CONTAINER_NAME="bot-operateur-112"

echo "1. 📊 Status du container..."
docker ps --filter "name=$CONTAINER_NAME" --format "{{.Status}}"

echo ""
echo "2. 📅 StartedAt via inspect..."
started_at=$(docker inspect $CONTAINER_NAME | grep -o '"StartedAt":"[^"]*"' | sed 's/"StartedAt":"//' | sed 's/"//' | head -n1)
echo "StartedAt: $started_at"

echo ""
echo "3. ⏰ Test de conversion timestamp..."
if [ -n "$started_at" ]; then
    start_timestamp=$(date -d "$started_at" +%s 2>/dev/null || echo "ERROR")
    current_timestamp=$(date +%s)
    echo "Start timestamp: $start_timestamp"
    echo "Current timestamp: $current_timestamp"
    
    if [ "$start_timestamp" != "ERROR" ] && [ -n "$start_timestamp" ]; then
        uptime_seconds=$((current_timestamp - start_timestamp))
        hours=$((uptime_seconds / 3600))
        minutes=$(((uptime_seconds % 3600) / 60))
        echo "✅ Uptime calculé: ${hours}h ${minutes}m (${uptime_seconds}s)"
    else
        echo "❌ Erreur conversion timestamp"
    fi
else
    echo "❌ StartedAt non trouvé"
fi

echo ""
echo "4. 🔄 Méthode alternative - docker ps status..."
container_status=$(docker ps --filter "name=$CONTAINER_NAME" --format "{{.Status}}" 2>/dev/null)
echo "Status: $container_status"

if echo "$container_status" | grep -q "Up"; then
    if echo "$container_status" | grep -q "hour"; then
        hours=$(echo "$container_status" | grep -o '[0-9]\+ hour' | grep -o '[0-9]\+' || echo "0")
        minutes=$(echo "$container_status" | grep -o '[0-9]\+ minute' | grep -o '[0-9]\+' || echo "0")
        echo "✅ Méthode alternative: ${hours}h ${minutes}m"
    elif echo "$container_status" | grep -q "minute"; then
        minutes=$(echo "$container_status" | grep -o '[0-9]\+ minute' | grep -o '[0-9]\+' || echo "0")
        echo "✅ Méthode alternative: 0h ${minutes}m"
    else
        echo "⚠️ Format de status non reconnu"
    fi
fi