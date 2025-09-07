# Guide de Déploiement - Bot Opérateur 112

## 🚀 **Déploiement de Production**

### **Architecture de Production Recommandée**

```
┌─────────────────────────────────────────────────────────────────┐
│                        PRODUCTION SETUP                         │
├─────────────────┬─────────────────┬─────────────────┬───────────┤
│   APPLICATION   │   MONITORING    │    STORAGE      │  NETWORK  │
│                 │                 │                 │           │
│ ┌─────────────┐ │ ┌─────────────┐ │ ┌─────────────┐ │ ┌───────┐ │
│ │Bot Opérateur│ │ │   Logs      │ │ │Config Files │ │ │Firewall│ │
│ │  (Primary)  │ │ │  (Loguru)   │ │ │   (.env)    │ │ │Rules   │ │
│ └─────────────┘ │ └─────────────┘ │ └─────────────┘ │ └───────┘ │
│                 │                 │                 │           │
│ ┌─────────────┐ │ ┌─────────────┐ │ ┌─────────────┐ │ ┌───────┐ │
│ │ Chromium    │ │ │Performance  │ │ │ Data Files  │ │ │ VPN   │ │
│ │ Headless    │ │ │  Metrics    │ │ │(JSON Config)│ │ │Optional│ │
│ └─────────────┘ │ └─────────────┘ │ └─────────────┘ │ └───────┘ │
│                 │                 │                 │           │
│ ┌─────────────┐ │ ┌─────────────┐ │ ┌─────────────┐ │ ┌───────┐ │
│ │ Backup Bot  │ │ │ Alerts &    │ │ │Screenshots  │ │ │ Proxy │ │
│ │ (Optional)  │ │ │Notifications│ │ │   (Debug)   │ │ │Optional│ │
│ └─────────────┘ │ └─────────────┘ │ └─────────────┘ │ └───────┘ │
└─────────────────┴─────────────────┴─────────────────┴───────────┘
```

### **Prérequis Système**

#### **Configuration Minimale**
```bash
# OS Support  
Ubuntu 20.04+ / CentOS 8+ / Windows 10+ / macOS 10.15+

# Hardware
RAM: 2GB minimum, 4GB recommandé
CPU: 2 cores minimum, 4 cores recommandé  
Stockage: 5GB disponible (logs + browser cache)
Réseau: Connexion stable >10 Mbps

# Software
Python 3.8+ (testé jusqu'à Python 3.11)
pip 21.0+
Git (pour clonage repository)
```

#### **Configuration Optimale**
```bash
# Hardware haute performance
RAM: 8GB+ 
CPU: 6+ cores (Intel i5/AMD Ryzen 5+)
SSD: 20GB+ disponible
Réseau: Fibre optique >50 Mbps

# OS optimisé
Ubuntu 22.04 LTS (recommandé)
Kernel: 5.15+ pour meilleures performances Playwright
```

### **Installation Production**

#### **Étape 1: Préparation Système**
```bash
# Ubuntu/Debian
sudo apt update && sudo apt upgrade -y
sudo apt install python3 python3-pip python3-venv git curl htop -y

# CentOS/RHEL  
sudo yum update -y
sudo yum install python3 python3-pip git curl htop -y

# Création utilisateur dédié
sudo useradd -m -s /bin/bash botoperateur
sudo usermod -aG sudo botoperateur  # Si privilèges admin nécessaires
sudo su - botoperateur
```

#### **Étape 2: Installation Application**
```bash
# Clone du repository
cd /home/botoperateur
git clone https://github.com/votre-repo/Bot_OperateurV3.git
cd Bot_OperateurV3

# Environment virtuel Python
python3 -m venv venv
source venv/bin/activate

# Installation dépendances
pip install --upgrade pip
pip install -r requirements.txt

# Installation navigateur
playwright install chromium
playwright install-deps  # Dépendances système pour Chromium
```

#### **Étape 3: Configuration Production**
```bash
# Configuration optimisée production
cp .env.example .env.prod

cat > .env.prod << 'EOF'
# === CONFIGURATION PRODUCTION ===
USERNAME=production_username
PASSWORD=production_password_securise

# Stratégie optimisée
DEFAULT_STRATEGY=smart
VEHICLE_THRESHOLD=3
MIN_CREDITS_THRESHOLD=1000
MAX_CONCURRENT_MISSIONS=3

# Performance haute performance
HEADLESS=true
LOG_LEVEL=INFO
PAGE_LOAD_TIMEOUT=10
ELEMENT_WAIT_TIMEOUT=5
FAST_TIMEOUT=2
BROWSER_SLOW_MO=0
FAST_NAVIGATION=true
USE_CACHE_NAVIGATION=true

# Sécurité
FAIL_SAFE_MODE=true
MAX_RETRY_ATTEMPTS=3
RATE_LIMITING=true
ENABLE_SCREENSHOT=false

# Logging production
LOG_FILE=/home/botoperateur/logs/bot.log
LOG_ROTATION=50MB
LOG_RETENTION=30d
ENABLE_PERFORMANCE_LOGS=true
EOF

# Création dossiers
mkdir -p /home/botoperateur/logs
mkdir -p /home/botoperateur/config/backup
mkdir -p /home/botoperateur/screenshots
```

#### **Étape 4: Tests de Validation**
```bash
# Test connexion basique
python main.py --test-connection --config .env.prod

# Test performance
python main.py --list --config .env.prod --debug

# Test déploiement simple  
python main.py --auto --max-missions 2 --config .env.prod

# Validation complète
python test_architecture.py --config .env.prod
```

---

## 🔄 **Automatisation et Services**

### **Service Systemd** *(Linux)*

#### **Création du Service**
```bash
# Fichier service
sudo tee /etc/systemd/system/bot-operateur.service << 'EOF'
[Unit]
Description=Bot Opérateur 112 - Emergency Vehicle Deployment Bot
After=network.target
StartLimitIntervalSec=0

[Service]
Type=simple
Restart=always
RestartSec=5
User=botoperateur
WorkingDirectory=/home/botoperateur/Bot_OperateurV3
ExecStartPre=/bin/sleep 10
ExecStart=/home/botoperateur/Bot_OperateurV3/venv/bin/python main.py --continuous --config .env.prod
ExecReload=/bin/kill -HUP $MAINPID
KillMode=mixed
KillSignal=SIGTERM
TimeoutStopSec=30

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=bot-operateur

# Sécurité  
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/home/botoperateur/Bot_OperateurV3 /home/botoperateur/logs

# Resource limits
LimitNOFILE=65536
LimitNPROC=4096

[Install]
WantedBy=multi-user.target
EOF

# Activation
sudo systemctl daemon-reload
sudo systemctl enable bot-operateur
sudo systemctl start bot-operateur

# Vérification
sudo systemctl status bot-operateur
sudo journalctl -u bot-operateur -f
```

#### **Service de Monitoring**
```bash
# Service monitoring complémentaire
sudo tee /etc/systemd/system/bot-operateur-monitor.service << 'EOF'
[Unit]
Description=Bot Opérateur Monitor - Health Check & Alerts
After=bot-operateur.service
Requires=bot-operateur.service

[Service]
Type=simple
Restart=always
RestartSec=60
User=botoperateur
WorkingDirectory=/home/botoperateur/Bot_OperateurV3
ExecStart=/home/botoperateur/Bot_OperateurV3/venv/bin/python -m bot_operateur.utils.monitor --config .env.prod

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable bot-operateur-monitor
sudo systemctl start bot-operateur-monitor
```

### **Script de Démarrage Windows**

#### **PowerShell Service**
```powershell
# bot-operateur-service.ps1
$ServiceName = "BotOperateur112"
$BinaryPath = "C:\BotOperateur112\venv\Scripts\python.exe"
$Arguments = "C:\BotOperateur112\main.py --continuous --config .env.prod"
$WorkingDirectory = "C:\BotOperateur112"

# Création service Windows
New-Service -Name $ServiceName `
            -BinaryPathName "$BinaryPath $Arguments" `
            -DisplayName "Bot Opérateur 112" `
            -Description "Emergency Vehicle Deployment Automation" `
            -StartupType Automatic

# Configuration recovery
sc.exe failure $ServiceName reset= 86400 actions= restart/5000/restart/10000/restart/30000
```

#### **Batch Script Simple**  
```batch
@echo off
REM start-bot-operateur.bat
cd /d "C:\BotOperateur112"
call venv\Scripts\activate.bat

:RESTART
echo Starting Bot Operateur 112...
python main.py --continuous --config .env.prod

if %ERRORLEVEL% NEQ 0 (
    echo Bot crashed with error level %ERRORLEVEL%
    echo Restarting in 10 seconds...
    timeout /t 10 /nobreak
    goto RESTART
)

echo Bot terminated normally.
pause
```

### **Docker Deployment**

#### **Dockerfile Production**
```dockerfile
FROM python:3.11-slim

# Installer dépendances système
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Création utilisateur non-root
RUN useradd -m -u 1000 botoperateur
WORKDIR /app

# Copie et installation des dépendances
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Installation Playwright
RUN playwright install chromium
RUN playwright install-deps chromium

# Copie code application
COPY --chown=botoperateur:botoperateur . .

# Configuration
RUN mkdir -p /app/logs /app/screenshots
RUN chown -R botoperateur:botoperateur /app

USER botoperateur

# Health check
HEALTHCHECK --interval=5m --timeout=30s --start-period=1m --retries=3 \
    CMD python main.py --test-connection --timeout 30 || exit 1

# Point d'entrée
ENTRYPOINT ["python", "main.py"]
CMD ["--continuous", "--config", ".env.prod"]
```

#### **Docker Compose Production**
```yaml
# docker-compose.prod.yml
version: '3.8'

services:
  bot-operateur:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: bot-operateur-prod
    restart: unless-stopped
    
    environment:
      - TZ=Europe/Paris
    
    env_file:
      - .env.prod
    
    volumes:
      - ./logs:/app/logs
      - ./config:/app/config
      - ./screenshots:/app/screenshots
      
    networks:
      - bot-network
      
    security_opt:
      - no-new-privileges:true
    
    mem_limit: 2g
    cpus: 2
    
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
    
    healthcheck:
      test: ["CMD", "python", "main.py", "--test-connection", "--timeout", "30"]
      interval: 5m
      timeout: 30s
      retries: 3
      start_period: 1m

  # Service monitoring (optionnel)
  bot-monitor:
    image: prom/node-exporter:latest
    container_name: bot-monitor
    restart: unless-stopped
    ports:
      - "9100:9100"
    networks:
      - bot-network

networks:
  bot-network:
    driver: bridge
```

#### **Déploiement Docker**
```bash
# Construction et lancement
docker-compose -f docker-compose.prod.yml build
docker-compose -f docker-compose.prod.yml up -d

# Monitoring
docker-compose -f docker-compose.prod.yml logs -f bot-operateur

# Redémarrage
docker-compose -f docker-compose.prod.yml restart bot-operateur

# Mise à jour
git pull
docker-compose -f docker-compose.prod.yml build --no-cache
docker-compose -f docker-compose.prod.yml up -d
```

---

## 📊 **Monitoring et Alertes**

### **Monitoring Système**

#### **Script de Monitoring**
```bash
#!/bin/bash
# monitor-bot-operateur.sh

LOG_FILE="/home/botoperateur/logs/bot.log"
ALERT_EMAIL="admin@yourcompany.com"
CHECK_INTERVAL=300  # 5 minutes

# Configuration alertes
ERROR_THRESHOLD=5          # 5 erreurs en 10 minutes = alerte
PERFORMANCE_THRESHOLD=10   # >10s par mission = alerte lenteur
SUCCESS_RATE_THRESHOLD=80  # <80% succès = alerte

monitor_performance() {
    # Dernière heure de logs
    local last_hour=$(date -d '1 hour ago' '+%Y-%m-%d %H:%M:%S')
    
    # Compter succès/échecs
    local success_count=$(grep -c "déployée avec succès" "$LOG_FILE" | tail -n 100)
    local total_count=$(grep -c "Mission.*déployée\|Échec du déploiement" "$LOG_FILE" | tail -n 100)
    local success_rate=$((success_count * 100 / total_count))
    
    # Temps moyen de déploiement
    local avg_time=$(grep -oE "Mission.*déployée.*\\([0-9.]+s\\)" "$LOG_FILE" | tail -n 20 | \
                     grep -oE "[0-9.]+s" | sed 's/s//' | \
                     awk '{sum+=$1; n++} END {print sum/n}')
    
    # Alertes
    if (( $(echo "$avg_time > $PERFORMANCE_THRESHOLD" | bc -l) )); then
        send_alert "PERFORMANCE" "Temps moyen: ${avg_time}s > ${PERFORMANCE_THRESHOLD}s"
    fi
    
    if (( success_rate < SUCCESS_RATE_THRESHOLD )); then
        send_alert "SUCCESS_RATE" "Taux de succès: ${success_rate}% < ${SUCCESS_RATE_THRESHOLD}%"
    fi
    
    echo "$(date): Performance OK - Success: ${success_rate}%, Avg time: ${avg_time}s"
}

monitor_errors() {
    local error_count=$(grep -c "ERROR\|CRITICAL" "$LOG_FILE" | tail -n 50)
    
    if (( error_count > ERROR_THRESHOLD )); then
        local last_errors=$(grep "ERROR\|CRITICAL" "$LOG_FILE" | tail -n 5)
        send_alert "ERRORS" "Trop d'erreurs: $error_count\n$last_errors"
    fi
}

send_alert() {
    local alert_type=$1
    local message=$2
    
    # Email
    echo -e "ALERTE Bot Opérateur 112 - $alert_type\n\n$message\n\nTimestamp: $(date)" | \
        mail -s "🚨 Bot Opérateur Alert: $alert_type" "$ALERT_EMAIL"
    
    # Slack (optionnel)
    # curl -X POST -H 'Content-type: application/json' \
    #      --data "{\"text\":\"🚨 Bot Alert: $alert_type\n$message\"}" \
    #      YOUR_SLACK_WEBHOOK_URL
    
    # Log local
    echo "$(date): ALERT sent - $alert_type: $message" >> "/home/botoperateur/logs/alerts.log"
}

check_bot_running() {
    if ! pgrep -f "python.*main.py" > /dev/null; then
        send_alert "SERVICE_DOWN" "Bot Opérateur service is not running!"
        
        # Auto-restart (optionnel)
        echo "$(date): Attempting auto-restart..." >> "/home/botoperateur/logs/alerts.log"
        sudo systemctl restart bot-operateur
    fi
}

# Boucle principale
while true; do
    check_bot_running
    monitor_performance
    monitor_errors
    
    sleep $CHECK_INTERVAL
done
```

#### **Configuration Logrotate**
```bash
# /etc/logrotate.d/bot-operateur
/home/botoperateur/logs/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    sharedscripts
    postrotate
        systemctl reload bot-operateur 2>/dev/null || true
    endscript
}

# Rotation immédiate (test)
sudo logrotate -d /etc/logrotate.d/bot-operateur
sudo logrotate -f /etc/logrotate.d/bot-operateur
```

### **Dashboard de Monitoring**

#### **Script Métriques Simple**
```python
#!/usr/bin/env python3
# dashboard.py - Simple dashboard for Bot Operateur metrics

import json
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

class BotMetricsDashboard:
    def __init__(self, log_file="logs/bot.log"):
        self.log_file = Path(log_file)
        self.db_file = "metrics.db"
        self._init_db()
    
    def _init_db(self):
        conn = sqlite3.connect(self.db_file)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS metrics (
                timestamp TEXT,
                mission_id TEXT,
                duration REAL,
                success INTEGER,
                vehicle_count INTEGER,
                credits INTEGER
            )
        ''')
        conn.commit()
        conn.close()
    
    def parse_recent_logs(self, hours=24):
        """Parse logs des dernières heures"""
        if not self.log_file.exists():
            return []
        
        cutoff = datetime.now() - timedelta(hours=hours)
        metrics = []
        
        with open(self.log_file, 'r') as f:
            for line in f:
                # Parse timestamp
                timestamp_match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                if not timestamp_match:
                    continue
                
                timestamp = datetime.strptime(timestamp_match.group(1), '%Y-%m-%d %H:%M:%S')
                if timestamp < cutoff:
                    continue
                
                # Parse mission success
                success_match = re.search(r'Mission (\d+).*déployée avec succès.*\(([0-9.]+)s\)', line)
                if success_match:
                    metrics.append({
                        'timestamp': timestamp.isoformat(),
                        'mission_id': success_match.group(1),
                        'duration': float(success_match.group(2)),
                        'success': 1,
                        'credits': self._extract_credits(line)
                    })
        
        return metrics
    
    def generate_report(self, hours=24):
        """Génère un rapport de performance"""
        metrics = self.parse_recent_logs(hours)
        
        if not metrics:
            return "Aucune donnée disponible"
        
        total_missions = len(metrics)
        successful_missions = sum(1 for m in metrics if m['success'])
        avg_duration = sum(m['duration'] for m in metrics) / total_missions
        total_credits = sum(m.get('credits', 0) for m in metrics)
        success_rate = (successful_missions / total_missions) * 100
        
        report = f"""
🤖 Bot Opérateur 112 - Rapport {hours}h

📊 Performance:
   • Missions totales: {total_missions}
   • Missions réussies: {successful_missions}
   • Taux de succès: {success_rate:.1f}%
   • Temps moyen: {avg_duration:.2f}s
   • Crédits générés: {total_credits:,}

⚡ Vitesse:
   • Missions/heure: {total_missions / hours * 60:.0f}
   • Plus rapide: {min(m['duration'] for m in metrics):.2f}s
   • Plus lente: {max(m['duration'] for m in metrics):.2f}s

💰 Rentabilité:
   • Crédits/heure: {total_credits / hours:.0f}
   • Crédits/mission: {total_credits / total_missions:.0f}
        """
        
        return report
    
    def _extract_credits(self, line):
        """Extrait les crédits d'une ligne de log"""
        match = re.search(r'(\d+)\s+crédits', line)
        return int(match.group(1)) if match else 0

if __name__ == "__main__":
    dashboard = BotMetricsDashboard()
    print(dashboard.generate_report(24))
```

---

## 🛡️ **Sécurité Production**

### **Configuration Sécurisée**

#### **Variables d'Environnement Sécurisées**
```bash
# Utilisation d'un gestionnaire de secrets (optionnel)
# .env.prod.secure
USERNAME_FILE=/run/secrets/bot_username
PASSWORD_FILE=/run/secrets/bot_password

# Ou chiffrement simple
USERNAME=$(echo "encrypted_username" | base64 -d)
PASSWORD=$(echo "encrypted_password" | base64 -d)

# Restrictions IP (si nécessaire)
ALLOWED_IPS="192.168.1.0/24,10.0.0.0/8"

# Audit et logging
ENABLE_AUDIT_LOG=true
AUDIT_LOG_FILE=/home/botoperateur/logs/audit.log
ENABLE_SECURITY_HEADERS=true
```

#### **Firewall Configuration** *(UFW/iptables)*
```bash
# UFW (Ubuntu)
sudo ufw enable
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Autoriser SSH (adapté selon votre port)
sudo ufw allow 22/tcp

# Autoriser HTTP/HTTPS pour le jeu
sudo ufw allow out 80/tcp
sudo ufw allow out 443/tcp

# Bloquer ports inutiles
sudo ufw deny 3000:9000/tcp

# Si dashboard monitoring
sudo ufw allow from 192.168.1.0/24 to any port 8080

# Vérification
sudo ufw status verbose
```

#### **Permissions Système**
```bash
# Permissions strictes
chmod 700 /home/botoperateur/Bot_OperateurV3
chmod 600 /home/botoperateur/Bot_OperateurV3/.env*
chmod 755 /home/botoperateur/logs
chmod 644 /home/botoperateur/logs/*.log

# SELinux (CentOS/RHEL)
sudo setsebool -P httpd_can_network_connect 1
sudo semanage port -a -t http_port_t -p tcp 8080

# AppArmor (Ubuntu)
sudo aa-status
# Profil custom si nécessaire
```

### **Backup et Recovery**

#### **Script de Backup**
```bash
#!/bin/bash
# backup-bot-operateur.sh

BACKUP_DIR="/backup/bot-operateur"
DATE=$(date +%Y%m%d-%H%M%S)
BOT_DIR="/home/botoperateur/Bot_OperateurV3"

create_backup() {
    echo "Creating backup: $DATE"
    
    mkdir -p "$BACKUP_DIR/$DATE"
    
    # Configuration
    cp "$BOT_DIR/.env.prod" "$BACKUP_DIR/$DATE/"
    cp -r "$BOT_DIR/bot_operateur/data/" "$BACKUP_DIR/$DATE/"
    
    # Logs récents (7 derniers jours)
    find /home/botoperateur/logs -name "*.log" -mtime -7 -exec cp {} "$BACKUP_DIR/$DATE/" \;
    
    # Compression
    cd "$BACKUP_DIR"
    tar -czf "bot-operateur-backup-$DATE.tar.gz" "$DATE/"
    rm -rf "$DATE/"
    
    # Nettoyage anciens backups (30 jours)
    find "$BACKUP_DIR" -name "*.tar.gz" -mtime +30 -delete
    
    echo "Backup completed: bot-operateur-backup-$DATE.tar.gz"
}

restore_backup() {
    local backup_file=$1
    
    if [[ -z "$backup_file" ]]; then
        echo "Usage: $0 restore <backup_file>"
        exit 1
    fi
    
    echo "Restoring from: $backup_file"
    
    # Arrêter le service
    sudo systemctl stop bot-operateur
    
    # Backup current
    create_backup
    
    # Restaurer
    cd "$BACKUP_DIR"
    tar -xzf "$backup_file"
    
    # Copier fichiers
    cp -r */bot_operateur/data/* "$BOT_DIR/bot_operateur/data/"
    cp -r */.env.prod "$BOT_DIR/"
    
    # Redémarrer service
    sudo systemctl start bot-operateur
    
    echo "Restore completed"
}

case "$1" in
    backup|"")
        create_backup
        ;;
    restore)
        restore_backup "$2"
        ;;
    *)
        echo "Usage: $0 {backup|restore <file>}"
        exit 1
        ;;
esac
```

#### **Backup Automatisé** *(Cron)*
```bash
# Crontab pour utilisateur botoperateur
crontab -e

# Backup quotidien à 2h du matin
0 2 * * * /home/botoperateur/scripts/backup-bot-operateur.sh backup

# Backup configuration toutes les heures (juste config)
0 * * * * cp /home/botoperateur/Bot_OperateurV3/.env.prod /home/botoperateur/backup/config-$(date +\%H).env

# Nettoyage logs hebdomadaire
0 3 * * 0 find /home/botoperateur/logs -name "*.log.gz" -mtime +14 -delete
```

---

## 🚀 **Mise à Jour et Maintenance**

### **Procédure de Mise à Jour**

#### **Update Script Automatisé**
```bash
#!/bin/bash
# update-bot-operateur.sh

BOT_DIR="/home/botoperateur/Bot_OperateurV3"
BACKUP_DIR="/home/botoperateur/backup"

update_bot() {
    echo "🔄 Début mise à jour Bot Opérateur 112..."
    
    # 1. Backup avant mise à jour
    echo "📦 Création backup pré-mise-à-jour..."
    ./backup-bot-operateur.sh backup
    
    # 2. Arrêt service
    echo "⏹️ Arrêt du service..."
    sudo systemctl stop bot-operateur
    
    # 3. Mise à jour code
    echo "⬇️ Récupération dernière version..."
    cd "$BOT_DIR"
    git fetch origin
    git pull origin main
    
    # 4. Mise à jour dépendances
    echo "📚 Mise à jour dépendances..."
    source venv/bin/activate
    pip install -r requirements.txt --upgrade
    
    # 5. Mise à jour navigateur
    echo "🌐 Mise à jour Chromium..."
    playwright install chromium
    
    # 6. Validation configuration
    echo "⚙️ Validation configuration..."
    python main.py --test-connection --config .env.prod --timeout 30
    
    if [ $? -ne 0 ]; then
        echo "❌ Validation échouée! Rollback..."
        rollback_update
        exit 1
    fi
    
    # 7. Redémarrage service
    echo "▶️ Redémarrage service..."
    sudo systemctl start bot-operateur
    
    # 8. Vérification santé
    sleep 10
    if sudo systemctl is-active --quiet bot-operateur; then
        echo "✅ Mise à jour réussie!"
        echo "📊 Version: $(git rev-parse --short HEAD)"
    else
        echo "❌ Service non démarré! Vérification nécessaire."
        exit 1
    fi
}

rollback_update() {
    echo "🔄 Rollback en cours..."
    
    # Restaurer le dernier backup
    latest_backup=$(ls -t $BACKUP_DIR/bot-operateur-backup-*.tar.gz | head -n1)
    ./backup-bot-operateur.sh restore "$latest_backup"
    
    echo "⚠️ Rollback terminé - Version précédente restaurée"
}

health_check() {
    echo "🏥 Vérification santé du système..."
    
    # Test service
    if ! sudo systemctl is-active --quiet bot-operateur; then
        echo "❌ Service non actif"
        return 1
    fi
    
    # Test connexion
    cd "$BOT_DIR"
    source venv/bin/activate
    python main.py --test-connection --config .env.prod --timeout 30
    
    if [ $? -eq 0 ]; then
        echo "✅ Santé système OK"
        return 0
    else
        echo "❌ Problème de connexion détecté"
        return 1
    fi
}

case "$1" in
    update)
        update_bot
        ;;
    rollback)
        rollback_update
        ;;
    health)
        health_check
        ;;
    *)
        echo "Usage: $0 {update|rollback|health}"
        echo ""
        echo "  update   - Met à jour le bot vers la dernière version"
        echo "  rollback - Revient à la version précédente"  
        echo "  health   - Vérifie la santé du système"
        exit 1
        ;;
esac
```

#### **Automatisation avec Cron**
```bash
# Mise à jour automatique hebdomadaire (dimanche 1h)
0 1 * * 0 /home/botoperateur/scripts/update-bot-operateur.sh update

# Health check quotidien
0 6 * * * /home/botoperateur/scripts/update-bot-operateur.sh health
```

### **Maintenance Préventive**

#### **Script de Maintenance**
```bash
#!/bin/bash
# maintenance-bot-operateur.sh

maintenance_routine() {
    echo "🔧 Maintenance préventive Bot Opérateur 112..."
    
    # 1. Nettoyage logs
    echo "🧹 Nettoyage des logs..."
    find /home/botoperateur/logs -name "*.log" -size +100M -exec truncate -s 50M {} \;
    
    # 2. Nettoyage cache navigateur
    echo "🗑️ Nettoyage cache navigateur..."
    rm -rf /home/botoperateur/.cache/ms-playwright/chromium-*/
    
    # 3. Nettoyage screenshots
    echo "📸 Nettoyage screenshots..."
    find /home/botoperateur/screenshots -name "*.png" -mtime +7 -delete
    
    # 4. Vérification espace disque
    echo "💾 Vérification espace disque..."
    df -h | grep -E "/(home|var/log)" | awk '{if($5 > "80%") print "ATTENTION: "$0}'
    
    # 5. Optimization base de données (si utilisée)
    echo "🗄️ Optimisation données..."
    if [ -f "/home/botoperateur/metrics.db" ]; then
        sqlite3 /home/botoperateur/metrics.db "VACUUM;"
    fi
    
    # 6. Test performance
    echo "⚡ Test performance..."
    cd /home/botoperateur/Bot_OperateurV3
    source venv/bin/activate
    python -c "
import time
start = time.time()
import bot_operateur
print(f'Import time: {time.time() - start:.2f}s')
"
    
    echo "✅ Maintenance terminée"
}

# Maintenance mensuelle complète
maintenance_routine
```

---

## 📈 **Optimisation Continue**

### **Profiling et Analyse Performance**

#### **Script de Profiling**
```python
#!/usr/bin/env python3
# profile_bot.py

import asyncio
import cProfile
import pstats
import time
from pathlib import Path
import sys
import os

# Ajouter le bot au path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot_operateur.core.bot import OperateurBot
from bot_operateur.config.settings import Settings

async def profile_bot_performance():
    """Profile les performances du bot"""
    
    settings = Settings.from_env('.env.prod')
    
    # Profiling avec cProfile
    profiler = cProfile.Profile()
    
    async with OperateurBot(settings) as bot:
        print("🔍 Début du profiling...")
        
        profiler.enable()
        start_time = time.time()
        
        # Test performance sur 5 missions
        missions = await bot.get_available_missions()
        if missions:
            for i, mission in enumerate(missions[:5]):
                print(f"Mission {i+1}/5: {mission.id}")
                await bot.deploy_mission(mission.id)
        
        end_time = time.time()
        profiler.disable()
        
        print(f"⏱️ Temps total: {end_time - start_time:.2f}s")
        
        # Analyse résultats
        stats = pstats.Stats(profiler)
        stats.sort_stats('cumulative')
        
        # Top 20 fonctions les plus coûteuses
        print("\n📊 Top 20 fonctions les plus coûteuses:")
        stats.print_stats(20)
        
        # Sauvegarder résultats
        stats.dump_stats(f'profile_results_{int(time.time())}.prof')
        
        return {
            'total_time': end_time - start_time,
            'missions_count': min(len(missions), 5),
            'avg_time_per_mission': (end_time - start_time) / min(len(missions), 5)
        }

def analyze_memory_usage():
    """Analyse l'utilisation mémoire"""
    import psutil
    import gc
    
    process = psutil.Process()
    
    print("💾 Analyse mémoire:")
    print(f"  RSS: {process.memory_info().rss / 1024 / 1024:.1f} MB")
    print(f"  VMS: {process.memory_info().vms / 1024 / 1024:.1f} MB")
    print(f"  CPU: {process.cpu_percent():.1f}%")
    
    # Garbage collection info
    print(f"  GC Objects: {len(gc.get_objects())}")
    print(f"  GC Stats: {gc.get_stats()}")

if __name__ == "__main__":
    # Profiling performance
    results = asyncio.run(profile_bot_performance())
    
    print(f"\n✅ Profiling terminé:")
    print(f"  • Temps total: {results['total_time']:.2f}s")
    print(f"  • Missions: {results['missions_count']}")
    print(f"  • Temps/mission: {results['avg_time_per_mission']:.2f}s")
    
    # Analyse mémoire
    analyze_memory_usage()
```

### **Optimisations Automatiques**

#### **Auto-Tuner Configuration**
```python
#!/usr/bin/env python3
# auto_tune.py

import asyncio
import time
from typing import Dict, List, Tuple
from dataclasses import dataclass
import json

@dataclass
class PerformanceTest:
    config: Dict
    avg_time: float
    success_rate: float
    error_count: int

class AutoTuner:
    def __init__(self):
        self.baseline_config = {
            'PAGE_LOAD_TIMEOUT': 15,
            'ELEMENT_WAIT_TIMEOUT': 5,
            'FAST_TIMEOUT': 3,
            'VEHICLE_THRESHOLD': 3,
            'BROWSER_SLOW_MO': 0
        }
        self.test_results: List[PerformanceTest] = []
    
    async def run_optimization_tests(self):
        """Teste différentes configurations pour optimiser"""
        
        # Configurations à tester
        test_configs = [
            # Configuration actuelle (baseline)
            self.baseline_config,
            
            # Tests timeouts réduits
            {**self.baseline_config, 'PAGE_LOAD_TIMEOUT': 10, 'ELEMENT_WAIT_TIMEOUT': 3},
            {**self.baseline_config, 'PAGE_LOAD_TIMEOUT': 8, 'FAST_TIMEOUT': 2},
            
            # Tests VEHICLE_THRESHOLD
            {**self.baseline_config, 'VEHICLE_THRESHOLD': 5},
            {**self.baseline_config, 'VEHICLE_THRESHOLD': 1},
            
            # Tests combinaisons optimisées
            {
                'PAGE_LOAD_TIMEOUT': 8,
                'ELEMENT_WAIT_TIMEOUT': 3,
                'FAST_TIMEOUT': 2,
                'VEHICLE_THRESHOLD': 5,
                'BROWSER_SLOW_MO': 0
            }
        ]
        
        print("🚀 Début des tests d'optimisation...")
        
        for i, config in enumerate(test_configs):
            print(f"\nTest {i+1}/{len(test_configs)}: {config}")
            result = await self._test_configuration(config)
            self.test_results.append(result)
            
            print(f"  Résultat: {result.avg_time:.2f}s/mission, "
                  f"succès: {result.success_rate:.1f}%, "
                  f"erreurs: {result.error_count}")
    
    async def _test_configuration(self, config: Dict) -> PerformanceTest:
        """Teste une configuration spécifique"""
        
        # Créer fichier .env temporaire
        env_content = "\n".join([f"{k}={v}" for k, v in config.items()])
        with open('.env.test', 'w') as f:
            f.write(env_content)
        
        # Importer et tester
        from bot_operateur.config.settings import Settings
        from bot_operateur.core.bot import OperateurBot
        
        settings = Settings.from_env('.env.test')
        
        times = []
        errors = 0
        successes = 0
        
        async with OperateurBot(settings) as bot:
            missions = await bot.get_available_missions()
            
            # Tester sur 3 missions max
            for mission in missions[:3]:
                try:
                    start = time.time()
                    success = await bot.deploy_mission(mission.id)
                    end = time.time()
                    
                    times.append(end - start)
                    if success:
                        successes += 1
                except Exception:
                    errors += 1
        
        avg_time = sum(times) / len(times) if times else 0
        success_rate = (successes / len(times)) * 100 if times else 0
        
        return PerformanceTest(config, avg_time, success_rate, errors)
    
    def generate_recommendations(self) -> Dict:
        """Génère des recommandations basées sur les tests"""
        
        if not self.test_results:
            return {"error": "Aucun test effectué"}
        
        # Trouver la meilleure configuration
        best_result = min(self.test_results, 
                         key=lambda x: x.avg_time if x.success_rate > 80 else float('inf'))
        
        baseline = self.test_results[0]  # Premier test = baseline
        
        improvement = ((baseline.avg_time - best_result.avg_time) / baseline.avg_time) * 100
        
        return {
            'baseline_performance': {
                'avg_time': baseline.avg_time,
                'success_rate': baseline.success_rate
            },
            'recommended_config': best_result.config,
            'expected_performance': {
                'avg_time': best_result.avg_time,
                'success_rate': best_result.success_rate,
                'improvement': f"{improvement:.1f}%"
            },
            'all_results': [
                {
                    'config': r.config,
                    'performance': f"{r.avg_time:.2f}s ({r.success_rate:.1f}%)"
                }
                for r in sorted(self.test_results, key=lambda x: x.avg_time)
            ]
        }

async def main():
    tuner = AutoTuner()
    await tuner.run_optimization_tests()
    
    recommendations = tuner.generate_recommendations()
    
    print("\n" + "="*50)
    print("📊 RECOMMANDATIONS D'OPTIMISATION")
    print("="*50)
    
    print(f"\n🎯 Configuration recommandée:")
    for key, value in recommendations['recommended_config'].items():
        print(f"  {key}={value}")
    
    print(f"\n📈 Performance attendue:")
    perf = recommendations['expected_performance']
    print(f"  • Temps moyen: {perf['avg_time']:.2f}s/mission")
    print(f"  • Taux succès: {perf['success_rate']:.1f}%")
    print(f"  • Amélioration: {perf['improvement']}")
    
    # Sauvegarder résultats
    with open('optimization_results.json', 'w') as f:
        json.dump(recommendations, f, indent=2)
    
    print(f"\n💾 Résultats sauvés dans: optimization_results.json")

if __name__ == "__main__":
    asyncio.run(main())
```

Ce guide de déploiement complet couvre tous les aspects de la mise en production du Bot Opérateur 112, des configurations de base aux optimisations avancées, en passant par la sécurité et la maintenance.