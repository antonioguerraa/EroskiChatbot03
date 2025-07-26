# =====================================================
# utils/llm/providers.py - Proveedores de LLM CORREGIDO
# =====================================================
from langchain_openai import AzureChatOpenAI
from typing import Optional, List
import logging
from openai import AzureOpenAI
from typing import Optional
import os


from config.settings import get_settings

logger = logging.getLogger("LLM.Provider")

# Cache global para instancia de LLM
_llm_instance: Optional[AzureChatOpenAI] = None

def get_llm() -> AzureChatOpenAI:
    """
    Obtener instancia singleton del LLM configurado.
    
    Returns:
        Instancia configurada de AzureChatOpenAI
    """
    global _llm_instance
    
    if _llm_instance is None:
        settings = get_settings()
        
        logger.info(f"🤖 Inicializando LLM: {settings.llm.model}")
        logger.info(f"🔵 Proveedor: Azure OpenAI")
        
        # 🔥 SOLUCIÓN: Usar configuración correcta de Azure OpenAI
        _llm_instance = AzureChatOpenAI(
            # Configuración de Azure OpenAI
            api_key=settings.llm.azure_openai_api_key,  # ✅ API key de Azure
            azure_endpoint=settings.llm.azure_openai_endpoint,  # ✅ Endpoint de Azure
            azure_deployment=settings.llm.azure_deployment_name,  # ✅ Deployment name
            api_version=settings.llm.azure_api_version,  # ✅ API version
            
            # Configuración común
            temperature=settings.llm.temperature,
            max_tokens=settings.llm.max_tokens,
            timeout=settings.llm.timeout
        )
        
        logger.info(f"✅ Azure OpenAI inicializado correctamente")
        logger.info(f"🔧 Deployment: {settings.llm.azure_deployment_name}")
        logger.info(f"🌐 Endpoint: {settings.llm.azure_openai_endpoint}")
    
    return _llm_instance


_vectorizer_client: Optional[AzureOpenAI] = None

class EmbeddingVectorizer:
    """Wrapper reutilizable para generar embeddings usando Azure OpenAI"""
    
    def __init__(self):
        settings = get_settings()

        self.client = AzureOpenAI(
            api_key=settings.llm.azure_openai_api_key,
            azure_endpoint=settings.llm.azure_openai_endpoint,
            api_version=settings.llm.azure_api_version
        )
        self.deployment = os.getenv("LLM_AZURE_EMBEDDING_DEPLOYMENT")
        if not self.deployment:
            raise ValueError("LLM_AZURE_EMBEDDING_DEPLOYMENT no definido")

    def embed(self, text: str) -> List[float]:
        """Genera embedding del texto usando el deployment configurado"""
        response = self.client.embeddings.create(
            model=self.deployment,
            input=text,
            encoding_format="float"
        )
        return response.data[0].embedding

def get_vectorizer() -> EmbeddingVectorizer:
    global _vectorizer_client
    if _vectorizer_client is None:
        _vectorizer_client = EmbeddingVectorizer()
    return _vectorizer_client

def reset_llm():
    """Resetear instancia de LLM (útil para tests)"""
    global _llm_instance
    _llm_instance = None
    logger.info("🔄 Instancia LLM reseteada")