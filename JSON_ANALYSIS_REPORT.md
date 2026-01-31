# Rapport d'Analyse des Fichiers JSON de Configuration

**Date:** 2025-10-30
**Statut:** ❌ Corrections nécessaires
**Fichiers analysés:** 4

---

## 📊 Vue d'Ensemble

| Métrique | Valeur |
|----------|--------|
| Types de besoins définis | 80 |
| Mappings de véhicules | 88 |
| Véhicules uniques référencés | 68 |
| Véhicules avec specs | 23 |
| Types de personnel | 11 |
| Règles de déduplication | 10 |
| Seuils de probabilité | 11 |
| Patterns regex | 211 |

---

## ❌ ERREURS CRITIQUES (1)

### 1. Types de besoins sans mapping dans vehicles_v2.json

Les types suivants sont définis dans `needs_labels_v2.json` mais n'ont pas de mapping correspondant dans `vehicles_v2.json`:

- **INTENSIVE_CARE** - Soins intensifs
- **BURN_UNIT** - Unité grands brûlés
- **PEDIATRIC** - Pédiatrie
- **WATER_REQUIRED** - Besoins en eau
- **MIN_PUMP_CAPACITY** - Capacité minimum de pompe

#### 🔧 Recommandation
Ces types sont soit:
1. Des indicateurs qui ne nécessitent pas de véhicules spécifiques (WATER_REQUIRED, MIN_PUMP_CAPACITY)
2. Des types médicaux spécialisés qui devraient rediriger vers des véhicules existants (INTENSIVE_CARE, BURN_UNIT, PEDIATRIC)

**Action recommandée:**
```json
// À ajouter dans vehicles_v2.json sous "medical":
"INTENSIVE_CARE": {
  "primary": ["SMUR(A)", "HeliSMUR"],
  "secondary": ["VSAV"]
},
"BURN_UNIT": {
  "primary": ["SMUR(A)", "HeliSMUR"],
  "secondary": ["VSAV"]
},
"PEDIATRIC": {
  "primary": ["VSAV", "SMUR(A)"],
  "secondary": []
}
```

Pour WATER_REQUIRED et MIN_PUMP_CAPACITY, ces types sont des **resource_indicators** et non des types de véhicules. Ils peuvent rester sans mapping.

---

## ⚠️ AVERTISSEMENTS (4)

### 1. Véhicules référencés sans specs détaillées (36 véhicules)

Les véhicules suivants sont utilisés dans `vehicle_mapping` mais n'ont pas de spécifications dans `vehicle_specs`:

**Véhicules médicaux:**
- ASSU, VSAV, SMUR(A), PC

**Véhicules incendie:**
- BEA, EPA, VSR, VIM, MAH

**Véhicules spécialisés:**
- CEAR, CEDEPOL, CEDEV, CEFSP, CENOVI, CEPC, CEREV, CESR, CETRAN, CMIC, CMIR, VAR, VLHR, VLCM, VIRP

**Véhicules police:**
- VCT, RAM, VAT, VR, ReBP, ELE, RMV, RMP, VB, VIC, ERI

#### 🔧 Recommandation
Ajouter les specs pour les véhicules les plus fréquemment utilisés:

```json
// À ajouter dans vehicle_specs:
"VSAV": {
  "crew_size": 3
},
"ASSU": {
  "crew_size": 2
},
"SMUR(A)": {
  "crew_size": 3
},
"VSR": {
  "crew_size": 4
},
"BEA": {
  "crew_size": 3
},
"VR": {
  "crew_size": 6
},
"VLHR": {
  "crew_size": 2
}
```

**Impact:** Ces véhicules fonctionnent actuellement, mais l'absence de specs empêche:
- Le calcul précis du personnel disponible
- L'optimisation des déploiements
- La gestion des capacités en eau/pompe

---

### 2. Véhicules dans personnel_mapping non trouvés (3 références)

Certaines références dans `missing_needs_config.json` pointent vers des types qui ne sont pas définis dans le mapping:

- **CYN** (Cynophile) → **CARS_DROGUE** ❌ (devrait être "Equipe")
- **MED** (Médecin) → **HELICOPTER** ❌ (devrait être "Dragon" ou "HeliSMUR")
- **CHEF** (Chef d'intervention) → **CHEF_DE_GROUPE** ❌ (devrait être "VPC")

#### 🔧 Recommandation
Corriger dans `missing_needs_config.json`:

```json
"CYN": {
  "name": "Cynophile",
  "vehicles": ["Equipe"],  // ← Correction
  "priority": ["Equipe"],
  "description": "Unité cynophile (maître-chien)"
},
"MED": {
  "name": "Médecin",
  "vehicles": ["VSAV", "SMUR(A)", "Dragon"],  // ← Correction
  "priority": ["SMUR(A)", "VSAV", "Dragon"],
  "description": "Médecin urgentiste"
},
"CHEF": {
  "name": "Chef d'intervention",
  "vehicles": ["VPC", "VLHR"],  // ← Correction
  "priority": ["VPC", "VLHR"],
  "description": "Chef d'intervention ou responsable secteur"
}
```

---

### 3. Conflits dans deduplication_rules (6 conflits)

Certains types de véhicules apparaissent dans plusieurs règles de déduplication:

```
- FPT apparaît dans 'FPT_SR' et 'FPT_BEA'
- FPT apparaît dans 'FPT_SR' et 'FPT_SR_BEA'
- VSR apparaît dans 'FPT_SR' et 'FPT_SR_BEA'
- BEA apparaît dans 'FPT_BEA' et 'FPT_SR_BEA'
- CARS_POLICE apparaît dans 'CARS_POLICE_VR' et 'CARS_POLICE_PATROUILLE_VR'
- VR_CRS apparaît dans 'CARS_POLICE_VR' et 'CARS_POLICE_PATROUILLE_VR'
```

#### 🔧 Recommandation
Ces conflits sont **acceptables** car ils représentent des hiérarchies de déduplications:
- `FPT_SR_BEA` déduplique `FPT_SR` qui lui-même déduplique `FPT`
- `CARS_POLICE_PATROUILLE_VR` déduplique `CARS_POLICE_VR` qui déduplique `CARS_POLICE`

**Aucune action requise** - Ces conflits sont intentionnels pour gérer les combinaisons de véhicules.

---

### 4. Types contraints sans version non-contrainte (8 types)

Les types suivants existent en version `_CONSTRAINED` mais pas en version de base:

- CCF(M)_CONSTRAINED ❌ pas de CCF(M)
- CCF(S)_CONSTRAINED ❌ pas de CCF(S)
- CCGC_CONSTRAINED ❌ pas de CCGC
- VPI_CONSTRAINED ❌ pas de VPI
- FS_CONSTRAINED ❌ pas de FS
- VTP(ers)_CONSTRAINED ❌ pas de VTP(ers)
- GN_CONSTRAINED ❌ pas de GN
- VR_CONSTRAINED ❌ pas de VR

#### 🔧 Recommandation
Ces types sont utilisés dans des groupes (CCF, FPT, CARS_POLICE) donc la version de base n'est pas nécessaire.

**Exemple:** `CCF(M)` et `CCF(S)` sont tous deux dans le groupe `CCF`, donc pas besoin d'un mapping `CCF(M)` individuel.

**Aucune action requise** - Le système utilise les groupes correctement.

---

## ✅ Points Validés

1. ✅ **Syntaxe JSON valide** - Tous les fichiers sont syntaxiquement corrects
2. ✅ **Patterns regex valides** - 211 patterns testés, aucune erreur
3. ✅ **Probability thresholds cohérents** - 11 seuils avec indicateurs correspondants
4. ✅ **Fallback strategy cohérente** - 3 stratégies de repli définies correctement

---

## 🎯 Plan d'Action Prioritaire

### Priorité 1 - CRITIQUE (Bloquant)
1. ✅ Ajouter mappings pour INTENSIVE_CARE, BURN_UNIT, PEDIATRIC dans vehicles_v2.json

### Priorité 2 - HAUTE (Recommandé)
2. ✅ Corriger les références dans personnel_mapping (CYN, MED, CHEF)
3. ✅ Ajouter specs pour véhicules fréquents (VSAV, ASSU, SMUR(A), VSR, BEA)

### Priorité 3 - MOYENNE (Amélioration)
4. ⚠️ Documenter les types WATER_REQUIRED et MIN_PUMP_CAPACITY comme resource_indicators
5. ⚠️ Ajouter specs pour véhicules spécialisés (VR, VLHR, etc.)

### Priorité 4 - BASSE (Optionnel)
6. ℹ️ Documenter les conflits de déduplication intentionnels
7. ℹ️ Ajouter commentaires pour les types _CONSTRAINED

---

## 📋 Résumé Exécutif

**État actuel:** Les fichiers JSON sont **utilisables** mais nécessitent des corrections pour être **complètement fonctionnels**.

**Impact des problèmes:**
- ❌ **5 types de missions** ne pourront pas être déployés automatiquement (soins intensifs, brûlés, pédiatrie)
- ⚠️ **36 véhicules** fonctionnent sans optimisation de personnel
- ⚠️ **3 types de personnel** peuvent être mal assignés

**Temps estimé de correction:** 15-30 minutes

**Recommandation finale:** Corriger les erreurs de Priorité 1 et 2 avant utilisation en production.

---

## 🛠️ Script de Test

Pour re-vérifier après corrections:
```bash
python3 analyze_json_conflicts.py
```

Le script retournera `exit 0` si tout est correct.
