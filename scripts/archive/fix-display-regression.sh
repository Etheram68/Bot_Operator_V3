#!/bin/bash
# Script pour corriger la régression d'affichage des stats

echo "🔧 Correction de la régression d'affichage"
echo "=========================================="

# Détecter docker compose
DOCKER_COMPOSE_CMD=""
if docker compose version &> /dev/null; then
    DOCKER_COMPOSE_CMD="docker compose"
elif command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE_CMD="docker-compose"
else
    echo "❌ Docker Compose non trouvé"
    exit 1
fi

echo "1. 🔍 Test de l'état actuel..."
echo "API Response actuelle:"
curl -s http://localhost:8081/api/container/stats | jq . 2>/dev/null || curl -s http://localhost:8081/api/container/stats

echo ""
echo "2. 🔄 Redémarrage du monitoring avec corrections..."
$DOCKER_COMPOSE_CMD stop monitoring
$DOCKER_COMPOSE_CMD build --no-cache monitoring
$DOCKER_COMPOSE_CMD up -d monitoring

echo ""
echo "3. ⏱️  Attente redémarrage (15s)..."
sleep 15

echo ""
echo "4. 🧪 Test après correction..."
echo "Nouvelle API Response:"
curl -s http://localhost:8081/api/container/stats | jq . 2>/dev/null || curl -s http://localhost:8081/api/container/stats

echo ""
echo "5. 📊 Vérification des valeurs..."
response=$(curl -s http://localhost:8081/api/container/stats)
status=$(echo "$response" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
uptime=$(echo "$response" | grep -o '"uptime":"[^"]*"' | cut -d'"' -f4)  
cpu=$(echo "$response" | grep -o '"cpu_percent":"[^"]*"' | cut -d'"' -f4)
memory=$(echo "$response" | grep -o '"memory_usage":"[^"]*"' | cut -d'"' -f4)

echo ""
echo "✅ Valeurs extraites:"
echo "   Status Container: $status"
echo "   Uptime Container: $uptime"
echo "   CPU Usage: ${cpu}%"
echo "   Memory Usage: $memory"

echo ""
echo "🌐 Testez maintenant: http://192.168.1.29:8081"
echo "   → Uptime Container devrait afficher: $uptime"
echo "   → Status Container devrait afficher: $status"
echo "   → CPU Usage devrait afficher: ${cpu}%"
echo "   → Memory Usage devrait afficher: $memory"