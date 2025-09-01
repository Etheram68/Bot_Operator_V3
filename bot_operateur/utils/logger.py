import sys
from loguru import logger
from ..config.settings import Settings


def setup_logger(settings: Settings) -> None:
    """Configure le système de logging"""
    
    # Supprimer le handler par défaut
    logger.remove()
    
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
        logger.add(
            settings.log_file,
            level=log_config["level"],
            format=log_config["format"],
            backtrace=log_config["backtrace"],
            diagnose=log_config["diagnose"],
            rotation=log_config.get("rotation", "10 MB"),
            retention=log_config.get("retention", "7 days"),
            compression="zip"
        )
    
    logger.info(f"Logger configuré - Niveau: {log_config['level']}")
    if settings.log_file:
        logger.info(f"Logs sauvegardés dans: {settings.log_file}")


def get_logger(name: str = None):
    """Retourne un logger avec un nom spécifique"""
    if name:
        return logger.bind(name=name)
    return logger