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
    
    # Timeouts optimisés (en secondes)
    page_load_timeout: int = Field(default=15, description="Timeout de chargement de page (réduit pour performance)")
    element_wait_timeout: int = Field(default=5, description="Timeout d'attente d'élément standard")
    fast_timeout: int = Field(default=3, description="Timeout rapide pour éléments qui doivent être présents")
    slow_timeout: int = Field(default=12, description="Timeout lent pour opérations complexes uniquement")
    retry_delay: float = Field(default=0.5, description="Délai entre les tentatives (ultra-optimisé)")
    max_retries: int = Field(default=1, description="Nombre maximum de tentatives (réduit pour vitesse)")
    
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
    mission_cooldown: int = Field(default=5, description="Cooldown entre missions (ultra-optimisé)")
    cycle_delay: int = Field(default=5, description="Délai entre cycles en mode continu (secondes)")
    
    # Optimisation des déploiements
    vehicle_threshold: int = Field(default=3, description="DEPRECATED: Utiliser optimization_threshold et deployment_threshold")
    optimization_threshold: int = Field(default=3, description="Seuil pour privilégier un gros véhicule vs plusieurs petits")
    deployment_threshold: int = Field(default=5, description="Seuil de véhicules manquants pour skip mission")
    personnel_threshold: int = Field(default=1, description="Seuil critique de personnel spécialisé manquant pour skip mission")
    
    @classmethod
    def from_env(cls, env_file: str = ".env") -> "Settings":
        """Crée une instance Settings depuis les variables d'environnement"""
        # Charger le fichier .env si il existe
        if os.path.exists(env_file):
            from dotenv import load_dotenv
            load_dotenv(env_file, override=True)
        return cls(
            game_url=os.getenv("GAME_URL", "https://www.operateur112.fr"),
            username=os.getenv("USERNAME", ""),
            password=os.getenv("PASSWORD", ""),
            
            page_load_timeout=int(os.getenv("PAGE_LOAD_TIMEOUT", "15")),
            element_wait_timeout=int(os.getenv("ELEMENT_WAIT_TIMEOUT", "5")),
            fast_timeout=int(os.getenv("FAST_TIMEOUT", "3")),
            slow_timeout=int(os.getenv("SLOW_TIMEOUT", "12")),
            retry_delay=float(os.getenv("RETRY_DELAY", "0.5")),
            max_retries=int(os.getenv("MAX_RETRIES", "1")),
            
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            log_file=os.getenv("LOG_FILE", "bot.log"),
            
            headless=os.getenv("HEADLESS", "true").lower() == "true",
            browser_slow_mo=int(os.getenv("BROWSER_SLOW_MO", "100")),
            
            default_strategy=os.getenv("DEFAULT_STRATEGY", "balanced"),
            auto_deploy=os.getenv("AUTO_DEPLOY", "true").lower() == "true",
            min_credits_threshold=int(os.getenv("MIN_CREDITS_THRESHOLD", "1000")),
            
            max_concurrent_missions=int(os.getenv("MAX_CONCURRENT_MISSIONS", "5")),
            mission_cooldown=int(os.getenv("MISSION_COOLDOWN", "5")),
            cycle_delay=int(os.getenv("CYCLE_DELAY", "5")),
            
            vehicle_threshold=int(os.getenv("VEHICLE_THRESHOLD", "3")),
            optimization_threshold=int(os.getenv("OPTIMIZATION_THRESHOLD", os.getenv("VEHICLE_THRESHOLD", "3"))),
            deployment_threshold=int(os.getenv("DEPLOYMENT_THRESHOLD", "5")),
            personnel_threshold=int(os.getenv("PERSONNEL_THRESHOLD", "1"))
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