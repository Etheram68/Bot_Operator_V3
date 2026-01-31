#!/bin/bash
# Script d'installation unique et robuste pour Bot Opérateur 112 sur QNAP
# Version optimisée avec toutes les fonctionnalités
# Usage: ./install-qnap.sh [--build] [--start] [--stop] [--restart] [--logs] [--status] [--cleanup]

set -e

# Configuration
PROJECT_NAME="bot-operateur-112"
IMAGE_NAME="bot-operateur"
CONTAINER_NAME="bot-operateur-112"
MONITORING_CONTAINER_NAME="bot-monitoring"
DOCKER_COMPOSE_CMD=""

# Couleurs pour output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
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

log_title() {
    echo -e "${PURPLE}🚀 $1${NC}"
}

log_step() {
    echo -e "${CYAN}📋 $1${NC}"
}

# Bannière d'accueil
show_banner() {
    echo -e "${PURPLE}"
    echo "╔═══════════════════════════════════════════════════════════════╗"
    echo "║                   BOT OPÉRATEUR 112                          ║"
    echo "║                  Installation QNAP                           ║"
    echo "║              Robuste & Optimisé pour NAS                     ║"
    echo "╚═══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

# Vérifier les prérequis
check_prerequisites() {
    log_step "Vérification des prérequis..."

    # Vérifier Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker n'est pas installé ou accessible"
        log_info "Installez Container Station depuis l'App Center QNAP"
        exit 1
    fi
    log_success "Docker détecté"

    # Vérifier Docker Compose (V2 ou V1)
    if docker compose version &> /dev/null; then
        DOCKER_COMPOSE_CMD="docker compose"
        log_success "Docker Compose V2 détecté"
    elif command -v docker-compose &> /dev/null; then
        DOCKER_COMPOSE_CMD="docker-compose"
        log_success "Docker Compose V1 détecté"
    else
        log_error "Docker Compose n'est pas disponible"
        exit 1
    fi

    # Vérifier les fichiers nécessaires
    if [[ ! -f "Dockerfile" ]]; then
        log_error "Dockerfile manquant dans le répertoire courant"
        exit 1
    fi

    if [[ ! -f "docker-compose.yml" ]]; then
        log_error "docker-compose.yml manquant dans le répertoire courant"
        exit 1
    fi

    if [[ ! -f ".env.example" ]]; then
        log_warning "Fichier .env.example manquant"
    fi

    log_success "Tous les prérequis sont satisfaits"
}

# Configuration du fichier .env
setup_environment() {
    log_step "Configuration de l'environnement..."

    if [[ ! -f ".env" ]]; then
        if [[ -f ".env.example" ]]; then
            cp .env.example .env
            log_success "Fichier .env créé depuis .env.example"
        else
            log_warning "Création d'un fichier .env minimal"
            cat > .env << EOF
# Configuration Bot Opérateur 112
USERNAME=your_username
PASSWORD=your_password

# Configuration basique pour QNAP
HEADLESS=true
LOG_LEVEL=INFO
MAX_CONCURRENT_MISSIONS=40

# Sécurité
PYTHONOPTIMIZE=1
PYTHONDONTWRITEBYTECODE=1
EOF
        fi

        log_warning "⚠️  IMPORTANT: Éditez le fichier .env avec vos identifiants:"
        log_info "   nano .env"
        log_info "   Modifiez USERNAME et PASSWORD"
    else
        log_success "Fichier .env existant détecté"
    fi
}

# Arrêter les conteneurs existants
stop_containers() {
    log_step "Arrêt des conteneurs existants..."

    # Arrêter avec docker-compose si disponible
    if [[ -f "docker-compose.yml" ]]; then
        $DOCKER_COMPOSE_CMD down --remove-orphans 2>/dev/null || true
    fi

    # Arrêter les conteneurs individuels s'ils existent
    for container in "$CONTAINER_NAME" "$MONITORING_CONTAINER_NAME"; do
        if docker ps -q -f name="$container" | grep -q .; then
            docker stop "$container" 2>/dev/null || true
            log_success "Conteneur $container arrêté"
        fi
    done

    # Nettoyer les conteneurs arrêtés
    docker container prune -f 2>/dev/null || true
}

# Construire l'image
build_image() {
    log_step "Construction de l'image Docker..."

    # Nettoyer les images orphelines
    docker image prune -f 2>/dev/null || true

    # Configuration QNAP pour éviter les problèmes de permissions
    export DOCKER_BUILDKIT=0
    export COMPOSE_DOCKER_CLI_BUILD=0

    # Créer les répertoires nécessaires avec bonnes permissions
    mkdir -p data/logs data/cache
    chmod 777 data data/logs data/cache 2>/dev/null || true

    # Construire l'image - essayer d'abord avec docker-compose
    if [[ -f "docker-compose.yml" ]]; then
        log_info "Tentative avec Docker Compose..."
        if ! $DOCKER_COMPOSE_CMD build --no-cache 2>/dev/null; then
            log_warning "Docker Compose échoué, utilisation de Docker direct..."
            # Fallback: construction directe avec Docker
            docker build --no-cache -t "$IMAGE_NAME:latest" .
        fi
    else
        docker build --no-cache -t "$IMAGE_NAME:latest" .
    fi

    # Vérifier que l'image a été créée
    if docker images | grep -q "$IMAGE_NAME"; then
        log_success "Image construite avec succès"
    else
        log_error "Échec de construction de l'image"
        exit 1
    fi
}

# Démarrer les services
start_services() {
    log_step "Démarrage des services..."

    if [[ -f "docker-compose.yml" ]]; then
        $DOCKER_COMPOSE_CMD up -d
        log_success "Services démarrés avec Docker Compose"
    else
        # Démarrage manuel si pas de docker-compose
        docker run -d \
            --name "$CONTAINER_NAME" \
            --restart unless-stopped \
            --env-file .env \
            -v "$(pwd)/logs:/app/logs" \
            -v "$(pwd)/data:/app/data" \
            -v "$(pwd)/cache:/app/cache" \
            "$IMAGE_NAME"
        log_success "Conteneur démarré manuellement"
    fi
}

# Vérifier le statut des services
check_status() {
    log_step "Vérification du statut des services..."

    # Attendre que les conteneurs soient prêts
    sleep 5

    local all_healthy=true

    for container in "$CONTAINER_NAME" "$MONITORING_CONTAINER_NAME"; do
        if docker ps --format "table {{.Names}}\t{{.Status}}" | grep -q "$container"; then
            local status=$(docker ps --format "{{.Status}}" --filter "name=$container")
            log_success "$container: $status"
        else
            if docker ps -a --format "table {{.Names}}\t{{.Status}}" | grep -q "$container"; then
                local status=$(docker ps -a --format "{{.Status}}" --filter "name=$container")
                log_error "$container: $status"
                all_healthy=false
            else
                log_warning "$container: Non trouvé"
            fi
        fi
    done

    if $all_healthy; then
        log_success "Tous les services sont opérationnels"

        # Afficher les URLs d'accès
        log_info "URLs d'accès:"
        log_info "  - Bot: Vérifiez les logs avec: $0 --logs"

        # Vérifier si monitoring est accessible
        if docker ps -q -f name="$MONITORING_CONTAINER_NAME" | grep -q .; then
            local qnap_ip=$(ip route get 1.1.1.1 | grep -oP 'src \K\S+' 2>/dev/null || echo "IP_DU_QNAP")
            log_info "  - Monitoring: http://$qnap_ip:8081"
        fi
    else
        log_error "Certains services ont des problèmes. Vérifiez les logs."
        return 1
    fi
}

# Afficher les logs
show_logs() {
    log_step "Affichage des logs..."

    if docker ps -q -f name="$CONTAINER_NAME" | grep -q .; then
        echo -e "${BLUE}--- Logs du Bot Opérateur ---${NC}"
        docker logs --tail=50 -f "$CONTAINER_NAME"
    else
        log_error "Le conteneur $CONTAINER_NAME n'est pas en cours d'exécution"
        return 1
    fi
}

# Nettoyage complet
cleanup_all() {
    log_step "Nettoyage complet du système..."

    # Arrêter tous les conteneurs
    stop_containers

    # Supprimer les conteneurs
    for container in "$CONTAINER_NAME" "$MONITORING_CONTAINER_NAME"; do
        if docker ps -a -q -f name="$container" | grep -q .; then
            docker rm -f "$container" 2>/dev/null || true
            log_success "Conteneur $container supprimé"
        fi
    done

    # Supprimer les images
    for image in "$IMAGE_NAME" "bot-monitoring"; do
        if docker images -q "$image" | grep -q .; then
            docker rmi -f "$image" 2>/dev/null || true
            log_success "Image $image supprimée"
        fi
    done

    # Nettoyer le système Docker
    docker system prune -f 2>/dev/null || true
    docker volume prune -f 2>/dev/null || true

    log_success "Nettoyage terminé"
}

# Installation complète
full_install() {
    log_title "Installation complète du Bot Opérateur 112"

    check_prerequisites
    setup_environment
    stop_containers
    build_image
    start_services
    check_status

    echo ""
    log_success "🎉 Installation terminée avec succès !"
    echo ""
    log_info "Commandes utiles:"
    log_info "  - Voir les logs:     $0 --logs"
    log_info "  - Redémarrer:        $0 --restart"
    log_info "  - Vérifier statut:   $0 --status"
    log_info "  - Nettoyer tout:     $0 --cleanup"
    echo ""
}

# Redémarrage rapide
restart_services() {
    log_step "Redémarrage des services..."
    stop_containers
    start_services
    check_status
    log_success "Services redémarrés"
}

# Affichage de l'aide
show_help() {
    echo -e "${CYAN}Usage: $0 [OPTION]${NC}"
    echo ""
    echo "Options:"
    echo "  --build      Construire uniquement l'image"
    echo "  --start      Démarrer uniquement les services"
    echo "  --stop       Arrêter les services"
    echo "  --restart    Redémarrer les services"
    echo "  --logs       Afficher les logs en temps réel"
    echo "  --status     Vérifier le statut des services"
    echo "  --cleanup    Nettoyage complet (ATTENTION: supprime tout)"
    echo "  --help       Afficher cette aide"
    echo ""
    echo "Sans option: Installation complète"
    echo ""
    echo "Exemples:"
    echo "  $0                    # Installation complète"
    echo "  $0 --restart         # Redémarrage rapide"
    echo "  $0 --logs            # Voir les logs"
}

# Main
main() {
    show_banner

    case "${1:-}" in
        --build)
            check_prerequisites
            build_image
            ;;
        --start)
            check_prerequisites
            start_services
            check_status
            ;;
        --stop)
            stop_containers
            ;;
        --restart)
            check_prerequisites
            restart_services
            ;;
        --logs)
            show_logs
            ;;
        --status)
            check_status
            ;;
        --cleanup)
            read -p "⚠️  Êtes-vous sûr de vouloir tout supprimer ? (y/N): " -n 1 -r
            echo ""
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                cleanup_all
            else
                log_info "Nettoyage annulé"
            fi
            ;;
        --help)
            show_help
            ;;
        "")
            full_install
            ;;
        *)
            log_error "Option inconnue: $1"
            show_help
            exit 1
            ;;
    esac
}

# Trap pour gestion d'erreur
trap 'log_error "Erreur détectée à la ligne $LINENO. Script interrompu."' ERR

# Exécution
main "$@"