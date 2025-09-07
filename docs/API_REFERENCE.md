# API Reference - Bot Opérateur 112

## 🔗 **Interface CLI**

### **Arguments Principaux**

#### **Modes d'Exécution**
```bash
python main.py [MODE] [OPTIONS]
```

| Mode | Description | Exemple |
|------|-------------|---------|
| `--list` | Liste les missions disponibles | `python main.py --list` |
| `--mission ID` | Déploie une mission spécifique | `python main.py --mission 123456` |
| `--auto` | Mode automatique avec limite | `python main.py --auto --max-missions 5` |
| `--continuous` | Mode continu 24/7 | `python main.py --continuous` |
| `--status` | Affiche le statut du bot | `python main.py --status` |

#### **Modes d'Analyse**
```bash
# Analyse des conditions de mission
python main.py --analyze-conditions [--max-analyze N]
python main.py --analyze-mission ID
python main.py --test-mission ID

# Tests de fonctionnalités
python main.py --test-connection
python main.py --test-browser
```

#### **Options de Debug**
```bash
# Interface et logging
--debug              # Mode debug avec logs détaillés
--no-headless       # Affiche le navigateur (désactive HEADLESS)
--verbose           # Logs plus verbeux
--config FILE       # Utilise un fichier .env spécifique

# Contrôle d'exécution
--max-missions N    # Limite le nombre de missions (mode auto)
--max-analyze N     # Limite l'analyse aux N premières missions
--min-credits N     # Seuil minimum de crédits par mission
--strategy STRAT    # Force une stratégie (smart/balanced/minimum/optimal)
--timeout N         # Timeout global en secondes
```

#### **Exemples Complets**
```bash
# Session de développement
python main.py --list --debug --no-headless --verbose

# Test mission spécifique  
python main.py --mission 123456 --strategy smart --debug

# Production optimisée
python main.py --continuous --strategy smart --min-credits 1000

# Analyse batch
python main.py --analyze-conditions --max-analyze 20 --config .env.analysis
```

### **Codes de Retour**

| Code | Signification | Action Recommandée |
|------|---------------|-------------------|
| `0` | Succès complet | Aucune |
| `1` | Succès partiel (certaines missions échouées) | Vérifier les logs |
| `2` | Erreur de configuration | Corriger .env |
| `3` | Erreur de connexion | Vérifier identifiants/réseau |
| `4` | Erreur critique système | Redémarrer, vérifier dépendances |
| `5` | Interruption utilisateur (Ctrl+C) | Normal |

---

## ⚙️ **Configuration API**

### **Variables d'Environnement Complètes**

#### **Authentification** *(Obligatoire)*
```bash
USERNAME=votre_nom_utilisateur_operateur112
PASSWORD=votre_mot_de_passe_securise
GAME_URL=https://www.operateur112.fr
```

#### **Stratégies de Déploiement**
```bash
DEFAULT_STRATEGY=smart              # smart|balanced|minimum|optimal
VEHICLE_THRESHOLD=3                 # Skip si > N véhicules manquants
MIN_CREDITS_THRESHOLD=1000          # Seuil minimum crédits/mission
MAX_CONCURRENT_MISSIONS=5           # Limite sécurité déploiements simultanés
FORCE_DEPLOYMENT=false             # Force déploiement même si sous-optimal
```

#### **Performance et Timeouts** *(Optimisé)*
```bash
# Timeouts principaux (millisecondes converties automatiquement)
PAGE_LOAD_TIMEOUT=15               # Chargement page (optimisé de 30→15s)
ELEMENT_WAIT_TIMEOUT=5             # Attente éléments (optimisé de 10→5s)
FAST_TIMEOUT=3                     # Éléments critiques rapides
SLOW_TIMEOUT=12                    # Opérations complexes uniquement
RETRY_DELAY=1                      # Délai entre retries (optimisé de 2→1s)

# Navigation optimisée
FAST_NAVIGATION=true               # Active la navigation rapide par défaut
USE_CACHE_NAVIGATION=true          # Cache les sessions de navigation
```

#### **Interface Navigateur**
```bash
HEADLESS=true                      # Mode sans interface (plus rapide)
BROWSER_SLOW_MO=0                  # Ralentissement (ms) - 0 = maximum vitesse
BROWSER_TYPE=chromium              # chromium|firefox|webkit
BROWSER_ARGS="--no-sandbox,--disable-dev-shm-usage"  # Args Chrome supplémentaires
```

#### **Logging et Debug**
```bash
LOG_LEVEL=INFO                     # DEBUG|INFO|WARNING|ERROR|CRITICAL
LOG_FILE=bot.log                   # Fichier de log principal
LOG_ROTATION=10MB                  # Rotation automatique des logs
LOG_RETENTION=7d                   # Rétention des anciens logs
ENABLE_PERFORMANCE_LOGS=true       # Logs de performance détaillés
```

#### **Contrôles de Sécurité**
```bash
ENABLE_SCREENSHOT=false            # Screenshots automatiques en cas d'erreur
MAX_RETRY_ATTEMPTS=3               # Nombre max de tentatives
FAIL_SAFE_MODE=true               # Arrêt en cas d'erreur critique
RATE_LIMITING=true                 # Limitation du taux de requêtes
```

#### **Fonctionnalités Avancées**
```bash
ENABLE_PROBABILITY_DETECTION=true  # Détection des indicateurs de probabilité
ENABLE_PERSONNEL_CONVERSION=true   # Conversion personnel→véhicules
ENABLE_CAPACITY_CONSTRAINTS=true   # Respect des capacités véhicules
ENABLE_ALTERNATIVE_MAPPING=true    # Mapping automatique alternatives
ENABLE_PARALLEL_PROCESSING=true    # Traitement parallèle des véhicules
```

### **Configuration par Profil**

#### **Profil Développement** `.env.dev`
```bash
USERNAME=your_username
PASSWORD=your_password
DEFAULT_STRATEGY=smart
HEADLESS=false                     # Interface visible
LOG_LEVEL=DEBUG                    # Logs détaillés
BROWSER_SLOW_MO=500               # Ralentissement pour observation
VEHICLE_THRESHOLD=1               # Tolérance faible pour tests
ENABLE_SCREENSHOT=true            # Screenshots de debug
PAGE_LOAD_TIMEOUT=30              # Timeouts longs pour debug
```

#### **Profil Production** `.env.prod`  
```bash
USERNAME=production_user
PASSWORD=secure_password
DEFAULT_STRATEGY=smart
HEADLESS=true                      # Mode rapide
LOG_LEVEL=WARNING                  # Logs minimaux
BROWSER_SLOW_MO=0                 # Vitesse maximale
VEHICLE_THRESHOLD=3               # Équilibre performance/efficacité
MIN_CREDITS_THRESHOLD=1200        # Focus missions rentables
PAGE_LOAD_TIMEOUT=10              # Timeouts optimisés
ENABLE_PERFORMANCE_LOGS=true      # Métriques production
```

#### **Profil Performance** `.env.perf`
```bash
USERNAME=perf_user
PASSWORD=password
DEFAULT_STRATEGY=smart
HEADLESS=true
LOG_LEVEL=ERROR                   # Logs minimaux
FAST_NAVIGATION=true              # Navigation ultra-rapide
USE_CACHE_NAVIGATION=true         # Cache maximal
PAGE_LOAD_TIMEOUT=8               # Timeouts très courts
ELEMENT_WAIT_TIMEOUT=3            
FAST_TIMEOUT=1                    
RETRY_DELAY=0.5                   
VEHICLE_THRESHOLD=5               # Tolérance élevée
ENABLE_PARALLEL_PROCESSING=true   # Parallélisme maximal
```

---

## 🏗️ **Architecture API**

### **Classes Principales**

#### **`OperateurBot`** *(Main Controller)*
```python
class OperateurBot:
    """Contrôleur principal du système bot"""
    
    def __init__(self, settings: Settings)
    async def __aenter__(self) -> 'OperateurBot'
    async def __aexit__(self, exc_type, exc_val, exc_tb)
    
    # Modes d'exécution
    async def run_auto_mode(self, max_missions: int = 10) -> dict
    async def run_continuous_mode(self) -> None
    async def deploy_mission(self, mission_id: str) -> bool
    async def get_available_missions(self) -> List[Mission]
    async def get_bot_status(self) -> dict
    
    # Analyse et tests
    async def analyze_mission_conditions(self, max_analyze: int = 5) -> List[dict]
    async def test_mission_scraping(self, mission_id: str) -> dict
    async def test_connection(self) -> bool
```

#### **`MissionManager`** *(Core Logic)*
```python
class MissionManager:
    """Gestionnaire principal des déploiements"""
    
    def __init__(self, browser_manager, vehicle_scraper, patient_scraper, settings)
    
    # Déploiement principal (optimisé)
    async def deploy_vehicles_for_mission_optimized(
        self, mission: Mission, strategy: str = None
    ) -> bool
    
    # Récupération données mission
    async def get_mission_details(self, mission_url: str) -> Mission
    async def get_mission_conditions(self, mission_id: str) -> List[MissionCondition]
    
    # Analyse intelligente des besoins
    async def _extract_missing_vehicles_from_alert(
        self, page: Page, mission: Mission
    ) -> List[MissionRequirement]
    
    # Transport de patients
    async def _handle_patient_transport_initial(
        self, page: Page, mission: Mission
    ) -> bool
```

#### **`BrowserManager`** *(Infrastructure)*
```python
class BrowserManager:
    """Gestionnaire optimisé Playwright"""
    
    def __init__(self, settings: Settings)
    async def initialize(self) -> None
    async def cleanup(self) -> None
    
    # Navigation optimisée 
    async def navigate_to(
        self, url: str, 
        wait_for_load: bool = True, 
        fast_navigation: bool = False
    ) -> None
    
    # Attentes intelligentes
    async def wait_for_selector(
        self, selector: str, 
        timeout: int = None, 
        fast: bool = False
    ) -> ElementHandle
    
    async def wait_for_any_selector(
        self, selectors: List[str], 
        timeout: int = None
    ) -> tuple[ElementHandle, int]
    
    # Utilitaires
    async def take_screenshot(self, filename: str = None) -> str
    async def get_page_title(self) -> str
    async def is_element_visible(self, selector: str) -> bool
```

#### **`VehicleScraper`** *(Core Intelligence)*  
```python
class VehicleScraper:
    """Scraper intelligent des véhicules avec optimisations"""
    
    def __init__(self, browser_manager, settings)
    
    # API principale (signature optimisée)
    async def vehicle_needs(
        self, 
        needs: dict,
        alternatives_mapping: dict,
        mission_type: str,
        mission: Mission,
        alert_override_types: list = None,
        constrained_vehicles: list = None,
        constrained_alternatives: dict = None
    ) -> tuple[int, int]  # (selected_count, missing_count)
    
    # Déploiement
    async def deploy_selected_vehicles(self) -> bool
    
    # Extraction optimisée (parallélisée)
    async def _extract_vehicle_basic_info(
        self, row: ElementHandle, index: int
    ) -> dict
    
    # Logique de sélection avancée
    async def _select_vehicles_with_alternatives_and_capacity_constraints(
        self, vehicle_rows: List, needs: dict, alternatives_mapping: dict,
        constrained_vehicles: list, constrained_alternatives: dict
    ) -> tuple[int, int]
```

#### **`RequirementParser`** *(AI Logic)*
```python
class RequirementParser:
    """Analyseur intelligent des exigences de mission"""
    
    def __init__(self, needs_data: dict, vehicles_data: dict)
    
    # Parsing principal
    def parse_mission_text(self, text: str, mission_type: str = None) -> List[MissionRequirement]
    
    # Conversions intelligentes
    def _convert_personnel_to_vehicle_requirements(
        self, personnel_needs: List[MissionRequirement]
    ) -> List[MissionRequirement]
    
    def _deduplicate_overlapping_requirements(
        self, requirements: List[MissionRequirement]
    ) -> List[MissionRequirement]
    
    # Détection probabilités
    def _is_probability_indicator(self, requirement_type: str, context: str) -> bool
```

### **Modèles de Données** *(Pydantic)*

#### **`Mission`**
```python
class Mission(BaseModel):
    id: str
    title: str
    type: MissionType
    credits: int
    url: str
    patients: List[Patient] = []
    requirements: List[MissionRequirement] = []
    conditions: List[MissionCondition] = []
    
    # Méthodes utilitaires
    def get_total_credits(self) -> int
    def has_patients(self) -> bool  
    def is_critical(self) -> bool
    def get_complexity_score(self) -> float
```

#### **`Vehicle`**
```python
class Vehicle(BaseModel):
    vehicle_type: str
    caption: str
    distance: Optional[int] = None
    fuel_level: Optional[int] = None
    crew_size: Optional[int] = None
    water_capacity_l: Optional[int] = None
    is_selected: bool = False
    is_available: bool = True
    
    # Capacités
    def can_satisfy_requirement(self, requirement: MissionRequirement) -> bool
    def get_efficiency_score(self) -> float
```

#### **`MissionRequirement`**  
```python
class MissionRequirement(BaseModel):
    vehicle_type: str
    quantity: int
    optional: bool = False
    source: str = "parsed"  # parsed|alert|manual
    priority: int = 1       # 1=high, 2=medium, 3=low
    
    def is_critical(self) -> bool
    def can_be_satisfied_by(self, vehicle: Vehicle) -> bool
```

#### **`Settings`** *(Configuration)*
```python
class Settings(BaseModel):
    # Authentification
    username: str
    password: str
    game_url: str = "https://www.operateur112.fr"
    
    # Stratégie (optimisé)
    default_strategy: str = "smart"
    vehicle_threshold: int = 3
    min_credits_threshold: int = 1000
    max_concurrent_missions: int = 5
    
    # Performance (optimisé)  
    page_load_timeout: int = 15        # Réduit de 30s
    element_wait_timeout: int = 5      # Réduit de 10s  
    fast_timeout: int = 3              # Nouveau
    slow_timeout: int = 12             # Nouveau
    retry_delay: int = 1               # Réduit de 2s
    
    # Interface
    headless: bool = True
    browser_slow_mo: int = 0           # Optimisé
    log_level: str = "INFO"
    
    @classmethod
    def from_env(cls, env_file: str = ".env") -> "Settings"
    
    def get_timeout_ms(self, timeout_type: str) -> int
    def is_fast_mode(self) -> bool
    def get_strategy_config(self) -> dict
```

---

## 🔌 **Hooks et Extensions**

### **Strategy Hooks**
```python
# Implémentation d'une stratégie personnalisée
class CustomStrategy(DeploymentStrategy):
    def __init__(self, custom_param: str):
        self.custom_param = custom_param
    
    async def get_vehicle_needs(self, mission: Mission) -> dict:
        # Logique personnalisée
        base_needs = await self._analyze_mission_text(mission.title)
        
        # Modifications selon paramètre custom
        if self.custom_param == "aggressive":
            return {k: v * 2 for k, v in base_needs.items()}
        
        return base_needs
        
    def get_strategy_name(self) -> str:
        return f"custom_{self.custom_param}"

# Enregistrement
from bot_operateur.strategies import STRATEGIES
STRATEGIES['custom'] = CustomStrategy('aggressive')
```

### **Scraper Extensions**
```python
# Extension du scraper de véhicules
class ExtendedVehicleScraper(VehicleScraper):
    async def vehicle_needs(self, needs, alternatives, mission_type, mission, **kwargs):
        # Pré-traitement personnalisé
        needs = self._apply_custom_logic(needs, mission_type)
        
        # Appel de la méthode parente  
        selected, missing = await super().vehicle_needs(
            needs, alternatives, mission_type, mission, **kwargs
        )
        
        # Post-traitement
        logger.info(f"Custom logic: selected={selected}, missing={missing}")
        return selected, missing
    
    def _apply_custom_logic(self, needs: dict, mission_type: str) -> dict:
        # Logique métier personnalisée
        if mission_type == "FIRE":
            needs["FPT"] = needs.get("FPT", 0) + 1  # Toujours +1 FPT
        return needs
```

### **Monitoring Hooks**
```python
# Hook de monitoring des performances
class PerformanceMonitor:
    def __init__(self):
        self.metrics = {}
    
    async def on_mission_start(self, mission_id: str):
        self.metrics[mission_id] = {
            'start_time': time.time(),
            'steps': []
        }
    
    async def on_mission_complete(self, mission_id: str, success: bool):
        if mission_id in self.metrics:
            duration = time.time() - self.metrics[mission_id]['start_time']
            logger.info(f"Mission {mission_id} completed in {duration:.2f}s (success={success})")
    
    async def on_step_complete(self, mission_id: str, step_name: str, duration: float):
        if mission_id in self.metrics:
            self.metrics[mission_id]['steps'].append({
                'step': step_name,
                'duration': duration
            })

# Intégration dans OperateurBot
monitor = PerformanceMonitor()
await monitor.on_mission_start(mission.id)
# ... execution mission ...
await monitor.on_mission_complete(mission.id, success)
```

---

## 📊 **API de Métriques**

### **Métriques Système**
```python
# Collecte des métriques en temps réel
class MetricsCollector:
    async def get_system_metrics(self) -> dict:
        return {
            'performance': {
                'avg_deployment_time': 4.7,  # secondes
                'success_rate': 0.95,        # 95%
                'missions_per_hour': 761,
                'vehicle_accuracy': 0.98     # 98%
            },
            'resources': {
                'memory_usage': self._get_memory_usage(),
                'browser_instances': self._count_browser_instances(),
                'active_missions': len(self.active_missions)
            },
            'errors': {
                'timeout_errors': self.timeout_count,
                'network_errors': self.network_error_count,
                'parsing_errors': self.parsing_error_count
            }
        }
    
    async def get_performance_report(self, hours: int = 24) -> dict:
        """Rapport de performance sur les N dernières heures"""
        return {
            'period': f'{hours}h',
            'total_missions': self._count_missions(hours),
            'successful_missions': self._count_successful_missions(hours),
            'average_time': self._avg_deployment_time(hours),
            'credits_earned': self._total_credits(hours),
            'top_errors': self._get_top_errors(hours, limit=5)
        }
```

### **API de Santé**
```python
# Health Check API
class HealthChecker:
    async def health_check(self) -> dict:
        checks = {}
        
        # Test connexion
        try:
            await self._test_game_connection()
            checks['game_connection'] = {'status': 'ok', 'response_time': '1.2s'}
        except Exception as e:
            checks['game_connection'] = {'status': 'error', 'error': str(e)}
        
        # Test browser  
        try:
            await self._test_browser_functionality()
            checks['browser'] = {'status': 'ok', 'version': 'chromium-91.0'}
        except Exception as e:
            checks['browser'] = {'status': 'error', 'error': str(e)}
        
        # Test parsing  
        checks['data_files'] = {
            'needs_labels_v2.json': self._check_file_integrity('needs_labels_v2.json'),
            'vehicles_v2.json': self._check_file_integrity('vehicles_v2.json')
        }
        
        return {
            'status': 'healthy' if all(c.get('status') == 'ok' for c in checks.values()) else 'degraded',
            'checks': checks,
            'timestamp': datetime.now().isoformat()
        }
```

---

## 🔧 **Utilitaires API**

### **Analyseurs de Patterns**
```python
# Analyse des patterns non reconnus
from bot_operateur.utils.analyze_patterns import PatternAnalyzer

analyzer = PatternAnalyzer()

# Analyser les véhicules non reconnus
unknown_patterns = await analyzer.analyze_unrecognized_vehicles()
print(f"Found {len(unknown_patterns)} unknown vehicle patterns")

# Suggérer des patterns pour améliorer la reconnaissance
suggestions = analyzer.suggest_patterns(unknown_patterns)
for suggestion in suggestions:
    print(f"Pattern: {suggestion['pattern']} -> Vehicle: {suggestion['suggested_vehicle']}")
```

### **Outils de Configuration**
```python
# Validation et optimisation de configuration
from bot_operateur.utils.config_optimizer import ConfigOptimizer

optimizer = ConfigOptimizer()

# Analyser la configuration actuelle
analysis = optimizer.analyze_current_config()
print(f"Performance score: {analysis['performance_score']}/100")

# Suggestions d'optimisation  
suggestions = optimizer.get_optimization_suggestions()
for suggestion in suggestions:
    print(f"{suggestion['parameter']}: {suggestion['current']} -> {suggestion['suggested']} ({suggestion['improvement']})")

# Appliquer automatiquement les optimisations
optimizer.apply_suggestions(suggestions, backup=True)
```

### **Migration de Données**
```python
# Outils de migration pour les mises à jour
from bot_operateur.utils.data_migrator import DataMigrator

migrator = DataMigrator()

# Migrer de v1 vers v2
await migrator.migrate_needs_labels_v1_to_v2()
await migrator.migrate_vehicles_v1_to_v2()

# Sauvegarder et restaurer configuration
backup_path = migrator.backup_configuration()
# ... modifications ...  
migrator.restore_configuration(backup_path)
```

Cette API Reference couvre l'intégralité des interfaces disponibles dans le Bot Opérateur 112, avec tous les paramètres optimisés et les nouvelles fonctionnalités implementées (VEHICLE_THRESHOLD, optimisations performance 68.5%, patterns probabilité, etc.).