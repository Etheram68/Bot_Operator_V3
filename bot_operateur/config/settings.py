import os
from typing import Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()


class Settings(BaseModel):
    """Configuration globale du bot"""
    
    # URLs et connexion
    game_url: str = Field(default="https://www.operateur112.fr", description="URL du jeu")
    username: str = Field(description="Nom d'utilisateur")
    password: str = Field(description="Mot de passe")
    
    # Timeouts (en secondes)
    page_load_timeout: int = Field(default=30, description="Timeout de chargement de page")
    element_wait_timeout: int = Field(default=10, description="Timeout d'attente d'élément")
    retry_delay: int = Field(default=2, description="Délai entre les tentatives")
    max_retries: int = Field(default=3, description="Nombre maximum de tentatives")
    
    # Logging
    log_level: str = Field(default="INFO", description="Niveau de logging")
    log_file: Optional[str] = Field(default="bot.log", description="Fichier de log")
    
    # Navigation
    headless: bool = Field(default=True, description="Mode headless du navigateur")
    browser_slow_mo: int = Field(default=100, description="Ralentissement du navigateur (ms)")
    
    # Stratégies
    default_strategy: str = Field(default="balanced", description="Stratégie par défaut")
    auto_deploy: bool = Field(default=True, description="Déploiement automatique")
    min_credits_threshold: int = Field(default=1000, description="Seuil minimum de crédits")
    
    # Sécurité
    max_concurrent_missions: int = Field(default=5, description="Nombre max de missions simultanées")
    mission_cooldown: int = Field(default=30, description="Cooldown entre missions (secondes)")
    
    @classmethod
    def from_env(cls) -> "Settings":
        """Crée une instance Settings depuis les variables d'environnement"""
        return cls(
            game_url=os.getenv("GAME_URL", "https://www.operateur112.fr"),
            username=os.getenv("USERNAME", ""),
            password=os.getenv("PASSWORD", ""),
            
            page_load_timeout=int(os.getenv("PAGE_LOAD_TIMEOUT", "30")),
            element_wait_timeout=int(os.getenv("ELEMENT_WAIT_TIMEOUT", "10")),
            retry_delay=int(os.getenv("RETRY_DELAY", "2")),
            max_retries=int(os.getenv("MAX_RETRIES", "3")),
            
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            log_file=os.getenv("LOG_FILE", "bot.log"),
            
            headless=os.getenv("HEADLESS", "true").lower() == "true",
            browser_slow_mo=int(os.getenv("BROWSER_SLOW_MO", "100")),
            
            default_strategy=os.getenv("DEFAULT_STRATEGY", "balanced"),
            auto_deploy=os.getenv("AUTO_DEPLOY", "true").lower() == "true",
            min_credits_threshold=int(os.getenv("MIN_CREDITS_THRESHOLD", "1000")),
            
            max_concurrent_missions=int(os.getenv("MAX_CONCURRENT_MISSIONS", "5")),
            mission_cooldown=int(os.getenv("MISSION_COOLDOWN", "30"))
        )
    
    def validate_credentials(self) -> bool:
        """Valide que les credentials sont présents"""
        return bool(self.username and self.password)
    
    def get_log_config(self) -> dict:
        """Retourne la configuration de logging"""
        config = {
            "level": self.log_level,
            "format": "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            "backtrace": True,
            "diagnose": True
        }
        
        if self.log_file:
            config["sink"] = self.log_file
            config["rotation"] = "10 MB"
            config["retention"] = "7 days"
        
        return config