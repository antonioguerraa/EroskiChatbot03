from langchain_core.messages import AIMessage, HumanMessage, BaseMessage
from typing import List

def construir_historico_mensajes(self, messages: list) -> str:
    historico = []
    for msg in messages:
        if msg.__class__.__name__ == "HumanMessage":
            historico.append(f"Usuario: {msg.content}")
        elif msg.__class__.__name__ == "AIMessage":
            historico.append(f"Asistente: {msg.content}")
        # Opcional: manejar ToolMessage, FunctionMessage, etc. si los usas.
    return "\n".join(historico)

def format_full_chat_history(messages: List[BaseMessage], max_messages: int = 100) -> str:
    lines = []
    for msg in messages[-max_messages:]:
        if isinstance(msg, HumanMessage):
            lines.append(f"👤 Usuario: {msg.content}")
        elif isinstance(msg, AIMessage):
            lines.append(f"🤖 Asistente: {msg.content}")
    return "\n".join(lines)