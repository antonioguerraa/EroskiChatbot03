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
Eres un asistente experto que evalúa la respuesta generada por un agente de soporte técnico de Eroski.

Tu objetivo es analizar si el agente:
1. Ha identificado claramente el problema del usuario.
2. Necesita confirmar con el usuario si la identificación o la solución es correcta.
3. Ha propuesto una solución específica al problema.
4. Ha formulado una respuesta clara y útil para el usuario.

Contexto relevante:
- Tipo de incidencia: {incident_type}
- Último mensaje del usuario: {last_user_message}

Respuesta generada por el agente:
\"\"\"
{agent_output}
\"\"\"

🔧 INSTRUCCIONES:
Analiza la respuesta del agente y genera un objeto JSON (sin formato Markdown) con los siguientes campos:

{{
  "problem_identified": booleano,          // ¿El agente ha identificado un problema específico?
  "confidence": número entre 0.0 y 1.0,    // Grado de certeza sobre la identificación del problema
  "problema": texto,                       // Descripción del problema identificado o "" si no hay
  "requires_confirmation": booleano,       // ¿Es necesario que el usuario confirme si la solución resuelve el problema?
  "message_to_user": texto,                // Mensaje que el sistema debe enviar al usuario
  "solution_content": texto                // Solución propuesta por el agente o "" si no hay
}}

Completa todos los campos del objeto JSON y asegúrate de que el grado de certeza esté entre 0.0 y 1.0.
IMPORTANTE:
1. En el mensaje al usuario, ("message_to_user") incluye toda la solución propuesta por el agente.
2. Cuando haya una solución propuesta, extrae la solucion del mensaje y reescribela en el campo: "solution_content"
3. Asegurate que se genera el campo "solution_content" con la solución propuesta por el agente o con "" si no la hay
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
            result = chain.invoke(input_data)
            #print(f"👹result: {result}")
            resultado_formato = self._format_result(result, state)
            #print(f"👹resultado_formato: {resultado_formato}")
            #for key, value in resultado_formato.items():
            #    print(f"👹\nkey: {key}, \nvalue: {value}")

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
            "messages": [
                AIMessage(content=result.get("message_to_user", "¿Podrías proporcionar más detalles?"))
            ],
            "solution_content": result.get("solution_content", False),
            "awaiting_user_input": True,
            "confidence": result.get("confidence", 0.0)
        }


    def _get_last_user_message(self, state: Dict[str, Any]) -> str:
        for msg in reversed(state.get("messages", [])):
            if isinstance(msg, HumanMessage):
                return msg.content
        return ""
