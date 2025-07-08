from langchain_core.messages import AIMessage
from typing import Optional
from models.eroski_state import EroskiState


def get_last_ai_message(state: EroskiState) -> Optional[str]:
    for msg in reversed(state["messages"]):
        if isinstance(msg, AIMessage):
            return msg.content
    return None  # Si no hay mensaje del tipo AI