"""
Constantes techniques pour le Bot Opérateur 112.
Les valeurs configurables par l'utilisateur sont dans settings.py.
"""

# Timeouts par défaut (en millisecondes)
DEFAULT_ELEMENT_TIMEOUT_MS = 5000
DEFAULT_NAVIGATION_TIMEOUT_MS = 10000

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
