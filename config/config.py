#!/usr/bin/env python3
"""
Configuración Simplificada - Chatbot Eroski
Reemplaza múltiples archivos de configuración dispersos
"""

import os
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

@dataclass
class DatabaseConfig:
    """Configuración de base de datos"""
    host: str = os.getenv("DB_HOST", "localhost")
    port: int = int(os.getenv("DB_PORT", "5432"))
    name: str = os.getenv("DB_NAME", "eroski_chatbot")
    user: str = os.getenv("DB_USER", "postgres")
    password: str = os.getenv("DB_PASSWORD", "")
    
    @property
    def connection_string(self) -> str:
        """Generar string de conexión PostgreSQL"""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"

@dataclass
class LLMConfig:
    """Configuración de LLM"""
    provider: str = os.getenv("LLM_PROVIDER", "openai")
    api_key: str = os.getenv("OPENAI_API_KEY", "")
    model: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
    temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.1"))
    max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "1000"))
    
    def validate(self) -> bool:
        """Validar configuración de LLM"""
        if not self.api_key:
            return False
        if self.provider == "openai" and not self.api_key.startswith("sk-"):
            return False
        return True

@dataclass  
class ChainlitConfig:
    """Configuración de Chainlit"""
    host: str = os.getenv("CHAINLIT_HOST", "localhost")
    port: int = int(os.getenv("CHAINLIT_PORT", "8000"))
    debug: bool = os.getenv("CHAINLIT_DEBUG", "false").lower() == "true"
    show_readme: bool = os.getenv("CHAINLIT_SHOW_README", "false").lower() == "true"
    theme: str = os.getenv("CHAINLIT_THEME", "light")

@dataclass
class AppConfig:
    """Configuración general de la aplicación"""
    name: str = os.getenv("APP_NAME", "Chatbot de Incidencias Eroski")
    version: str = "1.0.0"
    debug_mode: bool = os.getenv("DEBUG_MODE", "false").lower() == "true"
    environment: str = os.getenv("ENVIRONMENT", "development")
    timezone: str = os.getenv("TIMEZONE", "Europe/Madrid")
    
    # Directorios del proyecto
    project_root: Path = Path(__file__).parent.parent
    data_dir: Path = project_root / "data"
    logs_dir: Path = project_root / "logs"
    
    def __post_init__(self):
        """Crear directorios si no existen"""
        self.data_dir.mkdir(exist_ok=True)
        self.logs_dir.mkdir(exist_ok=True)

class EroskiConfig:
    """Configuración principal del chatbot Eroski"""
    
    def __init__(self):
        self.app = AppConfig()
        self.database = DatabaseConfig()
        self.llm = LLMConfig()
        self.chainlit = ChainlitConfig()
        
        # Configurar logging
        self._setup_logging()
        
        # Validar configuración
        self._validate_config()
    
    def _setup_logging(self):
        """Configurar logging de la aplicación"""
        log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        log_format = "[%(asctime)s] %(levelname)s in %(name)s: %(message)s"
        
        # Configurar logging básico
        logging.basicConfig(
            level=getattr(logging, log_level),
            format=log_format,
            datefmt='%H:%M:%S'
        )
        
        # Configurar archivo de log si estamos en producción
        if self.app.environment == "production":
            log_file = self.app.logs_dir / "eroski_chatbot.log"
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(logging.Formatter(log_format))
            logging.getLogger().addHandler(file_handler)
    
    def _validate_config(self):
        """Validar configuración crítica"""
        logger = logging.getLogger("Config")
        
        # Validar LLM
        if not self.llm.validate():
            logger.error("❌ Configuración de LLM inválida - revisa OPENAI_API_KEY")
            
        # Validar directorios
        if not self.app.data_dir.exists():
            logger.warning(f"⚠️ Directorio de datos no existe: {self.app.data_dir}")
            
        # Validar archivos críticos
        incidents_file = self.app.data_dir / "eroski_incidents.json"
        if not incidents_file.exists():
            logger.warning(f"⚠️ Archivo de incidencias no encontrado: {incidents_file}")
        
        logger.info("✅ Configuración validada")
    
    def get_database_url(self) -> str:
        """Obtener URL de conexión a la base de datos"""
        return self.database.connection_string
    
    def get_llm_config(self) -> Dict[str, Any]:
        """Obtener configuración de LLM como diccionario"""
        return {
            "provider": self.llm.provider,
            "api_key": self.llm.api_key,
            "model": self.llm.model,
            "temperature": self.llm.temperature,
            "max_tokens": self.llm.max_tokens
        }
    
    def is_development(self) -> bool:
        """Verificar si estamos en modo desarrollo"""
        return self.app.environment == "development"
    
    def is_debug(self) -> bool:
        """Verificar si el debug está activado"""
        return self.app.debug_mode

# Instancia global de configuración
_config_instance: Optional[EroskiConfig] = None

def get_config() -> EroskiConfig:
    """
    Obtener instancia singleton de configuración
    """
    global _config_instance
    if _config_instance is None:
        _config_instance = EroskiConfig()
    return _config_instance

def validate_environment() -> bool:
    """
    Validar que el entorno esté correctamente configurado
    """
    config = get_config()
    
    # Lista de verificaciones críticas
    checks = [
        (config.llm.validate(), "LLM configuration"),
        (config.app.project_root.exists(), "Project root directory"),
        (len(config.llm.api_key) > 0, "API key present")
    ]
    
    all_passed = True
    logger = logging.getLogger("Environment")
    
    for check, description in checks:
        if check:
            logger.debug(f"✅ {description}")
        else:
            logger.error(f"❌ {description}")
            all_passed = False
    
    return all_passed

def create_chainlit_config_file():
    """
    Crear archivo de configuración de Chainlit dinámicamente
    """
    config = get_config()
    chainlit_config_dir = config.app.project_root / ".chainlit"
    chainlit_config_dir.mkdir(exist_ok=True)
    
    chainlit_config_content = f"""[project]
name = "{config.app.name}"

[UI]
name = "🛒 {config.app.name}"
show_readme_as_default = {str(config.chainlit.show_readme).lower()}
default_theme = "{config.chainlit.theme}"

[features]
prompt_playground = false
multi_modal = false
speech_to_text = false

[meta]
generated_by = "eroski_config.py"
"""
    
    config_file = chainlit_config_dir / "config.toml"
    with open(config_file, "w", encoding="utf-8") as f:
        f.write(chainlit_config_content)
    
    logging.getLogger("Config").info(f"✅ Archivo de configuración Chainlit creado: {config_file}")

def print_config_summary():
    """
    Imprimir resumen de la configuración actual
    """
    config = get_config()
    
    print("\n" + "="*50)
    print("🔧 CONFIGURACIÓN DEL CHATBOT EROSKI")
    print("="*50)
    print(f"Aplicación: {config.app.name} v{config.app.version}")
    print(f"Entorno: {config.app.environment}")
    print(f"Debug: {'Activado' if config.app.debug_mode else 'Desactivado'}")
    print(f"Zona horaria: {config.app.timezone}")
    print()
    print(f"LLM Provider: {config.llm.provider}")
    print(f"Modelo: {config.llm.model}")
    print(f"API Key: {'✅ Configurada' if config.llm.api_key else '❌ No configurada'}")
    print()
    print(f"Base de datos: {config.database.host}:{config.database.port}/{config.database.name}")
    print()
    print(f"Chainlit: {config.chainlit.host}:{config.chainlit.port}")
    print(f"Tema: {config.chainlit.theme}")
    print("="*50)

if __name__ == "__main__":
    # Script para verificar configuración
    print("🔧 Verificador de Configuración - Chatbot Eroski")
    
    try:
        config = get_config()
        print_config_summary()
        
        if validate_environment():
            print("\n✅ Configuración válida - El chatbot puede ejecutarse")
            
            # Crear archivo de configuración de Chainlit
            create_chainlit_config_file()
            
        else:
            print("\n❌ Configuración inválida - Revisa las variables de entorno")
            print("\n💡 Variables de entorno requeridas:")
            print("   - OPENAI_API_KEY=sk-tu-clave-aqui")
            print("   - DB_HOST=localhost (opcional)")
            print("   - DB_NAME=eroski_chatbot (opcional)")
            
    except Exception as e:
        print(f"\n❌ Error validando configuración: {e}")