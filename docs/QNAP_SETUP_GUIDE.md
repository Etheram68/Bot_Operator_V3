# Guide de Déploiement QNAP - Bot Opérateur 112

Ce guide vous explique comment déployer le Bot Opérateur 112 sur votre NAS QNAP en utilisant Container Station.

## 🏗️ Prérequis

### QNAP Requirements
- **QNAP NAS** avec QTS 4.4+ ou QuTS hero
- **Container Station** installé (via App Center)
- **Minimum 2GB RAM** libre pour le container
- **500MB espace disque** pour l'image + logs
- **Connexion Internet** stable

### Comptes Requis
- Compte **Opérateur 112** actif (https://www.operateur112.fr)
- Accès **administrateur** au QNAP

## 📦 Installation Container Station

### Étape 1 : Installer Container Station
1. Ouvrir **App Center** sur QTS
2. Rechercher **"Container Station"**
3. Cliquer **"Installer"**
4. Attendre la fin de l'installation
5. Lancer **Container Station**

### Étape 2 : Configurer Container Station
1. **Premier lancement** : suivre l'assistant de configuration
2. **Réseau** : laisser la configuration par défaut
3. **Storage** : sélectionner le volume principal

## 🚀 Déploiement du Bot

### Méthode 1 : Via Docker Compose (Recommandée)

#### 1. Préparer les fichiers

**Copier les fichiers sur le QNAP :**
```bash
# Via SSH ou File Station, créer le dossier :
/share/Container/bot-operateur/

# Y copier tous les fichiers du projet Bot_OperateurV3
```

**Structure attendue :**
```
/share/Container/bot-operateur/
├── Dockerfile
├── docker-compose.yml
├── .env.docker
├── docker-entrypoint.sh
├── requirements.txt
├── main.py
├── bot_operateur/
├── data/
├── scripts/
└── docs/
```

#### 2. Configurer les identifiants

```bash
# Se connecter en SSH au QNAP
ssh admin@IP_QNAP

# Naviguer vers le dossier
cd /share/Container/bot-operateur/

# Copier et éditer la configuration
cp .env.docker .env
nano .env
```

**Éditer le fichier .env :**
```bash
# OBLIGATOIRE - Vos identifiants Opérateur 112
USERNAME=votre_username
PASSWORD=votre_password

# Le reste peut rester par défaut
DEFAULT_STRATEGY=smart
HEADLESS=true
MAX_CONCURRENT_MISSIONS=3
# ...
```

#### 3. Déployer avec le script

```bash
# Rendre le script exécutable
chmod +x scripts/deploy-qnap.sh

# Construire et démarrer
./scripts/deploy-qnap.sh --build --start

# Voir les logs
./scripts/deploy-qnap.sh --logs
```

### Méthode 2 : Via Container Station UI

#### 1. Créer l'image
1. **Container Station** → **Images** → **Build**
2. **Repository** : `bot-operateur`
3. **Tag** : `latest`
4. **Upload Dockerfile** et fichiers source
5. Cliquer **"Build"**

#### 2. Créer le container
1. **Containers** → **Create**
2. **Image** : `bot-operateur:latest`
3. **Container name** : `bot-operateur-112`
4. **CPU/Memory** : 1 CPU, 2GB RAM
5. **Network** : Bridge
6. **Restart policy** : Unless stopped

#### 3. Configuration des volumes
**Shared Folders** → **Advanced** :
```
Host Path              → Container Path → Mode
/share/Container/bot-operateur/data/logs → /app/logs → RW
/share/Container/bot-operateur/data/cache → /app/cache → RW
/share/Container/bot-operateur/data/config → /app/config → RO
```

#### 4. Variables d'environnement
**Environment** :
```
USERNAME=votre_username
PASSWORD=votre_password
DEFAULT_STRATEGY=smart
HEADLESS=true
LOG_LEVEL=INFO
MAX_CONCURRENT_MISSIONS=3
OPTIMIZATION_THRESHOLD=3
DEPLOYMENT_THRESHOLD=5
PERSONNEL_THRESHOLD=1
TZ=Europe/Paris
```

#### 5. Démarrer le container
1. Cliquer **"Create"**
2. Démarrer le container
3. Vérifier les logs dans **Container Station** → **Containers**

## 📊 Monitoring et Surveillance

### Dashboard Container Station
- **État du container** : Container Station → Containers
- **Utilisation ressources** : Onglet "Resource Monitor"
- **Logs en temps réel** : Cliquer sur le container → "Terminal" → "Log"

### Interface Web de Monitoring (Optionnelle)
Si le service monitoring est activé dans docker-compose :
- **URL** : `http://IP_QNAP:8080`
- **Logs** : Interface web pour voir les logs
- **Statut** : Information sur l'état du bot

### Commandes Utiles

**Pour QTS 5.1+ avec Container Station 3.0 (Compose V2) :**
```bash
# Voir le statut
docker compose ps

# Logs en temps réel
docker compose logs -f bot-operateur

# Redémarrer le bot
docker compose restart bot-operateur

# Arrêter complètement
docker compose down

# Mettre à jour (après modification du code)
docker compose build --no-cache
docker compose up -d
```

**Pour QTS <5.1 (Compose V1) :**
```bash
# Voir le statut
docker-compose ps

# Logs en temps réel
docker-compose logs -f bot-operateur

# Redémarrer le bot
docker-compose restart bot-operateur

# Arrêter complètement
docker-compose down

# Mettre à jour (après modification du code)
docker-compose build --no-cache
docker-compose up -d
```

## ⚙️ Configuration Avancée

### Optimisation Performances QNAP

**Pour NAS avec peu de RAM (<4GB) :**
```env
MAX_CONCURRENT_MISSIONS=1
PAGE_LOAD_TIMEOUT=45
BROWSER_SLOW_MO=200
DEPLOYMENT_THRESHOLD=8
```

**Pour NAS puissants (>8GB RAM) :**
```env
MAX_CONCURRENT_MISSIONS=5
PAGE_LOAD_TIMEOUT=20
BROWSER_SLOW_MO=50
DEPLOYMENT_THRESHOLD=3
```

### Configuration Réseau

**Port forwarding (si accès externe souhaité) :**
1. **Panneau de contrôle** → **Applications** → **Station de containers**
2. **Préférences** → **Docker**
3. Configurer port mapping : `8080:8080`

**Restrictions réseau :**
```yaml
# Dans docker-compose.yml
networks:
  default:
    driver: bridge
    ipam:
      config:
        - subnet: 172.20.0.0/24
```

### Sauvegarde et Restauration

**Sauvegarde automatique :**
```bash
# Script de sauvegarde (à placer dans cron)
#!/bin/bash
DATE=$(date +"%Y%m%d_%H%M%S")
cd /share/Container/bot-operateur
tar -czf /share/Backup/bot-operateur_${DATE}.tar.gz \
    data/ .env docker-compose.yml
```

**Restauration :**
```bash
# Arrêter le bot
docker-compose down

# Restaurer les données
tar -xzf /share/Backup/bot-operateur_YYYYMMDD_HHMMSS.tar.gz

# Redémarrer
docker-compose up -d
```

## 🔧 Dépannage

### Problèmes Courants

**Container ne démarre pas :**
```bash
# Vérifier les logs
docker-compose logs bot-operateur

# Problème fréquent : identifiants incorrects
# → Vérifier USERNAME/PASSWORD dans .env
```

**Erreur de connexion réseau :**
```bash
# Tester la connectivité depuis le container
docker-compose exec bot-operateur ping www.operateur112.fr

# Si échec : vérifier configuration réseau QNAP
```

**Manque de ressources :**
```bash
# Réduire la charge dans .env :
MAX_CONCURRENT_MISSIONS=1
DEPLOYMENT_THRESHOLD=8
```

**Logs non persistants :**
```bash
# Vérifier les permissions
chown -R 1000:1000 /share/Container/bot-operateur/data/
```

### Logs et Diagnostic

**Localisation des logs :**
- **Container logs** : Container Station → Containers → bot-operateur-112
- **App logs** : `/share/Container/bot-operateur/data/logs/`
- **System logs** : `/var/log/containers/`

**Debug avancé :**
```bash
# Mode debug
docker-compose exec bot-operateur python main.py --list --debug

# Shell interactif
docker-compose exec bot-operateur /bin/bash
```

## 📱 Notifications

### Intégration QNAP Notification Center

**Configuration dans QTS :**
1. **Panneau de contrôle** → **Notification Center**
2. **Applications service** → **Container Station**
3. Activer notifications pour événements containers

**Script de notification personnalisé :**
```bash
#!/bin/bash
# /share/Container/scripts/notify.sh
CONTAINER_STATUS=$(docker inspect --format='{{.State.Status}}' bot-operateur-112)
if [ "$CONTAINER_STATUS" != "running" ]; then
    # Envoyer notification (email, Telegram, etc.)
    echo "Bot Opérateur arrêté !" | mail -s "QNAP Alert" admin@domain.com
fi
```

## 🔄 Mise à Jour

### Mise à jour du Code

```bash
# 1. Sauvegarder la configuration
cp .env .env.backup

# 2. Télécharger la nouvelle version
# (remplacer les fichiers source)

# 3. Reconstruire l'image
docker-compose build --no-cache

# 4. Redémarrer
docker-compose down
docker-compose up -d

# 5. Vérifier
docker-compose logs -f
```

### Mise à jour Container Station

1. **App Center** → **Container Station** → **Mise à jour**
2. Redémarrer après mise à jour
3. Vérifier que les containers redémarrent automatiquement

## ✅ Checklist Finale

- [ ] Container Station installé et configuré
- [ ] Fichiers copiés dans `/share/Container/bot-operateur/`
- [ ] Fichier `.env` configuré avec identifiants
- [ ] Image Docker construite avec succès
- [ ] Container démarré et fonctionnel
- [ ] Logs accessibles et sans erreur
- [ ] Volumes persistants configurés
- [ ] Monitoring opérationnel
- [ ] Sauvegarde planifiée (optionnel)

## 📞 Support

**En cas de problème :**
1. Vérifier cette documentation
2. Consulter les logs détaillés
3. Tester manuellement depuis SSH
4. Vérifier configuration réseau QNAP

**Ressources utiles :**
- Documentation QNAP Container Station
- Docker Compose référence
- Logs du bot dans `/share/Container/bot-operateur/data/logs/`