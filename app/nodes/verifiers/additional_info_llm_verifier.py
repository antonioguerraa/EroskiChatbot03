# nodes/verifiers/additional_info_llm_verifier.py
from typing import Dict, Any
from app.utils.llm.providers import get_llm
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import BaseMessage, HumanMessage
import logging

logger = logging.getLogger(__name__)

class AdditionalInfoLLMVerifier:
    def __init__(self):
        self.llm = get_llm()
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """
Eres un verificador que debe determinar si un mensaje del usuario, dado tras rechazar una solución, contiene información adicional útil para identificar mejor el problema.

CONSIDERA COMO ÚTIL:
- Descripciones técnicas, nuevos síntomas, mensajes de error, comportamientos nuevos, etc.

NO ES ÚTIL:
- Respuestas vagas ("no", "sigue igual", "nada"), quejas, afirmaciones generales sin detalles.

INSTRUCCIONES:
Responde únicamente con "si" si contiene información útil, o "no" si no contiene nada útil.
"""),
            ("human", "Historial reciente:\n{user_history}\n\nÚltimo mensaje del usuario: {last_message}")
        ])

    def analyze(self, last_message: str, state: Dict[str, Any]) -> bool:
        try:
            history = "\n".join(
                [m.content for m in state.get("messages", []) if isinstance(m, HumanMessage)][-4:]
            )
            chain = self.prompt | self.llm
            response = chain.invoke({
                "last_message": last_message,
                "user_history": history
            }).content.strip().lower()
            return response == "si"
        except Exception as e:
            logger.warning(f"Error en AdditionalInfoLLMVerifier: {e}")
            return False
