from typing import Literal, Optional
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate
from utils.llm.providers import get_llm
import logging

# Configurar logging
logger = logging.getLogger(__name__)


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
        Chain original para confirmaciones explícitas (sí/no/vale/etc.)
        """
        llm = get_llm()
        
        # Prompt optimizado para identificar confirmaciones explícitas
        prompt = ChatPromptTemplate.from_messages([
            ("system", """Eres un asistente especializado en interpretar mensajes de confirmación en español.

Tu tarea es analizar el mensaje del usuario y determinar si expresa:
- CONFIRMACIÓN (sí): El usuario está de acuerdo, confirma o acepta algo
- NEGACIÓN (no): El usuario rechaza, niega o no está de acuerdo
- AMBIGUO (no se): El mensaje no es claro, es ambiguo o no expresa confirmación ni negación

EJEMPLOS DE CONFIRMACIÓN (responde "si"):
- "Sí", "Vale", "De acuerdo", "Correcto", "Exacto", "Perfecto"
- "s", "yes", "y"
- "Está bien", "Confirmo", "Acepto", "Adelante"
- "Sí, eso es", "Correcto, procede", "Vale, continúa"
- el usuario puede utilizar frases hechas o slang que impliquen confirmación, como "¡Claro!", "Por supuesto", "Sin duda", etc.             

EJEMPLOS DE NEGACIÓN (responde "no"):
- "No", "Nada que ver", "Incorrecto", "No es así"
- "No estoy de acuerdo", "Cancela", "No procede"
- "Para nada", "Negativo", "No, eso no es"
- "n", "nope", "no way"
- el usuario puede utilizar frases hechas o slang que impliquen negación, como "¡Para nada!", "En absoluto", "De ninguna manera", etc.

EJEMPLOS AMBIGUOS (responde "no se"):
- "Más o menos", "Puede ser", "No estoy seguro"
- "A ver...", "Hmmm", "Déjame pensar"
- Mensajes que no relacionados con confirmación/negación
- Preguntas del usuario
- Explicaciones largas sin confirmación clara
- Mensajes que no tienen sentido de confirmación/negación

INSTRUCCIONES:
1. Analiza SOLO el sentido de confirmación/negación del mensaje
2. Responde ÚNICAMENTE con: "si", "no" o "no se" (sin tildes, en minúsculas)
3. No añadas explicaciones ni comentarios adicionales
4. Si hay dudas, usa "no se" para mantener el flujo seguro"""),
            
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

            # Primero intentar confirmación explícita
            response = self.explicit_chain.invoke({"user_message": clean_message})
            result = response.content.strip().lower()

            # Si es explícitamente confirmado o negado, devolver resultado
            if result in ["si", "no"]:
                logger.info(f"Confirmación explícita detectada: {result}")
                return result

            # Si es ambiguo y tenemos contexto, intentar confirmación implícita
            if result == "no se" and context:
                logger.info("Intentando detectar confirmación implícita...")
                implicit_response = self.implicit_chain.invoke({
                    "confirmation_question": context,
                    "user_message": clean_message
                })
                implicit_result = implicit_response.content.strip().lower()
                
                if implicit_result in ["si", "no"]:
                    logger.info(f"Confirmación implícita detectada: {implicit_result}")
                    return implicit_result

            # Si todo falla, devolver "no se"
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

#-------------------------------------
#-------------------------------------
#FIN DE LA TOOL DE CONFIRMACIÓN
#-------------------------------------
#-------------------------------------
# Ejemplo de uso en nodos de LangGraph
class EroskiChatbotNode:
    """
    Clase base para nodos del chatbot que pueden usar la tool de confirmación.
    """
    
    def __init__(self):
        self.confirmation_tool = ConfirmationTool()
    
    def process_user_response(self, user_message: str) -> dict:
        """
        Procesa respuesta del usuario usando la tool de confirmación.
        
        Args:
            user_message: Mensaje del usuario
            
        Returns:
            Dict con información de la confirmación
        """
        confirmation_result = self.confirmation_tool.check_confirmation(user_message)
        
        return {
            "user_message": user_message,
            "confirmation": confirmation_result,
            "is_confirmed": confirmation_result == "si",
            "is_denied": confirmation_result == "no",
            "is_ambiguous": confirmation_result == "no se"
        }


# Ejemplo de implementación en nodo específico
class AuthenticateEmployeeNode(EroskiChatbotNode):
    """
    Nodo de autenticación que usa la tool de confirmación.
    """
    
    def authenticate_flow(self, state: dict) -> dict:
        """
        Flujo de autenticación con confirmación.
        """
        # ... lógica de autenticación ...
        
        # Ejemplo de uso de la tool de confirmación
        if "pending_confirmation" in state:
            user_response = state.get("user_message", "")
            confirmation_info = self.process_user_response(user_response)
            
            if confirmation_info["is_confirmed"]:
                state["authentication_confirmed"] = True
                state["next_action"] = "proceed_to_classification"
            elif confirmation_info["is_denied"]:
                state["authentication_confirmed"] = False
                state["next_action"] = "restart_authentication"
            else:  # ambiguous
                state["needs_clarification"] = True
                state["next_action"] = "ask_for_clarification"
        
        return state


# Función utilitaria para integrar en cualquier nodo
def add_confirmation_tool_to_node(node_class):
    """
    Decorator para añadir automáticamente la tool de confirmación a cualquier nodo.
    
    Args:
        node_class: Clase del nodo a decorar
        
    Returns:
        Clase decorada con la tool de confirmación
    """
    original_init = node_class.__init__
    
    def new_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        if not hasattr(self, 'confirmation_tool'):
            self.confirmation_tool = ConfirmationTool()
            self.check_confirmation = self.confirmation_tool.check_confirmation
    
    node_class.__init__ = new_init
    return node_class


# Ejemplo de configuración para LangGraph
def create_confirmation_tool_for_graph():
    """
    Crea la tool de confirmación para usar directamente en LangGraph.
    
    Returns:
        Tool configurada para LangGraph
    """
    confirmation_tool_instance = ConfirmationTool()
    return confirmation_tool_instance.get_tool()


# Tests básicos (opcional)
def test_confirmation_tool():
    """
    Tests básicos para validar la tool de confirmación.
    """
    tool = ConfirmationTool()
    
    # Test casos de confirmación
    test_cases = [
        ("Sí", "si"),
        ("Vale, perfecto", "si"),
        ("No, para nada", "no"),
        ("Hmm, no estoy seguro", "no se"),
        ("", "no se"),  # mensaje vacío
    ]
    
    print("=== Tests de Confirmation Tool ===")
    for message, expected in test_cases:
        result = tool.check_confirmation(message)
        status = "✅" if result == expected else "❌"
        print(f"{status} '{message}' -> '{result}' (esperado: '{expected}')")


if __name__ == "__main__":
    # Ejecutar tests si se ejecuta directamente
    test_confirmation_tool()

"""
class ProcessIncidentNode:
    def __init__(self):
        self.confirmation_tool = ConfirmationTool()
    
    def process(self, state):
        confirmation = self.confirmation_tool.check_confirmation(state["user_message"])
        # ... lógica del nodo

@add_confirmation_tool_to_node
class ClassifyQueryNode:
    def process(self, state):
        confirmation = self.check_confirmation(state["user_message"])
        # ... lógica del nodo

        

confirmation_tool = create_confirmation_tool_for_graph()
# Usar en el grafo como tool estándar


🚀 Características Clave
1. Respuestas Consistentes

Retorna únicamente: "si", "no", "no se"
Temperatura 0 para máxima consistencia
Validación de respuestas del LLM

2. Reutilizable en Todos los Nodos

Clase ConfirmationTool que puede instanciarse en cualquier nodo
Decorator @add_confirmation_tool_to_node para integración automática
Función create_confirmation_tool_for_graph() para uso directo en LangGraph

3. Manejo Robusto de Errores

Logging detallado para debugging
Fallback seguro a "no se" en caso de error
Validación de entradas vacías o inválidas

🛠 Formas de Integración
Opción 1: Instanciación directa en nodos
pythonclass ProcessIncidentNode:
    def __init__(self):
        self.confirmation_tool = ConfirmationTool()
    
    def process(self, state):
        confirmation = self.confirmation_tool.check_confirmation(state["user_message"])
        # ... lógica del nodo
Opción 2: Usando decorator
python@add_confirmation_tool_to_node
class ClassifyQueryNode:
    def process(self, state):
        confirmation = self.check_confirmation(state["user_message"])
        # ... lógica del nodo
Opción 3: Tool directa en LangGraph
pythonconfirmation_tool = create_confirmation_tool_for_graph()
# Usar en el grafo como tool estándar

"""