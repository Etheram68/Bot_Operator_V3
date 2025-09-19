import sys
from loguru import logger
from ..config.settings import Settings


def setup_logger(settings: Settings) -> None:
    """Configure le système de logging"""

    # Supprimer le handler par défaut
    logger.remove()

    # Créer le dossier logs si nécessaire
    from pathlib import Path
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)

    # Configuration de base
    log_config = settings.get_log_config()

    # Handler pour la console
    logger.add(
        sys.stdout,
        level=log_config["level"],
        format=log_config["format"],
        backtrace=log_config["backtrace"],
        diagnose=log_config["diagnose"],
        colorize=True
    )

    # Handler pour le fichier si spécifié
    if settings.log_file:
        # S'assurer que le fichier de log est dans le dossier logs/
        log_file_path = settings.log_file
        if not log_file_path.startswith("logs/"):
            log_file_path = f"logs/{log_file_path}"

        logger.add(
            log_file_path,
            level=log_config["level"],
            format=log_config["format"],
            backtrace=log_config["backtrace"],
            diagnose=log_config["diagnose"],
            rotation="10 MB",        # Rotation à 10MB
            retention="7 days",      # Garder 7 jours d'historique
            compression="zip"        # Compression ZIP remise en place
        )
    
    logger.info(f"Logger configuré - Niveau: {log_config['level']}")
    if settings.log_file:
        logger.info(f"Logs sauvegardés dans: {settings.log_file}")


def get_logger(name: str = None):
    """Retourne un logger avec un nom spécifique"""
    if name:
        return logger.bind(name=name)
    return logger