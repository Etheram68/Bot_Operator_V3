# Guide - Gestion des Véhicules Tracteurs et Remorques

## Vue d'ensemble

Le système de déploiement gère automatiquement les véhicules remorques qui nécessitent un tracteur pour être déployés. Si le tracteur d'une remorque n'est pas disponible, le véhicule est automatiquement ignoré et le système passe au suivant.

## Problématique

Certains véhicules dans Opérateur 112 sont des **remorques** (ex: CEEP, certains équipements spécialisés) qui ne peuvent pas être déployées seules. Elles nécessitent un **véhicule tracteur** pour les transporter.

### Cas problématique
- Mission nécessite 1x CEEP
- CEEP 1 disponible mais son tracteur est en mission
- Le système tentait de sélectionner CEEP 1 → **ÉCHEC DE DÉPLOIEMENT**

## Solution implémentée

### Détection automatique

Le bot vérifie maintenant **avant chaque sélection** si le véhicule tracteur est disponible en recherchant ce message d'erreur dans le DOM :

```html
<small class="text-danger vehicle_not_tractive_message_8912132" style="display: inline;">
    Véhicule tracteur non disponible
</small>
```

### Logique de vérification

```python
async def _check_tractor_availability(self, vehicle_row) -> bool:
    """
    Vérifie si le véhicule tracteur est disponible pour une remorque.
    
    Returns:
        bool: True si disponible, False si tracteur occupé
    """
    # Chercher le message d'erreur
    error_message = await vehicle_row.query_selector(
        'small.text-danger[class*="vehicle_not_tractive_message"]'
    )
    
    if error_message:
        # Vérifier si le message est affiché
        style = await error_message.get_attribute('style')
        if style and 'display: inline' in style:
            return False  # Tracteur non disponible
            
        is_visible = await error_message.is_visible()
        if is_visible:
            return False  # Tracteur non disponible
    
    return True  # Tracteur disponible ou véhicule normal
```

## Impact sur le déploiement

### Avant l'amélioration ❌
```
Mission nécessite: 1x CEEP
Véhicules trouvés:
  - CEEP 1 Brunstatt (tracteur occupé) → SÉLECTIONNÉ → ÉCHEC
```

### Après l'amélioration ✅
```
Mission nécessite: 1x CEEP
Véhicules trouvés:
  - CEEP 1 Brunstatt (tracteur occupé) → IGNORÉ
  - CEEP 2 Mulhouse (tracteur libre) → SÉLECTIONNÉ → SUCCÈS
```

## Types de véhicules concernés

Les véhicules suivants sont susceptibles d'être des remorques :

- **CEEP** - Cellule d'Épuisement d'Eau Pompe
- **Remorques équipement** - Matériels spécialisés
- **Remorques de désincarcération**
- **Autres équipements tractés**

## Messages de log

### Véhicule ignoré (tracteur occupé)
```
⚠️  CEEP 1 Brunstatt ignoré: Véhicule tracteur non disponible
```

### Véhicule sélectionné normalement
```
✅ Sélectionné: CEEP 2 Mulhouse -> Type: CEEP (pour MOTOPOMPES)
```

## Gestion des erreurs

En cas d'erreur lors de la vérification du tracteur :
- Le système **suppose que le véhicule est disponible** (principe de précaution)
- Un log de debug est généré
- La sélection continue normalement

```python
except Exception as e:
    logger.debug(f"Erreur lors de la vérification du tracteur: {e}")
    # Par sécurité, considérer le véhicule comme disponible
    return True
```

## Test et validation

### Script de test disponible
```bash
python test_tractor_availability.py
```

Ce script valide :
- ✅ Détection des véhicules normaux
- ✅ Détection des remorques avec tracteur libre
- ✅ Détection des remorques avec tracteur occupé
- ✅ Gestion des erreurs

### Validation manuelle

Surveillez les logs lors des déploiements :

1. **Messages d'ignorance** (`⚠️  ... ignoré: Véhicule tracteur non disponible`)
2. **Sélections réussies** avec véhicules alternatifs
3. **Absence d'échecs de déploiement** liés aux tracteurs

## Intégration avec le système de fallback

Cette vérification est intégrée avec le système de fallback par capacité :

1. **Calcul des besoins** → Ex: 1x CEEP nécessaire
2. **Recherche des véhicules** → Trouve CEEP 1, CEEP 2, CEEP 3
3. **Vérification tracteur** → CEEP 1 ignoré (tracteur occupé)
4. **Sélection alternative** → CEEP 2 sélectionné (tracteur libre)
5. **Fallback capacité** → Si aucun CEEP disponible → recherche FDGP, etc.

## Maintenance

### Mise à jour des sélecteurs CSS

Si l'interface d'Opérateur 112 change, mettre à jour le sélecteur dans `_check_tractor_availability()` :

```python
# Sélecteur actuel
'small.text-danger[class*="vehicle_not_tractive_message"]'

# Exemple de mise à jour si nécessaire
'div.vehicle-error[data-error="no-tractor"]'
```

### Nouveaux types de remorques

Aucune modification nécessaire : le système détecte automatiquement **tous** les véhicules avec message d'erreur tracteur, peu importe leur type.