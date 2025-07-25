#!/usr/bin/env python3
"""
Workflow Refactorizado - Chatbot Eroski
Basado en el test_grafo.py que está funcionando correctamente
"""

import os
import sys
import asyncio
import logging
from datetime import datetime
from typing import Optional
from pathlib import Path

import chainlit as cl
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import StateGraph, END

# Configurar path del proyecto
ROOT_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR))

# Importaciones del proyecto (igual que en test_grafo.py)
from models.eroski_state import create_initial_eroski_state, EroskiState
from nodes.identificador_orquestador import identificador_orquestador_node
from nodes.identificador_manual_node import recoger_datos_empleado_node
from nodes.identificacion_incidencia_node import identificacion_node
from nodes.buscar_solucion_node import buscar_solucion_node
from nodes.supervisor_node import supervisor_node
from nodes.finalize_node import finalize_node
from nodes.incident_info_adicional_node import recoger_datos_adicionales_node
from nodes.orquestador_busqueda_node import orquestador_busqueda_node

# Configuración de logging (igual que en test_grafo.py)
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s in %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

class EroskiWorkflow:
    """
    Workflow principal basado en la implementación exitosa de test_grafo.py
    """
    
    def __init__(self):
        """Inicializar el workflow"""
        self.session_counter = 0
        self.graph = self.build_graph()
        logger.info("🤖 EroskiWorkflow inicializado correctamente")
    
    def build_graph(self):
        """
        Construir el grafo exactamente como en test_grafo.py (que funciona)
        """
        builder = StateGraph(EroskiState)
        
        # Añadir nodos exactamente como en test_grafo.py
        builder.add_node("orquestador", identificador_orquestador_node)
        builder.add_node("identificador_manual", recoger_datos_empleado_node)
        builder.add_node("identificar_incidencia", identificacion_node)
        builder.add_node("buscar_solucion", buscar_solucion_node)
        builder.add_node("supervisor_node", supervisor_node)
        builder.add_node("resolucion_exitosa", finalize_node)
        builder.add_node("info_adicional_incidencia", recoger_datos_adicionales_node)
        
        # Opcional: añadir orquestador de búsqueda si está disponible
        try:
            builder.add_node("orquestador_busqueda", orquestador_busqueda_node)
            orquestador_busqueda_available = True
        except:
            orquestador_busqueda_available = False
            logger.info("orquestador_busqueda_node no disponible, continuando sin él")
        
        builder.set_entry_point("orquestador")

        # Función de enrutamiento desde orquestador (copiada de test_grafo.py)
        def router_orquestador(state: EroskiState):
            logger.debug(f"🔀 Router orquestador - Estado: authenticated={state.get('authenticated')}")
            
            if state.get("authenticated"):
                return "identificar_incidencia"
            else:
                return "identificador_manual"

        # Función de enrutamiento desde identificador_manual
        def router_identificador_manual(state: EroskiState):
            logger.debug(f"🔀 Router manual - Autenticado: {state.get('authenticated')}")
            
            if state.get("authenticated"):
                return "identificar_incidencia"
            else:
                return "supervisor_node"  # Escalación si no se pudo identificar

        # Función de enrutamiento desde identificar_incidencia
        def router_identificar_incidencia(state: EroskiState):
            logger.debug(f"🔀 Router incidencia - Tipo: {state.get('incident_type')}")
            
            if state.get("incident_type"):
                if orquestador_busqueda_available:
                    return "orquestador_busqueda"
                else:
                    return "buscar_solucion"
            else:
                return "info_adicional_incidencia"

        # Función de enrutamiento desde buscar_solucion
        def router_buscar_solucion(state: EroskiState):
            logger.debug(f"🔀 Router solución - Encontrada: {state.get('solution_found')}")
            
            if state.get("solution_found"):
                return "resolucion_exitosa"
            else:
                return "supervisor_node"

        # Función de enrutamiento desde info_adicional_incidencia
        def router_info_adicional(state: EroskiState):
            logger.debug(f"🔀 Router info adicional")
            
            # Si ya tenemos suficiente información, ir a buscar solución
            if state.get("additional_info_collected"):
                return "identificar_incidencia"  # Reintentar identificación
            else:
                return "supervisor_node"  # Si no se puede recopilar más info

        # Función de enrutamiento desde orquestador_busqueda (si está disponible)
        def router_orquestador_busqueda(state: EroskiState):
            logger.debug(f"🔀 Router orquestador búsqueda")
            return "buscar_solucion"

        # Configurar edges condicionales (igual que en test_grafo.py)
        builder.add_conditional_edges(
            "orquestador",
            router_orquestador,
            {
                "identificar_incidencia": "identificar_incidencia",
                "identificador_manual": "identificador_manual"
            }
        )

        builder.add_conditional_edges(
            "identificador_manual",
            router_identificador_manual,
            {
                "identificar_incidencia": "identificar_incidencia",
                "supervisor_node": "supervisor_node"
            }
        )

        builder.add_conditional_edges(
            "identificar_incidencia",
            router_identificar_incidencia,
            {
                "buscar_solucion": "buscar_solucion",
                "orquestador_busqueda": "orquestador_busqueda" if orquestador_busqueda_available else "buscar_solucion",
                "info_adicional_incidencia": "info_adicional_incidencia"
            }
        )

        if orquestador_busqueda_available:
            builder.add_conditional_edges(
                "orquestador_busqueda",
                router_orquestador_busqueda,
                {
                    "buscar_solucion": "buscar_solucion"
                }
            )

        builder.add_conditional_edges(
            "buscar_solucion",
            router_buscar_solucion,
            {
                "resolucion_exitosa": "resolucion_exitosa",
                "supervisor_node": "supervisor_node"
            }
        )

        builder.add_conditional_edges(
            "info_adicional_incidencia",
            router_info_adicional,
            {
                "identificar_incidencia": "identificar_incidencia",
                "supervisor_node": "supervisor_node"
            }
        )

        # Edges finales
        builder.add_edge("resolucion_exitosa", END)
        builder.add_edge("supervisor_node", END)

        return builder.compile()

    def create_new_session(self) -> EroskiState:
        """Crear nueva sesión (igual que en test_grafo.py)"""
        self.session_counter += 1
        session_id = f"chainlit_session_{self.session_counter}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        return create_initial_eroski_state(
            session_id=session_id,
            timezone="Europe/Madrid"
        )

    async def process_message(self, user_message: str, state: EroskiState) -> EroskiState:
        """
        Procesar mensaje del usuario usando el grafo
        """
        try:
            # Añadir mensaje del usuario al estado
            state["messages"].append(HumanMessage(content=user_message))
            state["last_activity"] = datetime.now()
            
            # Ejecutar el grafo
            result_state = await self.graph.ainvoke(state)
            
            logger.info(f"✅ Mensaje procesado - Nodo actual: {result_state.get('current_node')}")
            
            return result_state
            
        except Exception as e:
            logger.error(f"❌ Error procesando mensaje: {e}")
            # Añadir mensaje de error al estado
            error_msg = AIMessage(content="Lo siento, ha ocurrido un error técnico. ¿Puedes intentarlo de nuevo?")
            state["messages"].append(error_msg)
            return state

    def get_last_ai_message(self, state: EroskiState) -> Optional[str]:
        """
        Extraer el último mensaje del asistente del estado
        """
        if not state.get("messages"):
            return None
        
        # Buscar el último mensaje del asistente
        for message in reversed(state["messages"]):
            if isinstance(message, AIMessage):
                return message.content
        
        return None

# Instancia global del workflow
workflow = EroskiWorkflow()

# Variable global para almacenar el estado de la sesión
session_states = {}

@cl.on_chat_start
async def start():
    """Inicializar sesión de chat"""
    # Crear nuevo estado para esta sesión
    session_id = cl.user_session.get("id")
    if not session_id:
        session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        cl.user_session.set("id", session_id)
    
    # Crear estado inicial
    initial_state = workflow.create_new_session()
    initial_state["session_id"] = session_id
    session_states[session_id] = initial_state
    
    # Mensaje de bienvenida
    welcome_message = """🛒 **¡Hola! Soy el asistente de incidencias de Eroski**

Te ayudo a resolver problemas técnicos en tienda. Para comenzar, necesito identificarte.

¿Podrías darme tu email corporativo o número de empleado?"""
    
    await cl.Message(content=welcome_message).send()

@cl.on_message
async def main_message(message: cl.Message):
    """Procesar mensaje del usuario"""
    try:
        # Obtener estado de la sesión
        session_id = cl.user_session.get("id")
        current_state = session_states.get(session_id)
        
        if not current_state:
            # Si no hay estado, crear uno nuevo
            current_state = workflow.create_new_session()
            session_states[session_id] = current_state
        
        # Mostrar indicador de procesamiento
        async with cl.Step(name="Procesando tu mensaje...") as step:
            # Procesar mensaje con el workflow
            updated_state = await workflow.process_message(message.content, current_state)
            
            # Actualizar estado en sesión
            session_states[session_id] = updated_state
            
            # Extraer respuesta del asistente
            ai_response = workflow.get_last_ai_message(updated_state)
            
            if ai_response:
                step.output = ai_response
            else:
                step.output = "Mensaje procesado correctamente."
        
        # Enviar respuesta al usuario
        if ai_response:
            await cl.Message(content=ai_response).send()
        else:
            await cl.Message(content="He procesado tu mensaje. ¿En qué más puedo ayudarte?").send()
            
        # Debug: mostrar información del estado (solo en desarrollo)
        if os.getenv("DEBUG_MODE") == "true":
            debug_info = f"""
**Estado Debug:**
- Autenticado: {updated_state.get('authenticated', False)}
- Tipo incidencia: {updated_state.get('incident_type', 'No identificado')}
- Nodo actual: {updated_state.get('current_node', 'Desconocido')}
- Esperando entrada: {updated_state.get('awaiting_user_input', False)}
"""
            await cl.Message(content=debug_info).send()
            
    except Exception as e:
        logger.error(f"❌ Error en main_message: {e}")
        await cl.Message(
            content="Lo siento, ha ocurrido un error técnico. Un supervisor será notificado."
        ).send()

if __name__ == "__main__":
    # Ejecutar aplicación Chainlit
    import subprocess
    subprocess.run(["chainlit", "run", __file__, "-w"])