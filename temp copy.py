from typing import Optional, Dict, Any
from langgraph.types import Command
from langchain_core.messages import AIMessage, HumanMessage
from langchain.agents import create_react_agent, Tool
from langchain_core.runnables import Runnable
from utils.llm.providers import get_llm
from models.eroski_state import EroskiState
from nodes.tools.confirmation_tool import ConfirmationTool
import json
import os
import numpy as np
from sentence_transformers import SentenceTransformer

class IdentificacionNode:
    def __init__(self):
        self.llm = get_llm()
        self.confirmation_tool = ConfirmationTool()
        self.embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
        self.incident_data = self._load_incident_data()
        self.problem_embeddings = self._precompute_embeddings()

    def _load_incident_data(self) -> Dict[str, Dict[str, str]]:
        path = "data/eroski_incidents.json"
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("incident_types", {})

    def _precompute_embeddings(self) -> Dict[str, np.ndarray]:
        all_problems = []
        self.problem_lookup = []  # list of (incident_type, problem_text)

        for incident_type, content in self.incident_data.items():
            problemas = content.get("problemas", {})
            for problema in problemas:
                all_problems.append(problema)
                self.problem_lookup.append((incident_type, problema))

        embeddings = self.embedding_model.encode(all_problems)
        return dict(zip(range(len(embeddings)), embeddings))

    def _find_similar_problems(self, user_message: str, top_k: int = 3) -> Dict[str, float]:
        query_embedding = self.embedding_model.encode([user_message])[0]
        similarities = {
            idx: float(np.dot(query_embedding, emb) / (np.linalg.norm(query_embedding) * np.linalg.norm(emb)))
            for idx, emb in self.problem_embeddings.items()
        }
        top_indices = sorted(similarities, key=similarities.get, reverse=True)[:top_k]
        return {
            self.problem_lookup[i][0]: similarities[i] for i in top_indices
        }

    def identify_incident_type(self, user_message: str) -> Dict[str, Any]:
        top_matches = self._find_similar_problems(user_message)
        if not top_matches:
            return {"incident_type": None, "confidence": 0.0}

        best_type, best_score = list(top_matches.items())[0]
        return {"incident_type": best_type, "confidence": best_score}

    def _build_agent(self) -> Runnable:
        tool = Tool(
            name="identify_incident_type",
            func=self.identify_incident_type,
            description="Identifica el tipo de incidencia dado el mensaje del usuario"
        )
        return create_react_agent(self.llm, tools=[tool])

    async def execute(self, state: EroskiState) -> Command:
        messages = state.get("messages", [])
        last_message = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)

        if not last_message:
            return Command(update={"messages": messages + [AIMessage(content="¿En qué puedo ayudarte?")]})

        # Si estamos esperando confirmación
        if state.get("pending_confirmation") and state.get("tentative_incident_type"):
            respuesta = last_message.content
            decision = self.confirmation_tool.check_confirmation(respuesta)
            if decision == "si":
                return Command(update={
                    "incident_type": state["tentative_incident_type"],
                    "pending_confirmation": False,
                    "tentative_incident_type": None,
                    "current_node": "next_node",
                    "awaiting_user_input": True,
                    "messages": messages + [AIMessage(content="Perfecto, he registrado la incidencia.")]
                })
            elif decision == "no":
                return Command(update={
                    "pending_confirmation": False,
                    "tentative_incident_type": None,
                    "messages": messages + [AIMessage(content="Gracias, volvamos a intentarlo. ¿Qué problema tienes?")]
                })
            else:
                return Command(update={
                    "messages": messages + [AIMessage(content="¿Puedes confirmarlo con un sí o un no?")]
                })

        # Identificar tipo
        agent = self._build_agent()
        result = await agent.ainvoke({"input": last_message.content})
        tipo = result.get("incident_type")
        confianza = result.get("confidence", 0.0)

        if tipo and confianza >= 0.75:
            return Command(update={
                "pending_confirmation": True,
                "tentative_incident_type": tipo,
                "messages": messages + [
                    AIMessage(content=f"Parece que el problema es con el sistema **{tipo}**. ¿Puedes confirmarlo?")
                ]
            })

        return Command(update={
            "messages": messages + [AIMessage(content="Todavía no tengo claro qué tipo de problema es. ¿Puedes explicarlo con más detalle?")]
        })
