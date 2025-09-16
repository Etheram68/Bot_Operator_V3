#!/bin/bash
# Script de maintenance générale

echo "🔧 Maintenance du Bot Opérateur 112"
echo "==================================="

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

# Menu des actions
echo ""
echo "📋 Actions disponibles:"
echo "   1) Status des services"
echo "   2) Redémarrer bot uniquement"
echo "   3) Redémarrer monitoring uniquement"
echo "   4) Redémarrer tous les services"
echo "   5) Voir logs du bot"
echo "   6) Voir logs du monitoring"
echo "   7) Nettoyer les images Docker"
echo "   8) Test complet du monitoring"
echo "   9) Quitter"

read -p "Choisissez une action [1-9]: " action

case $action in
    1)
        echo "📊 Status des services..."
        $DOCKER_COMPOSE_CMD ps
        ;;
    2)
        echo "🔄 Redémarrage du bot..."
        $DOCKER_COMPOSE_CMD restart bot-operateur
        ;;
    3)
        echo "🔄 Redémarrage du monitoring..."
        $DOCKER_COMPOSE_CMD restart monitoring
        ;;
    4)
        echo "🔄 Redémarrage de tous les services..."
        $DOCKER_COMPOSE_CMD restart
        ;;
    5)
        echo "📋 Logs du bot (20 dernières lignes)..."
        $DOCKER_COMPOSE_CMD logs bot-operateur --tail=20
        ;;
    6)
        echo "📋 Logs du monitoring (20 dernières lignes)..."
        $DOCKER_COMPOSE_CMD logs monitoring --tail=20
        ;;
    7)
        echo "🗑️  Nettoyage des images Docker..."
        docker image prune -f
        echo "✅ Images inutilisées supprimées"
        ;;
    8)
        echo "🧪 Test complet du monitoring..."
        if [ -f "debug/test-monitoring-api.sh" ]; then
            ./debug/test-monitoring-api.sh
        else
            echo "❌ Script de test non trouvé"
        fi
        ;;
    9)
        echo "👋 Au revoir !"
        exit 0
        ;;
    *)
        echo "❌ Option invalide"
        exit 1
        ;;
esac

echo ""
echo "✅ Action terminée !"