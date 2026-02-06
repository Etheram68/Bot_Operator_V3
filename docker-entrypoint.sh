#!/bin/bash
# Script d'entrée Docker pour Bot Opérateur 112

set -e

echo "🚀 Démarrage Bot Opérateur 112 dans container Docker"
echo "📅 $(date)"
echo "🖥️  Architecture: $(uname -m)"
echo "🐍 Python version: $(python --version)"

# Vérifier les variables d'environnement critiques
if [ -z "$USERNAME" ] || [ -z "$PASSWORD" ]; then
    echo "❌ ERREUR: Variables USERNAME et PASSWORD requises"
    echo "💡 Exemple: docker run -e USERNAME=user -e PASSWORD=pass bot-operateur"
    exit 1
fi

# Vérifier la connectivité réseau (sans curl, avec Python)
echo "🌐 Test de connectivité réseau..."
if ! python -c "
import urllib.request, sys
try:
    urllib.request.urlopen('https://www.operateur112.fr', timeout=10)
    print('✅ Connectivité OK')
except Exception as e:
    print(f'⚠️  ATTENTION: Impossible de joindre operateur112.fr: {e}')
    sys.exit(1)
" 2>/dev/null; then
    echo "🔧 Vérifiez la configuration réseau du container"
fi

# Afficher la configuration
echo "📋 Configuration actuelle:"
echo "   - Stratégie: ${DEFAULT_STRATEGY:-smart}"
echo "   - Mode headless: ${HEADLESS:-true}"
echo "   - Missions max simultanées: ${MAX_CONCURRENT_MISSIONS:-5}"
echo "   - Seuil crédits: ${MIN_CREDITS_THRESHOLD:-1000}"
echo "   - Seuil optimisation: ${OPTIMIZATION_THRESHOLD:-3}"
echo "   - Seuil déploiement: ${DEPLOYMENT_THRESHOLD:-5}"
echo "   - Seuil personnel spécialisé: ${PERSONNEL_THRESHOLD:-1}"

# Le fichier .env sera créé par les variables d'environnement Docker
# Pas besoin de créer un fichier .env séparé avec les variables d'environnement
echo "📝 Utilisation directe des variables d'environnement Docker"

# Test rapide du bot
echo "🧪 Test de démarrage du bot..."
if ! python -c "from bot_operateur.core.bot import OperateurBot; print('✅ Import bot réussi')"; then
    echo "❌ ERREUR: Impossible d'importer le bot"
    exit 1
fi

echo "✅ Prêt ! Lancement du bot avec les arguments: $@"
echo "🔄 Pour arrêter: docker stop <container_id>"
echo "📊 Logs en temps réel: docker logs -f <container_id>"
echo ""

# Lancer la commande principale
exec "$@"