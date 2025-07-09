"""
interactive_identification_test.py - Test interactivo con el grafo de identificación

Permite conversar manualmente con el grafo desde consola y ver cómo evoluciona el estado.
"""

import asyncio
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage
from datetime import datetime
from models.eroski_state import EroskiState
from nodes.identificador_orquestador import identificador_orquestador_node
from nodes.identificador_base_de_datos import identificador_base_de_datos_node
from nodes.identificacion_manual import identificacion_manual_node
from langgraph.utils.runnable import RunnableLambda


async def run_interactive_test():
    # Crear el grafo
    builder = StateGraph(EroskiState)

    # Envolver nodos async con RunnableLambda
    builder.add_node("orquestador", identificador_orquestador_node)
    builder.add_node("identificador_base_de_datos", identificador_base_de_datos_node)
    builder.add_node("identificacion_manual", identificacion_manual_node)

    print(f"🌄JGL state.get('authenticated'): {EroskiState.get('authenticated')}")
    print(f"🌄JGL state.get('email_authen_tried'): {EroskiState.get('email_authen_tried')}")
    print(f"🌄JGL state.get('employee_id_authent_tried'): {EroskiState.get('employee_id_authent_tried')}")

    # Ruta condicional
    def route(state: EroskiState):
        if state.get("authenticated"):
            return END
        if state.get("email_authen_tried", False) and state.get("employee_id_authent_tried", False):
            return "identificacion_manual"
        return "identificador_base_de_datos"

    builder.set_entry_point("orquestador")
    builder.add_conditional_edges("orquestador", route, {
        "identificador_base_de_datos": "identificador_base_de_datos",
        "identificacion_manual": "identificacion_manual",
        END: END
    })

    graph = builder.compile()

    # Estado inicial vacío
    state = EroskiState(
        session_id="interactive_test_001",
        messages=[],
        start_time=datetime.now(),
        last_activity=datetime.now()
    )

    print("🧪 Interfaz interactiva de identificación")
    print("Escribe mensajes como si fueras el usuario. Escribe 'salir' para terminar.")

    while True:
        user_input = input("👤 Tú: ").strip()
        if user_input.lower() in ["salir", "exit", "quit"]:
            print("👋 Terminando conversación.")
            break

        state["messages"].append(HumanMessage(content=user_input))
        state["last_activity"] = datetime.now()

        state = await graph.ainvoke(state)

        print("🤖 Bot:")
        for msg in reversed(state["messages"]):
            if hasattr(msg, "content") and isinstance(msg, HumanMessage) is False:
                print(msg.content)
                break

        if state.get("authenticated") or state.get("manual_identification_completed"):
            print("✅ Usuario identificado correctamente.")
            break

if __name__ == "__main__":
    asyncio.run(run_interactive_test())
