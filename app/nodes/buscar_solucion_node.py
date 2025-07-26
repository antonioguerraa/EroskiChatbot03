# =====================================================
# nodes/buscar_solucion_node.py - ACTUALIZADO CON RAG OPTIMIZADO
# =====================================================
"""
Nodo de búsqueda de soluciones integrado con el RAG optimizado y diccionario técnico.

CAMBIOS PRINCIPALES:
- Reemplazada clase EroskiKnowledgeBase por versión optimizada
- Integración con diccionario técnico
- Threshold optimizado (0.4 en lugar de 0.7)
- Mejor formateo de resultados
- Manejo de errores mejorado
"""

import logging
import pprint
from typing import Dict, Any, List
from datetime import datetime
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain.schema.runnable import RunnableSequence, Runnable
# Imports del proyecto
from app.models.eroski_state import EroskiState
from app.models.faq_problem_match import FAQ_ProblemMatch
from app.utils.llm.providers import get_llm
from app.utils.construir_historico_mensajes import format_full_chat_history

# PostgreSQL imports
from app.utils.incident_manager import get_incident_manager
from app.utils.cargar_incidentes import EroskiIncidentsManager
from app.models.indentificacion_solucion import IdentificacionSolucion
from app.models.ordenar_chunks import OrdenarChunks
from app.utils.clean_chunk_text import clean_chunk_text
logger = logging.getLogger(__name__)
try:
    from app.nodes.improved_eroski_knowledge_base import OptimizedEroskiKnowledgeBaseWithMetadata
    ENHANCED_RAG_AVAILABLE = True
    logger.info("✅ RAG con metadatos importado correctamente")
except ImportError as e:
    logger.warning(f"⚠️ No se pudo importar RAG mejorado: {e}")
    from app.nodes.old.optimized_eroski_knowledge_base import OptimizedEroskiKnowledgeBase
    ENHANCED_RAG_AVAILABLE = False


# =====================================================
# CLASE RAG OPTIMIZADA - REEMPLAZA LA ANTERIOR
# =====================================================


# =====================================================
# RESTO DEL CÓDIGO ORIGINAL SIN CAMBIOS
# =====================================================

class BuscarSolucionNode:
    """
    Nodo principal para búsqueda de soluciones en el chatbot de Eroski.
    
    ACTUALIZADO CON:
    - RAG optimizado (OptimizedEroskiKnowledgeBase)
    - Integración con diccionario técnico
    - Mejor manejo de errores
    - Logging mejorado
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # CAMBIO PRINCIPAL: Usar RAG optimizado
        if ENHANCED_RAG_AVAILABLE:
            self.knowledge_base = OptimizedEroskiKnowledgeBaseWithMetadata()
            logging.info("🔧 Usando RAG optimizado con metadatos")
        else:
            self.knowledge_base = OptimizedEroskiKnowledgeBase()
            logging.info("⚠️ Usando RAG básico (sin metadatos)")
        
        self.incidents_manager = EroskiIncidentsManager()
        self.llm = get_llm()
        self.node_name = "buscar_solucion"

        # Configurar herramientas para el agente
        
        self.agent_faq = self.setup_agent_faq()
        self.ordenar_chunks_chain = self.setup_ordenar_chunks_chain()
        self.analizando_consulta_chain = self._setup_analizando_consulta_chain()

    async def execute(self, state: EroskiState) -> dict:
        """
        Método execute principal para LangGraph que maneja todo el flujo de búsqueda de soluciones.
        
        MEJORADO CON:
        - Integración del RAG optimizado
        - Mejor logging
        - Manejo de errores robusto
        """
        self.logger.info("🔍 Ejecutando buscar_solucion_node con RAG optimizado")
        
        try:
            # Obtener información del estado
            messages = state.get("messages", [])
            last_message = messages[-1]
            incident_type = state.get("incident_type", "")
            problem_identified = state.get("problem_identified", False)
            solution_attempts = state.get("solution_attempts",0)
            max_solution_attempts = state.get("max_solution_attempts",0)
            incident_id = state.get("incident_id", None)
            if solution_attempts >= max_solution_attempts:
                return {
                    "current_node": self.node_name,
                    "awaiting_user_input": True,
                    "escalation_needed":True
                }
            

            if not incident_id:
                incident_id = get_incident_manager().manage_incident(state)
            logger.info(f"👹Incidente ID: {incident_id}👹")
            
            if not isinstance(last_message, HumanMessage):
                return {
                    "current_node": self.node_name,
                    "awaiting_user_input": True
                }
            
            
            # Base para actualizaciones del estado
            base_update = {
                "incident_id": incident_id,
                "current_node": self.node_name,
                "last_activity": datetime.now(),
                "solution_attempts": solution_attempts + 1
            }
            if not incident_type:
                # Preparar actualización base del estado
                return {
                    **base_update,
                    "messages": [AIMessage(content="Primero debemos indentificar el tipo de incidencia.")],
                    "incident_type_confirmed": False
                }

            # Lógica principal de identificación y búsqueda
            if not problem_identified:
                self.logger.info(f"🔍 Identificando problema para incident_type: {incident_type}")
                

                if not last_message:
                    # Primera vez - mostrar ejemplos
                    response = self._mostrar_ejemplos_frecuentes(state.get("incident_type", ""))
                    return {
                        **base_update,
                        "messages": state.get("messages", []) + [AIMessage(content=response)],
                        "awaiting_user_input": True,
                        "problem_identified": False
                    }

                historial_formateado = format_full_chat_history(messages=messages)
                try:
                    result = await self.analizando_consulta_chain.ainvoke({
                        "incident_type": incident_type,
                        "chat_history": historial_formateado})
                    logging.info(f"👹 intent: {result['user_intent']}")
                    print("👹"*10)
                    pprint.pprint(result)
                    print("👹"*10)
                    base_update.update(result)
                    print("👹 base_update")
                    pprint.pprint(base_update)
                    if result['escalation_needed']:
                        return {
                            **base_update,
                            "escalation_needed": True,
                            "messages": [
                                AIMessage(content=result['message_to_user'])
                            ],
                            "awaiting_user_input": False,
                            "problem_identified": False
                        }
                    if result['solution_found']:
                        return {
                            **base_update,
                            "messages": [
                                AIMessage(content=result['message_to_user'])
                            ],
                            "awaiting_user_input": False,
                            "solution_found": True
                        }
                    if result['problem_identified']:
                        #Buscamos en el RAG
                        logging.info(f"👹 problem_identified: {result['problem_identified']}")
                        logging.info(f"👹 problem_description: {result['problem_description']}")
                        base_update.update({"problem_description":result['problem_description']})
                        
                        return {
                            **base_update,
                            "problem_identified": True,
                            "problem_description": result["problem_description"],
                            "messages": [
                                AIMessage(content="Gracias. Voy a buscar la solución más adecuada para este problema.")
                            ],
                            "awaiting_user_input": False
                        }                        
 
                        
                    else:#no se ha identificado el problema. volvemos a preguntar
                        return {
                            **base_update,
                            "messages": [
                                AIMessage(content=result['message_to_user'])
                            ],
                            "awaiting_user_input": True,
                            "problem_identified": False
                        }
                except Exception as e:
                    logging.error(f"Error en la identificación de la solución: {e}")
                    return {
                        **base_update,
                        "messages": [
                            AIMessage(content="Lo siento, no se pudo procesar tu solicitud. Por favor, intenta de nuevo.")
                        ],
                        "awaiting_user_input": True,
                        "problem_identified": False
                    }
            else:
                return {
                    "solution_found":True,
                    "messages": [
                        AIMessage(content="Ha sido un placer ayudarte")
                    ],
                    "awaiting_user_input": False
                }

        except Exception as e:
            self.logger.error(f"❌ Error en buscar_solucion_node: {e}")
            return {
                "current_node": self.node_name,
                "last_activity": datetime.now(),
                "messages": state.get("messages", []) + [
                    AIMessage(content="Lo siento, hubo un error interno. ¿Podrías intentar describir tu problema de nuevo?")
                ],
                "awaiting_user_input": True
            }
        finally:
            # Limpiar recursos
            try:
                await self.knowledge_base.close()
            except Exception as e:
                self.logger.error(f"❌ Error al cerrar el RAG: {e}")
                pass

    async def _procesar_chunks(self, resultado_manual: Dict[str, Any]) -> List[str]:

        "Añade el chunk anterior y el posterior para darle contexto antes de pasarlo al llm"
        try:
            chunks_list = []
            logging.info(f"👹resultado_manual['results']: {resultado_manual}")
            for item in resultado_manual['results']:
                logging.info(f"👹item: {item}")
                logging.info(f"👹item['chunk_id']: {item['chunk_id']}")
                logging.info(f"👹item['documento']['pagina_numero']: {item['documento']['pagina_numero']}")
                chunks = await self.knowledge_base.get_chunk_with_context(item['chunk_id'])
                logging.info(f"👹chunks: {chunks}")
                logging.info(f"👹chunks['chunk_anterior']['chunk_text']: {chunks['chunk_anterior']['chunk_text']}")
                chunks_list.append(
                    {'page' : item['documento']['pagina_numero'],
                    'text' : clean_chunk_text(chunks['chunk_anterior']['chunk_text']+'\n'+
                                              chunks['chunk_actual']['chunk_text']+'\n'+
                                              chunks['chunk_siguiente']['chunk_text'])
                    })
            
            lista_chunks = "\n\n".join(
                f"[{i+1}] (página {chunk['page']})\n{chunk['text']}"
                for i, chunk in enumerate(chunks_list)
            )
            return lista_chunks
        except Exception as e:
            self.logger.error(f"❌ Error en añadir_chunks: {e}")
            return resultado_manual
    
    def setup_ordenar_chunks_chain(self) -> RunnableSequence:
        """Crea una cadena que analiza si los chunks del RAG responden a la consulta del usuario y devuelve el resultado."""

        parser = JsonOutputParser(pydantic_object=OrdenarChunks)

        prompt = PromptTemplate(
            template="""
            Eres un asistente técnico experto de Eroski. Tu tarea es analizar si los fragmentos (chunks) de un manual contienen la respuesta a la consulta del usuario.

            🧠 Primero, comprende exactamente qué pregunta el usuario.

            Consulta del usuario (basada en el historial de mensajes):
            {chat_history}

            A continuación tienes una lista de {top_k} fragmentos del manual técnico. Cada uno contiene contenido parcial, con instrucciones, secciones o descripciones técnicas.

            {lista_chunks}

            📌 Tienes que hacer lo siguiente:

            1. Lee con atención la consulta del usuario y **entiende su intención exacta**.
            2. Evalúa **si alguno de los fragmentos contiene instrucciones, explicaciones o información que respondan directamente** a la consulta.
            3. Si encuentras un fragmento útil, **extrae la información clave y genera una respuesta clara** para el usuario.
            4. Guarda en la lista "chunk_id_list" los identificadores de los fragmentos que responden a la consulta.
            5. Si los fragmentos no responden directamente a la consulta, indica que no hay información suficiente.

            Devuelve un JSON válido con el siguiente formato:

            ```json
            {{
            "problem_identified": true/false,
            "confidence": 0.0 - 1.0,
            "solution_content": "texto generado para el usuario"
            "chunk_id_list": ['chunk_000484', 'chunk_000136', ...]
            }}

            ⚠️ No inventes información. Si el fragmento más claro habla de un tema distinto al de la consulta, ignóralo.

            Ejemplo:

            Consulta: "Cómo configurar la retroiluminación del display"

            Chunk: "Para mostrar publicidad en el display, pulse MENU + 42"
            → No es relevante: se habla de publicidad, no de retroiluminación.

            """,
            input_variables=["chat_history", "lista_chunks", "top_k"],
            partial_variables={"format_instructions": parser.get_format_instructions()}
        )

        return prompt | self.llm | parser

    def setup_agent_faq(self) -> Runnable:
        parser = JsonOutputParser(pydantic_object=FAQ_ProblemMatch)
        
        """Configura el agente para buscar la solución en el archivo json que guarda los problemas más frecuentes.
        Misión:
        1. Identificar el problema dentro del listado de problemas para el tipo de incidente que hay en el json
        2. Recuperar la solución más adecuada a ese problema.
        
        """
        
        prompt_template = PromptTemplate.from_template("""
            Eres un asistente técnico que ayuda a identificar el problema más probable en función del historial de mensajes de un usuario y una lista de problemas conocidos.

            ### Instrucciones:

            1. Lee cuidadosamente el mensaje del usuario.
            2. Compara su contenido con los problemas disponibles (las claves del JSON).
            3. Devuelve el problema más parecido en el campo "problem_name" y la solución asociada en "solution_content".
            4. Estima una confianza (entre 0.0 y 1.0).
            5. Si no hay ninguna coincidencia razonable (confianza < 0.4), responde con:
            {{
                "problem_identified": false,
                "problem_name": "",
                "confidence": 0.0,
                "solution_content": ""
            }}

            Mensajes del usuario:
            {problema_identificado}

            Problemas conocidos:
            {problemas_json}

            ⚠️ No inventes ni asumas información que no esté explícitamente en los mensajes o problemas conocidos. Limítate a comparar texto y seleccionar la opción más adecuada.

            Devuelve únicamente un JSON válido (sin markdown), con esta estructura:

            {format_instructions}

            Ejemplo:

            {{
            "problem_identified": true,
            "problem_name": "La Balanza no imprime las Etiquetas",
            "confidence": 0.93,
            "solution_content": "Comprobar si tiene papel, y en caso afirmativo Apagar y Encender la Balanza"
            }}
            """)
        

        prompt = prompt_template.partial(format_instructions=parser.get_format_instructions())
        chain = prompt | self.llm | parser

        return chain
    
    def _setup_analizando_consulta_chain(self) -> RunnableSequence:
        """Crea una cadena que analiza si el usuario ha descrito un problema técnico claro."""

        parser = JsonOutputParser(pydantic_object=IdentificacionSolucion)
        
        prompt = PromptTemplate(
            template="""
        Eres un asistente técnico conversacional de Eroski.

        Tu tarea es analizar la conversación reciente y determinar:

        1. Si el usuario ha descrito un problema técnico o una consulta clara relacionada con el equipo indicado.
        2. Si el usuario ha proporcionado nueva información útil (incluso si ya se le había propuesto algo antes).
        3. Si el usuario está confirmando, rechazando o escalando.
        4. Si no ha aportado información relevante todavía.

        ---

        TIPO DE EQUIPO: {incident_type}

        CONVERSACIÓN RECIENTE:
        {chat_history}

        ---

        🔍 Instrucciones:

        - Si el usuario describe un problema o hace una consulta clara (por ejemplo: "la balanza no imprime", "cómo se cambia el papel"), responde con "problem_identified": true y resume en "problem_description".
        - Si el usuario da más detalles después de una solución fallida (por ejemplo: "ahora suena un pitido"), responde con "problem_identified": true, y "requires_confirmation": true.
        - Si el usuario manifiesta que no se ha resutelto su consulta sin dar más información, responde "problem_identified": false y pide detalles en "message_to_user".
        - Si el usuario manifiesta que no se ha resutelto su consulta y proporciona más información en el mensaje, responde "problem_identified": false y pide detalles en "message_to_user".
        - Si el usuario confirma que se ha resuelto la consulta responde "solution_found":true y "problem_identified":true
        - Si quiere hablar con un supervisor, muestra frustración o dice "esto no sirve", marca "escalation_needed": true y "problem_identified":true
        - En todos los casos, añade un campo "user_intent" con la intención principal del mensaje.
        - Contesta al usuario con lo que sepas, no te inventes nada ni infieras nada.

        ⚠️ Nunca inventes datos. Basa tus respuestas únicamente en el historial.

        ---

        🎯 Intenciones válidas para "user_intent":
        - "consulta_manual" → el usuario hace una pregunta técnica o de uso
        - "problema_tecnico" → el usuario reporta un mal funcionamiento
        - "confirmacion_positiva" → acepta una solución o avanza
        - "confirmacion_negativa" → dice que no, sin aportar más
        - "confirmacion_negativa_con_info" → dice que no y da nueva información útil
        - "escalada" → pide ayuda urgente o contacto humano
        - "sin_informacion" → no da datos suficientes

        ---

        Devuelve únicamente un JSON válido (sin markdown) con esta estructura:

        {format_instructions}

        Ejemplo:

        {{
        "problem_identified": true,
        "confidence": 0.95,
        "problem_description": "La balanza no imprime etiquetas",
        "requires_confirmation": false,
        "message_to_user": "Gracias por la información. Ahora intentaré ayudarte con este problema.",
        "escalation_needed": false,
        "user_intent": "problema_tecnico"
        }}
        """,
            input_variables=["chat_history", "incident_type"],
            partial_variables={"format_instructions": parser.get_format_instructions()}
        )

        return prompt | self.llm | parser

    def _mostrar_ejemplos_frecuentes(self, incident_type: str) -> str:
        """Muestra ejemplos de problemas frecuentes al usuario."""
        ejemplos = self.incidents_manager.get_ejemplos_frecuentes(incident_type, 3)
        
        if not ejemplos:
            return f"¿Podrías describir el problema que tienes con {incident_type}?"
        
        ejemplos_text = "\n".join([f"• {ej}" for ej in ejemplos])
        
        return f"""Algunos problemas frecuentes con {incident_type} son:

{ejemplos_text}

¿Cuál de estos se parece a tu problema o podrías describir qué está ocurriendo?"""
    
async def buscar_solucion_node(state: EroskiState) -> dict:
    """
    Función wrapper para LangGraph - Nodo de Búsqueda de Soluciones
    
    Args:
        state: Estado actual como EroskiState
        
    Returns:
        Command con las actualizaciones de estado
    """
    # Crear instancia del nodo
    node = BuscarSolucionNode()
    result = await node.execute(state)
    #print("👹✅ RESULTADO DEL NODO buscar_solucion:")
    #pprint.pprint(result)
    return result
    # Ejecutar el nodo