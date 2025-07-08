"""
test_identificacion_flujo.py - Test de integración para el flujo de identificación

Verifica que los tres nodos:
- identificador_orquestador
- identificador_base_de_datos
- identificacion_manual

Funcionan correctamente dentro de un StateGraph.
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
    # 1. Crear grafo de estado
    builder = StateGraph(EroskiState)

    # 2. Añadir nodos
    builder.add_node("orquestador", identificador_orquestador_node)
    builder.add_node("identificador_base_de_datos", identificador_base_de_datos_node)
    builder.add_node("identificacion_manual", identificacion_manual_node)

    # 3. Definir transición dinámica
    def route(state: EroskiState):
        if state.get("authenticated"):
            return END
        if state.get("email_authen_tried", False) and state.get("employee_id_authent_tried", False):
            return "identificacion_manual"
        return "identificador_base_de_datos"

    builder.set_entry_point("orquestador")
    builder.add_edge("orquestador", route)

    # 4. Compilar grafo
    graph = builder.compile()

    # 5. Crear estado inicial de prueba
    initial_state = EroskiState(
        session_id="test_session_001",
        messages=[HumanMessage(content="Mi email es prueba@eroski.es")],
        start_time=datetime.now(),
        last_activity=datetime.now()
    )

    print("🚀 Ejecutando flujo de identificación...")

    # 6. Ejecutar el grafo
    final_state = await graph.invoke(initial_state)

    print("✅ Estado final:")
    for k, v in final_state.items():
        print(f"{k}: {v}")

    # 7. Verificar autenticación
    assert final_state.get("authenticated") is True or final_state.get("manual_identification_completed") is True,         "El usuario no fue autenticado por ningún método"

if __name__ == "__main__":
    asyncio.run(test_flujo_identificacion())
