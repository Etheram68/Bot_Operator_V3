# 🚀 Bot Opérateur 112 v3

Bot d'automatisation intelligent pour le jeu de gestion d'interventions **"Opérateur 112"**.

## ✨ Fonctionnalités

- 🔍 **Détection automatique** de toutes les missions (normales, transport, sécurité, alliance)
- 🚑 **Analyse intelligente** des patients et exigences
- 🚗 **Sélection optimisée** des véhicules selon différentes stratégies  
- 🤖 **Déploiement automatique** avec gestion des erreurs robuste
- 📊 **Logging complet** et monitoring en temps réel
- ⚙️ **Configuration flexible** via variables d'environnement

## 🏗️ Architecture

```
bot_operateur/
├── config/              # Configuration (Settings)
├── core/               # Classes principales (Bot, BrowserManager, MissionManager)
├── scrapers/           # Scrapers spécialisés (Mission, Vehicle, Patient)
├── models/             # Modèles de données (Mission, Vehicle, Patient)
├── utils/              # Utilitaires (Retry, DOMUtils, Logger)
├── strategies/         # Stratégies de déploiement (Balanced, Minimum, Optimal)
└── examples/           # Exemples d'utilisation
```

## 📦 Installation

### 1. Cloner et installer les dépendances
```bash
git clone <repo>
cd Bot_OperateurV3
pip install -r requirements.txt
```

### 2. Installer Playwright
```bash
playwright install chromium
```

### 3. Configuration
```bash
cp .env.example .env
# Éditer .env avec vos credentials
```

### 4. Test de l'architecture
```bash
python test_architecture.py
python test_smart_strategy.py  # Test de la stratégie intelligente
python quick_test.py          # Test rapide de connexion
```

## ⚙️ Configuration

Éditez le fichier `.env` :

```env
# Credentials (OBLIGATOIRE)
USERNAME=votre_username
PASSWORD=votre_password

# Configuration du navigateur
HEADLESS=true                    # Mode sans interface
BROWSER_SLOW_MO=100             # Ralentissement (ms)

# Timeouts
PAGE_LOAD_TIMEOUT=30            # Timeout chargement pages
ELEMENT_WAIT_TIMEOUT=10         # Timeout éléments DOM

# Stratégies et limites
DEFAULT_STRATEGY=smart          # Stratégie par défaut (smart recommandée)
MIN_CREDITS_THRESHOLD=1000      # Seuil minimum de crédits
MAX_CONCURRENT_MISSIONS=5       # Missions simultanées max

# Logging
LOG_LEVEL=INFO                  # DEBUG, INFO, WARNING, ERROR
LOG_FILE=bot.log               # Fichier de log
```

## 🚀 Utilisation

### Interface en ligne de commande

```bash
# Lister les missions disponibles
python main.py --list

# Déployer une mission spécifique
python main.py --mission 12345

# Déploiement automatique (3 missions max)
python main.py --auto --max-missions 3

# Mode continu (10 cycles puis arrêt)
python main.py --continuous --cycles 10

# Mode continu infini (Ctrl+C pour arrêter)
python main.py --continuous

# Afficher le statut du bot
python main.py --status

# Mode debug avec interface graphique
python main.py --list --no-headless --debug
```

### API Python

```python
import asyncio
from bot_operateur import OperateurBot

async def example():
    # Utilisation avec context manager (recommandé)
    async with OperateurBot() as bot:
        
        # Récupérer toutes les missions
        missions = await bot.get_missions()
        print(f"Trouvé {len(missions)} missions")
        
        # Déployer une mission spécifique avec stratégie
        success = await bot.deploy_mission("12345", strategy="balanced")
        
        # Mode automatique
        stats = await bot.run_auto_missions(max_missions=3)
        print(f"Déployé {stats['deployed']} missions")

asyncio.run(example())
```

## 🎯 Stratégies de déploiement

### **Smart** (Recommandée ⭐)
- **Parser intelligent** avec reconnaissance des véhicules réels du jeu
- **Mappings réels** depuis `needs_labels_v2.json` et `vehicles_v2.json` 
- **Système d'alternatives** automatique (ex: VSAV → ASSU → Ambulance)
- **Sélection par proximité** (premier véhicule trouvé = plus proche)
- **Support adaptatif** selon la complexité (simple → major_incident)
- **Analyse prédictive** des besoins avec fallback intelligent

### **Balanced**
- Respecte les exigences + marge de sécurité
- Ajoute des véhicules de support pour grandes missions
- Bon compromis sécurité/coût

### **Minimum** 
- Déploie exactement les véhicules requis
- Économique mais risqué
- Pour missions simples

### **Optimal**
- Analyse le ratio coût/bénéfice
- Sélectionne les meilleurs véhicules (état, carburant)
- Pour optimiser les gains

### Créer une stratégie personnalisée

```python
from bot_operateur.strategies.base_strategy import BaseStrategy

class MaStrategie(BaseStrategy):
    def __init__(self):
        super().__init__("ma_strategie")
    
    async def select_vehicles_for_mission(self, mission, vehicles):
        # Votre logique de sélection
        return ["vehicle_id_1", "vehicle_id_2"]

# Enregistrer la stratégie
bot.mission_manager.strategies["ma_strategie"] = MaStrategie()
```

## 📋 Exemples détaillés

### Déploiement simple
```bash
python bot_operateur/examples/basic_usage.py
```

### Stratégies avancées
```bash
python bot_operateur/examples/advanced_strategies.py
```

## 🔧 Gestion des erreurs

Le bot intègre une gestion robuste des erreurs :

- **Retry automatique** avec backoff exponentiel
- **Détection de changements DOM** avec attente adaptative
- **Gestion des timeouts** sur toutes les opérations
- **Logging détaillé** pour debug et monitoring
- **Récupération gracieuse** en cas d'échec de mission

## 📊 Monitoring et logs

### Logs automatiques
```bash
tail -f bot.log  # Suivre les logs en temps réel
```

### Métriques disponibles
- Nombre de missions trouvées/déployées/échouées
- Temps de traitement par mission  
- Taux de succès par stratégie
- Utilisation des véhicules

## 🚨 Bonnes pratiques

### Sécurité
- ✅ **Ne jamais** commit le fichier `.env`
- ✅ Utiliser des **credentials dédiés** pour le bot
- ✅ Surveiller les **logs d'activité**
- ✅ Tester en mode **non-headless** d'abord

### Performance
- ✅ Ajuster les **timeouts** selon votre connexion
- ✅ Utiliser le **mode headless** en production
- ✅ Limiter les **missions simultanées**
- ✅ Surveiller la **charge système**

### Maintenance
- ✅ **Sauvegarder** les logs régulièrement
- ✅ **Tester** les stratégies sur quelques missions
- ✅ **Mettre à jour** selon les changements du jeu
- ✅ **Nettoyer** les fichiers temporaires

## 🐛 Dépannage

### Le bot ne trouve pas de missions
1. Vérifier la connexion Internet
2. Vérifier les credentials dans `.env`
3. Tester en mode `--no-headless --debug`

### Erreurs de timeout
1. Augmenter `PAGE_LOAD_TIMEOUT` et `ELEMENT_WAIT_TIMEOUT`
2. Vérifier la stabilité de la connexion
3. Réduire `BROWSER_SLOW_MO`

### Missions non déployées
1. Vérifier les **exigences vs véhicules disponibles**
2. Tester avec la stratégie `minimum`
3. Analyser les logs pour identifier le blocage

## 📄 License

MIT License - Voir le fichier LICENSE pour les détails.

## 🤝 Contribution

Les contributions sont les bienvenues ! N'hésitez pas à :
- Signaler des bugs
- Proposer des améliorations  
- Créer de nouvelles stratégies
- Améliorer la documentation

---

**⚠️ Disclaimer**: Ce bot est conçu pour l'automatisation de tâches répétitives dans un jeu. Respectez les conditions d'utilisation du service.