# =====================================================
# utils/extractors/incident_extractor.py - Extractor de incidencias
# =====================================================
from app.models.incidencia import TipoIncidencia, CategoriaIncidencia, PrioridadIncidencia
from typing import Dict, Any, Optional
from pydantic import Field, BaseModel
from langchain.output_parsers import PydanticOutputParser
from langchain.prompts import PromptTemplate
from app.utils.llm.providers import get_llm
import logging


logger = logging.getLogger("Graph")


class IncidenciaExtraida(BaseModel):
    """Modelo para incidencia extraída"""
    tipo: TipoIncidencia = Field(..., description="Tipo principal de incidencia")
    categoria: Optional[CategoriaIncidencia] = Field(None, description="Categoría específica si se puede determinar")
    descripcion_original: str = Field(..., description="Descripción original del usuario")
    descripcion_procesada: str = Field(..., description="Descripción procesada y estructurada")
    prioridad_sugerida: PrioridadIncidencia = Field(PrioridadIncidencia.MEDIA, description="Prioridad sugerida")
    palabras_clave: list[str] = Field(default_factory=list, description="Palabras clave identificadas")
    confianza: float = Field(0.0, description="Confianza en la clasificación (0-1)")

incident_parser = PydanticOutputParser(pydantic_object=IncidenciaExtraida)

incident_prompt = PromptTemplate(
    template="""
Analiza el siguiente mensaje describiendo un problema técnico y clasifícalo según estos tipos:

TIPOS DE INCIDENCIA:
- hardware: Problemas con computadora, pantalla, teclado, mouse, impresora
- software: Problemas con aplicaciones, programas, sistema operativo  
- red: Problemas de internet, WiFi, conexión, VPN
- acceso: Problemas de contraseñas, cuentas bloqueadas, permisos
- email: Problemas con correo electrónico
- telefonia: Problemas con teléfono, videoconferencias
- otro: Problemas que no encajan en las categorías anteriores

CATEGORÍAS ESPECÍFICAS (ejemplos):
- computadora_lenta, pantalla_problemas, aplicacion_no_abre, internet_lento, olvide_password, etc.

PRIORIDADES:
- critica: Sistema completamente caído, afecta trabajo crítico
- alta: Problema severo que impide trabajar normalmente
- media: Problema molesto pero hay workarounds
- baja: Problema menor, mejora de funcionalidad

Instrucciones:
1. Identifica el tipo principal de incidencia
2. Determina la categoría específica si es posible
3. Asigna prioridad basada en severidad e impacto
4. Extrae palabras clave relevantes
5. Proporciona descripción procesada más clara
6. Asigna confianza alta solo si el tipo es muy claro

Mensaje del usuario: {mensaje}

{format_instructions}
""",
    input_variables=["mensaje"],
    partial_variables={"format_instructions": incident_parser.get_format_instructions()}
)

async def extraer_tipo_incidencia(mensaje: str) -> TipoIncidencia:
    """
    Extraer tipo de incidencia de un mensaje.
    
    Args:
        mensaje: Mensaje describiendo el problema
        
    Returns:
        TipoIncidencia identificado
    """
    try:
        logger.debug(f"🔍 Clasificando incidencia: {mensaje[:50]}...")
        
        llm = get_llm()
        formatted_prompt = incident_prompt.format(mensaje=mensaje)
        response = await llm.ainvoke(formatted_prompt)
        
        extracted = incident_parser.parse(response.content)
        
        logger.info(f"✅ Incidencia clasificada: {extracted.tipo.value} (conf: {extracted.confianza})")
        
        return extracted.tipo
        
    except Exception as e:
        logger.error(f"❌ Error clasificando incidencia: {e}")
        return TipoIncidencia.OTRO

async def extraer_detalles_incidencia(mensaje: str, tipo: TipoIncidencia) -> Dict[str, Any]:
    """
    Extraer detalles específicos de una incidencia.
    
    Args:
        mensaje: Mensaje del usuario
        tipo: Tipo de incidencia ya identificado
        
    Returns:
        Diccionario con detalles extraídos
    """
    try:
        llm = get_llm()
        
        # Prompt específico para extraer detalles según el tipo
        detail_prompt = f"""
Extrae detalles específicos para una incidencia de tipo '{tipo.value}' del siguiente mensaje:

{mensaje}

Busca específicamente:
"""
        
        if tipo == TipoIncidencia.HARDWARE:
            detail_prompt += """
- ¿Qué equipo específico tiene problemas?
- ¿Cuándo empezó el problema?  
- ¿Hay mensajes de error?
- ¿Se escuchan ruidos extraños?
"""
        elif tipo == TipoIncidencia.SOFTWARE:
            detail_prompt += """
- ¿Qué aplicación específica?
- ¿Qué error aparece exactamente?
- ¿Cuándo ocurre el problema?
- ¿Se puede reproducir consistentemente?
"""
        elif tipo == TipoIncidencia.RED:
            detail_prompt += """
- ¿Es WiFi o cable?
- ¿Afecta a todos los sitios web?
- ¿Velocidad lenta o sin conexión?
- ¿Otros dispositivos afectados?
"""
        
        detail_prompt += """
Responde en formato JSON con las claves: equipo, aplicacion, momento_inicio, mensaje_error, reproducible, otros_detalles.
Usa null para información no mencionada.
"""
        
        response = await llm.ainvoke(detail_prompt)
        
        # Intentar parsear JSON, si falla retornar detalles básicos
        try:
            import json
            detalles = json.loads(response.content)
        except:
            detalles = {
                "descripcion_original": mensaje,
                "tipo_detectado": tipo.value,
                "parsing_error": True
            }
        
        logger.debug(f"📋 Detalles extraídos: {detalles}")
        return detalles
        
    except Exception as e:
        logger.error(f"❌ Error extrayendo detalles: {e}")
        return {"descripcion_original": mensaje, "error": str(e)}

