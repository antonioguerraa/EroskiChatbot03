#!/usr/bin/env python3
"""
Chatbot de Atención al Usuario Interno - Eroski
Aplicación Chainlit que integra el grafo LangGraph para manejo de incidencias

Uso:
    uv run chainlit run chainlit_app.py -w
"""

import os
import sys
import logging
from datetime import datetime
from typing import Optional, Dict

import chainlit as cl
from langchain_core.messages import AIMessage, HumanMessage

# Añadir raíz del proyecto al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Importaciones del proyecto
from app.models.eroski_state import create_initial_eroski_state, EroskiState
from app.nodes.identificador_orquestador import identificador_orquestador_node
from app.nodes.identificador_manual_node import recoger_datos_empleado_node
from app.nodes.identificacion_incidencia_node import identificacion_node
from app.nodes.buscar_solucion_node import buscar_solucion_node
from app.nodes.supervisor_node import supervisor_node
from app.nodes.orquestador_busqueda_node import orquestador_busqueda_node
from app.nodes.finalize_node import finalize_node
from app.nodes.incident_info_adicional_node import recoger_datos_adicionales_node
from langgraph.graph import StateGraph, END
from app.graphs.eroski_graph import build_eroski_graph


# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s in %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# Configuración de autenticación
@cl.password_auth_callback
def auth_callback(username: str, password: str) -> Optional[cl.User]:
    """
    Callback de autenticación para Chainlit.
    Verifica las credenciales del usuario.
    """
    # Obtener credenciales del entorno o usar valores por defecto
    # En producción, estas credenciales deberían estar en una base de datos segura
    valid_users = {
        os.getenv("CHAINLIT_USER", "admin"): os.getenv("CHAINLIT_PASSWORD", "eroski2024"),
        "supervisor": "eroski_supervisor_2024",
        "operador": "eroski_operador_2024"
    }
    
    # Verificar credenciales
    if username in valid_users and valid_users[username] == password:
        logger.info(f"✅ Usuario autenticado: {username}")
        return cl.User(
            identifier=username,
            metadata={"role": "admin" if username == "admin" else "user"}
        )
    else:
        logger.warning(f"❌ Intento de login fallido para usuario: {username}")
        return None

class EroskiChatbot:
    """
    Chatbot principal para Eroski basado en LangGraph
    """
    
    def __init__(self):
        """Inicializar el chatbot"""
        #self.graph = self.build_graph()
        self.graph = build_eroski_graph()

        
        logger.info("🤖 Chatbot Eroski inicializado")
    

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
 
    def create_new_session(self, session_id: str) -> EroskiState:
        """Crear nueva sesión con estado inicial"""
        initial_state = create_initial_eroski_state(session_id=session_id)
        initial_state["channel"] = "chainlit"
        return initial_state
    
    def create_new_session_kk(self) -> EroskiState:
        self.session_counter += 1
        session_id = f"test_session_{self.session_counter}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        return create_initial_eroski_state(session_id=session_id, timezone="Europe/Madrid")

    async def process_message(self, message: str, state: EroskiState) -> EroskiState:
        """Procesar mensaje del usuario a través del grafo"""
        try:
            # Añadir mensaje del usuario al estado
            state["messages"] = state.get("messages", []) + [HumanMessage(content=message)]
            state["last_activity"] = datetime.now()
            
            # Ejecutar el grafo con límite de recursión más alto
            logger.info(f"🔄 Procesando mensaje: {message[:50]}...")
            config = {"recursion_limit": 50}  # Aumentar límite de recursión
            result = await self.graph.ainvoke(state, config=config)
            
            # Actualizar estado
            state.update(result)
            
            # Log del estado actual para debug
            current_node = state.get('current_node', 'unknown')
            authenticated = state.get('authenticated', False)
            incident_id = state.get('incident_id', None)
            
            logger.info(f"📍 Nodo: {current_node}, Auth: {authenticated}, Incident: {incident_id}")
            
            return state
            
        except Exception as e:
            logger.error(f"❌ Error procesando mensaje: {e}")
            # Añadir mensaje de error al estado
            error_msg = f"Lo siento, ha ocurrido un error técnico: {str(e)}"
            state["messages"].append(AIMessage(content=error_msg))
            return state
    
    def get_bot_response(self, state: EroskiState) -> Optional[str]:
        """Extraer la respuesta del bot del estado"""
        messages = state.get("messages", [])
        
        # Buscar el último mensaje del AI (igual que en tu lógica original)
        msg = ""
        for message in reversed(messages):
            if not isinstance(message, AIMessage):
                return msg
            else:
                msg = msg + message.content + "\n"
        
        return None

# Instancia global del chatbot
chatbot = EroskiChatbot()

@cl.on_chat_start
async def start():
    """Inicializar nueva sesión de chat"""
    # Obtener usuario autenticado
    user = cl.user_session.get("user")
    
    # Generar ID de sesión único
    session_id = f"eroski_session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    # Crear estado inicial usando tu función existente
    initial_state = chatbot.create_new_session(session_id)
    
    # Guardar información del usuario autenticado en el estado
    if user:
        initial_state["chainlit_user"] = user.identifier
        initial_state["user_role"] = user.metadata.get("role", "user")
    
    # Guardar estado en la sesión de Chainlit
    cl.user_session.set("eroski_state", initial_state)
    cl.user_session.set("session_id", session_id)
    
    logger.info(f"🚀 Nueva sesión iniciada: {session_id} - Usuario: {user.identifier if user else 'Unknown'}")
    
    # Mensaje de bienvenida personalizado
    user_name = user.identifier if user else "Usuario"
    welcome_message = f"""¡Hola {user_name}! 👋 

Soy el **Asistente de Incidencias de Eroski**. Para ayudarte necestio que me proporciones tu nombre, apellido y la tienda y sección del incidente"""

    await cl.Message(content=welcome_message).send()
    
"""    await cl.SidebarButton(
        name="reiniciar_sesion",
        label="🔄 Reiniciar conversación"
    ).send()"""
@cl.on_message
async def main(message: cl.Message):
    """Manejar mensaje del usuario"""
    """        # Ver si el mensaje es una acción del botón lateral
        if isinstance(message, cl.Action) and message.name == "reiniciar_sesion":
            session_id = f"eroski_session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            initial_state = chatbot.create_new_session(session_id)

            cl.user_session.set("eroski_state", initial_state)
            cl.user_session.set("session_id", session_id)

            logger.info(f"🔄 Sesión reiniciada: {session_id}")

            await cl.Message(
                content="✅ He reiniciado la sesión. Puedes empezar de nuevo cuando quieras.\n\n¿Cómo puedo ayudarte hoy?"
            ).send()
            return"""
    try:
        # Obtener estado de la sesión
        state = cl.user_session.get("eroski_state")
        session_id = cl.user_session.get("session_id")
        
        if not state:
            await cl.Message(content="❌ Error: Sesión no válida. Por favor, recarga la página.").send()
            return
        
        # Mostrar indicador de escritura
        async with cl.Step(name="Procesando", type="run") as step:
            step.output = "Analizando tu mensaje y buscando la mejor respuesta..."
            
            # Procesar mensaje a través del grafo (usando tu lógica existente)
            updated_state = await chatbot.process_message(message.content, state)
            
            # Actualizar estado en la sesión
            cl.user_session.set("eroski_state", updated_state)
        
        # Obtener respuesta del bot
        bot_response = chatbot.get_bot_response(updated_state)
        
        if bot_response:
            # Enviar respuesta
            await cl.Message(content=bot_response).send()
            # Construir bloque de estado

            
            # Información adicional de debug (igual que en tu código original)
            if os.getenv("CHAINLIT_DEBUG", "false").lower() == "true":
                debug_info = f"""
                   
                
                    - Usuario Chainlit: `{updated_state.get('chainlit_user', 'None')}`  
                    - Rol: `{updated_state.get('user_role', 'None')}`  
                    - Sesión: `{session_id}`  
                    - Nodo actual: `{updated_state.get('current_node', 'unknown')}`  
                    - Intentos de identificación: `{updated_state.get('intento_identificacion', 0)}`  
                    - Intento de tienda: `{updated_state.get('intento_tienda', 0)}`  
                    - Autenticado: `{updated_state.get('authenticated', False)}`  
                    - Nombre: `{updated_state.get('incident_user_name', 'None')}`  
                    - Apellido: `{updated_state.get('incident_last_name', 'None')}`  
                    - Tienda: `{updated_state.get('incident_store_name', 'None')}`  
                    - Sección: `{updated_state.get('incident_department', 'None')}`  
                    - Tienda tentativa: `{updated_state.get('tienda_tentativa', 'None')}`  
                    - Descripción del problema: `{updated_state.get('problem_description', 'None')}`  
                    - Detalles de la incidencia: `{updated_state.get('incident_details', 'None')}`  
                    - Información adicional: `{updated_state.get('incident_info_adicional', 'None')}`  

                    """
                await cl.Message(content=debug_info).send()
        else:
            await cl.Message(content="No he podido generar una respuesta adecuada. ¿Puedes reformular tu consulta?").send()
            
    except Exception as e:
        logger.error(f"❌ Error en main: {e}")
        error_message = f"Ha ocurrido un error inesperado: {str(e)}\n\nPor favor, intenta de nuevo o contacta con soporte técnico."
        await cl.Message(content=error_message).send()

@cl.on_chat_end
async def end():
    """Finalizar sesión de chat"""
    session_id = cl.user_session.get("session_id", "unknown")
    logger.info(f"👋 Sesión finalizada: {session_id}")




if __name__ == "__main__":
    # Este archivo debe ejecutarse con: uv run chainlit run chainlit_app.py -w
    print("🚀 Para ejecutar el chatbot, usa: uv run chainlit run chainlit_app.py -w")