# =====================================================
# workflows/eroski_main_workflow.py - Workflow Principal Optimizado
# =====================================================
"""
Workflow principal simplificado para el chatbot de Eroski.

RESPONSABILIDADES:
- Construir el grafo principal con ramas a END
- Definir routing entre nodos
- Gestionar flujo de conversación
- Manejo de escalación

PRINCIPIOS DE DISEÑO:
- Flujo lineal y predecible
- Decisiones claras en cada punto
- Escalación rápida cuando sea necesario
- Estado mínimo pero completo
- Ramas directas a END para solicitud de información
"""

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from typing import Literal, Dict, Any
import logging

from models.eroski_state import EroskiState, ConsultaType
from .base_workflow import BaseWorkflow

class EroskiFinalWorkflow(BaseWorkflow):
    """
    Workflow principal optimizado para Eroski con ramas a END.
    
    FLUJO SIMPLIFICADO:
    1. Autenticación del empleado
    2. Clasificación de la consulta  
    3. Procesamiento específico según tipo
    4. Resolución o escalación
    5. Finalización
    
    CARACTERÍSTICAS:
    - Cada nodo que necesite input del usuario tiene rama a END
    - Estado persistente entre ejecuciones
    - Respuestas inmediatas al usuario
    - Continuación automática en siguiente invoke()
    """
    
    def __init__(self):
        super().__init__("EroskiMainWorkflow")
        self.memory = MemorySaver()
        
    def get_entry_point(self) -> str:
        return "authenticate"
    
    def get_workflow_description(self) -> str:
        return """
        Workflow Principal de Eroski - Chatbot de Incidencias Optimizado
        
        Flujo optimizado para:
        1. Autenticación rápida de empleados
        2. Clasificación inteligente de consultas
        3. Resolución automática cuando sea posible
        4. Escalación eficiente cuando sea necesario
        
        Características:
        - Flujo lineal y predecible
        - Decisiones claras en cada paso
        - Manejo robusto de errores
        - Métricas integradas
        - Optimizado para casos de uso de Eroski
        """
        
    def build_graph(self) -> StateGraph:
        """
        Construir el grafo principal optimizado con ramas a END.
        
        Returns:
            Grafo compilado con checkpointer y persistencia
        """
        self.logger.info("🔨 Construyendo grafo principal de Eroski...")
        
        # Crear grafo con el estado
        graph = StateGraph(EroskiState)
        
        # ========== IMPORTAR Y AGREGAR NODOS ==========
        try:
            from nodes.authenticate_enhanced import authenticate_employee_node
            from nodes.classify_enhanced import classify_query_node
            from nodes.collect_incident import collect_incident_details_node
            from nodes.search_solution import search_solution_node
            from nodes.search_knowledge import search_knowledge_node
            from nodes.escalate import escalate_supervisor_node
            from nodes.pte.verify import verify_resolution_node
            from nodes.finalize_node import finalize_conversation_node
            
            graph.add_node("authenticate", authenticate_employee_node)
            graph.add_node("classify", classify_query_node)
            graph.add_node("collect_incident", collect_incident_details_node)
            graph.add_node("search_solution", search_solution_node)
            graph.add_node("search_knowledge", search_knowledge_node)
            graph.add_node("escalate", escalate_supervisor_node)
            graph.add_node("verify", verify_resolution_node)
            graph.add_node("finalize", finalize_conversation_node)
            
            self.logger.info("✅ Todos los nodos importados y agregados correctamente")
            
        except ImportError as e:
            self.logger.error(f"❌ Error importando nodos: {e}")
            # Fallback: usar nodos mock para desarrollo
            self._add_mock_nodes(graph)
        
        # ========== DEFINIR FLUJO CON RAMAS A END ==========
        
        # Punto de entrada
        graph.add_edge(START, "authenticate")
        
        # AUTHENTICATE: Puede solicitar credenciales y terminar, o continuar
        graph.add_conditional_edges(
            "authenticate",
            self.route_authenticate,
            {
                "continue": "classify",      # Autenticado, continuar
                "need_input": END,           # 🎯 RAMA A END: Esperando credenciales
                "escalate": "escalate"       # Demasiados intentos
            }
        )
        
        # CLASSIFY: Puede solicitar clarificación y terminar, o continuar
        graph.add_conditional_edges(
            "classify",
            self.route_classify,
            {
                "incident": "collect_incident",  # Es incidencia
                "query": "search_knowledge",     # Es consulta
                "urgent": "escalate",            # Es urgente
                "need_clarification": END,       # 🎯 RAMA A END: Necesita clarificación
                "escalate": "escalate"           # No se pudo clasificar
            }
        )
        
        # COLLECT_INCIDENT: Puede solicitar más detalles y terminar, o continuar
        graph.add_conditional_edges(
            "collect_incident",
            self.route_collect_incident,
            {
                "search_solution": "search_solution",  # Info completa
                "need_details": END,                    # 🎯 RAMA A END: Necesita más detalles
                "escalate": "escalate"                  # Demasiados intentos
            }
        )
        
        # SEARCH_SOLUTION: Siempre continúa (no solicita input del usuario)
        graph.add_conditional_edges(
            "search_solution",
            self.route_search_solution,
            {
                "verify": "verify",         # Solución encontrada
                "escalate": "escalate"      # No hay solución
            }
        )
        
        # SEARCH_KNOWLEDGE: Siempre continúa (no solicita input del usuario)
        graph.add_conditional_edges(
            "search_knowledge",
            self.route_search_knowledge,
            {
                "finalize": "finalize",     # Información encontrada
                "escalate": "escalate"      # No hay información
            }
        )
        
        # VERIFY: Puede solicitar confirmación y terminar, o continuar
        graph.add_conditional_edges(
            "verify",
            self.route_verify,
            {
                "finalize": "finalize",         # Problema resuelto
                "need_confirmation": END,       # 🎯 RAMA A END: Esperando confirmación
                "escalate": "escalate"          # No se resolvió
            }
        )
        
        # ESCALATE y FINALIZE siempre terminan
        graph.add_edge("escalate", "finalize")
        graph.add_edge("finalize", END)
        
        self.logger.info("✅ Grafo construido exitosamente con ramas a END")
        
        return graph
    
    def _add_mock_nodes(self, graph: StateGraph):
        """Agregar nodos mock para desarrollo cuando los reales no están disponibles"""
        self.logger.warning("⚠️ Usando nodos mock para desarrollo")
        
        async def mock_node(state: EroskiState):
            from langgraph.types import Command
            from langchain_core.messages import AIMessage
            from datetime import datetime
            
            node_name = state.get("current_node", "unknown")
            
            return Command(update={
                "messages": state.get("messages", []) + [
                    AIMessage(content=f"Nodo mock: {node_name} - En desarrollo")
                ],
                "current_node": node_name,
                "last_activity": datetime.now(),
                "escalation_needed": True,
                "escalation_reason": f"Nodo {node_name} no implementado"
            })
        
        # Agregar nodos mock
        for node_name in ["authenticate", "classify", "collect_incident", 
                         "search_solution", "search_knowledge", "escalate", 
                         "verify", "finalize"]:
            graph.add_node(node_name, mock_node)
    
    def compile_with_checkpointer(self, checkpointer=None) -> StateGraph:
        """
        Compilar el workflow con checkpointer para persistencia de estado.
        
        Args:
            checkpointer: Checkpointer personalizado (opcional)
            
        Returns:
            Grafo compilado con persistencia
        """
        if checkpointer is None:
            checkpointer = self.memory
            
        graph = self.build_graph()
        
        return graph.compile(
            checkpointer=checkpointer,
            interrupt_before=[]  # Sin interrupciones automáticas
        )
    
    # ========== FUNCIONES DE ROUTING ==========
    
    def route_authenticate(self, state: EroskiState) -> Literal["continue", "need_input", "escalate"]:
        """
        Routing para nodo de autenticación.
        
        Args:
            state: Estado actual
            
        Returns:
            Siguiente acción a tomar
        """
        self.logger.info(f"🌄JGL Entrada en el router de autenticación")
        self.logger.info(f"🌄JGL employee_email: {state.get('employee_email')}")
        self.logger.info(f"🌄JGL store_name: {state.get('store_name')}")
        self.logger.info(f"🌄JGL authenticated: {state.get('authenticated')}")

        
        # Si ya está autenticado, continuar
        if (state.get("employee_email") and 
            state.get("store_name") and 
            state.get("authenticated")):
            self.logger.info(f"✅ Empleado autenticado: {state.get('employee_name')}")
            return "continue"
        
        # Si hay demasiados intentos, escalar
        attempts = state.get("attempts", 0)
        if attempts >= 3:
            self.logger.warning(f"⚠️ Límite de intentos de autenticación alcanzado: {attempts}")
            return "escalate"
        
        # Necesita información del usuario
        self.logger.info("📥 Solicitando credenciales del usuario")
        return "need_input"
    
    def route_classify(self, state: EroskiState) -> Literal["incident", "query", "urgent", "need_clarification", "escalate"]:
        """
        Routing para nodo de clasificación.
        
        Args:
            state: Estado actual
            
        Returns:
            Siguiente acción a tomar
        """
        query_type = state.get("query_type")
        confidence = state.get("confidence_score", 0)
        
        # Si tenemos clasificación con buena confianza
        if query_type and confidence >= 0.6:
            if query_type == ConsultaType.URGENTE:
                self.logger.info("🚨 Consulta urgente detectada")
                return "urgent"
            elif query_type == ConsultaType.INCIDENCIA:
                self.logger.info("🔧 Incidencia detectada")
                return "incident"
            elif query_type == ConsultaType.CONSULTA:
                self.logger.info("❓ Consulta general detectada")
                return "query"
        
        # Si hay demasiados intentos de clarificación, escalar
        attempts = state.get("attempts", 0)
        if attempts >= 2:
            self.logger.warning("⚠️ Demasiados intentos de clarificación")
            return "escalate"
        
        # Necesita clarificación del usuario
        self.logger.info("❔ Solicitando clarificación del tipo de consulta")
        return "need_clarification"
    
    def route_collect_incident(self, state: EroskiState) -> Literal["search_solution", "need_details", "escalate"]:
        """
        Routing para recopilar detalles de incidencia.
        
        Args:
            state: Estado actual
            
        Returns:
            Siguiente acción a tomar
        """
        # Verificar si tenemos información suficiente
        incident_type = state.get("incident_type")
        incident_description = state.get("incident_description", "")
        
        if incident_type and len(incident_description) >= 20:
            self.logger.info(f"✅ Información de incidencia completa: {incident_type}")
            return "search_solution"
        
        # Si hay demasiados intentos, escalar
        attempts = state.get("attempts", 0)
        if attempts >= 3:
            self.logger.warning("⚠️ Límite de intentos para recopilar información alcanzado")
            return "escalate"
        
        # Necesita más detalles del usuario
        self.logger.info("📝 Solicitando más detalles de la incidencia")
        return "need_details"
    
    def route_search_solution(self, state: EroskiState) -> Literal["verify", "escalate"]:
        """
        Routing después de buscar solución.
        
        Args:
            state: Estado actual
            
        Returns:
            Siguiente acción a tomar
        """
        solution_found = state.get("solution_found", False)
        
        if solution_found:
            self.logger.info("✅ Solución encontrada, verificando con usuario")
            return "verify"
        else:
            self.logger.info("❌ No se encontró solución automática, escalando")
            return "escalate"
    
    def route_search_knowledge(self, state: EroskiState) -> Literal["finalize", "escalate"]:
        """
        Routing después de buscar en base de conocimiento.
        
        Args:
            state: Estado actual
            
        Returns:
            Siguiente acción a tomar
        """
        solution_found = state.get("solution_found", False)
        
        if solution_found:
            self.logger.info("✅ Información encontrada en base de conocimiento")
            return "finalize"
        else:
            self.logger.info("❌ No se encontró información relevante, escalando")
            return "escalate"
    
    def route_verify(self, state: EroskiState) -> Literal["finalize", "need_confirmation", "escalate"]:
        """
        Routing para verificación de resolución.
        
        Args:
            state: Estado actual
            
        Returns:
            Siguiente acción a tomar
        """
        # Si ya tenemos confirmación del usuario
        if "resolved" in state:
            if state["resolved"]:
                self.logger.info("✅ Problema confirmado como resuelto")
                return "finalize"
            else:
                self.logger.info("❌ Usuario confirma que problema no está resuelto")
                return "escalate"
        
        # Si hay demasiados intentos de verificación, escalar
        attempts = state.get("attempts", 0)
        if attempts >= 2:
            self.logger.warning("⚠️ Demasiados intentos de verificación")
            return "escalate"
        
        # Necesita confirmación del usuario
        self.logger.info("✓ Solicitando confirmación de resolución")
        return "need_confirmation"
    
    # ========== MÉTODOS AUXILIARES ==========
    
    def should_escalate_urgency(self, state: EroskiState) -> bool:
        """
        Determinar si se debe escalar por urgencia.
        
        Args:
            state: Estado actual
            
        Returns:
            True si debe escalar por urgencia
        """
        urgency_level = state.get("urgency_level")
        if not urgency_level:
            return False
        
        # Escalar si es urgencia alta o crítica
        return urgency_level.value >= 3 if hasattr(urgency_level, 'value') else urgency_level >= 3
    
    def has_complete_incident_info(self, state: EroskiState) -> bool:
        """
        Verificar si tenemos información completa de la incidencia.
        
        Args:
            state: Estado actual
            
        Returns:
            True si la información está completa
        """
        required_fields = [
            "incident_type",
            "incident_description"
        ]
        
        for field in required_fields:
            value = state.get(field)
            if not value:
                return False
            
            # Verificar longitud mínima para descripción
            if field == "incident_description" and len(str(value)) < 10:
                return False
        
        return True
    
    def get_execution_metrics(self, state: EroskiState) -> Dict[str, Any]:
        """
        Obtener métricas de ejecución del workflow.
        
        Args:
            state: Estado actual
            
        Returns:
            Diccionario con métricas
        """
        from datetime import datetime
        
        start_time = state.get("start_time")
        current_time = datetime.now()
        
        execution_path = state.get("execution_path", [])
        
        return {
            "session_id": state.get("session_id"),
            "employee_id": state.get("employee_id"),
            "store_id": state.get("store_id"),
            "current_node": state.get("current_node"),
            "execution_path": execution_path,
            "total_nodes_visited": len(execution_path),
            "total_time_minutes": (current_time - start_time).total_seconds() / 60 if start_time else 0,
            "resolved": state.get("resolved", False),
            "escalated": state.get("escalation_needed", False),
            "query_type": state.get("query_type"),
            "incident_type": state.get("incident_type"),
            "workflow_name": self.name
        }

# ========== FUNCIONES DE CONVENIENCIA ==========

def create_eroski_workflow() -> EroskiFinalWorkflow:
    """
    Crear y configurar el workflow principal de Eroski.
    
    Returns:
        Instancia del workflow principal
    """
    return EroskiFinalWorkflow()

def get_compiled_eroski_graph():
    """
    Obtener grafo compilado listo para usar.
    
    Returns:
        Grafo compilado con checkpointer
    """
    workflow = create_eroski_workflow()
    return workflow.compile_with_checkpointer()

def get_workflow_description() -> str:
    """
    Obtener descripción del workflow.
    
    Returns:
        Descripción textual del workflow
    """
    workflow = create_eroski_workflow()
    return workflow.get_workflow_description()