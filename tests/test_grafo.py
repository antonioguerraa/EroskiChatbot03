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
from nodes.identificador_manual_node import recoger_datos_empleado_node
from nodes.identificacion_incidencia_node import identificacion_node
from src.nodes.buscar_solucion_node import buscar_solucion_node
from nodes.supervisor_node import supervisor_node
from src.nodes.finalize_node import finalize_node
from nodes.incident_info_adicional_node import recoger_datos_adicionales_node
from nodes.orquestador_busqueda_node import orquestador_busqueda_node
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
        
        self.graph = self.build_graph()
        self.state = self.create_new_session()

    def build_graph(self):
        builder = StateGraph(EroskiState)
        builder.add_node("orquestador", identificador_orquestador_node)
        #builder.add_node("identificador_base_de_datos", identificador_base_de_datos_node)
        builder.add_node("identificador_manual", recoger_datos_empleado_node)
        builder.add_node("identificar_incidencia", identificacion_node)
        builder.add_node("buscar_solucion", buscar_solucion_node)
        

        builder.add_node("supervisor_node", supervisor_node)
        builder.add_node("resolucion_exitosa", finalize_node)
        builder.add_node("info_adicional_incidencia", recoger_datos_adicionales_node)
        builder.add_node("orquestador_busqueda", orquestador_busqueda_node)
        builder.add_edge("orquestador_busqueda", END)

        builder.set_entry_point("orquestador")

        def route(state: EroskiState):
            print("🎛️Entra en el router🎛️")
            print(f"👹 incident_info_adicional_completa: {state.get('incident_info_adicional_completa')}")
            campos = [  
                        "problem_identified",
                        #"busqueda_manual",
                        #"busqueda_faq",
                        #"incident_id",
                        #"incident_department",
                        #"authenticated",
                        #"email_authen_tried",
                        #"employee_id_authent_tried",
                        #"incident_found", 
                        #"incident_type",
                        #"incident_info_adicional",
                        "incident_type_confirmed",
                        "escalation_needed:", 
                        "awaiting_user_input", 
                        "resolved", 
                        "automated_resolution",
                        "incident_id",
                        "awaiting_user_input",
                        #"current_node",
                        "identification_source",
                        #"pending_confirmation"
                      ]
            for campo in campos:
                print(f"🎛️ {campo}: {state.get(campo)}")

            #if not state.get("email_authen_tried") and not state.get("employee_id_authent_tried"):
            #    logging.info("👹 Entra en identificador base de datos")
            #    return "identificador_base_de_datos"
            if state.get("escalation_needed"):
                return "supervisor_node"
            if not state.get("authenticated"):
                logging.info("👹 Entra en recoger_datos")
                return "identificador_manual"
            if not state.get("incident_found"):
                logging.info("👹 Entra en identificar tipo incidencia")
                return "identificar_incidencia"
            if not state.get("incident_info_adicional_completa", False):
                return "info_adicional_incidencia"
            if state.get("solution_found"):
                return "resolucion_exitosa"
            logging.info("👹 Entra en buscar solución")
            return "buscar_solucion"


        
        builder.add_conditional_edges(
            "info_adicional_incidencia",
            lambda state: "buscar_solucion" if state.get("incident_info_adicional_completa", False) 
            else ("supervisor_node" if state.get("escalation_needed")
            else END)
        )

        builder.add_conditional_edges(
            "identificador_manual",
            lambda state: "identificar_incidencia" if state.get("authenticated") 
            else ("supervisor_node" if state.get("escalation_needed")
            else END)
        )

        builder.add_conditional_edges(
            "identificar_incidencia",
            lambda state: "info_adicional_incidencia" if state.get("incident_type_confirmed") 
                else ("supervisor_node" if state.get("escalation_needed") 
                else END
                )
            )

        def ruta_post_buscar_solucion(state: dict) -> str:
            logging.info("👹Entra en el enrutador buscar_solucion")
            #logging.info(f"📊 Estado completo en transición:\n{pprint.pformat(state)}")
            #logging.info(f"👹 ruta_post_buscar_solucion. problem_identified: {state.get('problem_identified')}")
            #logging.info(f"📥 Estado recibido en orquestador_busqueda: {state}")
            if state.get("solution_found"):
                logging.info(f"👹 enrutador solution_found: {state.get('solution_found')}")
                return "resolucion_exitosa"
            if state.get("problem_identified"):
                logging.info(f"👹 problem_identified true: {state.get('problem_identified')}\nVa al nodo orquestador_busqueda")
                return "orquestador_busqueda"
            if state.get("escalation_needed"):
                logging.info(f"👹 enrutador escalation_needed: {state.get('escalation_needed')}")
                return "supervisor_node"
            logging.info("👹 enrutador END")
            return END
        
        builder.add_conditional_edges(
            "buscar_solucion",
            ruta_post_buscar_solucion,
            {
                "orquestador_busqueda": "orquestador_busqueda",
                "supervisor_node": "supervisor_node",
                "resolucion_exitosa": "resolucion_exitosa",
                END: END
            }
        )
        
        builder.add_conditional_edges("orquestador", route, {
            #"identificador_base_de_datos": "identificador_base_de_datos",
            "identificador_manual": "identificador_manual",
            "identificar_incidencia": "identificar_incidencia",
            "buscar_solucion": "buscar_solucion",
            "resolucion_exitosa":"resolucion_exitosa",
            "info_adicional_incidencia":"info_adicional_incidencia",
            "supervisor_node":"supervisor_node",
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

        # 🧠 Guardar cuántos mensajes había antes
        prev_messages = self.state.get("messages", [])
        prev_len = len(prev_messages)

        self.state["messages"] = self.state.get("messages", []) + [HumanMessage(content=user_input)]
        result = await self.graph.ainvoke(self.state)
        #print(f"\n🧩 Resultado del grafo: {result}")
        self.state.update(result)
        # 🧩 Mostrar SOLO los mensajes nuevos del agente
        new_messages = self.state.get("messages", [])[prev_len:]
        
        #messages = self.state.get("messages", [])
        #last = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
        #if last:
        #    print("🧩"*10)
        #    print(f"🧩🤖 AGENTE: {last.content}")
        #    print("🧩"*10)
            # 🧩 Mostrar SOLO los mensajes nuevos del agente
        for m in new_messages:
            if isinstance(m, AIMessage):
                print("🧩" * 10)
                print(f"🤖 AGENTE: {m.content}")
                print("🧩" * 10)

        
        campos = [  
                    "incident_user_name", 
                    "incident_last_name", 
                    #"employee_email", 
                    #"authenticated",
                    'incident_id'
                    #"incident_store_name", 
                    #"incident_department",
                    #"incident_type",
                    #"solution_validation_pending",
                    #"problem_description"
                    #"solution_type",
                    #"solution_content"
                    ]
        for campo in campos:
            print(f"🪐 {campo}: {self.state.get(campo)}") if self.state.get(campo) else None
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
