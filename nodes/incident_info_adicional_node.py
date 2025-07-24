# =====================================================
# nodes/incident_info_adicional_node.py - Nodo de recoje información adicional del incidente
# =====================================================

# nodes/recoger_info_adicional_node.py
from typing import List, Dict
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.runnables import RunnableSequence
from langchain_core.prompts import PromptTemplate
from langchain_core.pydantic_v1 import BaseModel, Field
from langgraph.graph.message import add_messages

from models.eroski_state import EroskiState
from langgraph.types import Command
from nodes.base_node import BaseNode
from utils.llm.providers import get_llm
from utils.cargar_incidentes import EroskiIncidentsManager
from utils.incident_manager import get_incident_manager
from utils.construir_historico_mensajes import format_full_chat_history
import logging
logger = logging.getLogger(__name__)
# ----------------------
# Pydantic output model
# ----------------------
class InfoAdicionalResponse(BaseModel):
    info_recogida: Dict[str, str] = Field(...)
    fields_pending: List[str] = Field(...)
    escalation_needed: bool = Field(...)
    message_to_user: str = Field(...)

# ----------------------
# Nodo principal
# ----------------------
class RecogerDatosAdicionalesNode(BaseNode):
    def __init__(self):
        super().__init__("RecogerInfoAdicional")
        self.incidents_manager = EroskiIncidentsManager()
        self.node_name = "RecogerDatosAdicionales"
        self.llm = get_llm()
        self.parser = JsonOutputParser(pydantic_object=InfoAdicionalResponse)
        self.chain = self._setup_chain()


    def _setup_chain(self) -> RunnableSequence:
        prompt = PromptTemplate(
            template="""
Eres un asistente de soporte de Eroski.

El usuario ha reportado un problema con el equipo: **{incident_type}**.
Necesitamos recopilar esta información adicional: {info_adicional}

Este es el historial de la conversación:
{chat_history}

INSTRUCCIONES:
- Si el usuario ya ha proporcionado algún dato, no lo repitas.
- Si falta información, pídela de una en una.
- Si el usuario no sabe algo, acepta su respuesta, guardala en el campo correspondiente, y avanza.
- Si el usuario responde algo irrelevante o no relacionado con la información solicitada, redirígelo con amabilidad a proporcionar el dato pendiente.
- Si el usuario menciona que quiere hablar con un supervisor, marca `escalation_needed: true`.
- Si el usuario corrige algo ya recogido, actualiza el valor.
- Rellena el campo que estas solicitando con lo que te indique el usuario
- Devuelve un mensaje natural, breve y amable.


DEVUELVE SOLO ESTE JSON (sin markdown):
{format_instructions}
""",
            input_variables=["incident_type", "info_adicional", "chat_history"],
            partial_variables={"format_instructions": self.parser.get_format_instructions()}
        )
        return prompt | self.llm | self.parser

    def get_required_fields(self) -> List[str]:
        return ["incident_type", "messages"]

    def get_actor_description(self) -> str:
        return "Recoge información adicional relacionada con el tipo de incidencia confirmada"


    async def execute(self, state: EroskiState) -> Command:
        logger.info("👹👹👹\n\n\nEntra en bucar info adicional\n\n\n👹👹👹")
        incident_type = state.get("incident_type")
        logger.info(f"👹incident_type: {incident_type}")
        incident_id = state.get("incident_id", None)

        if not incident_id:
            incident_id = get_incident_manager().manage_incident(state)

        info_adicional = self.incidents_manager.get_info_adicional(incident_type)
        ya_recogido = state.get("incident_info_adicional", {})
        attempts = state.get("additional_info_attempts", 0)
        pendientes = [campo for campo in info_adicional if campo not in ya_recogido]

        logger.info(f"👹 incident_id: {incident_id}")
        logger.info(f"👹info_adicional: {info_adicional}")
        logger.info(f"👹 ya_recogido en el state: {ya_recogido}")
        logger.info(f"👹check 1: info adicional {info_adicional}")
        logger.info(f"👹check 2: pendientes {pendientes}")

        if not pendientes:
            return Command(update={
                "incident_id":incident_id,
                "current_node": "buscar_solucion",
                "incident_info_adicional_completa": True,
                "awaiting_user_input": False
            })

        if attempts >= 3:
            return Command(update={
                "incident_id":incident_id,
                "messages": add_messages([], [AIMessage(content="No hemos podido recoger toda la información adicional. Pasamos a la siguiente fase.")]),
                "current_node": "buscar_solucion",
                "incident_info_adicional_completa": False,
                "awaiting_user_input": False
            })

        chat_history = format_full_chat_history(state.get("messages", []))

        response: InfoAdicionalResponse = await self.chain.ainvoke({
            "incident_type": incident_type,
            "info_adicional": ", ".join(pendientes),
            "chat_history": chat_history
        })


        logger.info(f"👹response: {response}")

        update = {
            "incident_id":incident_id,
            "messages": [AIMessage(content=response["message_to_user"])],
            #"incident_info_adicional": {**ya_recogido, **response["info_recogida"]},
            "incident_info_adicional": {**ya_recogido, **response["info_recogida"]},
            "additional_info_attempts": attempts + 1
        }
        logging.info(f"👹update1: {update}")
    # ...

        if response["escalation_needed"]:
            update.update({
                "incident_id":incident_id,
                "escalation_needed": True,
                "current_node": "supervisor",
                "awaiting_user_input": False
            })
        elif response["fields_pending"]:
            update.update({
                "incident_id":incident_id,
                "current_node": "info_adicional_incidencia",
                "awaiting_user_input": True,
                "incident_info_adicional_completa": False,
            })
        else:
            update.update({
                "incident_id":incident_id,
                "current_node": "buscar_solucion",
                "awaiting_user_input": False,
                "incident_info_adicional_completa": True
            })

        logging.info(f"👹update2: {update}")
        return Command(update=update)



# Factory para LangGraph
async def recoger_datos_adicionales_node(state: EroskiState) -> Command:
    node = RecogerDatosAdicionalesNode()
    return await node.execute(state)
