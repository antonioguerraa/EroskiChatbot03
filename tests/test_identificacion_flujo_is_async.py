"""
test_identificacion_flujo.py - Test actualizado para LangGraph 0.4.8 con is_async=True
"""

import asyncio
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage
from datetime import datetime
from models.eroski_state import EroskiState
from nodes.identificador_orquestador import identificador_orquestador_node
from nodes.identificador_base_de_datos import identificador_base_de_datos_node
from nodes.identificacion_manual import identificacion_manual_node

async def test_flujo_identificacion():
    # Crear grafo
    builder = StateGraph(EroskiState)

    # Añadir nodos con is_async=True (LangGraph >= 0.4.8)
    builder.add_node("orquestador", identificador_orquestador_node)
    builder.add_node("identificador_base_de_datos", identificador_base_de_datos_node)
    builder.add_node("identificacion_manual", identificacion_manual_node)


    # Ruta condicional basada en flags del estado
    def route(state: EroskiState):
        if state.get("authenticated"):
            return END
        if state.get("email_authen_tried", False) and state.get("employee_id_authent_tried", False):
            return "identificacion_manual"
        return "identificador_base_de_datos"

    # Transiciones
    builder.set_entry_point("orquestador")
    builder.add_conditional_edges("orquestador", route, {
        "identificador_base_de_datos": "identificador_base_de_datos",
        "identificacion_manual": "identificacion_manual",
        END: END
    })

    graph = builder.compile()

    # Estado inicial mínimo
    initial_state = EroskiState(
        session_id="test_session_001",
        messages=[HumanMessage(content="Mi email es prueba@eroski.es")],
        start_time=datetime.now(),
        last_activity=datetime.now()
    )

    print("🚀 Ejecutando flujo de identificación...")

    final_state = await graph.ainvoke(initial_state)

    print("✅ Estado final:")
    for k, v in final_state.items():
        print(f"{k}: {v}")

    # Verificación de éxito
    assert final_state.get("authenticated") or final_state.get("manual_identification_completed"),         "El usuario no fue autenticado correctamente"

if __name__ == "__main__":
    asyncio.run(test_flujo_identificacion())
