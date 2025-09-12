"""
Constantes globales pour le Bot Opérateur 112.
Centralise les valeurs magiques pour améliorer la maintainabilité.
"""

# Timeouts par défaut (en millisecondes)
DEFAULT_ELEMENT_TIMEOUT_MS = 5000
DEFAULT_PAGE_LOAD_TIMEOUT_MS = 30000
DEFAULT_NAVIGATION_TIMEOUT_MS = 10000
DEFAULT_RETRY_TIMEOUT_MS = 3000

# Timeouts optimisés pour les opérations rapides
FAST_NAVIGATION_TIMEOUT_MS = 5000
FAST_ELEMENT_TIMEOUT_MS = 2000
CLEANUP_TIMEOUT_MS = 2000
BROWSER_CLOSE_TIMEOUT_MS = 3000

# Seuils et limites
MIN_CREDITS_THRESHOLD = 1000
MAX_CONCURRENT_MISSIONS = 5
MAX_RETRY_ATTEMPTS = 3
VEHICLE_THRESHOLD_DEFAULT = 3

# Sélecteurs DOM communs
SELECTORS = {
    'VEHICLE_CHECKBOX': '.vehicle_checkbox',
    'VEHICLE_TABLE': '#vehicle_show_table_all',
    'VEHICLE_ROW': 'tr[id^="vehicle_element_content_"]',
    'MISSION_TABLE': '.table',
    'PATIENT_TABLE': '.table',
}

# URLs de base
BASE_URLS = {
    'MISSIONS': 'https://www.operateur112.fr/missions',
    'VEHICLES': 'https://www.operateur112.fr/vehicles',
    'LOGIN': 'https://www.operateur112.fr/users/sign_in',
}

# Expressions régulières communes
REGEX_PATTERNS = {
    'MISSION_ID': r'missions/(\d+)',
    'VEHICLE_ID': r'vehicle_element_content_(\d+)',
    'NUMBER_EXTRACTION': r'(\d+)',
    'CREDITS_EXTRACTION': r'(\d+)\s*crédits?',
}

# Viewport et navigateur
BROWSER_CONFIG = {
    'VIEWPORT_WIDTH': 1920,
    'VIEWPORT_HEIGHT': 1080,
    'USER_AGENT': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
}

# Configuration de logging
LOG_CONFIG = {
    'MAX_LOG_FILE_SIZE': 10 * 1024 * 1024,  # 10MB
    'LOG_ROTATION_COUNT': 5,
    'LOG_FORMAT': "<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
}

# Codes de retour
EXIT_CODES = {
    'SUCCESS': 0,
    'ERROR': 1,
    'CONFIGURATION_ERROR': 2,
    'NETWORK_ERROR': 3,
    'AUTHENTICATION_ERROR': 4,
}

# Statuts de mission
MISSION_STATUS = {
    'AVAILABLE': 'available',
    'IN_PROGRESS': 'in_progress',
    'COMPLETED': 'completed',
    'FAILED': 'failed',
    'SKIPPED': 'skipped',
}

# Types de véhicules critiques (utilisés fréquemment)
CRITICAL_VEHICLE_TYPES = {
    'AMBULANCE', 'FPT', 'CARS_POLICE', 'BEA', 'CCF', 
    'VSAV', 'RESCUE_DIRECTOR', 'CHEF_DE_GROUPE'
}

# Configuration des stratégies
STRATEGY_CONFIG = {
    'SMART_STRATEGY_COMPLEXITY_THRESHOLD': 10,
    'BALANCED_STRATEGY_MARGIN_PERCENT': 20,
    'MINIMUM_STRATEGY_CONFIDENCE_THRESHOLD': 80,
}

# Messages d'erreur standardisés
ERROR_MESSAGES = {
    'BROWSER_NOT_INITIALIZED': "Le navigateur n'est pas initialisé",
    'ELEMENT_NOT_FOUND': "Élément non trouvé: {selector}",
    'TIMEOUT_OCCURRED': "Timeout lors de l'opération: {operation}",
    'MISSION_PARSING_FAILED': "Échec du parsing de la mission {mission_id}",
    'VEHICLE_SELECTION_FAILED': "Échec de la sélection du véhicule {vehicle_type}",
    'CONFIGURATION_INVALID': "Configuration invalide: {detail}",
}

# Configuration de performance
PERFORMANCE_CONFIG = {
    'PARALLEL_MISSION_LIMIT': 3,
    'CONCURRENT_VEHICLE_CHECKS': 5,
    'DOM_POLLING_INTERVAL_MS': 100,
    'CACHE_TTL_SECONDS': 300,  # 5 minutes
}

# Métadonnées du bot
BOT_METADATA = {
    'VERSION': '3.0',
    'NAME': 'Bot Opérateur 112',
    'DESCRIPTION': 'Bot automatisé pour le déploiement de véhicules d\'urgence',
    'AUTHOR': 'Assistant Claude',
}