from typing import Optional
from langgraph.types import Command
from models.eroski_state import EroskiState
from nodes.base_node import BaseNode
from utils.routing import ClassificationRouter
from utils.llm.providers import get_llm
from utils.incident_helpers import IncidentHelpersFactory
from utils.two_phase_classifier import execute_two_phase_classification
from pathlib import Path


class LLMDrivenClassifyNode(BaseNode):
    """
    Nodo simplificado de clasificación de incidencias con LLM
    """

    def __init__(self):
        super().__init__("classify")
        self.llm = get_llm()
        self.router = ClassificationRouter(self)
        self.incidents_file = Path("incidents_database.json")
        self.incident_types = self._load_incident_types()
        self.helpers = self._load_helpers()

        self.code_manager = self.helpers.get("code_manager")
        self.solution_searcher = self.helpers.get("solution_searcher")
        self.confirmation_handler = self.helpers.get("confirmation_handler")
        self.persistence_manager = self.helpers.get("persistence_manager")

    def get_required_fields(self):
        return ["messages", "authenticated"]

    def get_actor_description(self):
        return "Clasifico incidencias técnicas usando IA conversacional y propongo soluciones"

    def _load_incident_types(self):
        from config.incident_config import IncidentConfigLoader
        try:
            return IncidentConfigLoader().get_incident_types()
        except Exception as e:
            self.logger.error(f"❌ Error cargando incident types: {e}")
            return {}

    def _load_helpers(self):
        try:
            return IncidentHelpersFactory.create_all_helpers(
                incident_types=self.incident_types,
                incidents_file=self.incidents_file
            )
        except Exception as e:
            self.logger.error(f"❌ Error creando helpers: {e}")
            return {}

    def _initialize_incident_if_needed(self, state: EroskiState) -> EroskiState:
        if not state.get("incident_id"):
            code = self.code_manager.generate_unique_code()
            print(f"👹code generado: {code}")
            new_state = {**state, "incident_id": code}

            self.persistence_manager.initialize_incident(new_state, code)
            return new_state
        return state

    async def execute(self, state: EroskiState) -> Command:
        print("👹Entra en el clasificador")
        try:
            self.logger.info("🚀 Nodo Classify iniciado")
            state = self._initialize_incident_if_needed(state)
            return await execute_two_phase_classification(state)
        except Exception as e:
            self.logger.error(f"❌ Error en nodo classify: {e}")
            return self._handle_error(state, str(e))

    def _handle_error(self, state: EroskiState, error_message: str) -> Command:
        from langchain_core.messages import AIMessage

        error_response = """⚠️ **Error Temporal**\n\nHa ocurrido un problema técnico. Intenta describir tu incidencia de nuevo o contacta con un supervisor."""

        return Command(
            update={
                "messages": state.get("messages", []) + [AIMessage(content=error_response)],
                "current_node": "escalate",
                "error_occurred": True,
                "error_details": error_message
            }
        )

# =============================================================================
# FUNCIÓN PARA CREAR INSTANCIA
# =============================================================================

async def classify_node(state: EroskiState) -> EroskiState:
    """
    Función wrapper para LangGraph - Nodo Classify LLM-driven
    
    Args:
        state: Estado actual como dict
        
    Returns:
        Estado actualizado como dict
    """
    
    # Crear instancia del nodo
    node = LLMDrivenClassifyNode()
    
    # Ejecutar el nodo (retorna Command)
    command = await node.execute(state)
    
    # Aplicar las actualizaciones al estado
    updated_state = {**state, **command.update}
    
    # Logging para verificar actualizaciones
    
    return updated_state
