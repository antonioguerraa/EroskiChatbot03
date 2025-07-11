from typing import Literal, Optional, List, Dict, Any
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from utils.llm.providers import get_llm
import logging

# Configurar logging
logger = logging.getLogger(__name__)

class ConfirmationTool:
    """
    Tool reutilizable para identificar si un mensaje del usuario es de confirmación.
    Incluye soporte para confirmación implícita cuando el usuario continúa hablando del tema.
    """
    def __init__(self):
        self.explicit_chain = self._build_explicit_chain()
        self.implicit_chain = self._build_implicit_chain()

    def _build_explicit_chain(self):
        """
        Chain para confirmaciones explícitas directas (sí/no/vale/etc.)
        """
        llm = get_llm()
        
        # Prompt más específico para evitar falsos positivos
        prompt = ChatPromptTemplate.from_messages([
            ("system", """Eres un asistente especializado en identificar confirmaciones y negaciones EXPLÍCITAS en español.

Tu tarea es detectar si el usuario está dando una respuesta directa de SÍ o NO, no descripción o explicaciones.

CONFIRMACIÓN EXPLÍCITA (responde "si"):
- "Sí", "Si", "Vale", "De acuerdo", "Correcto", "Exacto", "Perfecto"
- "Está bien", "Confirmo", "Acepto", "Adelante", "OK"
- "Claro", "Por supuesto", "Sin duda", "Efectivamente"
- "Sí, eso es", "Correcto, procede", "Vale, continúa"

NEGACIÓN EXPLÍCITA (responde "no"):
- "No" (como respuesta directa)
- "Nada que ver", "Incorrecto", "No es así"
- "No estoy de acuerdo", "Para nada", "En absoluto"
- "No, eso no es", "Negativo", "De ninguna manera"

IMPORTANTE - ESTOS NO SON CONFIRMACIONES/NEGACIONES EXPLÍCITAS (responde "no se"):
- Descripciones de problemas que empiecen con "No": "No pesa bien", "No funciona", "No imprime"
- Explicaciones largas o detalladas
- Preguntas del usuario
- Descripciones técnicas o síntomas
- Cualquier mensaje que proporcione información específica en lugar de una respuesta directa sí/no

CRITERIO CLAVE:
- Si el mensaje es una respuesta directa de confirmación/negación → "si" o "no"
- Si el mensaje describe, explica o proporciona información → "no se"

INSTRUCCIONES:
1. Detecta SOLO respuestas directas de confirmación/negación
2. Si es una descripción, explicación o síntoma → "no se"
3. Responde ÚNICAMENTE con: "si", "no" o "no se" (sin tildes, en minúsculas)
4. En caso de duda, usa "no se" para evitar falsos positivos"""),
            
            ("human", "Mensaje del usuario: {user_message}")
        ])
        
        return prompt | llm

    def _build_implicit_chain(self):
        """
        Chain para detectar confirmaciones implícitas cuando el usuario sigue hablando del tema
        """
        llm = get_llm()
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """Eres un asistente especializado en detectar confirmaciones implícitas en conversaciones.

Tu tarea es determinar si el usuario está confirmando implícitamente algo al continuar hablando del tema.

CONTEXTO:
El bot le ha preguntado al usuario si confirma algo específico (ej: "¿Confirmas que el problema es con balanza?")

CONFIRMACIÓN IMPLÍCITA (responde "si"):
- El usuario describe problemas o detalles específicos relacionados con el tema preguntado
- Proporciona información adicional sobre el tema sin negar ni cambiar de tema
- Menciona síntomas, errores o características específicas del equipo/tema en cuestión

EJEMPLOS de confirmación implícita para "¿Confirmas que el problema es con balanza?":
- "El equipo no pesa bien"
- "No imprime las etiquetas"
- "La pantalla se queda en blanco"
- "Está dando error al conectar"
- "No puedo calibrarla"

NEGACIÓN IMPLÍCITA (responde "no"):
- El usuario cambia completamente de tema
- Describe problemas con equipos o sistemas diferentes
- Corrige específicamente el tema propuesto

EJEMPLOS de negación implícita para "¿Confirmas que el problema es con balanza?":
- "No, es la caja registradora"
- "El problema es con la impresora"
- "Es el TPV que no funciona"

AMBIGUO (responde "no se"):
- Mensajes muy cortos sin contexto
- Preguntas generales
- Información insuficiente para determinar el tema
- Mensajes que no aportan información específica

INSTRUCCIONES:
1. Analiza si el mensaje del usuario proporciona información específica sobre el tema mencionado en la pregunta de confirmación
2. Responde ÚNICAMENTE con: "si", "no" o "no se" (sin tildes, en minúsculas)
3. Si el usuario aporta detalles específicos del tema, es confirmación implícita
4. Si hay dudas, usa "no se" para mantener el flujo seguro"""),
            
            ("human", """Pregunta de confirmación del bot: {confirmation_question}

Último mensaje del usuario: {user_message}

¿El usuario está confirmando implícitamente el tema de la pregunta?""")
        ])
        
        return prompt | llm

    def _extract_confirmation_context(self, messages: List[BaseMessage]) -> Optional[str]:
        """
        Extrae la última pregunta de confirmación del historial de mensajes
        """
        try:
            # Buscar hacia atrás en los mensajes el último mensaje del bot que contenga una pregunta de confirmación
            for message in reversed(messages):
                if isinstance(message, AIMessage):
                    content = message.content.lower()
                    # Buscar patrones de confirmación
                    confirmation_patterns = [
                        "¿confirmas que",
                        "confirmas que",
                        "¿es correcto",
                        "¿está bien",
                        "¿es así",
                        "parece que",
                        "¿verdad?"
                    ]
                    
                    if any(pattern in content for pattern in confirmation_patterns):
                        return message.content
            
            return None
            
        except Exception as e:
            logger.error(f"Error extrayendo contexto de confirmación: {e}")
            return None

    def _is_explicit_confirmation(self, message: str) -> bool:
        """
        Determina si el mensaje es claramente una confirmación/negación explícita
        """
        message_lower = message.lower().strip()
        
        # Palabras que indican confirmación/negación explícita inequívoca
        explicit_confirmations = [
            "sí", "si", "s", "yes", "y", "vale", "ok", "correcto", "exacto", 
            "perfecto", "está bien", "de acuerdo", "confirmo", "acepto", 
            "adelante", "claro", "por supuesto", "sin duda"
        ]
        
        explicit_negations = [
            "no", "n", "nope", "negativo", "para nada", "en absoluto", 
            "de ninguna manera", "nada que ver", "incorrecto", "no es así",
            "no estoy de acuerdo", "cancela", "no procede"
        ]
        
        # Si el mensaje ES EXACTAMENTE una de estas palabras o frases cortas
        if message_lower in explicit_confirmations or message_lower in explicit_negations:
            return True
            
        # Frases cortas que son claramente explícitas
        short_explicit_patterns = [
            "sí, eso es", "no, eso no es", "correcto, procede", "no, para nada",
            "vale, continúa", "no, incorrecto", "está bien", "no está bien"
        ]
        
        if any(pattern in message_lower for pattern in short_explicit_patterns):
            return True
            
        # Si el mensaje es muy corto (menos de 4 palabras) y contiene palabras explícitas
        words = message_lower.split()
        if len(words) <= 3:
            if any(word in explicit_confirmations + explicit_negations for word in words):
                return True
        
        return False

    def check_raw(self, user_message: str, context: Optional[str] = None) -> Literal["si", "no", "no se"]:
        """
        Lógica central de confirmación, usable directamente desde código Python.
        Mantiene compatibilidad con la versión anterior.
        """
        try:
            if not user_message or not user_message.strip():
                logger.warning("Mensaje vacío recibido")
                return "no se"

            clean_message = user_message.strip()
            logger.info(f"Analizando confirmación: '{clean_message}'")

            # NUEVA LÓGICA: Determinar si es explícita o implícita
            is_explicit = self._is_explicit_confirmation(clean_message)
            
            if is_explicit:
                # Usar chain explícito para confirmaciones claras
                logger.info("Detectado como confirmación explícita")
                response = self.explicit_chain.invoke({"user_message": clean_message})
                result = response.content.strip().lower()
                
                if result in ["si", "no"]:
                    logger.info(f"Confirmación explícita detectada: {result}")
                    return result
            
            # Si no es explícita Y tenemos contexto, intentar confirmación implícita
            if not is_explicit and context:
                logger.info("Intentando detectar confirmación implícita...")
                implicit_response = self.implicit_chain.invoke({
                    "confirmation_question": context,
                    "user_message": clean_message
                })
                implicit_result = implicit_response.content.strip().lower()
                
                if implicit_result in ["si", "no"]:
                    logger.info(f"Confirmación implícita detectada: {implicit_result}")
                    return implicit_result
            
            # Si no tenemos contexto pero no es explícita, probar explicit_chain como fallback
            elif not context:
                logger.info("Sin contexto, usando chain explícito como fallback")
                response = self.explicit_chain.invoke({"user_message": clean_message})
                result = response.content.strip().lower()
                
                if result in ["si", "no"]:
                    logger.info(f"Confirmación explícita (fallback) detectada: {result}")
                    return result

            # Si todo falla, devolver "no se"
            logger.info("No se pudo determinar confirmación, devolviendo 'no se'")
            return "no se"

        except Exception as e:
            logger.error(f"Error en check_raw: {e}")
            return "no se"

    def check_with_history(self, user_message: str, messages: List[BaseMessage]) -> Literal["si", "no", "no se"]:
        """
        Versión mejorada que usa el historial de mensajes para extraer contexto automáticamente
        """
        try:
            # Extraer contexto del historial
            confirmation_context = self._extract_confirmation_context(messages)
            
            if confirmation_context:
                logger.info(f"Contexto de confirmación extraído: {confirmation_context[:100]}...")
            
            # Usar check_raw con el contexto extraído
            return self.check_raw(user_message, confirmation_context)
            
        except Exception as e:
            logger.error(f"Error en check_with_history: {e}")
            return self.check_raw(user_message)  # Fallback sin contexto

    def check_with_state(self, user_message: str, state: Dict[str, Any]) -> Literal["si", "no", "no se"]:
        """
        Versión que usa el estado completo para extraer contexto
        """
        try:
            messages = state.get("messages", [])
            return self.check_with_history(user_message, messages)
            
        except Exception as e:
            logger.error(f"Error en check_with_state: {e}")
            return self.check_raw(user_message)  # Fallback sin contexto

    @tool
    @staticmethod
    def check_confirmation(user_message: str, context: Optional[str] = None) -> Literal["si", "no", "no se"]:
        """
        Tool compatible con LangChain Agents o LangGraph.
        Internamente llama a check_raw().
        """
        return ConfirmationTool().check_raw(user_message, context)

    def get_tool(self):
        """
        Retorna la tool para ser utilizada en LangGraph.
        
        Returns:
            Tool configurada para usar en agentes
        """
        return self.check_confirmation

# Funciones de conveniencia para usar en nodos
def check_confirmation_with_state(user_message: str, state: Dict[str, Any]) -> Literal["si", "no", "no se"]:
    """
    Función de conveniencia para usar directamente en nodos con estado
    """
    tool = ConfirmationTool()
    return tool.check_with_state(user_message, state)

def check_confirmation_with_history(user_message: str, messages: List[BaseMessage]) -> Literal["si", "no", "no se"]:
    """
    Función de conveniencia para usar directamente en nodos con historial
    """
    tool = ConfirmationTool()
    return tool.check_with_history(user_message, messages)



