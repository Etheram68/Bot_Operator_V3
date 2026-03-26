#!/usr/bin/env python3
"""
Serveur API Flask pour gérer les actions Docker depuis l'interface de monitoring
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import subprocess
import json
import logging
import os

app = Flask(__name__)
CORS(app)  # Permettre les requêtes depuis nginx

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

CONTAINER_NAME = "bot-operateur-112"

def run_docker_command(command):
    """Exécute une commande Docker et retourne le résultat"""
    try:
        logger.info(f"Exécution de la commande: {' '.join(command)}")
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            logger.info(f"Commande réussie: {result.stdout}")
            return True, result.stdout
        else:
            logger.error(f"Commande échouée: {result.stderr}")
            return False, result.stderr
    except subprocess.TimeoutExpired:
        logger.error("Timeout lors de l'exécution de la commande")
        return False, "Timeout: la commande a pris trop de temps"
    except Exception as e:
        logger.error(f"Erreur lors de l'exécution: {str(e)}")
        return False, str(e)

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({"status": "ok", "service": "bot-monitoring-api"}), 200

@app.route('/api/container/restart', methods=['POST'])
def restart_container():
    """Redémarre le container du bot"""
    logger.info(f"Demande de redémarrage du container {CONTAINER_NAME}")

    success, output = run_docker_command(['docker', 'restart', CONTAINER_NAME])

    if success:
        return jsonify({
            "success": True,
            "message": f"Container {CONTAINER_NAME} redémarré avec succès",
            "output": output.strip()
        }), 200
    else:
        return jsonify({
            "success": False,
            "error": "Erreur lors du redémarrage",
            "details": output
        }), 500

@app.route('/api/container/stop', methods=['POST'])
def stop_container():
    """Arrête le container du bot"""
    logger.info(f"Demande d'arrêt du container {CONTAINER_NAME}")

    success, output = run_docker_command(['docker', 'stop', CONTAINER_NAME])

    if success:
        return jsonify({
            "success": True,
            "message": f"Container {CONTAINER_NAME} arrêté avec succès",
            "output": output.strip()
        }), 200
    else:
        return jsonify({
            "success": False,
            "error": "Erreur lors de l'arrêt",
            "details": output
        }), 500

@app.route('/api/container/start', methods=['POST'])
def start_container():
    """Démarre le container du bot"""
    logger.info(f"Demande de démarrage du container {CONTAINER_NAME}")

    success, output = run_docker_command(['docker', 'start', CONTAINER_NAME])

    if success:
        return jsonify({
            "success": True,
            "message": f"Container {CONTAINER_NAME} démarré avec succès",
            "output": output.strip()
        }), 200
    else:
        return jsonify({
            "success": False,
            "error": "Erreur lors du démarrage",
            "details": output
        }), 500

@app.route('/api/container/clear-cache', methods=['POST'])
def clear_cache():
    """Vide le cache du bot"""
    logger.info(f"Demande de vidage du cache pour {CONTAINER_NAME}")

    # Exécuter la commande pour vider le cache
    success, output = run_docker_command([
        'docker', 'exec', CONTAINER_NAME,
        'sh', '-c', 'rm -rf /tmp/browser_cache/* /app/cache/* 2>/dev/null || true'
    ])

    if success:
        return jsonify({
            "success": True,
            "message": "Cache vidé avec succès",
            "output": output.strip()
        }), 200
    else:
        return jsonify({
            "success": False,
            "error": "Erreur lors du vidage du cache",
            "details": output
        }), 500

@app.route('/api/container/debug', methods=['GET', 'POST'])
def debug_mode():
    """Gère le mode debug (lecture seule pour l'instant)"""
    if request.method == 'GET':
        # Vérifier le niveau de log actuel
        success, output = run_docker_command([
            'docker', 'inspect', CONTAINER_NAME,
            '--format', '{{range .Config.Env}}{{println .}}{{end}}'
        ])

        if success:
            log_level = "INFO"
            for line in output.split('\n'):
                if line.startswith('LOG_LEVEL='):
                    log_level = line.split('=')[1]
                    break

            return jsonify({
                "success": True,
                "debug_mode": log_level == "DEBUG",
                "log_level": log_level
            }), 200
        else:
            return jsonify({
                "success": False,
                "error": "Impossible de lire le mode debug"
            }), 500

    # POST: Informe que le changement nécessite une modification docker-compose
    return jsonify({
        "success": False,
        "message": "Le mode debug nécessite une modification de docker-compose.yml",
        "instruction": "Éditez LOG_LEVEL dans le fichier .env ou docker-compose.yml puis redémarrez"
    }), 501

@app.route('/api/container/logs-stream', methods=['GET'])
def logs_stream():
    """Retourne les derniers logs en streaming"""
    try:
        # Récupérer les 200 dernières lignes de logs
        success, output = run_docker_command([
            'docker', 'logs', '--tail', '200', CONTAINER_NAME
        ])

        if success:
            return jsonify({
                "success": True,
                "logs": output
            }), 200
        else:
            return jsonify({
                "success": False,
                "error": output
            }), 500
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

RUNTIME_CONFIG_PATH = "/app/bot_operateur/data/runtime_config.json"
ALL_MISSION_TYPES = ["normal", "transport", "security", "alliance", "alliance_event"]
VALID_MISSION_SORTS = ["importance_desc", "created_at_asc", "created_at_desc", "credits_asc", "credits_desc"]

@app.route('/api/runtime-config', methods=['GET'])
def get_runtime_config():
    """Lit la configuration runtime depuis le container du bot"""
    logger.info("Lecture de la configuration runtime")

    success, output = run_docker_command([
        'docker', 'exec', CONTAINER_NAME,
        'cat', RUNTIME_CONFIG_PATH
    ])

    if success:
        try:
            config = json.loads(output)
            # S'assurer que tous les champs sont présents
            config.setdefault("enabled_mission_types", ALL_MISSION_TYPES)
            config.setdefault("max_missions", 5)
            config.setdefault("mission_sort", "importance_desc")
            config.setdefault("min_credits_threshold", None)
            config.setdefault("optimization_threshold", None)
            config.setdefault("deployment_threshold", None)
            config.setdefault("personnel_threshold", None)
            return jsonify({"success": True, "config": config}), 200
        except json.JSONDecodeError:
            return jsonify({
                "success": False,
                "error": "Fichier de configuration invalide"
            }), 500
    else:
        # Retourner les valeurs par défaut si le fichier n'existe pas
        return jsonify({
            "success": True,
            "config": {
                "enabled_mission_types": ALL_MISSION_TYPES,
                "max_missions": 5,
                "mission_sort": "importance_desc",
                "min_credits_threshold": None,
                "optimization_threshold": None,
                "deployment_threshold": None,
                "personnel_threshold": None
            },
            "default": True
        }), 200

@app.route('/api/runtime-config', methods=['POST'])
def update_runtime_config():
    """Met à jour la configuration runtime dans le container du bot"""
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "Données JSON requises"}), 400

    logger.info(f"Mise à jour de la configuration runtime: {data}")

    # Valider les types de missions
    enabled_types = data.get("enabled_mission_types", ALL_MISSION_TYPES)
    invalid_types = [t for t in enabled_types if t not in ALL_MISSION_TYPES]
    if invalid_types:
        return jsonify({
            "success": False,
            "error": f"Types de mission invalides: {invalid_types}"
        }), 400

    # Valider max_missions
    max_missions = data.get("max_missions", 5)
    if not isinstance(max_missions, int) or max_missions < 1 or max_missions > 200:
        return jsonify({
            "success": False,
            "error": "max_missions doit être un entier entre 1 et 200"
        }), 400

    # Valider mission_sort
    mission_sort = data.get("mission_sort", "importance_desc")
    if mission_sort not in VALID_MISSION_SORTS:
        return jsonify({
            "success": False,
            "error": f"Tri invalide: {mission_sort}. Valeurs acceptées: {VALID_MISSION_SORTS}"
        }), 400

    # Valider les thresholds (null = utiliser valeur .env)
    THRESHOLD_LIMITS = {
        "min_credits_threshold": (0, 100000),
        "optimization_threshold": (1, 20),
        "deployment_threshold": (1, 50),
        "personnel_threshold": (1, 20),
    }
    thresholds = {}
    for key, (lo, hi) in THRESHOLD_LIMITS.items():
        val = data.get(key)
        if val is not None:
            if not isinstance(val, int) or val < lo or val > hi:
                return jsonify({
                    "success": False,
                    "error": f"{key} doit être un entier entre {lo} et {hi} (ou null pour valeur .env)"
                }), 400
        thresholds[key] = val

    config = {
        "enabled_mission_types": enabled_types,
        "max_missions": max_missions,
        "mission_sort": mission_sort,
        **thresholds
    }

    config_json = json.dumps(config, ensure_ascii=False)

    # Écrire via docker exec + python pour un JSON propre sans problème d'échappement
    python_write = (
        f"import json; "
        f"json.dump(json.loads('{config_json}'), "
        f"open('{RUNTIME_CONFIG_PATH}', 'w'), indent=2, ensure_ascii=False); "
        f"print('ok')"
    )
    success, output = run_docker_command([
        'docker', 'exec', CONTAINER_NAME,
        'python', '-c', python_write
    ])

    if success:
        return jsonify({
            "success": True,
            "message": "Configuration mise à jour (prise en compte au prochain cycle)",
            "config": config
        }), 200
    else:
        return jsonify({
            "success": False,
            "error": "Erreur lors de l'écriture de la configuration",
            "details": output
        }), 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "success": False,
        "error": "Endpoint non trouvé"
    }), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        "success": False,
        "error": "Erreur interne du serveur"
    }), 500

if __name__ == '__main__':
    # Écouter sur le port 5000 (accessible seulement depuis le réseau Docker)
    logger.info("Démarrage du serveur API Flask sur le port 5000")
    app.run(host='0.0.0.0', port=5000, debug=False)
