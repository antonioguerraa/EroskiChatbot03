# =====================================================
# config/settings.py - CORREGIDO para forzar .env
# =====================================================
"""
Corrección para forzar que las variables del .env sobrescriban
las variables del sistema operativo.
"""

from pydantic_settings import BaseSettings
from typing import Optional, Literal
from pydantic import ConfigDict
from pathlib import Path
import os
import logging

logger = logging.getLogger("Settings")

# 🔥 SOLUCIÓN: Cargar .env manualmente con prioridad
def load_env_with_override():
    """Cargar .env manualmente con override de variables del sistema"""
    
    env_file = Path(".env")
    if not env_file.exists():
        return
    
    try:
        from dotenv import load_dotenv
        # 🔥 CLAVE: override=True fuerza que .env sobrescriba variables del sistema
        load_dotenv(env_file, override=True)
        
        # Verificar que se cargó correctamente
        if os.getenv('DB_NAME') == 'chatbot_db':
            print("✅ Variables .env cargadas correctamente con override")
        else:
            print(f"⚠️ DB_NAME sigue siendo: {os.getenv('DB_NAME')}")
            
    except ImportError:
        print("❌ python-dotenv no está instalado")
    except Exception as e:
        print(f"❌ Error cargando .env: {e}")

# Cargar .env inmediatamente al importar este módulo
load_env_with_override()

class DatabaseSettings(BaseSettings):
    """Configuración de base de datos PostgreSQL"""
    
    host: str = "localhost"
    port: int = 5432
    name: str = "chatbot_db"  # 🔥 Default correcto
    user: str = "postgres"
    password: str = ""
    pool_min_size: int = 1
    pool_max_size: int = 10
    command_timeout: int = 60
    
    model_config = ConfigDict(extra="ignore", env_prefix="DB_")
        
    @property
    def connection_string(self) -> str:
        """Generar string de conexión PostgreSQL"""
        # Check if we should use Supabase pooler or direct connection
        supabase_db_string = os.getenv('SUPABASE_DB_STRING')
        supabase_pooler_string = os.getenv('SUPABASE_POOLER_STRING')
        use_pooler = os.getenv('USE_SUPABASE_POOLER', 'false').lower() == 'true'
        
        # If Supabase strings are available, use them
        if supabase_db_string and not use_pooler:
            logger.info("🌐 Using Supabase direct connection")
            return supabase_db_string
        elif supabase_pooler_string and use_pooler:
            logger.info("🌐 Using Supabase pooler connection")
            return supabase_pooler_string
        else:
            # Fallback to constructed connection string
            return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"
    
    @property
    def test_connection_string(self) -> str:
        """String de conexión para tests"""
        # For Supabase, we can't create test databases, so use the main one
        if 'supabase.co' in self.host:
            logger.warning("⚠️ Using main Supabase database for tests (can't create test DBs)")
            return self.connection_string
        else:
            test_db_name = f"test_{self.name}"
            return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{test_db_name}"

class LLMSettings(BaseSettings):
    """Configuración de LLM con soporte para Azure OpenAI"""
    
    provider: Literal["openai", "azure"] = "azure"
    
    # Configuración de OpenAI (original)
    openai_api_key: Optional[str] = None
    
    # Configuración de Azure OpenAI
    azure_openai_api_key: Optional[str] = None
    azure_openai_endpoint: Optional[str] = None
    azure_deployment_name: Optional[str] = None
    azure_api_version: str = "2024-02-15-preview"
    
    # Configuración común
    model: str = "gpt-4"
    temperature: float = 0.7
    max_tokens: int = 2000
    timeout: int = 30
    
    model_config = ConfigDict(extra="ignore", env_prefix="LLM_")

    def get_active_api_key(self) -> str:
        """Obtener la API key activa según el proveedor"""
        if self.provider == "azure":
            if not self.azure_openai_api_key:
                raise ValueError("AZURE_OPENAI_API_KEY requerida para provider 'azure'")
            return self.azure_openai_api_key
        else:
            if not self.openai_api_key:
                raise ValueError("OPENAI_API_KEY requerida para provider 'openai'")
            return self.openai_api_key
    
    def validate_azure_config(self) -> bool:
        """Validar configuración específica de Azure"""
        if self.provider != "azure":
            return True
            
        required_fields = [
            ("azure_openai_api_key", self.azure_openai_api_key),
            ("azure_openai_endpoint", self.azure_openai_endpoint), 
            ("azure_deployment_name", self.azure_deployment_name)
        ]
        
        missing_fields = [name for name, value in required_fields if not value]
        
        if missing_fields:
            raise ValueError(f"Campos requeridos para Azure: {missing_fields}")
        
        return True

class ApplicationSettings(BaseSettings):
    """Configuración general de la aplicación"""
    
    debug_mode: bool = False
    log_level: str = "INFO"
    session_timeout: int = 3600
    
    # Configuración específica del chatbot
    max_intentos_identificacion: int = 5
    max_intentos_incidencia: int = 3
    enable_auto_escalation: bool = True
    
    model_config = ConfigDict(extra="ignore", env_prefix="APP_")

    @property
    def is_development(self) -> bool:
        """Verificar si estamos en modo desarrollo"""
        return self.debug_mode or self.log_level == "DEBUG"

class WorkflowSettings(BaseSettings):
    """Configuración específica de workflows"""
    
    enable_database_lookup: bool = True
    require_email_confirmation: bool = True
    auto_escalate_after_attempts: int = 5
    enable_llm_message_generation: bool = True
    enable_similarity_matching: bool = True
    
    # Timeouts para diferentes operaciones
    user_response_timeout: int = 300  # 5 minutos
    database_query_timeout: int = 10  # 10 segundos
    llm_response_timeout: int = 30    # 30 segundos
    
    model_config = ConfigDict(extra="ignore", env_prefix="WORKFLOW_")

class LoggingSettings(BaseSettings):
    """Configuración de logging"""
    
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    file_path: str = "logs/chatbot.log"
    max_file_size: int = 10 * 1024 * 1024  # 10MB
    backup_count: int = 5
    
    # Configuración específica por módulo
    node_log_level: str = "DEBUG"
    database_log_level: str = "WARNING" 
    llm_log_level: str = "INFO"
    
    model_config = ConfigDict(extra="ignore", env_prefix="LOG_")

    @property
    def log_dir(self) -> Path:
        """Directorio de logs"""
        return Path(self.file_path).parent

class ChainlitSettings(BaseSettings):
    """Configuración específica de Chainlit"""
    
    port: int = 8000
    host: str = "localhost"
    debug: bool = False
    
    # UI Configuration
    theme: str = "light"
    show_readme_as_default: bool = False
    enable_telemetry: bool = False
    
    model_config = ConfigDict(extra="ignore", env_prefix="CHAINLIT_")

class SecuritySettings(BaseSettings):
    """Configuración de seguridad"""
    
    secret_key: str = "change-me-in-production"
    token_expire_minutes: int = 30
    
    # Rate limiting
    max_requests_per_minute: int = 60
    max_requests_per_hour: int = 1000
    
    model_config = ConfigDict(extra="ignore", env_prefix="SECURITY_")

class SupabaseSettings(BaseSettings):
    """Configuración específica de Supabase"""
    
    url: Optional[str] = None
    service_role: Optional[str] = None
    db_string: Optional[str] = None
    pooler_string: Optional[str] = None
    project_ref: Optional[str] = None
    
    model_config = ConfigDict(extra="ignore", env_prefix="SUPABASE_")
    
    @property
    def is_configured(self) -> bool:
        """Verificar si Supabase está configurado"""
        return bool(self.db_string or self.pooler_string)

class Settings(BaseSettings):
    """Configuración principal que agrupa todas las demás"""
    
    def __init__(self, **kwargs):
        # 🔥 VERIFICAR que .env se cargó antes de inicializar
        # For Supabase, DB_NAME should be 'postgres'
        expected_db_name = 'postgres' if os.getenv('SUPABASE_DB_STRING') else 'chatbot_db'
        if os.getenv('DB_NAME') != expected_db_name:
            print(f"⚠️ ADVERTENCIA: DB_NAME = {os.getenv('DB_NAME')} (debería ser {expected_db_name})")
            print("💡 Revisa tu archivo .env")
        
        super().__init__(**kwargs)
        
        # Inicializar cada sub-configuración independientemente
        self.database = DatabaseSettings()
        self.llm = LLMSettings()
        self.app = ApplicationSettings()
        self.workflow = WorkflowSettings()
        self.logging = LoggingSettings()
        self.security = SecuritySettings()
        self.supabase = SupabaseSettings()
        
        # Cargar ChainlitSettings solo si aplica
        if self.channel == "chainlit":
            self.chainlit = ChainlitSettings()
    
    # Declarar los campos como Optional para evitar conflictos
    channel: Literal["chainlit", "whatsapp"] = "chainlit"
    database: Optional[DatabaseSettings] = None
    llm: Optional[LLMSettings] = None
    app: Optional[ApplicationSettings] = None
    workflow: Optional[WorkflowSettings] = None
    logging: Optional[LoggingSettings] = None
    chainlit: Optional[ChainlitSettings] = None
    security: Optional[SecuritySettings] = None
    supabase: Optional[SupabaseSettings] = None
    
    # 🔥 CAMBIO: Configurar para que .env tenga prioridad
    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    def validate_configuration(self) -> list[str]:
        """Validar toda la configuración y retornar errores"""
        errors = []
        
        # Validar que DB_NAME sea correcto (postgres para Supabase, chatbot_db para local)
        expected_db_name = 'postgres' if self.supabase.is_configured else 'chatbot_db'
        if self.database.name != expected_db_name:
            errors.append(f"DB_NAME incorrecto: {self.database.name} (debería ser {expected_db_name})")
        
        # Validar configuración de Supabase si está habilitada
        if self.supabase.is_configured:
            if not self.supabase.db_string and not self.supabase.pooler_string:
                errors.append("Supabase configurado pero falta connection string")
            if self.database.host == 'localhost':
                errors.append("Supabase configurado pero DB_HOST sigue siendo localhost")
        
        # Validar configuración de Azure
        try:
            self.llm.validate_azure_config()
        except ValueError as e:
            errors.append(f"Error en configuración LLM: {e}")
        
        # Validar directorio de logs
        try:
            self.logging.log_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            errors.append(f"No se puede crear directorio de logs: {e}")
        
        # Validar configuración de BD en producción
        if not self.app.is_development and self.database.password == "" and not self.supabase.is_configured:
            errors.append("Usar password vacío en producción es inseguro")
        
        return errors

# Singleton pattern para configuración global
_settings: Optional[Settings] = None

def get_settings() -> Settings:
    """
    Obtener instancia singleton de configuración.
    
    Returns:
        Instancia de Settings con toda la configuración cargada
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings

def reload_settings():
    """Recargar configuración (útil para tests o cambios en runtime)"""
    global _settings
    _settings = None
    # Recargar .env también
    load_env_with_override()

def validate_environment() -> bool:
    """
    Validar que el entorno esté configurado correctamente.
    
    Returns:
        True si todo está bien, False si hay errores
    """
    settings = get_settings()
    errors = settings.validate_configuration()
    
    if errors:
        import logging
        logger = logging.getLogger("Config")
        logger.error("Errores de configuración encontrados:")
        for error in errors:
            logger.error(f"  - {error}")
        return False
    
    return True

# 🔥 FUNCIÓN DE DEBUG
def debug_current_settings():
    """Función de debug para ver configuración actual"""
    print("🔍 DEBUG - Configuración Actual:")
    print(f"   DB_NAME (OS): {os.getenv('DB_NAME')}")
    
    try:
        settings = get_settings()
        print(f"   DB_NAME (Settings): {settings.database.name}")
        print(f"   DB_HOST: {settings.database.host}")
        print(f"   DB_USER: {settings.database.user}")
    except Exception as e:
        print(f"   ❌ Error obteniendo settings: {e}")