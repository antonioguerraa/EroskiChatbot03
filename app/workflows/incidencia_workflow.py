from app.graphs.eroski_graph import build_eroski_graph
from app.models.eroski_state import create_initial_eroski_state
from langchain_core.messages import HumanMessage, AIMessage

async def procesar_mensaje_whatsapp(phone_number: str, mensaje: str) -> str:
    grafo = build_eroski_graph()
    state = create_initial_eroski_state(session_id=phone_number)
    state["channel"] = "whatsapp"
    state["messages"] = [HumanMessage(content=mensaje)]
    result = await grafo.ainvoke(state)

    for msg in reversed(result["messages"]):
        if isinstance(msg, AIMessage):
            return msg.content
    
    return "No he podido procesar tu mensaje."
