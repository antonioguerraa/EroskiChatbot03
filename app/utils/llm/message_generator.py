# =====================================================
# utils/llm/message_generator.py - Generador de mensajes naturales
# =====================================================
from typing import Dict, Any, List
from app.models.incidencia import TipoIncidencia
from app.utils.llm import get_llm
import logging 

logger = logging.getLogger("Graph")

async def generate_natural_message(tipo_mensaje: str, contexto: Dict[str, Any] = None) -> str:
    """
    Generar mensajes naturales usando LLM en lugar de templates rígidos.
    
    Args:
        tipo_mensaje: Tipo de mensaje a generar
        contexto: Información adicional para personalizar el mensaje
        
    Returns:
        Mensaje natural generado
    """
    contexto = contexto or {}
    llm = get_llm()
    
    prompts = {
        "solicitar_email": """
        Genera un mensaje corto y natural para pedir el email corporativo a un usuario.
        El mensaje debe ser amigable, directo y profesional.
        NO uses frases como "Para poder ayudarte" o templates genéricos.
        Máximo 15 palabras.
        Ejemplos: "¿Me das tu email corporativo?" / "¿Cuál es tu email de trabajo?"
        """,
        
        "solicitar_nombre": """
        Genera un mensaje corto y natural para pedir el nombre completo a un usuario.
        El mensaje debe ser amigable y directo.
        Máximo 12 palabras.
        Ejemplos: "¿Me dices tu nombre completo?" / "¿Cómo te llamas?"
        """,
        
        "solicitar_ambos": """
        Genera un mensaje natural para pedir tanto nombre como email a un usuario.
        Debe ser conversacional y no robótico.
        Máximo 20 palabras.
        Ejemplo: "Para ayudarte mejor, ¿me das tu nombre completo y email corporativo?"
        """,
        
        "confirmacion_datos": f"""
        Genera un mensaje natural para confirmar datos del usuario.
        Datos: Nombre: {contexto.get('nombre', 'N/A')}, Email: {contexto.get('email', 'N/A')}
        El mensaje debe ser conversacional, no robótico.
        Incluye los datos y pregunta si son correctos.
        Máximo 25 palabras.
        Ejemplo: "Perfecto Juan! Confirmo: juan@empresa.com ¿es correcto?"
        """,
        
        "confirmacion_datos_bd": f"""
        Genera un mensaje para cuando encontramos datos en la base de datos.
        Datos encontrados: {contexto.get('nombre', 'N/A')}, {contexto.get('email', 'N/A')}, 
        Empleado #{contexto.get('numero_empleado', 'N/A')}
        Debe sonar como confirmación amigable con todos los datos.
        Máximo 30 palabras.
        Ejemplo: "¡Hola María! Te encontré en el sistema: maria@empresa.com, empleado #1234 ¿correcto?"
        """,
        
        "datos_confirmados": """
        Genera un mensaje corto y natural para indicar que los datos están confirmados 
        y preguntar por la incidencia.
        Debe sonar como una persona real, no un bot.
        Máximo 15 palabras.
        Usa "incidencia" no "problema técnico".
        Ejemplos: "¡Perfecto! ¿Qué incidencia quieres registrar?" / "¡Listo! ¿Cuál es la incidencia?"
        """,
        
        "aclaracion_confirmacion": f"""
        Genera un mensaje natural cuando no está claro si el usuario confirma sus datos.
        Datos: {contexto.get('nombre', 'N/A')}, {contexto.get('email', 'N/A')}
        El mensaje debe ser amigable y pedir aclaración.
        Máximo 20 palabras.
        Ejemplo: "No estoy seguro... ¿confirmas que tus datos son correctos?"
        """,
        
        "solicitar_incidencia_detalles": f"""
        Genera un mensaje natural para pedir más detalles sobre una incidencia de tipo {contexto.get('tipo', 'técnica')}.
        Debe ser específico y útil.
        Máximo 25 palabras.
        Ejemplo: "Para ayudarte con tu problema de software, ¿qué aplicación específica te da problemas?"
        """
    }
    
    if tipo_mensaje not in prompts:
        logger.warning(f"⚠️ Tipo de mensaje no reconocido: {tipo_mensaje}")
        return "¿Puedes ayudarme con más información?"
    
    try:
        prompt = prompts[tipo_mensaje]
        response = await llm.ainvoke(prompt)
        
        # Limpiar respuesta (quitar comillas si las tiene)
        mensaje = response.content.strip().strip('"').strip("'")
        
        logger.debug(f"🎭 Mensaje generado ({tipo_mensaje}): {mensaje}")
        return mensaje
        
    except Exception as e:
        logger.error(f"❌ Error generando mensaje natural: {e}")
        
        # Fallbacks simples en caso de error
        fallbacks = {
            "solicitar_email": "¿Cuál es tu email corporativo?",
            "solicitar_nombre": "¿Me dices tu nombre completo?",
            "solicitar_ambos": "¿Me das tu nombre completo y email corporativo?",
            "confirmacion_datos": f"¿Son correctos estos datos? {contexto.get('nombre', '')}, {contexto.get('email', '')}",
            "confirmacion_datos_bd": f"Hola {contexto.get('nombre', '')}! ¿Confirmas estos datos?",
            "datos_confirmados": "¡Perfecto! ¿Qué incidencia quieres registrar?",
            "aclaracion_confirmacion": "¿Confirmas que estos datos son correctos?",
            "solicitar_incidencia_detalles": "¿Puedes darme más detalles sobre el problema?"
        }
        return fallbacks.get(tipo_mensaje, "¿Puedes ayudarme con más información?")

async def detect_confirmation_intent(respuesta_usuario: str, nombre: str, email: str) -> str:
    """
    Usar LLM para detectar si el usuario está confirmando sus datos.
    
    Args:
        respuesta_usuario: La respuesta del usuario
        nombre: Nombre a confirmar
        email: Email a confirmar
        
    Returns:
        "CONFIRMA", "RECHAZA" o "AMBIGUO"
    """
    llm = get_llm()
    
    prompt = f"""
Analiza la siguiente respuesta del usuario y determina si está CONFIRMANDO o RECHAZANDO sus datos personales.

Contexto: Le pregunté al usuario si estos datos son correctos:
- Nombre: {nombre}
- Email: {email}

Respuesta del usuario: "{respuesta_usuario}"

Instrucciones:
- Si el usuario confirma, acepta o está de acuerdo con los datos → responde "CONFIRMA"
- Si el usuario rechaza, corrige o dice que hay errores → responde "RECHAZA"  
- Si no está claro o es ambiguo → responde "AMBIGUO"

Ejemplos:
- "sí" → CONFIRMA
- "así es" → CONFIRMA
- "todo correcto" → CONFIRMA
- "perfecto" → CONFIRMA
- "está bien" → CONFIRMA
- "correcto" → CONFIRMA
- "no, mi nombre es Juan" → RECHAZA
- "el email está mal" → RECHAZA
- "hay un error" → RECHAZA
- "hola, ¿cómo estás?" → AMBIGUO
- "no entiendo" → AMBIGUO

Responde solo: CONFIRMA, RECHAZA o AMBIGUO
"""
    
    try:
        logger.debug(f"🤖 Consultando LLM para detectar intención: '{respuesta_usuario}'")
        response = await llm.ainvoke(prompt)
        intencion = response.content.strip().upper()
        
        # Validar respuesta
        if intencion not in ["CONFIRMA", "RECHAZA", "AMBIGUO"]:
            logger.warning(f"⚠️ Respuesta LLM inválida: {intencion}, usando AMBIGUO")
            intencion = "AMBIGUO"
        
        logger.info(f"🎯 Intención detectada: {intencion} para '{respuesta_usuario}'")
        return intencion
        
    except Exception as e:
        logger.error(f"❌ Error en detección de intención: {e}")
        
        # Fallback a detección simple
        respuesta_lower = respuesta_usuario.lower()
        confirmaciones_positivas = ["si", "sí", "yes", "correcto", "bien", "ok", "vale", "confirmo", "exacto", "así es"]
        confirmaciones_negativas = ["no", "mal", "error", "incorrecto", "falso"]
        
        if any(palabra in respuesta_lower for palabra in confirmaciones_positivas):
            return "CONFIRMA"
        elif any(palabra in respuesta_lower for palabra in confirmaciones_negativas):
            return "RECHAZA"
        else:
            return "AMBIGUO"

async def generate_followup_questions(tipo: TipoIncidencia, detalles: Dict[str, Any]) -> List[str]:
    """
    Generar preguntas de seguimiento específicas para un tipo de incidencia.
    
    Args:
        tipo: Tipo de incidencia
        detalles: Detalles ya conocidos
        
    Returns:
        Lista de preguntas de seguimiento relevantes
    """
    llm = get_llm()
    
    prompt = f"""
Genera 3-5 preguntas específicas de seguimiento para una incidencia de tipo "{tipo.value}".

Detalles ya conocidos: {detalles}

Las preguntas deben:
1. Ser específicas y técnicas para el tipo de problema
2. Ayudar a diagnosticar la causa raíz
3. Ser fáciles de responder para el usuario
4. Evitar preguntas ya respondidas en los detalles

Tipos de preguntas según el tipo:
- Hardware: Estado físico, sonidos, luces, funcionamiento previo
- Software: Aplicaciones específicas, mensajes de error, pasos para reproducir
- Red: Velocidad, dispositivos afectados, tipo de conexión
- Acceso: Cuentas específicas, mensajes de error, último acceso exitoso

Formato: Una pregunta por línea, máximo 15 palabras cada una.
"""
    
    try:
        response = await llm.ainvoke(prompt)
        preguntas = [
            pregunta.strip().lstrip('-').lstrip('•').strip() 
            for pregunta in response.content.split('\n') 
            if pregunta.strip()
        ]
        
        # Filtrar y limitar
        preguntas_filtradas = [p for p in preguntas if len(p) > 10 and '?' in p][:5]
        
        logger.debug(f"❓ Preguntas generadas para {tipo.value}: {len(preguntas_filtradas)}")
        return preguntas_filtradas
        
    except Exception as e:
        logger.error(f"❌ Error generando preguntas: {e}")
        
        # Preguntas genéricas de fallback
        preguntas_genericas = {
            TipoIncidencia.HARDWARE: [
                "¿Hace cuánto tiempo empezó el problema?",
                "¿Escuchas algún ruido extraño?",
                "¿La computadora enciende normalmente?"
            ],
            TipoIncidencia.SOFTWARE: [
                "¿Qué aplicación específica da problemas?",
                "¿Aparece algún mensaje de error?",
                "¿Puedes reproducir el error consistentemente?"
            ],
            TipoIncidencia.RED: [
                "¿Usas WiFi o cable de red?",
                "¿Otros dispositivos tienen el mismo problema?",
                "¿Puedes acceder a algunos sitios pero no a otros?"
            ]
        }
        
        return preguntas_genericas.get(tipo, [
            "¿Cuándo ocurrió por primera vez?",
            "¿Has intentado alguna solución?",
            "¿Puedes proporcionar más detalles?"
        ])