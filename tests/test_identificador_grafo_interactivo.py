#!/usr/bin/env python3
"""
Tester interactivo para grafo de identificación:
- identificador_orquestador
- identificador_base_de_datos
- recoger_datos_empleado_node
"""

import os
import sys
import asyncio
from datetime import datetime

# Añadir raíz del proyecto al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.eroski_state import create_initial_eroski_state, EroskiState
from nodes.identificador_orquestador import identificador_orquestador_node
from nodes.identificador_base_de_datos import identificador_base_de_datos_node
from nodes.identificador_manual_node import recoger_datos_empleado_node
from nodes.classify_node import classify_node
from nodes.identificacion_incidencia_node import identificacion_node
from nodes.buscar_solucion_node import buscar_solucion_node
from langgraph.graph import StateGraph, END
from langchain_core.messages import AIMessage, HumanMessage
import logging
logging.basicConfig(
    level=logging.INFO,  # Puedes usar DEBUG, INFO, WARNING, ERROR, CRITICAL
    format='[%(asctime)s] %(levelname)s in %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)
class InteractiveGrafoTester:
    def __init__(self):
        self.session_counter = 0
        self.graph = self.build_graph()
        self.state = self.create_new_session()

    def build_graph(self):
        builder = StateGraph(EroskiState)
        builder.add_node("orquestador", identificador_orquestador_node)
        #builder.add_node("identificador_base_de_datos", identificador_base_de_datos_node)
        builder.add_node("identificador_manual", recoger_datos_empleado_node)
        builder.add_node("identificar_incidencia", identificacion_node)
        builder.add_node("buscar_solucion", buscar_solucion_node)
        
        builder.set_entry_point("orquestador")


        def route(state: EroskiState):
            print("🎛️Entra en el router🎛️")
            campos = [  
                        "incident_id",
                        "incident_department",
                        "authenticated",
                        "email_authen_tried",
                        "employee_id_authent_tried",
                        "solution_found", 
                        "incident_type",
                        "incident_type_confirmed",
                        "escalation_needed:", 
                        "awaiting_user_input", 
                        "resolved", 
                        "automated_resolution",
                        "incident_id",
                        "awaiting_user_input",
                        "current_node",
                        "identification_source",
                        "pending_confirmation"
                      ]
            for campo in campos:
                print(f"🎛️ {campo}: {state.get(campo)}")

            #if not state.get("email_authen_tried") and not state.get("employee_id_authent_tried"):
            #    logging.info("👹 Entra en identificador base de datos")
            #    return "identificador_base_de_datos"
            if not state.get("authenticated"):
                logging.info("👹 Entra en recoger_datos")
                return "identificador_manual"
            if not state.get("incident_type_confirmed"):
                logging.info("👹 Entra en identificar tipo incidencia")
                return "identificar_incidencia"
            logging.info("👹 Entra en buscar solución")
            return "buscar_solucion"

        def ruta_post_identificacion_db(state: EroskiState) -> str:
            if state.get("authenticated"):
                return "identificar_incidencia"
            else:
                return END

        #builder.add_conditional_edges(
        #    "identificador_base_de_datos",
        #    ruta_post_identificacion_db,
        #    {
        #        "identificar_incidencia": "identificar_incidencia",
        #        END: END
        #    }
        #)

        def ruta_post_identificacion_manual(state: EroskiState) -> str:
            return "identificar_incidencia" if state.get("authenticated") else END

        builder.add_conditional_edges(
            "identificador_manual",
            ruta_post_identificacion_manual,
            {
                "identificar_incidencia": "identificar_incidencia",
                END: END
            }
        )


        def ruta_post_identificar_incidencia(state: EroskiState) -> str:
            return "buscar_solucion" if state.get("incident_type_confirmed") else END

        builder.add_conditional_edges(
            "identificar_incidencia",
            ruta_post_identificar_incidencia,
            {
                "buscar_solucion": "buscar_solucion",
                END: END
            }
        )

        builder.add_edge("buscar_solucion", END)

        builder.add_conditional_edges(
            "buscar_solucion",
            lambda state: "buscar_solucion" if state.get("extra_info_provided") 
                else ("resolucion_exitosa" if state.get("solution_found") 
                else ("escalation" if state.get("escalation_needed") 
                else END
                )
            )
        )

        
        builder.add_conditional_edges("orquestador", route, {
            #"identificador_base_de_datos": "identificador_base_de_datos",
            "identificador_manual": "identificador_manual",
            "identificar_incidencia": "identificar_incidencia",
            "buscar_solucion": "buscar_solucion",
            END: END
        })

        return builder.compile()

    def create_new_session(self) -> EroskiState:
        self.session_counter += 1
        session_id = f"test_session_{self.session_counter}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        return create_initial_eroski_state(session_id=session_id, timezone="Europe/Madrid")

    async def handle_input(self, user_input: str):
        if user_input.lower() in {"exit", "quit"}:
            return False
        elif user_input.lower() == "reset":
            self.state = self.create_new_session()
            print("🔄 Nueva sesión iniciada")
            return True
        elif user_input.lower() == "state":
            for k, v in self.state.items():
                if k != "messages":
                    print(f"{k}: {v}")
            return True

        self.state["messages"] = self.state.get("messages", []) + [HumanMessage(content=user_input)]
        result = await self.graph.ainvoke(self.state)
        #print(f"\n🧩 Resultado del grafo: {result}")
        self.state.update(result)
        
        messages = self.state.get("messages", [])
        last = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
        if last:
            print("🧩"*100)
            print(f"🧩🤖 AGENTE: {last.content}")
            print("🧩"*100)
            campos = ["employee_name", "employee_lastname", "incident_store_name", "incident_department"]
            for campo in campos:
                print(f"{campo}: {self.state.get(campo)}") if self.state.get(campo) else None
        return True

    async def run(self):
        print("🧪 Tester interactivo del grafo de identificación\nEscribe 'exit' para salir, 'reset' para reiniciar, 'state' para ver estado\n")
        while True:
            user_input = input("\n👤 Tú: ").strip()
            if not await self.handle_input(user_input):
                break

async def main():
    tester = InteractiveGrafoTester()
    await tester.run()

if __name__ == "__main__":
    
    asyncio.run(main())
