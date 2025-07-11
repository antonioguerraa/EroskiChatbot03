from typing import Dict, Any
import logging
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field
from utils.llm.providers import get_llm

logger = logging.getLogger(__name__)

class AgentOutputSchema(BaseModel):
    problem_identified: bool
    confidence: float = Field(ge=0.0, le=1.0)
    problema: str
    requires_confirmation: bool
    solution_found: bool
    message_to_user: str

class AgentOutputLLMVerifier:
    """
    Analiza la salida del agente principal para determinar:
    - Si el problema ha sido identificado
    - Si se necesita confirmación
    - Si se ha encontrado una solución
    - Qué mensaje mostrar al usuario
    """

    def __init__(self):
        self.llm = get_llm()
        self.parser = JsonOutputParser(pydantic_object=AgentOutputSchema)
        self.prompt = ChatPromptTemplate.from_template(
            """
Eres un asistente experto que analiza la salida de un agente de soporte técnico de Eroski.

Tu tarea es:
1. Determinar si el agente ha identificado claramente el problema del usuario.
2. Evaluar si necesita confirmación.
3. Determinar si se encontró una solución.
4. Proporcionar un mensaje listo para enviar al usuario.

Contexto:
- Tipo de incidencia: {incident_type}
- Último mensaje del usuario: {last_user_message}
- Respuesta del agente:
\"\"\"
{agent_output}
\"\"\"

INSTRUCCIONES:

Responde en JSON (sin markdown) con los siguientes campos:
{{
  "problem_identified": bool,
  "confidence": float entre 0.0 y 1.0,
  "problema": string,
  "requires_confirmation": bool,
  "message_to_user": string
}}

-si el agente proporciona una solución, debe pedir al usuario confirmación sobre si la solución propuesta resuelva la incidencia. En este caso, requires confirmation se pondrá a True
-requires confirmation es False si el usuario debe proporcionar informacion adicional para resolver el problema.
-message_to_user es el mensaje que se enviará al usuario.

"""
        )

    def analyze(self, agent_output: str, state: Dict[str, Any]) -> Dict[str, Any]:
        input_data = {
            "agent_output": agent_output,
            "incident_type": state.get("incident_type", ""),
            "last_user_message": self._get_last_user_message(state)
        }

        try:
            chain = self.prompt | self.llm | self.parser
            print("👹check 1")
            result = chain.invoke(input_data)
            print(f"result: {result}")
            print("👹check 2")
            resultado_formato = self._format_result(result, state)
            print(f"resultado_formato: {resultado_formato}")
            print("👹check 3")
            return resultado_formato

        except Exception as e:
            logger.warning(f"LLMVerifier failed: {e}")
            return {
                "problem_identified": False,
                "solution_found": False,
                "messages": state.get("messages", []) + [
                    AIMessage(content="¿Puedes proporcionar más detalles o reformular el problema?")
                ],
                "awaiting_user_input": True
            }

    def _format_result(self, result: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "problem_description": result.get("problema"),
            "problem_identified": result.get("problem_identified", False),
            "pending_confirmation": result.get("requires_confirmation", False),
            "messages": state.get("messages", []) + [
                AIMessage(content=result.get("message_to_user", "¿Podrías proporcionar más detalles?"))
            ],
            "awaiting_user_input": True
        }

    def _get_last_user_message(self, state: Dict[str, Any]) -> str:
        for msg in reversed(state.get("messages", [])):
            if isinstance(msg, HumanMessage):
                return msg.content
        return ""
