#!/usr/bin/env python3
"""
Script d'installation automatique pour Bot Opérateur 112 v3
"""
import os
import sys
import subprocess
import shutil
from pathlib import Path


def run_command(command, description, check=True):
    """Exécute une commande avec gestion d'erreurs"""
    print(f"📦 {description}...")
    
    try:
        result = subprocess.run(command, shell=True, check=check, 
                              capture_output=True, text=True)
        
        if result.stdout:
            print(f"   ✅ {result.stdout.strip()}")
        
        return result.returncode == 0
        
    except subprocess.CalledProcessError as e:
        print(f"   ❌ Erreur: {e}")
        if e.stderr:
            print(f"   ℹ️  Détails: {e.stderr.strip()}")
        return False


def check_python_version():
    """Vérifie la version de Python"""
    print("🐍 Vérification de la version Python...")
    
    version = sys.version_info
    print(f"   Version détectée: {version.major}.{version.minor}.{version.micro}")
    
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print("   ❌ Python 3.8+ requis")
        return False
    
    print("   ✅ Version Python compatible")
    return True


def install_dependencies():
    """Installe les dépendances Python"""
    print("📦 Installation des dépendances Python...")
    
    # Tentative d'installation complète
    success = run_command("pip install -r requirements.txt", 
                         "Installation des packages", check=False)
    
    if not success:
        print("   ⚠️  Installation complète échouée, tentative avec packages essentiels...")
        
        # Packages essentiels
        essential_packages = [
            "playwright>=1.40.0",
            "pydantic>=2.0.0", 
            "loguru>=0.7.0",
            "python-dotenv>=1.0.0"
        ]
        
        for package in essential_packages:
            success = run_command(f"pip install {package}", 
                                f"Installation de {package}", check=False)
            if not success:
                print(f"   ❌ Échec pour {package}")
    
    return success


def install_playwright():
    """Installe les navigateurs Playwright"""
    print("🌐 Installation des navigateurs Playwright...")
    
    return run_command("playwright install chromium", 
                      "Installation de Chromium")


def setup_config():
    """Configure le fichier .env"""
    print("⚙️ Configuration du fichier .env...")
    
    env_example = Path(".env.example")
    env_file = Path(".env")
    
    if not env_example.exists():
        print("   ❌ Fichier .env.example non trouvé")
        return False
    
    if env_file.exists():
        print("   ℹ️  Fichier .env existe déjà")
        response = input("   Voulez-vous le remplacer ? (y/N): ").lower().strip()
        if response not in ['y', 'yes', 'oui']:
            print("   ⏭️  Conservation du fichier existant")
            return True
    
    try:
        shutil.copy2(env_example, env_file)
        print("   ✅ Fichier .env créé depuis .env.example")
        print("   ⚠️  N'oubliez pas de configurer USERNAME et PASSWORD dans .env")
        return True
        
    except Exception as e:
        print(f"   ❌ Erreur lors de la copie: {e}")
        return False


def test_installation():
    """Teste l'installation"""
    print("🧪 Test de l'installation...")
    
    success = run_command("python test_architecture.py", 
                         "Test de l'architecture")
    
    if success:
        print("   ✅ Tests réussis!")
        return True
    else:
        print("   ❌ Tests échoués")
        return False


def show_next_steps():
    """Affiche les prochaines étapes"""
    print("\n" + "="*60)
    print("🎉 Installation terminée!")
    print("="*60)
    
    print("\n📋 Prochaines étapes:")
    print("1. Éditez le fichier .env avec vos credentials:")
    print("   USERNAME=votre_username")
    print("   PASSWORD=votre_password")
    
    print("\n2. Testez le bot:")
    print("   python main.py --help")
    print("   python main.py --list")
    
    print("\n3. Consultez la documentation:")
    print("   cat README.md")
    
    print("\n4. Exemples d'utilisation:")
    print("   python bot_operateur/examples/basic_usage.py")
    
    print("\n🚀 Le bot est prêt à être utilisé!")
    print("   Pensez à configurer vos credentials avant le premier lancement.")


def main():
    """Fonction principale d'installation"""
    print("🚀 Installation du Bot Opérateur 112 v3")
    print("="*50)
    
    steps = [
        ("Vérification Python", check_python_version),
        ("Installation dépendances", install_dependencies), 
        ("Installation Playwright", install_playwright),
        ("Configuration .env", setup_config),
        ("Test installation", test_installation)
    ]
    
    success_count = 0
    
    for step_name, step_func in steps:
        print(f"\n🔄 {step_name}")
        print("-" * 30)
        
        try:
            success = step_func()
            if success:
                success_count += 1
                print(f"   ✅ {step_name} réussie")
            else:
                print(f"   ❌ {step_name} échouée")
                
                # Demander si on continue
                response = input("   Continuer l'installation ? (Y/n): ").lower().strip()
                if response in ['n', 'no', 'non']:
                    print("   ⏹️  Installation annulée")
                    return 1
                    
        except KeyboardInterrupt:
            print("\n   ⏹️  Installation interrompue par l'utilisateur")
            return 1
        except Exception as e:
            print(f"   💥 Erreur inattendue: {e}")
            return 1
    
    print(f"\n📊 Résultats: {success_count}/{len(steps)} étapes réussies")
    
    if success_count == len(steps):
        show_next_steps()
        return 0
    else:
        print("\n⚠️  Installation incomplète")
        print("   Consultez les messages d'erreur ci-dessus")
        print("   Vous pouvez relancer le script ou installer manuellement")
        return 1


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⏹️ Installation interrompue")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Erreur fatale: {e}")
        sys.exit(1)