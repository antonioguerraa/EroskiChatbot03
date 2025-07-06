from typing import Literal, Optional
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate
from utils.llm.providers import get_llm
import logging

# Configurar logging
logger = logging.getLogger(__name__)

class ConfirmationTool:
    """
    Tool reutilizable para identificar si un mensaje del usuario es de confirmación.
    Puede ser utilizada por todos los nodos del workflow de LangGraph.
    """
    
    def __init__(self, llm_model: str = "gpt-4o-mini"):
        """
        Inicializa la tool de confirmación.
        
        Args:
            llm_model: Modelo de LLM a utilizar (por defecto gpt-4o-mini para mejor coste-eficiencia)
        """
        self.llm = get_llm()
        
        # Prompt optimizado para identificar confirmaciones
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """Eres un asistente especializado en interpretar mensajes de confirmación en español.

Tu tarea es analizar el mensaje del usuario y determinar si expresa:
- CONFIRMACIÓN (sí): El usuario está de acuerdo, confirma o acepta algo
- NEGACIÓN (no): El usuario rechaza, niega o no está de acuerdo
- AMBIGUO (no se): El mensaje no es claro, es ambiguo o no expresa confirmación ni negación

EJEMPLOS DE CONFIRMACIÓN (responde "si"):
- "Sí", "Vale", "De acuerdo", "Correcto", "Exacto", "Perfecto"
- "Está bien", "Confirmo", "Acepto", "Adelante"
- "Sí, eso es", "Correcto, procede", "Vale, continúa"

EJEMPLOS DE NEGACIÓN (responde "no"):
- "No", "Nada que ver", "Incorrecto", "No es así"
- "No estoy de acuerdo", "Cancela", "No procede"
- "Para nada", "Negativo", "No, eso no es"

EJEMPLOS AMBIGUOS (responde "no se"):
- "Más o menos", "Puede ser", "No estoy seguro"
- "A ver...", "Hmmm", "Déjame pensar"
- Mensajes que no relacionados con confirmación/negación
- Preguntas del usuario
- Explicaciones largas sin confirmación clara

INSTRUCCIONES:
1. Analiza SOLO el sentido de confirmación/negación del mensaje
2. Responde ÚNICAMENTE con: "si", "no" o "no se" (sin tildes, en minúsculas)
3. No añadas explicaciones ni comentarios adicionales
4. Si hay dudas, usa "no se" para mantener el flujo seguro"""),
            
            ("human", "Mensaje del usuario: {user_message}")
        ])
        
        self.chain = self.prompt | self.llm

    @tool
    def check_confirmation(self, user_message: str, context: Optional[str] = None) -> Literal["si", "no", "no se"]:
        """
        Identifica si el mensaje del usuario es de confirmación.
        
        Args:
            user_message: Mensaje del usuario a analizar
            context: Contexto adicional opcional (para futuras mejoras)
            
        Returns:
            "si" si es confirmación, "no" si es negación, "no se" si es ambiguo
        """
        try:
            # Validar entrada
            if not user_message or not user_message.strip():
                logger.warning("Mensaje vacío recibido")
                return "no se"
            
            # Limpiar mensaje
            clean_message = user_message.strip()
            
            # Log para debugging
            logger.info(f"Analizando confirmación: '{clean_message}'")
            
            # Invocar LLM
            response = self.chain.invoke({
                "user_message": clean_message
            })
            
            # Extraer y limpiar respuesta
            result = response.content.strip().lower()
            
            # Validar respuesta del LLM
            valid_responses = ["si", "no", "no se"]
            if result not in valid_responses:
                logger.warning(f"Respuesta inesperada del LLM: '{result}'. Usando 'no se'")
                return "no se"
            
            logger.info(f"Resultado de confirmación: '{result}'")
            return result
            
        except Exception as e:
            logger.error(f"Error en check_confirmation: {str(e)}")
            # En caso de error, retornar estado seguro
            return "no se"

    def get_tool(self):
        """
        Retorna la tool para ser utilizada en LangGraph.
        
        Returns:
            Tool configurada para usar en agentes
        """
        return self.check_confirmation

#-------------------------------------
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