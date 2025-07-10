########################################
# Nodo para identificar tipo incidencia
########################################
# nodes/identificacion_node.py

import asyncpg
import numpy as np
from typing import List
from langgraph.types import Command
from models.eroski_state import EroskiState
from langchain_core.messages import HumanMessage, AIMessage
from nodes.tools.confirmation_tool import ConfirmationTool
from utils.llm.providers import get_llm, get_vectorizer
from config.settings import get_settings

class IdentificacionNode:
    def __init__(self):
        self.llm = get_llm()
        self.vectorizer = get_vectorizer()
        self.confirmation_tool = ConfirmationTool()
        self.current_node_name = "identificacion"

        settings = get_settings()
        db = settings.database
        self.conn_str = f"postgresql://{db.user}:{db.password}@{db.host}:{db.port}/{db.name}"

    async def _get_tipo_mas_probable(self, user_input: str) -> str:
        """Busca el tipo de incidencia más similar desde la base de datos."""
        conn = await asyncpg.connect(self.conn_str)
        rows = await conn.fetch("SELECT tipo_incidencia, embedding FROM tipo_incidencia_vectorizado")

        user_vector = np.array(self.vectorizer.embed(user_input), dtype=np.float32)

        best_match = None
        best_score = -1

        for row in rows:
            tipo = row["tipo_incidencia"]
            embedding = np.array(row["embedding"], dtype=np.float32)
            score = np.dot(user_vector, embedding)
            if score > best_score:
                best_score = score
                best_match = tipo

        await conn.close()
        return best_match

    async def execute(self, state: EroskiState) -> Command:
        messages = state.get("messages", [])
        if not messages or not isinstance(messages[-1], HumanMessage):
            return Command(update={})

        user_input = messages[-1].content

        # 🔁 Confirmación pendiente
        if state.get("pending_confirmation"):
            decision = self.confirmation_tool.check_confirmation(user_input)
            if decision == "si":
                return Command(update={
                    "incident_type": state.get("modificaciones_pendientes", {}).get("incident_type"),
                    "pending_confirmation": False,
                    "modificaciones_pendientes": None,
                    "messages": [AIMessage(content="Perfecto, procedo a registrar la incidencia.")],
                    "current_node": self.current_node_name,
                    "awaiting_user_input": False
                })
            elif decision == "no":
                return Command(update={
                    "pending_confirmation": False,
                    "modificaciones_pendientes": None,
                    "messages": [AIMessage(content="De acuerdo, ¿podrías describirme nuevamente la incidencia?")],
                    "current_node": self.current_node_name,
                    "awaiting_user_input": True
                })
            else:
                return Command(update={
                    "messages": [AIMessage(content="¿Puedes confirmarme con un sí o un no, por favor?")],
                    "awaiting_user_input": True
                })

        # 🧠 Identificación semántica desde DB
        try:
            tipo_probable = await self._get_tipo_mas_probable(user_input)
            confirm_message = f"He entendido que estás hablando de una incidencia del tipo **{tipo_probable}**. ¿Puedes confirmarlo?"
            return Command(update={
                "modificaciones_pendientes": {"incident_type": tipo_probable},
                "pending_confirmation": True,
                "messages": [AIMessage(content=confirm_message)],
                "current_node": self.current_node_name,
                "awaiting_user_input": True
            })
        except Exception as e:
            return Command(update={
                "messages": messages + [AIMessage(content="⚠️ Ha ocurrido un error identificando la incidencia. Por favor, intenta describirlo de nuevo.")],
                "awaiting_user_input": True,
                "current_node": self.current_node_name
            })
