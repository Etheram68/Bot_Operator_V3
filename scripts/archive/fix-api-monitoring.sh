#!/bin/bash
# Script pour corriger l'API de monitoring

echo "🔧 Correction de l'API de monitoring"
echo "===================================="

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

# Arrêter et supprimer l'ancien container monitoring
echo "⏹️  Arrêt de l'ancien monitoring..."
$DOCKER_COMPOSE_CMD stop monitoring 2>/dev/null
$DOCKER_COMPOSE_CMD rm -f monitoring 2>/dev/null

# Supprimer l'ancienne image pour forcer une reconstruction
echo "🗑️  Suppression de l'ancienne image..."
docker rmi bot-monitoring:latest 2>/dev/null || true

# Vérifier les fichiers nécessaires
echo "📁 Vérification des fichiers..."
if [ ! -f "monitoring/Dockerfile" ]; then
    echo "❌ monitoring/Dockerfile manquant"
    exit 1
fi

if [ ! -f "monitoring/update-api.sh" ]; then
    echo "❌ monitoring/update-api.sh manquant"
    exit 1
fi

if [ ! -f "monitoring/start-monitoring.sh" ]; then
    echo "❌ monitoring/start-monitoring.sh manquant"
    exit 1
fi

# Reconstruire l'image
echo "🔨 Reconstruction de l'image monitoring..."
$DOCKER_COMPOSE_CMD build --no-cache monitoring

if [ $? -ne 0 ]; then
    echo "❌ Erreur lors de la construction"
    exit 1
fi

# Redémarrer
echo "🚀 Redémarrage du monitoring..."
$DOCKER_COMPOSE_CMD up -d monitoring

if [ $? -ne 0 ]; then
    echo "❌ Erreur lors du démarrage"
    exit 1
fi

# Attendre le démarrage
echo "⏱️  Attente du démarrage (20 secondes)..."
sleep 20

# Vérifier le statut
if $DOCKER_COMPOSE_CMD ps | grep monitoring | grep -q "Up"; then
    echo ""
    echo "✅ Monitoring redémarré"
    
    # Test rapide
    echo ""
    echo "🧪 Tests rapides..."
    
    # Test interface
    echo "1. Test interface..."
    if curl -s -f http://localhost:8081/ > /dev/null 2>&1; then
        echo "   ✅ Interface accessible"
    else
        echo "   ⚠️  Interface non accessible"
    fi
    
    # Attendre que l'API se génère
    echo "   ⏱️  Attente génération API (10s)..."
    sleep 10
    
    # Test API stats
    echo "2. Test API stats..."
    api_response=$(curl -s http://localhost:8081/api/container/stats 2>/dev/null)
    if echo "$api_response" | grep -q '"status"'; then
        if echo "$api_response" | grep -q '"error"'; then
            echo "   ⚠️  API répond mais avec erreur: $(echo "$api_response" | head -n 1)"
        else
            echo "   ✅ API stats fonctionnelle"
            echo "   📊 Uptime: $(echo "$api_response" | grep -o '"uptime":"[^"]*"' | cut -d'"' -f4)"
        fi
    else
        echo "   ❌ API stats ne répond pas correctement"
    fi
    
    # Logs du monitoring
    echo ""
    echo "📋 Logs du monitoring (10 dernières lignes):"
    $DOCKER_COMPOSE_CMD logs monitoring --tail=10
    
    echo ""
    echo "🌐 Testez maintenant: http://192.168.1.29:8081"
    
else
    echo "❌ Erreur lors du redémarrage"
    echo "📋 Logs complets:"
    $DOCKER_COMPOSE_CMD logs monitoring
fi