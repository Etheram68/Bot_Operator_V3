#!/bin/bash
# Script pour appliquer l'augmentation CPU et redéployer

echo "🚀 Déploiement avec augmentation CPU et auto-reload"
echo "=================================================="

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

echo "🐳 Utilisation de: $DOCKER_COMPOSE_CMD"

echo ""
echo "1. 📋 Affichage des anciennes limites..."
$DOCKER_COMPOSE_CMD config | grep -A5 -B5 "cpus\|memory" || echo "Configuration non disponible"

echo ""
echo "2. ⏹️  Arrêt propre des services..."
$DOCKER_COMPOSE_CMD stop

echo ""
echo "3. 🔨 Reconstruction avec nouvelles limites CPU..."
$DOCKER_COMPOSE_CMD build --no-cache

echo ""
echo "4. 🚀 Redémarrage avec nouvelles ressources..."
$DOCKER_COMPOSE_CMD up -d

if [ $? -ne 0 ]; then
    echo "❌ Erreur lors du redémarrage"
    $DOCKER_COMPOSE_CMD logs --tail=20
    exit 1
fi

echo ""
echo "5. ⏱️  Attente du démarrage complet (30s)..."
sleep 30

echo ""
echo "6. ✅ Vérification des services..."
$DOCKER_COMPOSE_CMD ps

echo ""
echo "7. 📊 Test des nouvelles limites CPU..."
# Vérifier si le container utilise les nouvelles limites
container_id=$(docker ps --filter "name=bot-operateur-112" --format "{{.ID}}" 2>/dev/null)
if [ -n "$container_id" ]; then
    echo "Container ID: $container_id"
    echo "Limites CPU actuelles:"
    docker inspect "$container_id" | grep -A5 -B5 "NanoCpus\|Memory" 2>/dev/null || echo "Inspection échouée"
fi

echo ""
echo "8. 🔄 Test de l'API monitoring améliorée..."
sleep 5
api_response=$(curl -s http://localhost:8081/api/container/stats 2>/dev/null)
if echo "$api_response" | grep -q '"cpu_percent"'; then
    cpu_usage=$(echo "$api_response" | grep -o '"cpu_percent":"[^"]*"' | cut -d'"' -f4)
    memory_usage=$(echo "$api_response" | grep -o '"memory_usage":"[^"]*"' | cut -d'"' -f4)
    uptime=$(echo "$api_response" | grep -o '"uptime":"[^"]*"' | cut -d'"' -f4)
    
    echo "✅ Monitoring opérationnel:"
    echo "   CPU: ${cpu_usage}% (nouvelles limites appliquées)"
    echo "   Mémoire: ${memory_usage}"
    echo "   Uptime: ${uptime}"
else
    echo "⚠️  API monitoring pas encore prête, test manuel requis"
fi

echo ""
echo "🎉 Déploiement terminé !"
echo ""
echo "📊 Améliorations appliquées:"
echo "   • CPU limit: 1.0 → 2.0 cores"
echo "   • CPU reserved: 0.5 → 1.0 cores"
echo "   • Monitoring auto-refresh: 30s → 10s"
echo "   • Auto-reload interface si modifications détectées"
echo ""
echo "🌐 Interface: http://192.168.1.29:8081"
echo "   → Rechargement automatique des stats toutes les 10s"
echo "   → Rechargement automatique de la page si modifiée"

echo ""
echo "💡 Le bot dispose maintenant de plus de ressources CPU pour de meilleures performances !"