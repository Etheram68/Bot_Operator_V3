# Guide Développeur - Bot Opérateur 112

## 🔧 **Architecture de Développement**

### **Structure du Projet**
```
Bot_OperateurV3/
├── main.py                      # Point d'entrée CLI
├── requirements.txt             # Dépendances Python
├── .env.example                # Template de configuration
├── bot_operateur/              # Package principal
│   ├── __init__.py
│   ├── core/                   # Logique métier centrale
│   │   ├── bot.py             # Coordinateur principal
│   │   ├── mission_manager.py  # Gestionnaire missions
│   │   └── browser_manager.py  # Gestionnaire Playwright
│   ├── scrapers/              # Extracteurs de données
│   │   ├── mission_scraper.py  # Scraping missions
│   │   ├── vehicle_scraper.py  # Scraping véhicules
│   │   └── patient_scraper.py  # Scraping patients
│   ├── strategies/            # Algorithmes de déploiement
│   │   ├── smart_strategy.py   # IA avancée
│   │   ├── balanced_strategy.py # Équilibré
│   │   ├── minimum_strategy.py  # Minimal
│   │   └── optimal_strategy.py  # Performance
│   ├── models/                # Modèles de données
│   │   ├── mission.py         # Modèles mission
│   │   ├── vehicle.py         # Modèles véhicule
│   │   ├── patient.py         # Modèles patient
│   │   └── requirement_parser.py # Parseur IA
│   ├── config/                # Configuration
│   │   └── settings.py        # Settings Pydantic
│   ├── utils/                 # Utilitaires
│   │   ├── logger.py          # Configuration logs
│   │   ├── retry.py           # Logique retry
│   │   └── dom_utils.py       # Helpers DOM
│   └── data/                  # Données de configuration
│       ├── needs_labels_v2.json      # Patterns véhicules
│       ├── vehicles_v2.json          # Mapping véhicules
│       ├── missing_needs_config.json # Config "Il nous manque"
│       └── unrecognized_vehicle_patterns.jsonl
├── tests/                     # Tests automatisés
│   ├── test_performance_improvements.py
│   ├── test_vehicle_threshold_skip.py
│   ├── test_probability_patterns_complete.py
│   └── test_constrained_scenario.py
└── docs/                      # Documentation
    ├── README.md              # Vue d'ensemble
    ├── ARCHITECTURE.md        # Architecture technique
    ├── USER_GUIDE.md         # Guide utilisateur
    └── DEVELOPER_GUIDE.md    # Ce fichier
```

## 🛠️ **Setup Environnement de Développement**

### **Installation Développeur**
```bash
# Clone du repository
git clone <repository>
cd Bot_OperateurV3

# Environnement virtuel (recommandé)
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou venv\Scripts\activate  # Windows

# Installation dépendances dev
pip install -r requirements.txt
pip install pytest pytest-asyncio black isort mypy

# Installation browser
playwright install chromium

# Configuration développement
cp .env.example .env.dev
# Éditer .env.dev avec vos paramètres
```

### **Configuration IDE**

#### **VSCode (Recommandé)**
```json
// .vscode/settings.json
{
    "python.defaultInterpreterPath": "./venv/bin/python",
    "python.linting.enabled": true,
    "python.linting.pylintEnabled": true,
    "python.formatting.provider": "black",
    "python.sortImports.args": ["--profile", "black"],
    "files.associations": {
        "*.py": "python"
    }
}
```

#### **Extensions VSCode Utiles**
- Python (Microsoft)
- Pylance (Microsoft)  
- GitLens (GitKraken)
- Error Lens (usernamehw)
- Todo Tree (Gruntfuggly)

### **Standards de Code**

#### **Formatage Automatique**
```bash
# Black (formatage Python)
black bot_operateur/ tests/ main.py

# isort (imports)
isort bot_operateur/ tests/ main.py --profile black

# mypy (vérification types)
mypy bot_operateur/ --ignore-missing-imports
```

#### **Pre-commit Hooks**
```bash
# Installation
pip install pre-commit
pre-commit install

# Configuration (.pre-commit-config.yaml)
repos:
  - repo: https://github.com/psf/black
    rev: 22.3.0
    hooks:
      - id: black
  - repo: https://github.com/pycqa/isort
    rev: 5.10.1
    hooks:
      - id: isort
        args: ["--profile", "black"]
```

## 🏗️ **Patterns de Développement**

### **1. Context Manager Pattern**
```python
# bot_operateur/core/bot.py
class OperateurBot:
    async def __aenter__(self):
        """Initialisation ressources"""
        await self.browser_manager.initialize()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Nettoyage automatique"""
        await self.browser_manager.cleanup()

# Usage
async def main():
    async with OperateurBot(settings) as bot:
        await bot.deploy_mission("123456")
    # Cleanup automatique
```

### **2. Strategy Pattern**
```python
# bot_operateur/strategies/base.py
class DeploymentStrategy(ABC):
    @abstractmethod
    async def get_vehicle_needs(self, mission: Mission) -> dict:
        """Calcule les besoins en véhicules"""
        pass

# Implémentation
class SmartStrategy(DeploymentStrategy):
    async def get_vehicle_needs(self, mission: Mission) -> dict:
        # Logique IA avancée
        return calculated_needs
        
# Usage avec Factory
strategies = {
    'smart': SmartStrategy(parser),
    'balanced': BalancedStrategy(parser)
}
strategy = strategies[settings.default_strategy]
```

### **3. Pydantic Data Models**
```python
# bot_operateur/models/mission.py
class Mission(BaseModel):
    id: str = Field(..., description="ID unique de la mission")
    title: str = Field(..., description="Titre de la mission") 
    credits: int = Field(ge=0, description="Crédits récompense")
    type: MissionType = Field(default=MissionType.NORMAL)
    
    class Config:
        # Validation stricte
        validate_assignment = True
        # Conversion automatique des types
        coerce = True
        
    @validator('credits')
    def validate_credits(cls, v):
        if v < 0:
            raise ValueError('Credits must be positive')
        return v
```

### **4. Async/Await Patterns**
```python
# Opérations parallèles avec asyncio.gather
async def process_vehicles_parallel(self, vehicle_rows):
    tasks = []
    for i, row in enumerate(vehicle_rows):
        task = self._extract_vehicle_basic_info(row, i)
        tasks.append(task)
    
    # Traitement par lots pour éviter surcharge
    batch_size = 10
    results = []
    for i in range(0, len(tasks), batch_size):
        batch = tasks[i:i+batch_size]
        batch_results = await asyncio.gather(*batch, return_exceptions=True)
        results.extend(batch_results)
    
    return [r for r in results if not isinstance(r, Exception)]
```

### **5. Error Handling avec Retry**
```python
# bot_operateur/utils/retry.py
class RetryHandler:
    async def execute_with_retry(self, func, description: str):
        for attempt in range(self.max_retries):
            try:
                return await func()
            except Exception as e:
                if attempt == self.max_retries - 1:
                    raise
                logger.warning(f"Tentative {attempt + 1} échouée pour {description}: {e}")
                await asyncio.sleep(self.retry_delay * (2 ** attempt))  # Exponential backoff
```

## 🧪 **Tests et Qualité**

### **Structure des Tests**
```python
# tests/test_mission_manager.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from bot_operateur.core.mission_manager import MissionManager

@pytest.mark.asyncio
async def test_deploy_vehicles_success():
    # Arrange
    mock_browser = AsyncMock()
    mock_vehicle_scraper = AsyncMock()
    mock_vehicle_scraper.vehicle_needs.return_value = (5, 0)  # 5 sélectionnés, 0 manquants
    
    manager = MissionManager(mock_browser, mock_vehicle_scraper, settings)
    
    # Act
    result = await manager.deploy_vehicles_for_mission_optimized(mission)
    
    # Assert
    assert result is True
    mock_vehicle_scraper.vehicle_needs.assert_called_once()
```

### **Tests de Performance**
```python
# tests/test_performance_benchmarks.py
import time
import pytest

@pytest.mark.performance
async def test_deployment_speed():
    start_time = time.time()
    
    # Simulation déploiement
    result = await simulate_mission_deployment()
    
    end_time = time.time()
    duration = end_time - start_time
    
    # Assertion performance
    assert duration < 5.0, f"Deployment too slow: {duration:.2f}s"
    assert result.success_rate > 0.9, f"Success rate too low: {result.success_rate}"
```

### **Exécution des Tests**
```bash
# Tous les tests
pytest tests/

# Tests spécifiques
pytest tests/test_mission_manager.py -v

# Tests de performance uniquement
pytest tests/ -m performance

# Coverage
pytest tests/ --cov=bot_operateur --cov-report=html
```

## 🔍 **Debugging et Profiling**

### **Logging Avancé**
```python
from loguru import logger

# Configuration développeur
logger.add("debug.log", 
          level="DEBUG",
          format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} | {message}",
          rotation="1 MB")

# Logging contextuel
@logger.catch
async def risky_function():
    logger.debug("Début opération critique")
    try:
        result = await complex_operation()
        logger.info(f"Succès: {result}")
        return result
    except Exception as e:
        logger.error(f"Échec opération: {e}")
        raise
```

### **Profiling Performance**
```python
import cProfile
import pstats

# Profiling d'une fonction
def profile_mission_deployment():
    pr = cProfile.Profile()
    pr.enable()
    
    # Code à profiler
    asyncio.run(deploy_mission_example())
    
    pr.disable()
    stats = pstats.Stats(pr)
    stats.sort_stats('cumulative')
    stats.print_stats(10)  # Top 10 functions
```

### **Debugging avec pdb**
```python
import pdb

async def debug_vehicle_selection():
    vehicles = await get_available_vehicles()
    pdb.set_trace()  # Point d'arrêt
    
    # Inspection interactive
    # (Pdb) p vehicles
    # (Pdb) len(vehicles)
    # (Pdb) c  # Continue
```

## 🔧 **Développement de Nouvelles Features**

### **Ajout d'une Nouvelle Stratégie**

#### 1. Créer la classe stratégie
```python
# bot_operateur/strategies/experimental_strategy.py
from .base_strategy import DeploymentStrategy

class ExperimentalStrategy(DeploymentStrategy):
    def __init__(self, custom_param: float = 1.5):
        super().__init__()
        self.multiplier = custom_param
    
    async def get_vehicle_needs(self, mission: Mission) -> dict:
        # Logique personnalisée
        base_needs = await self._parse_basic_requirements(mission)
        
        # Appliquer multiplicateur expérimental
        enhanced_needs = {}
        for vehicle_type, quantity in base_needs.items():
            enhanced_needs[vehicle_type] = int(quantity * self.multiplier)
            
        return enhanced_needs
```

#### 2. Enregistrer la stratégie
```python
# bot_operateur/core/bot.py
def _initialize_strategies(self):
    return {
        'smart': SmartStrategy(self.parser),
        'balanced': BalancedStrategy(self.parser),
        'minimum': MinimumStrategy(self.parser),
        'optimal': OptimalStrategy(self.parser),
        'experimental': ExperimentalStrategy(1.5)  # Nouveau
    }
```

#### 3. Ajouter les tests
```python
# tests/test_experimental_strategy.py
@pytest.mark.asyncio
async def test_experimental_strategy():
    strategy = ExperimentalStrategy(multiplier=2.0)
    
    mock_mission = Mission(id="test", title="Test", credits=1000)
    needs = await strategy.get_vehicle_needs(mock_mission)
    
    # Vérifier que le multiplicateur est appliqué
    assert needs['FPT'] == 2  # Si base était 1
```

### **Ajout d'un Nouveau Type de Véhicule**

#### 1. Mettre à jour vehicles_v2.json
```json
{
  "vehicle_mapping": {
    "specialized": {
      "NEW_VEHICLE_TYPE": {
        "primary": ["REAL_GAME_CODE"],
        "secondary": ["ALTERNATIVE_CODE"]
      }
    }
  },
  "vehicle_specs": {
    "REAL_GAME_CODE": {
      "crew_size": 4,
      "water_capacity_l": 1500,
      "special_capability": "new_feature"
    }
  }
}
```

#### 2. Ajouter les patterns de détection
```json
// Dans needs_labels_v2.json
{
  "vehicle_requirements": {
    "NEW_VEHICLE_TYPE": [
      "nouveau véhicule requis",
      "besoin nouveau type",
      "(?<!probabilité )nouveau(?! chance)"
    ]
  }
}
```

#### 3. Tests de régression
```python
def test_new_vehicle_type():
    parser = RequirementParser()
    text = "Mission nécessite 2 nouveaux véhicules"
    
    requirements = parser.parse_mission_text(text)
    
    assert len(requirements) == 1
    assert requirements[0].vehicle_type == "NEW_VEHICLE_TYPE"
    assert requirements[0].quantity == 2
```

### **Optimisation des Performances**

#### 1. Identifier les goulots
```python
# Décorateur pour mesurer le temps
def timing_decorator(func):
    async def wrapper(*args, **kwargs):
        start = time.time()
        result = await func(*args, **kwargs)
        end = time.time()
        logger.info(f"{func.__name__} took {end-start:.2f}s")
        return result
    return wrapper

@timing_decorator
async def slow_operation():
    # Code à optimiser
    pass
```

#### 2. Cache intelligent
```python
# bot_operateur/utils/cache.py
class SmartCache:
    def __init__(self, ttl_seconds: int = 300):
        self.cache = {}
        self.ttl = ttl_seconds
    
    async def get_or_set(self, key: str, factory_func):
        if key in self.cache:
            data, timestamp = self.cache[key]
            if time.time() - timestamp < self.ttl:
                return data
        
        # Cache miss ou expiré
        data = await factory_func()
        self.cache[key] = (data, time.time())
        return data
```

## 📊 **Monitoring et Métriques**

### **Collecte de Métriques**
```python
# bot_operateur/utils/metrics.py
class MetricsCollector:
    def __init__(self):
        self.metrics = {
            'missions_deployed': 0,
            'missions_failed': 0,
            'total_deployment_time': 0.0,
            'vehicles_selected': 0
        }
    
    def record_deployment(self, duration: float, success: bool, vehicles: int):
        if success:
            self.metrics['missions_deployed'] += 1
        else:
            self.metrics['missions_failed'] += 1
            
        self.metrics['total_deployment_time'] += duration
        self.metrics['vehicles_selected'] += vehicles
    
    def get_summary(self) -> dict:
        total_missions = self.metrics['missions_deployed'] + self.metrics['missions_failed']
        
        return {
            'success_rate': self.metrics['missions_deployed'] / max(total_missions, 1),
            'average_time': self.metrics['total_deployment_time'] / max(total_missions, 1),
            'vehicles_per_mission': self.metrics['vehicles_selected'] / max(total_missions, 1)
        }
```

### **Health Checks**
```python
# bot_operateur/utils/health.py
class HealthChecker:
    async def check_browser_health(self) -> bool:
        """Vérifie si le navigateur répond"""
        try:
            await self.browser_manager.page.evaluate("1 + 1")
            return True
        except Exception:
            return False
    
    async def check_game_connectivity(self) -> bool:
        """Vérifie la connexion au jeu"""
        try:
            response = await self.browser_manager.page.goto("https://www.operateur112.fr")
            return response.status == 200
        except Exception:
            return False
```

## 🔄 **CI/CD et Déploiement**

### **GitHub Actions**
```yaml
# .github/workflows/test.yml
name: Tests and Quality

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v2
    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: 3.8
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        playwright install chromium
    
    - name: Run tests
      run: pytest tests/ --cov=bot_operateur
    
    - name: Check code quality
      run: |
        black --check bot_operateur/
        mypy bot_operateur/
```

### **Docker Support**
```dockerfile
# Dockerfile
FROM python:3.8-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

# Install Playwright browsers
RUN playwright install chromium

COPY . .

CMD ["python", "main.py", "--continuous"]
```

## 🚀 **Contribution Guidelines**

### **Pull Request Process**

1. **Créer une branche feature**
```bash
git checkout -b feature/nouvelle-fonctionnalite
```

2. **Développement avec tests**
```bash
# Développer la feature
# Écrire les tests
pytest tests/ -v
```

3. **Vérification qualité**
```bash
black bot_operateur/ tests/
mypy bot_operateur/
pytest tests/ --cov=bot_operateur
```

4. **Commit et push**
```bash
git add .
git commit -m "feat: nouvelle fonctionnalité X"
git push origin feature/nouvelle-fonctionnalite
```

### **Standards de Code**

#### **Nomenclature**
- **Variables** : `snake_case`
- **Fonctions** : `snake_case`  
- **Classes** : `PascalCase`
- **Constantes** : `UPPER_SNAKE_CASE`
- **Modules** : `snake_case.py`

#### **Documentation**
```python
def complex_function(param1: str, param2: int = 10) -> dict:
    """
    Fonction complexe qui fait quelque chose d'important.
    
    Args:
        param1: Description du premier paramètre
        param2: Description du second paramètre (défaut: 10)
        
    Returns:
        dict: Dictionnaire avec les résultats
        
    Raises:
        ValueError: Si param1 est vide
        ConnectionError: Si problème réseau
        
    Example:
        >>> result = complex_function("test", 5)
        >>> print(result['status'])
        'success'
    """
    pass
```

## 🔐 **Sécurité et Bonnes Pratiques**

### **Gestion des Secrets**
```python
# ❌ Mauvais
password = "mon_mot_de_passe"

# ✅ Bon
password = os.getenv("PASSWORD")
if not password:
    raise ValueError("PASSWORD environment variable required")
```

### **Validation des Entrées**
```python
# Utiliser Pydantic pour validation
class MissionRequest(BaseModel):
    mission_id: str = Field(..., regex=r'^\d{6}$')
    strategy: str = Field(..., enum=['smart', 'balanced', 'minimum', 'optimal'])
    max_vehicles: int = Field(default=10, ge=1, le=50)
```

### **Rate Limiting**
```python
import asyncio

class RateLimiter:
    def __init__(self, requests_per_second: float = 1.0):
        self.requests_per_second = requests_per_second
        self.last_request = 0.0
    
    async def wait_if_needed(self):
        now = time.time()
        time_since_last = now - self.last_request
        min_interval = 1.0 / self.requests_per_second
        
        if time_since_last < min_interval:
            await asyncio.sleep(min_interval - time_since_last)
        
        self.last_request = time.time()
```

Cette documentation couvre les aspects essentiels du développement sur le Bot Opérateur 112. Pour des questions spécifiques, consultez le code source et les tests existants.