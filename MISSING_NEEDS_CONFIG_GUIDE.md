# Guide d'Utilisation - missing_needs_config.json

## 📋 Vue d'Ensemble

Le fichier `missing_needs_config.json` est utilisé pour **convertir les besoins en personnel et ressources** détectés dans les alertes de mission **en véhicules appropriés à déployer**.

### 🎯 Objectif Principal

Quand le bot détecte une alerte comme :
> "Il manque 4 Spécialistes IMP"

Le fichier `missing_needs_config.json` permet de traduire cela en :
> "Il faut déployer 1 véhicule VIMP (capacité 4-5 personnes)"

---

## 🗂️ Structure du Fichier

```json
{
  "_schema_version": "1.0",
  "_description": "...",
  "_last_updated": "2025-09-05",

  "personnel_mapping": { ... },           // 🔑 Mapping personnel spécialisé → véhicules
  "other_needs_mapping": { ... },         // 🔧 Mapping ressources → types de besoins
  "personnel_vehicle_mapping": { ... },   // 👥 Mapping personnel générique → véhicules
  "deduplication_rules": { ... },         // 🔄 Règles pour éviter les doublons
  "parsing_patterns": { ... },            // 📝 Patterns regex pour parser le texte
  "vehicle_capacity_priorities": { ... }  // 📊 Priorités de sélection des véhicules
}
```

---

## 🔍 Sections Détaillées

### 1. `personnel_mapping` - Personnel Spécialisé

**Usage:** Convertir les codes courts de personnel spécialisé en véhicules

**Exemple:**
```json
"PLG": {
  "name": "Plongeur",
  "vehicles": ["VPL"],              // Liste des véhicules possibles
  "priority": ["VPL"],              // Ordre de priorité
  "description": "Personnel spécialisé dans les interventions subaquatiques"
}
```

**Utilisé dans le code:**
- `mission_manager.py:1477` - Parse les codes courts comme "4x PLG"
- `mission_manager.py:1796-1808` - Trouve les alternatives de véhicules
- `mission_manager.py:2600-2604` - Sélectionne le véhicule approprié

**Flux d'exécution:**
```
Alerte: "Il manque 3x PLG"
  ↓
Parse code "PLG" → mission_manager.py:1477
  ↓
Lookup dans personnel_mapping["PLG"]
  ↓
Résultat: vehicles = ["VPL"], priority = ["VPL"]
  ↓
Déploiement: 3x VPL
```

---

### 2. `other_needs_mapping` - Ressources & Besoins

**Usage:** Classifier les besoins non-véhicules détectés dans les alertes

**Exemple:**
```json
"water_sources": {
  "keywords": ["eau", "litre", "l", "water"],
  "exclusions": ["carburant", "essence", "diesel"],
  "type": "water_l",
  "description": "Besoins en eau pour extinction"
}
```

**Utilisé dans le code:**
- `mission_manager.py:1378-1401` - Détecte le type de besoin depuis le texte
- `mission_manager.py:2800-2820` - Suggère le type de besoin approprié

**Flux d'exécution:**
```
Alerte: "Il manque 5000 litres d'eau"
  ↓
Scan keywords: ["eau", "litre"] → mission_manager.py:1398
  ↓
Match avec "water_sources"
  ↓
Type identifié: "water_l"
  ↓
Calcul véhicule nécessaire (CCF(S), FMOGP, etc.)
```

---

### 3. `personnel_vehicle_mapping` - Personnel Générique

**Usage:** Mapper du personnel générique (pompiers, policiers) vers les véhicules standards

**Exemple:**
```json
"pompiers": {
  "vehicles": ["FPT", "FPT(SR)", "CCR(SR)", "CCF(M)", "CCF(S)", "FS", "VPC", "VTP(ers)", "VPI"],
  "priority": ["VTP(ers)", "FPT", "CCR(SR)", "CCF(M)", "FPT(SR)", "FS", "VPI"],
  "description": "Personnel pompier standard"
}
```

**Utilisé dans le code:**
- `mission_manager.py:1744-1780` - Calcule les véhicules pour personnel générique
- Convertit "20 pompiers" → véhicules appropriés selon capacité

**Flux d'exécution:**
```
Besoin: "20 pompiers requis"
  ↓
Lookup personnel_vehicle_mapping["pompiers"]
  ↓
Récupère vehicles et priority
  ↓
Calcule nombre de véhicules selon crew_size:
  - VTP(ers): 9 personnes → 3 véhicules
  - FPT: 6 personnes → 4 véhicules
  ↓
Sélection selon disponibilité et priorité
```

---

### 4. `deduplication_rules` - Éviter les Doublons

**Usage:** Empêcher le déploiement de types de véhicules redondants

**Exemple:**
```json
"FPT_SR": ["FPT", "VSR"]
```
Signifie: "Si FPT_SR est déployé, ignorer les besoins FPT et VSR séparés"

**Utilisé dans le code:**
- `requirement_parser.py` - Applique les règles lors du parsing
- Évite de déployer FPT + VSR quand FPT(SR) suffit

**Logique:**
```
Besoins détectés: FPT: 1, VSR: 1
  ↓
Check deduplication_rules
  ↓
FPT_SR peut remplacer FPT + VSR
  ↓
Résultat: FPT_SR: 1 (au lieu de FPT: 1 + VSR: 1)
```

---

### 5. `parsing_patterns` - Patterns Regex

**Usage:** Patterns pour extraire quantités et types depuis le texte des alertes

**Exemple:**
```json
"personnel_pattern": "(\\d+)x\\s+([A-Z][A-Z0-9]*)\\s*(?:\\([^)]+\\))?",
"water_pattern": "(\\d+)(?:\\s*&nbsp;|\\s+)l(?:\\s+d[\\'']?eau)?"
```

**Utilisé dans le code:**
- `mission_manager.py:1379-1395` - Parse les besoins en eau et personnel
- Extrait quantités depuis formats variés

**Exemples de parsing:**
```
"4x PLG" → personnel_pattern → quantité: 4, code: PLG
"5000 l d'eau" → water_pattern → quantité: 5000, type: eau
```

---

### 6. `vehicle_capacity_priorities` - Priorités de Capacité

**Usage:** Sélectionner les véhicules selon leur capacité en eau

**Exemple:**
```json
"water_vehicles": {
  "large_capacity": ["CCF(S)", "CCGC", "FMOGP"],      // > 10000L
  "medium_capacity": ["CEEM", "CCF(M)", "FPT"],       // 3000-10000L
  "small_capacity": ["VPI"],                          // < 3000L
  "bonus_vehicles": ["FDGP", "RLC"]                   // Pompes additionnelles
}
```

**Utilisé dans le code:**
- `missing_needs_parser.py:261-294` - Sélectionne véhicule selon besoin en eau
- Choix intelligent: besoin 15000L → CCF(S), besoin 4000L → FPT

---

## 🔄 Flux Complet d'Utilisation

```mermaid
graph TD
    A[Alerte Mission] --> B{Type de besoin}

    B -->|Personnel spécialisé<br/>"4x PLG"| C[personnel_mapping]
    B -->|Ressources<br/>"5000L eau"| D[other_needs_mapping]
    B -->|Personnel générique<br/>"20 pompiers"| E[personnel_vehicle_mapping]

    C --> F[Lookup PLG]
    F --> G[vehicles: VPL]
    G --> H[Déploiement: 4x VPL]

    D --> I[Match keywords: eau, litre]
    I --> J[type: water_l]
    J --> K[vehicle_capacity_priorities]
    K --> L[Sélection: CCF S pour 5000L]

    E --> M[Lookup pompiers]
    M --> N[Calcul capacité crew_size]
    N --> O[20 ÷ 9 = 3x VTP ers]

    H --> P{Vérifier doublons}
    L --> P
    O --> P

    P --> Q[deduplication_rules]
    Q --> R[Déploiement final]
```

---

## 📝 Exemples Concrets

### Exemple 1: Personnel Spécialisé

**Alerte:**
```
Il manque 2x GRI (GRIMP)
```

**Code exécuté:**
```python
# mission_manager.py:1477
personnel_code = "GRI"
personnel_mapping = config.get("personnel_mapping", {})
if "GRI" in personnel_mapping:
    # Récupère: vehicles = ["VIMP"], priority = ["VIMP"]
    vehicles_to_deploy = ["VIMP"] * 2
```

**Résultat:**
```
Déploiement: 2x VIMP
```

---

### Exemple 2: Besoins en Eau

**Alerte:**
```
Il manque 8000 litres d'eau
```

**Code exécuté:**
```python
# mission_manager.py:1378-1395
text = "Il manque 8000 litres d'eau"
other_needs_mapping = config.get("other_needs_mapping", {})

# Match avec water_sources.keywords: ["eau", "litre"]
water_pattern = r"(\d+) litres? d[''']eau"
match = re.search(water_pattern, text)
quantity = 8000

# missing_needs_parser.py:261-294
# Sélection véhicule selon capacité:
# - CCF(S): 14500L ✓
# - FMOGP: 12000L ✓
# - CCGC: 11000L ✓
# - CCF(M): 4000L ✗
# → Choix: CCF(M) (plus petit suffisant)
```

**Résultat:**
```
Déploiement: 1x CCF(M)
```

---

### Exemple 3: Personnel Générique

**Alerte:**
```
Personnel manquant: 15 pompiers
```

**Code exécuté:**
```python
# mission_manager.py:1744-1780
personnel_type = "pompiers"
quantity = 15

personnel_mapping = config.get("personnel_vehicle_mapping", {})
vehicles = personnel_mapping["pompiers"]["vehicles"]
# ["VTP(ers)", "FPT", "CCR(SR)", ...]

# Calcul selon crew_size:
# VTP(ers): 9 personnes → 15 ÷ 9 = 2 véhicules (reste 6)
# FPT: 6 personnes → 15 ÷ 6 = 3 véhicules (exact)
```

**Résultat:**
```
Option 1: 2x VTP(ers) (couvre 18 personnes)
Option 2: 3x FPT (couvre 18 personnes)
→ Sélection selon priorité: VTP(ers)
```

---

## 🛠️ Cas d'Usage dans le Code

### 1. `MissingNeedsParser` (services/missing_needs_parser.py)

```python
# Ligne 313-320: Utilise un mapping hardcodé (devrait utiliser missing_needs_config)
personnel_mapping = {
    'SPECIALIST_IMP': ('VIMP', ['VGRIMP']),
    'FIREFIGHTER': ('FPT', ['FS', 'CCF(M)', 'VPI']),
    'POLICE_OFFICER': ('PN', ['GN', 'VR']),
}
```

**⚠️ Problème:** Ce mapping est hardcodé et devrait utiliser `missing_needs_config.json`

---

### 2. `MissionManager` (core/mission_manager.py)

```python
# Ligne 1477-1480: Parse personnel spécialisé
personnel_mapping = self.missing_needs_config.get("personnel_mapping", {})
if personnel_code in personnel_mapping:
    personnel_needs[personnel_code] = quantity

# Ligne 1796-1808: Trouve alternatives pour personnel
personnel_mapping = config.get('personnel_mapping', {})
possible_vehicles = personnel_mapping[personnel_code].get('vehicles', [])
priority_vehicles = personnel_mapping[personnel_code].get('priority', [])

# Ligne 2600-2604: Convertit personnel en véhicules
personnel_mapping = self.missing_needs_config.get("personnel_mapping", {})
appropriate_vehicles = personnel_config.get("vehicles", [])
priority_vehicles = personnel_config.get("priority", appropriate_vehicles)
```

---

### 3. `RequirementParser` (models/requirement_parser.py)

```python
# Ligne 108: Charge le fichier
path = Path(__file__).parent.parent / "data" / "missing_needs_config.json"
with open(path, 'r', encoding='utf-8') as f:
    return json.load(f)
```

---

## ❌ Problèmes Détectés dans le Fichier Actuel

### 1. Références de Véhicules Incorrectes

**Problème:** Certains mappings référencent des types qui n'existent pas dans `vehicles_v2.json`

```json
❌ "CYN": {
  "vehicles": ["CARS_DROGUE"]  // N'existe pas dans vehicles_v2.json
}

✅ Solution:
"CYN": {
  "vehicles": ["Equipe"]  // Type correct
}
```

**Autres corrections nécessaires:**
```json
"MED": {
  "vehicles": ["VSAV", "SMUR(A)", "Dragon"]  // ← Pas "HELICOPTER"
}

"CHEF": {
  "vehicles": ["VPC", "VLHR"]  // ← Pas "CHEF_DE_GROUPE"
}
```

---

### 2. Incohérence avec vehicle_specs

**Problème:** Les véhicules référencés n'ont pas tous des specs dans `vehicles_v2.json`

**Impact:**
- Impossible de calculer crew_size
- Impossible d'optimiser les déploiements
- Risque de sur/sous-déploiement

**Solution:** Ajouter les specs dans `vehicles_v2.json:vehicle_specs`

---

## 🎯 Recommandations d'Amélioration

### 1. Synchroniser avec vehicles_v2.json

Tous les véhicules dans `personnel_mapping` doivent exister dans `vehicles_v2.json`

### 2. Remplacer les Mappings Hardcodés

Dans `missing_needs_parser.py:313`, remplacer le mapping hardcodé par:

```python
async def _find_personnel_vehicle_with_fallback(self, need_type: str, needed_quantity: int) -> Dict:
    """Trouve un véhicule pour besoins en personnel avec alternatives."""

    # Charger depuis missing_needs_config
    config = self.requirement_parser.missing_config
    personnel_vehicle_mapping = config.get('personnel_vehicle_mapping', {})

    # Mapping depuis besoins parsés → catégories
    need_to_category = {
        'SPECIALIST_IMP': 'medical',  # Ou personnel spécialisé
        'FIREFIGHTER': 'pompiers',
        'POLICE_OFFICER': 'policiers',
    }

    category = need_to_category.get(need_type, 'general')
    mapping = personnel_vehicle_mapping.get(category, {})

    return {
        'primary': mapping.get('priority', [])[0],
        'quantity': needed_quantity,
        'alternatives': mapping.get('vehicles', []),
        'need_type': need_type
    }
```

### 3. Ajouter Validation au Démarrage

```python
def validate_missing_needs_config():
    """Valide la cohérence du fichier avec vehicles_v2.json"""

    missing_config = load_json("missing_needs_config.json")
    vehicles_config = load_json("vehicles_v2.json")

    all_vehicle_types = set()
    for category in vehicles_config["vehicle_mapping"].values():
        for mapping in category.values():
            all_vehicle_types.update(mapping.get("primary", []))

    # Vérifier personnel_mapping
    for code, info in missing_config["personnel_mapping"].items():
        for vehicle in info["vehicles"]:
            if vehicle not in all_vehicle_types:
                logger.warning(f"Personnel {code} référence véhicule inconnu: {vehicle}")
```

---

## 📚 Résumé

| Section | Usage | Utilisé par |
|---------|-------|-------------|
| `personnel_mapping` | Codes courts (PLG, GRI) → véhicules | mission_manager.py |
| `other_needs_mapping` | Classification des besoins (eau, carburant) | mission_manager.py |
| `personnel_vehicle_mapping` | Personnel générique → véhicules | mission_manager.py |
| `deduplication_rules` | Éviter doublons de types | requirement_parser.py |
| `parsing_patterns` | Extraction quantités/types | mission_manager.py |
| `vehicle_capacity_priorities` | Sélection selon capacité | missing_needs_parser.py |

**Fichier essentiel pour:** Convertir les alertes textuelles en actions de déploiement concrètes ✅
