#!/usr/bin/env python3
"""
Script d'analyse des conflits et de la cohérence des fichiers JSON de configuration
"""
import json
import re
from collections import defaultdict
from pathlib import Path

def load_json(filepath):
    """Charge un fichier JSON"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def main():
    # Chargement des fichiers
    needs_labels = load_json('bot_operateur/data/needs_labels_v2.json')
    vehicles = load_json('bot_operateur/data/vehicles_v2.json')
    missing_needs = load_json('bot_operateur/data/missing_needs_config.json')

    print("=" * 80)
    print("ANALYSE DES CONFLITS ET COHÉRENCE DES FICHIERS JSON")
    print("=" * 80)

    errors = []
    warnings = []

    # 1. Vérifier que tous les besoins dans needs_labels ont un mapping dans vehicles
    print("\n[1] Vérification des mappings needs_labels -> vehicles")
    print("-" * 80)

    vehicle_requirements = needs_labels.get('vehicle_requirements', {})
    all_vehicle_mappings = {}

    for category in ['fire_rescue', 'medical', 'specialized', 'water_rescue', 'police', 'crs_specialized', 'civil_security', 'combined_requirements']:
        if category in vehicles.get('vehicle_mapping', {}):
            all_vehicle_mappings.update(vehicles['vehicle_mapping'][category])

    missing_mappings = []
    for need_type in vehicle_requirements.keys():
        if need_type.endswith('_PROBABILITY'):
            continue  # Les probabilités n'ont pas besoin de mapping

        if need_type not in all_vehicle_mappings:
            missing_mappings.append(need_type)

    if missing_mappings:
        errors.append(f"Types de besoins sans mapping dans vehicles_v2.json: {', '.join(missing_mappings)}")
        print(f"✗ ERREUR: {len(missing_mappings)} types sans mapping")
        for m in missing_mappings:
            print(f"  - {m}")
    else:
        print(f"✓ Tous les types de besoins ont un mapping dans vehicles_v2.json")

    # 2. Vérifier les véhicules référencés dans vehicles qui n'existent pas dans vehicle_specs
    print("\n[2] Vérification de la cohérence des véhicules dans vehicle_mapping")
    print("-" * 80)

    vehicle_specs = vehicles.get('vehicle_specs', {})
    referenced_vehicles = set()

    for category, mappings in vehicles.get('vehicle_mapping', {}).items():
        for need_type, config in mappings.items():
            if isinstance(config, dict):
                for veh in config.get('primary', []):
                    referenced_vehicles.add(veh)
                for veh in config.get('secondary', []):
                    referenced_vehicles.add(veh)

    # Véhicules qui n'ont pas besoin de specs (véhicules spéciaux ou externes)
    special_vehicles = {'Equipe', 'HeliSMUR', 'Dragon', 'Choucas', 'Pélican', 'Dash', 'HBE', 'Ambulance', 'CSL'}

    undefined_vehicles = []
    for veh in referenced_vehicles:
        if veh not in vehicle_specs and veh not in special_vehicles:
            undefined_vehicles.append(veh)

    if undefined_vehicles:
        warnings.append(f"Véhicules référencés sans specs: {', '.join(sorted(undefined_vehicles)[:10])}")
        print(f"⚠ AVERTISSEMENT: {len(undefined_vehicles)} véhicules sans specs détaillées")
        print(f"  Note: Ces véhicules peuvent fonctionner sans specs, mais il est recommandé de les définir")
        for v in sorted(undefined_vehicles)[:10]:
            print(f"  - {v}")
        if len(undefined_vehicles) > 10:
            print(f"  ... et {len(undefined_vehicles) - 10} autres")
    else:
        print(f"✓ Tous les véhicules ont des specs définies")

    # 3. Vérifier les patterns regex dans needs_labels
    print("\n[3] Vérification des patterns regex dans needs_labels_v2.json")
    print("-" * 80)

    regex_errors = []
    for need_type, patterns in vehicle_requirements.items():
        for pattern in patterns:
            try:
                re.compile(pattern)
            except re.error as e:
                regex_errors.append(f"{need_type}: '{pattern}' - {e}")

    if regex_errors:
        errors.append("Erreurs dans les patterns regex")
        print(f"✗ ERREUR: {len(regex_errors)} patterns regex invalides")
        for err in regex_errors[:5]:
            print(f"  - {err}")
    else:
        print(f"✓ Tous les patterns regex sont valides ({len(vehicle_requirements)} types, {sum(len(p) for p in vehicle_requirements.values())} patterns)")

    # 4. Vérifier la cohérence personnel_mapping vs vehicle_mapping
    print("\n[4] Vérification personnel_mapping dans missing_needs_config")
    print("-" * 80)

    personnel_mapping = missing_needs.get('personnel_mapping', {})
    personnel_issues = []

    for personnel_type, config in personnel_mapping.items():
        # Ignorer les champs de métadonnées
        if personnel_type.startswith('_') or not isinstance(config, dict):
            continue

        for veh in config.get('vehicles', []):
            # Vérifier que ces véhicules sont bien définis quelque part
            found = veh in referenced_vehicles or veh in special_vehicles

            if not found:
                personnel_issues.append(f"{personnel_type} -> {veh}")

    if personnel_issues:
        warnings.append(f"Véhicules dans personnel_mapping non trouvés dans vehicle_mapping")
        print(f"⚠ AVERTISSEMENT: {len(personnel_issues)} références potentiellement manquantes")
        for issue in personnel_issues:
            print(f"  - {issue}")
    else:
        print(f"✓ Cohérence entre personnel_mapping et vehicle_mapping ({len(personnel_mapping)} types de personnel)")

    # 5. Vérifier les doublons dans deduplication_rules
    print("\n[5] Vérification deduplication_rules")
    print("-" * 80)

    dedup_rules = missing_needs.get('deduplication_rules', {})
    all_deduplicated = {}
    conflicts = []

    for main_type, duplicates in dedup_rules.items():
        # Ignorer les métadonnées
        if main_type.startswith('_') or not isinstance(duplicates, list):
            continue

        for dup in duplicates:
            if dup in all_deduplicated:
                conflicts.append(f"{dup} apparaît dans '{all_deduplicated[dup]}' et '{main_type}'")
            else:
                all_deduplicated[dup] = main_type

    if conflicts:
        warnings.append("Conflits dans deduplication_rules")
        print(f"⚠ AVERTISSEMENT: {len(conflicts)} conflits de déduplication")
        for c in conflicts:
            print(f"  - {c}")
    else:
        print(f"✓ Pas de conflits dans les règles de déduplication ({len([k for k in dedup_rules.keys() if not k.startswith('_')])} règles)")

    # 6. Vérifier probability_thresholds
    print("\n[6] Vérification probability_thresholds")
    print("-" * 80)

    prob_thresholds = needs_labels.get('probability_thresholds', {})
    prob_indicators = needs_labels.get('resource_indicators', {})

    threshold_issues = []
    for prob_key in prob_thresholds.keys():
        if prob_key not in prob_indicators:
            threshold_issues.append(prob_key)

    if threshold_issues:
        warnings.append(f"Seuils de probabilité sans indicateur correspondant")
        print(f"⚠ AVERTISSEMENT: {len(threshold_issues)} seuils sans indicateur")
        for ti in threshold_issues:
            print(f"  - {ti}")
    else:
        print(f"✓ Tous les seuils ont un indicateur correspondant ({len(prob_thresholds)} seuils)")

    # 7. Vérifier la cohérence des véhicules _CONSTRAINED
    print("\n[7] Vérification des véhicules avec contraintes (_CONSTRAINED)")
    print("-" * 80)

    constrained_types = [k for k in all_vehicle_mappings.keys() if k.endswith('_CONSTRAINED')]
    non_constrained_missing = []

    for const_type in constrained_types:
        base_type = const_type.replace('_CONSTRAINED', '')
        if base_type not in all_vehicle_mappings:
            non_constrained_missing.append(f"{const_type} existe mais pas {base_type}")

    if non_constrained_missing:
        warnings.append("Types contraints sans version non-contrainte")
        print(f"⚠ AVERTISSEMENT: {len(non_constrained_missing)} types contraints sans base")
        for nm in non_constrained_missing:
            print(f"  - {nm}")
    else:
        print(f"✓ Tous les types contraints ont une version de base ({len(constrained_types)} types contraints)")

    # 8. Vérifier les alternatives de fallback
    print("\n[8] Vérification fallback_strategy")
    print("-" * 80)

    fallback_strategy = vehicles.get('fallback_strategy', {})
    fallback_issues = []

    for fallback_type, config in fallback_strategy.items():
        # Vérifier que les véhicules dans priority_order existent
        for veh in config.get('priority_order', []):
            if veh not in referenced_vehicles and veh not in special_vehicles and veh not in vehicle_specs:
                fallback_issues.append(f"{fallback_type}: véhicule '{veh}' non trouvé")

    if fallback_issues:
        warnings.append("Problèmes dans fallback_strategy")
        print(f"⚠ AVERTISSEMENT: {len(fallback_issues)} problèmes de fallback")
        for fi in fallback_issues:
            print(f"  - {fi}")
    else:
        print(f"✓ Stratégies de fallback cohérentes ({len(fallback_strategy)} stratégies)")

    # 9. Statistiques générales
    print("\n[9] Statistiques générales")
    print("-" * 80)

    print(f"📊 Statistiques:")
    print(f"  • Types de besoins définis: {len(vehicle_requirements)}")
    print(f"  • Mappings de véhicules: {len(all_vehicle_mappings)}")
    print(f"  • Véhicules uniques référencés: {len(referenced_vehicles)}")
    print(f"  • Véhicules avec specs: {len(vehicle_specs)}")
    print(f"  • Types de personnel: {len(personnel_mapping)}")
    print(f"  • Règles de déduplication: {len(dedup_rules)}")
    print(f"  • Seuils de probabilité: {len(prob_thresholds)}")

    # RÉSUMÉ FINAL
    print("\n" + "=" * 80)
    print("RÉSUMÉ DE L'ANALYSE")
    print("=" * 80)

    if errors:
        print(f"\n❌ ERREURS CRITIQUES ({len(errors)}):")
        for i, err in enumerate(errors, 1):
            print(f"  {i}. {err}")
    else:
        print("\n✅ Aucune erreur critique détectée")

    if warnings:
        print(f"\n⚠️  AVERTISSEMENTS ({len(warnings)}):")
        for i, warn in enumerate(warnings, 1):
            print(f"  {i}. {warn}")
    else:
        print("\n✅ Aucun avertissement")

    print("\n" + "=" * 80)
    if not errors:
        print("✅ LES FICHIERS JSON SONT COHÉRENTS ET PEUVENT ÊTRE UTILISÉS")
        if warnings:
            print("   Note: Les avertissements ne bloquent pas l'utilisation mais devraient être examinés")
    else:
        print("⚠️  DES CORRECTIONS SONT NÉCESSAIRES AVANT UTILISATION")
    print("=" * 80)

    return len(errors) == 0

if __name__ == '__main__':
    import sys
    success = main()
    sys.exit(0 if success else 1)
