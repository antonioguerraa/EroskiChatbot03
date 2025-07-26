# workflow.py

from langgraph.graph import StateGraph, END
from app.models.eroski_state import EroskiState
from app.nodes.identificador_orquestador import identificador_orquestador_node
from app.nodes.identificador_manual_node import recoger_datos_empleado_node
from app.nodes.identificacion_incidencia_node import identificacion_node
from app.nodes.buscar_solucion_node import buscar_solucion_node
from app.nodes.supervisor_node import supervisor_node
from app.nodes.finalize_node import finalize_node
from app.nodes.incident_info_adicional_node import recoger_datos_adicionales_node
from app.nodes.orquestador_busqueda_node import orquestador_busqueda_node
import logging

logging.basicConfig(level=logging.INFO)


def build_eroski_graph_kk() -> StateGraph:
    builder = StateGraph(EroskiState)

    builder.add_node("orquestador", identificador_orquestador_node)
    builder.add_node("identificador_manual", recoger_datos_empleado_node)
    builder.add_node("identificar_incidencia", identificacion_node)
    builder.add_node("buscar_solucion", buscar_solucion_node)
    builder.add_node("supervisor_node", supervisor_node)
    builder.add_node("resolucion_exitosa", finalize_node)
    builder.add_node("info_adicional_incidencia", recoger_datos_adicionales_node)
    builder.add_node("orquestador_busqueda", orquestador_busqueda_node)
    builder.add_edge("orquestador_busqueda", END)

    builder.set_entry_point("orquestador")

    # 🔀 Enrutadores condicionales
    def route(state: EroskiState):
        if state.get("escalation_needed"):
            return "supervisor_node"
        if not state.get("authenticated"):
            return "identificador_manual"
        if not state.get("incident_found"):
            return "identificar_incidencia"
        if not state.get("incident_info_adicional_completa", False):
            return "info_adicional_incidencia"
        if state.get("solution_found"):
            return "resolucion_exitosa"
        return "buscar_solucion"

    builder.add_conditional_edges("orquestador", route, {
        "identificador_manual": "identificador_manual",
        "identificar_incidencia": "identificar_incidencia",
        "buscar_solucion": "buscar_solucion",
        "resolucion_exitosa": "resolucion_exitosa",
        "info_adicional_incidencia": "info_adicional_incidencia",
        "supervisor_node": "supervisor_node",
        END: END
    })

    builder.add_conditional_edges("identificador_manual", lambda state:
        "identificar_incidencia" if state.get("authenticated")
        else ("supervisor_node" if state.get("escalation_needed") else END)
    )

    builder.add_conditional_edges("identificar_incidencia", lambda state:
        "info_adicional_incidencia" if state.get("incident_type_confirmed")
        else ("supervisor_node" if state.get("escalation_needed") else END)
    )

    builder.add_conditional_edges("info_adicional_incidencia", lambda state:
        "buscar_solucion" if state.get("incident_info_adicional_completa")
        else ("supervisor_node" if state.get("escalation_needed") else END)
    )

    def ruta_post_buscar_solucion(state: EroskiState):
        if state.get("solution_found"):
            return "resolucion_exitosa"
        if state.get("problem_identified"):
            return "orquestador_busqueda"
        if state.get("escalation_needed"):
            return "supervisor_node"
        return END

    builder.add_conditional_edges("buscar_solucion", ruta_post_buscar_solucion, {
        "orquestador_busqueda": "orquestador_busqueda",
        "supervisor_node": "supervisor_node",
        "resolucion_exitosa": "resolucion_exitosa",
        END: END
    })

    return builder.compile()
def build_eroski_graph()-> StateGraph :
    builder = StateGraph(EroskiState)
    builder.add_node("orquestador", identificador_orquestador_node)
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

# 🚀 Función principal para ejecutar el grafo
graph = build_eroski_graph()

async def run_graph(state: EroskiState) -> EroskiState:
    """Ejecuta el grafo LangGraph con el estado dado."""
    return await graph.ainvoke(state)
