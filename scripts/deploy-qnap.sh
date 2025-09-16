#!/bin/bash
# Script de déploiement Bot Opérateur 112 sur QNAP
# Usage: ./deploy-qnap.sh [--build] [--start] [--stop] [--logs]

set -e

# Configuration
PROJECT_NAME="bot-operateur-112"
IMAGE_NAME="bot-operateur"
CONTAINER_NAME="bot-operateur-112"
DOCKER_COMPOSE_CMD=""  # Sera défini dans check_prerequisites

# Couleurs pour output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Fonctions utilitaires
log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Vérifier les prérequis
check_prerequisites() {
    log_info "Vérification des prérequis..."
    
    # Vérifier Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker n'est pas installé ou accessible"
        exit 1
    fi
    
    # Vérifier Docker Compose (V2 ou V1)
    # Tester d'abord Docker Compose V2 (QTS 5.1 + Container Station 3.0)
    if docker compose version &> /dev/null; then
        DOCKER_COMPOSE_CMD="docker compose"
        log_success "Docker Compose V2 détecté (QTS 5.1+)"
    # Puis Docker Compose V1 (anciennes versions)
    elif command -v docker-compose &> /dev/null; then
        DOCKER_COMPOSE_CMD="docker-compose"
        log_success "Docker Compose V1 détecté"
    else
        log_error "Docker Compose non trouvé"
        log_info "Sur QNAP QTS 5.1+ avec Container Station 3.0: utilisez 'docker compose'"
        log_info "Sur QNAP QTS <5.1: installez docker-compose"
        exit 1
    fi
    
    log_info "Utilisation de: $DOCKER_COMPOSE_CMD"
    
    # Vérifier fichier .env
    if [ ! -f ".env" ]; then
        log_warning "Fichier .env non trouvé"
        if [ -f ".env.docker" ]; then
            log_info "Copie de .env.docker vers .env"
            cp .env.docker .env
            log_warning "⚠️  IMPORTANT: Éditez le fichier .env avec vos identifiants !"
            echo ""
            echo "   USERNAME=votre_username"
            echo "   PASSWORD=votre_password"
            echo ""
            read -p "Appuyez sur Entrée après avoir configuré .env..."
        else
            log_error "Aucun fichier de configuration trouvé"
            exit 1
        fi
    fi
    
    # Vérifier identifiants dans .env
    if grep -q "your_username_here" .env || grep -q "your_password_here" .env; then
        log_error "Veuillez configurer vos identifiants dans le fichier .env"
        exit 1
    fi
    
    log_success "Prérequis vérifiés"
}

# Créer structure de données
setup_data_structure() {
    log_info "Création de la structure de données..."
    
    mkdir -p data/{logs,cache,config,bot_data}
    mkdir -p monitoring
    
    # Créer configuration monitoring nginx si nécessaire
    if [ ! -f "monitoring/nginx.conf" ]; then
        cat > monitoring/nginx.conf << 'EOF'
events {
    worker_connections 1024;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;
    
    server {
        listen 80;
        server_name localhost;
        
        location / {
            root /usr/share/nginx/html;
            index index.html;
            autoindex on;
        }
        
        location /logs/ {
            alias /usr/share/nginx/html/logs/;
            autoindex on;
            autoindex_exact_size off;
            autoindex_localtime on;
        }
    }
}
EOF
    fi
    
    # Créer page d'accueil monitoring
    if [ ! -f "data/logs/index.html" ]; then
        cat > data/logs/index.html << 'EOF'
<!DOCTYPE html>
<html>
<head>
    <title>Bot Opérateur 112 - Monitoring</title>
    <meta charset="utf-8">
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; }
        .header { background: #2196F3; color: white; padding: 20px; border-radius: 5px; }
        .status { margin: 20px 0; padding: 15px; background: #f5f5f5; border-radius: 5px; }
        .logs { margin: 20px 0; }
        a { color: #2196F3; text-decoration: none; }
        a:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🚨 Bot Opérateur 112 - Monitoring</h1>
        <p>Interface de surveillance du bot automatisé</p>
    </div>
    
    <div class="status">
        <h2>📊 Statut</h2>
        <p>Container: <strong id="status">Vérification en cours...</strong></p>
        <p>Dernière mise à jour: <span id="timestamp"></span></p>
    </div>
    
    <div class="logs">
        <h2>📝 Logs</h2>
        <p><a href="/logs/">📁 Voir tous les fichiers de logs</a></p>
    </div>
    
    <script>
        // Mettre à jour timestamp
        document.getElementById('timestamp').textContent = new Date().toLocaleString();
        
        // Auto-refresh toutes les 60 secondes
        setTimeout(() => location.reload(), 60000);
    </script>
</body>
</html>
EOF
    fi
    
    log_success "Structure de données créée"
}

# Construire l'image Docker
build_image() {
    log_info "Construction de l'image Docker..."
    
    $DOCKER_COMPOSE_CMD build --no-cache
    
    log_success "Image construite avec succès"
}

# Démarrer les services
start_services() {
    log_info "Démarrage des services..."
    
    # Arrêter si déjà en cours
    $DOCKER_COMPOSE_CMD down 2>/dev/null || true
    
    # Démarrer en arrière-plan
    $DOCKER_COMPOSE_CMD up -d
    
    # Attendre que les services soient prêts
    log_info "Attente du démarrage des services..."
    sleep 10
    
    # Vérifier statut
    if $DOCKER_COMPOSE_CMD ps | grep -q "Up"; then
        log_success "Services démarrés avec succès"
        
        # Afficher informations de connexion
        echo ""
        log_info "🔗 Informations de connexion:"
        echo "   Container: $CONTAINER_NAME"
        echo "   Monitoring: http://localhost:8080 (si activé)"
        echo "   Logs: $DOCKER_COMPOSE_CMD logs -f"
        echo ""
        
    else
        log_error "Erreur lors du démarrage"
        $DOCKER_COMPOSE_CMD logs
        exit 1
    fi
}

# Arrêter les services
stop_services() {
    log_info "Arrêt des services..."
    
    $DOCKER_COMPOSE_CMD down
    
    log_success "Services arrêtés"
}

# Afficher les logs
show_logs() {
    log_info "Affichage des logs (Ctrl+C pour quitter)..."
    $DOCKER_COMPOSE_CMD logs -f
}

# Afficher l'aide
show_help() {
    echo "🚀 Script de déploiement Bot Opérateur 112 sur QNAP"
    echo ""
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  --build     Construire l'image Docker"
    echo "  --start     Démarrer les services"
    echo "  --stop      Arrêter les services"
    echo "  --restart   Redémarrer les services"
    echo "  --logs      Afficher les logs en temps réel"
    echo "  --status    Afficher le statut des services"
    echo "  --help      Afficher cette aide"
    echo ""
    echo "Exemples:"
    echo "  $0 --build --start    # Construire et démarrer"
    echo "  $0 --restart          # Redémarrer les services"
    echo "  $0 --logs             # Voir les logs"
    echo ""
}

# Afficher le statut
show_status() {
    log_info "Statut des services:"
    echo ""
    $DOCKER_COMPOSE_CMD ps
    echo ""
    
    if $DOCKER_COMPOSE_CMD ps | grep -q "Up"; then
        log_success "Services en cours d'exécution"
    else
        log_warning "Services arrêtés"
    fi
}

# Main
main() {
    echo "🚀 Bot Opérateur 112 - Déploiement QNAP"
    echo "========================================"
    echo ""
    
    # Si aucun argument, afficher aide
    if [ $# -eq 0 ]; then
        show_help
        exit 0
    fi
    
    # Vérifier prérequis pour toutes les actions sauf help
    if [[ "$1" != "--help" ]]; then
        check_prerequisites
        setup_data_structure
    fi
    
    # Traiter arguments
    case "$1" in
        --build)
            build_image
            ;;
        --start)
            start_services
            ;;
        --stop)
            stop_services
            ;;
        --restart)
            stop_services
            start_services
            ;;
        --logs)
            show_logs
            ;;
        --status)
            show_status
            ;;
        --help)
            show_help
            ;;
        *)
            log_error "Option non reconnue: $1"
            show_help
            exit 1
            ;;
    esac
    
    # Si build ET start demandés
    if [[ "$1" == "--build" && "$2" == "--start" ]]; then
        start_services
    fi
}

# Exécuter
main "$@"