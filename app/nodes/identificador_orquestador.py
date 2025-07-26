"""
identificador_orquestador.py - Nodo orquestador de identificación

Este nodo decide dinámicamente si usar la identificación por base de datos o manual,
en función del estado del flujo de identificación del usuario.
"""

from langgraph.types import Command
from datetime import datetime
from app.models.eroski_state import EroskiState
#from app.nodes.identificacion_manual import identificacion_manual_node
import logging

class IdentificadorOrquestadorNode:
    """
    Nodo orquestador que decide si usar identificación automática (BD)
    o manual (conversación asistida por LLM) según los flags del estado.
    """

    def __init__(self):
        self.node_name = "identificador_orquestador"

    async def execute(self, state: EroskiState) -> Command:
        # Si el usuario ya está autenticado, no repetir
        print("🤖🤖🤖Nodo Orquestador🤖🤖🤖")
        return Command(update={
            "current_node": self.node_name,
            "last_activity": datetime.now()
        })


   

    def _debe_usar_identificacion_manual(self, state: EroskiState) -> bool:
        return (
            state.get("email_authen_tried", False) and
            state.get("employee_id_authent_tried", False) and
            not state.get("authenticated", False)
        )


# Wrapper para LangGraph
async def identificador_orquestador_node(state: EroskiState) -> Command:
    logging.info(f"👹 Entra en el Orquestador")
    node = IdentificadorOrquestadorNode()
    return await node.execute(state)


# Export
__all__ = ["identificador_orquestador_node", "IdentificadorOrquestadorNode"]
