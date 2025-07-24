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

import json
import logging
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import Tool
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain.agents import create_react_agent, AgentExecutor
from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langchain.schema.runnable import RunnableSequence, Runnable
from langchain_core.runnables import RunnableLambda
from langgraph.types import Command

# Imports del proyecto
from models.eroski_state import EroskiState
from models.faq_problem_match import FAQ_ProblemMatch
from utils.llm.providers import get_llm
from utils.construir_historico_mensajes import format_full_chat_history
from nodes.tools.confirmation_tool import ConfirmationTool


# PostgreSQL imports
from utils.incident_manager import get_incident_manager
from models.indentificacion_solucion import IdentificacionSolucion
from models.ordenar_chunks import OrdenarChunks
logger = logging.getLogger(__name__)
try:
    from nodes.improved_eroski_knowledge_base import OptimizedEroskiKnowledgeBaseWithMetadata
    ENHANCED_RAG_AVAILABLE = True
    logger.info("✅ RAG con metadatos importado correctamente")
except ImportError as e:
    logger.warning(f"⚠️ No se pudo importar RAG mejorado: {e}")
    from nodes.optimized_eroski_knowledge_base import OptimizedEroskiKnowledgeBase
    ENHANCED_RAG_AVAILABLE = False


# =====================================================
# CLASE RAG OPTIMIZADA - REEMPLAZA LA ANTERIOR
# =====================================================


# =====================================================
# RESTO DEL CÓDIGO ORIGINAL SIN CAMBIOS
# =====================================================

class EroskiIncidentsManager:
    """Maneja la carga y búsqueda en el archivo JSON de incidencias frecuentes."""
    
    def __init__(self, json_path: str = "data/eroski_incidents.json"):
        self.json_path = Path(json_path)
        self.incidents_data = self._load_incidents()
    
    def _load_incidents(self) -> Dict[str, Any]:
        """Carga el archivo JSON de incidencias."""
        if not self.json_path.exists():
            logger.warning(f"Archivo de incidencias no encontrado: {self.json_path}")
            return {"incident_types": {}}
            
        try:
            with open(self.json_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error cargando incidencias JSON: {e}")
            return {"incident_types": {}}
    
    def get_incident_types(self) -> List[str]:
        """Obtiene la lista de tipos de incidencia disponibles."""
        return list(self.incidents_data.get("incident_types", {}).keys())
    
    def get_problems_for_type(self, incident_type: str) -> Dict[str, str]:
        """Obtiene los problemas frecuentes para un tipo de incidencia."""
        return self.incidents_data.get("incident_types", {}).get(incident_type, {}).get("problemas", {})

class FAQ_ProblemIdentificationTool:
    """Herramienta para identificar problemas usando el archivo JSON de incidencias frecuentes."""
    
    def __init__(self, incidents_manager: EroskiIncidentsManager):
        self.incidents_manager = incidents_manager
        self.llm = get_llm()
    
    def identify_problem(self, user_input: str, incident_type: str) -> Dict[str, Any]:
        """
        Identifica el problema específico basándose en el archivo JSON.
        """
        try:
            problems = self.incidents_manager.get_problems_for_type(incident_type)
            
            if not problems:
                return {
                    "problema": f"Problema con {incident_type}",
                    "confidence": 0.5,
                    "keywords": [incident_type],
                    "solucion": "Información no disponible en FAQ",
                    "similar_a_ejemplo": False,
                    "requiere_mas_info": True,
                    "solution_source": "JSON"
                }
            
            # Crear prompt para el LLM
            problems_text = "\n".join([f"- {prob}: {sol[:100]}..." for prob, sol in problems.items()])
            
            prompt = f"""
Analiza el mensaje del usuario y encuentra el problema más similar en la lista de problemas frecuentes.

MENSAJE DEL USUARIO: "{user_input}"

PROBLEMAS FRECUENTES PARA {incident_type.upper()}:
{problems_text}

Responde en JSON con:
- "problema": el problema más similar de la lista (texto exacto)
- "confidence": nivel de confianza 0.0-1.0
- "keywords": palabras clave relevantes del mensaje del usuario
- "solucion": la solución correspondiente del problema identificado
- "similar_a_ejemplo": true si hay alta similitud, false si no
- "requiere_mas_info": true si necesitas más información del usuario

Respuesta JSON:
"""
            
            response = self.llm.invoke(prompt)
            response_text = response.content if hasattr(response, 'content') else str(response)
            
            # Parsear respuesta JSON
            try:
                result = json.loads(response_text)
                result["solution_source"] = "JSON"
                return result
            except json.JSONDecodeError:
                # Fallback si el JSON no es válido
                return self._fallback_identification(user_input, incident_type, problems)
                
        except Exception as e:
            logger.error(f"Error en identificación de problema: {e}")
            return self._fallback_identification(user_input, incident_type, {})
    
    def _fallback_identification(self, text: str, incident_type: str, problems: Dict[str, str]) -> Dict[str, Any]:
        """Identificación de fallback cuando falla el LLM."""
        logger.warning(f"Usando identificación de fallback para: {text[:200]}")
        return {
            "problema": f"Error procesando consulta sobre {incident_type}",
            "confidence": 0.0,
            "keywords": [],
            "solucion": "",
            "similar_a_ejemplo": False,
            "requiere_mas_info": True,
            "solution_source": "Otros"
        }

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
            self.logger.info("🔧 Usando RAG optimizado con metadatos")
        else:
            self.knowledge_base = OptimizedEroskiKnowledgeBase()
            self.logger.info("⚠️ Usando RAG básico (sin metadatos)")
        
        
        self.incidents_manager = EroskiIncidentsManager()
        self.faq_problem_tool = FAQ_ProblemIdentificationTool(self.incidents_manager)
        self._incident_manager = None
        self.confirmation_tool = ConfirmationTool()
        self.llm = get_llm()
        self.max_attempts = 3
        self.node_name = "buscar_solucion"
        self.parser_json = JsonOutputParser()
        self.parser_str = StrOutputParser()
        
        # Configurar herramientas para el agente
        self.tools = self._setup_tools()
        self.tools_manual = self._setup_tools_manual()
        self.tools_faq = self._setup_tools_faq()
        
        self.agent = self._setup_agent()
        self.agent_faq = self._setup_agent_faq()
        self.ordenar_chunks_chain = self._setup_ordenar_chunks_chain()
        self.identificacion_solucion_chain = self._setup_identificacion_solucion_chain()
        self.solution_fusion_chain = self._setup_solution_fusion_chain()

        self.llm_extra_info_prompt = ChatPromptTemplate.from_messages([
            ("system", """Eres un experto en soporte técnico.

Analiza el siguiente mensaje del usuario, que se ha producido después de que se le propusiera una solución que **no resolvió el problema**.

Tu tarea es responder:
- "si": si el mensaje del usuario contiene nueva información útil para diagnosticar o entender mejor el problema.
- "no": si el usuario simplemente dice que no funcionó, sin aportar más información técnica.

Ejemplos:
Usuario: "No, no funcionó" → no  
Usuario: "No, sigue fallando" → no  
Usuario: "No, ahora aparece una luz roja en la pantalla" → si  
Usuario: "No, y suena un pitido al encender" → si

Mensaje del usuario: "{user_message}"

Responde únicamente con "si" o "no".
""")
        ])
    
    def _setup_tools_manual(self) -> List[Tool]:
        """Configura las herramientas disponibles para el agente."""

        def buscar_manual_wrapper(query: str) -> str:
            """Wrapper para búsqueda en manuales usando RAG optimizado."""
            try:
                # LÍNEA CLAVE: Aquí se usa el RAG optimizado
                return self.knowledge_base.buscar_solucion_rag(query)
            except Exception as e:
                logger.error(f"Error en búsqueda manual optimizada: {e}")
                return f"Error en búsqueda de manual: {str(e)}"
        
        return [
            Tool(
                name="buscar_solucion_en_manual",
                description="""
                Busca soluciones en los manuales técnicos usando RAG optimizado.
                Usa este tool cuando necesites información específica de manuales técnicos.
                Entrada: descripción del problema o consulta técnica.
                Salida: texto con soluciones del manual técnico.
                """,
                func=buscar_manual_wrapper
            )
        ]
    
    # ... [resto de métodos sin cambios - _setup_tools_faq, _setup_agent, etc.] ...
    
    async def execute(self, state: EroskiState) -> Command:
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
                return Command(update={
                    "current_node": self.node_name,
                    "awaiting_user_input": True,
                    "escalation_needed":True
                })
            

            if not incident_id:
                incident_id = get_incident_manager().manage_incident(state)
            logger.info(f"👹Incidente ID: {incident_id}👹")
            
            if not isinstance(last_message, HumanMessage):
                return Command(update={
                    "current_node": self.node_name,
                    "awaiting_user_input": True
                })
            
            
            # Base para actualizaciones del estado
            base_update = {
                "incident_id": incident_id,
                "current_node": self.node_name,
                "last_activity": datetime.now(),
                "solution_attempts": solution_attempts + 1
            }
            if not incident_type:
                # Preparar actualización base del estado
                return Command(update={
                    **base_update,
                    "messages": [AIMessage(content="Primero debemos indentificar el tipo de incidencia.")],
                    "incident_type_confirmed": False
                })

            # Lógica principal de identificación y búsqueda
            if not problem_identified:
                self.logger.info(f"🔍 Identificando problema para incident_type: {incident_type}")
                

                if not last_message:
                    # Primera vez - mostrar ejemplos
                    response = self._mostrar_ejemplos_frecuentes(state.get("incident_type", ""))
                    return Command(update={
                        **base_update,
                        "messages": state.get("messages", []) + [AIMessage(content=response)],
                        "awaiting_user_input": True,
                        "problem_identified": False
                    })

                historial_formateado = format_full_chat_history(messages=messages)
                try:
                    result = await self.identificacion_solucion_chain.ainvoke({
                        "incident_type": incident_type,
                        "chat_history": historial_formateado})
                    
                    if result['problem_identified']:
                        #Buscamos en el RAG
                        logging.info(f"👹 problem_identified: {result['problem_identified']}")
                        base_update.update({"problem_description":result['problem_description']})
                        

                        top_k = 3
                        resultado_manual_chunks = self.knowledge_base.buscar_solucion_rag_avanzada(
                            query=result['problem_description'],
                            equipo_context={"tipo": incident_type},
                            top_k=top_k,
                            return_formato = "json"
                        )
                        # devuelve una lista de diccionarios con {texto, pag, similarity}
                        lista_chunk = self._procesar_chunks(resultado_manual_chunks)

                        solucion_manual_llm = await self.ordenar_chunks_chain({
                            "lista_chunks": lista_chunk,
                            "top_k": top_k,
                            "chat_history": historial_formateado,
                        })

                        logging.info(f"👹 solucion manual rag: {solucion_manual_llm}")

                        #Empezamos a buscar en el json. Primero lo cargamo
                        problemas_dict = self.incidents_manager.get_problemas_soluciones(incident_type)
                        
                        agent_response_faq = self.agent_faq.invoke({
                                                            "problema_identificado": result['problem_description'],
                                                            "problemas_json": json.dumps(problemas_dict, indent=2, ensure_ascii=False)})
                        logging.info(f"👹 solucion manual rag: {agent_response_faq}")
                        solucion_faq_llm = agent_response_faq.get("solucion","No se pudo encontrar solución entre las FAQ")
                        logging.info(f"👹 solution_content_faq: {solucion_faq_llm}")

                        msg_IA = ""
                        #generar mensaje solución
                        if solucion_manual_llm['problem_identified']:
                            msg_IA = f"Esto es lo que encontré en el manual:\n\n{solucion_manual_llm['solution_content']}"
                        if solucion_faq_llm['problem_identified']:
                            msg_IA = f"Entre los FAQ encontré esto:\n\n{solucion_faq_llm['solution_content']}"
                        if msg_IA == "":
                            msg_IA = "Lo siento, no se pudo encontrar solución para este problema. Podrías darme más información?"
                            response = self._mostrar_ejemplos_frecuentes(state.get("incident_type", ""))
                            solution_attempts += 1
                            return Command(update={
                                **base_update,
                                "messages": state.get("messages", []) + [AIMessage(content=response)],
                                "awaiting_user_input": True,
                            })
                        
                        msg_IA = msg_IA + "\n\n¿resuelve esto tu cuestión?"
                        return Command(update={
                            **base_update,
                            "messages": [
                                AIMessage(content=msg_IA),
                            ],
                            "awaiting_user_input": True,
                            "problem_identified": False
                        })
                        
                    else:#no se ha identificado el problema. volvemos a preguntar
                        return Command(update={
                            **base_update,
                            "messages": [
                                AIMessage(content=result['message_to_user'])
                            ],
                            "awaiting_user_input": True,
                            "problem_identified": False
                        })
                except Exception as e:
                    logging.error(f"Error en la identificación de la solución: {e}")
                    return Command(update={
                        **base_update,
                        "messages": [
                            AIMessage(content="Lo siento, no se pudo procesar tu solicitud. Por favor, intenta de nuevo.")
                        ],
                        "awaiting_user_input": True,
                        "problem_identified": False
                    })
            else:
                return Command(update={
                    "solution_found":True,
                    "messages": [
                        AIMessage(content="Ha sido un placer ayudarte")
                    ],
                    "awaiting_user_input": False
                })

        except Exception as e:
            self.logger.error(f"❌ Error en buscar_solucion_node: {e}")
            return Command(update={
                "current_node": self.node_name,
                "last_activity": datetime.now(),
                "messages": state.get("messages", []) + [
                    AIMessage(content="Lo siento, hubo un error interno. ¿Podrías intentar describir tu problema de nuevo?")
                ],
                "awaiting_user_input": True
            })
        finally:
            # Limpiar recursos
            try:
                self.knowledge_base.close()
            except Exception as e:
                self.logger.error(f"❌ Error al cerrar el RAG: {e}")
                pass

    def _procesar_chunks(self, resultado_manual: Dict[str, Any]) -> List[str]:

        "Añade el chunk anterior y el posterior para darle contexto antes de pasarlo al llm"
        try:
            chunks = []
            for item in resultado_manual['results']:
                chunks = self.knowledge_base.get_chunk_with_context(item['chunk_id'])
                chunks.append(
                    {'page' : item['documento']['pagina_numero'],
                    'texto' : chunks['chunk_anterior']['chunk_text']+'\n'+chunks['chunk_actual']['chunk_text']+'\n'+chunks['chunk_siguiente']['chunk_text']
                    })
            
            lista_chunks = "\n\n".join(
                f"[{i+1}] (página {chunk['page']})\n{chunk['text']}"
                for i, chunk in enumerate(chunks)
            )
            return lista_chunks
        except Exception as e:
            self.logger.error(f"❌ Error en añadir_chunks: {e}")
            return resultado_manual


    async def _setup_ordenar_chunks_chain(self) -> Dict[str, Any]:
        """Crea una cadena que analiza si los chunks del RAG responden al problema y devuelve el resultado."""

        parser = JsonOutputParser(pydantic_object=OrdenarChunks)

        prompt = PromptTemplate(
            template="""
    Eres un asistente técnico de Eroski.

    Tu tarea es analizar los {top_k} fragmentos (chunks) recuperados mediante un sistema RAG para determinar si resuelven la consulta del usuario.

    Ten en cuenta que el usuario puede estar describiendo un problema o consultando instrucciones específicas. Para comprender mejor el contexto, revisa el siguiente historial de mensajes:

    HISTORIAL DE MENSAJES:
    {chat_history}

    A continuación, tienes los chunks junto con el número de página del manual de donde fueron extraídos:

    {lista_chunks}

    Debes hacer lo siguiente:
    1. Leer los chunks detenidamente y determinar si alguno de ellos resuelve la consulta del usuario.
    2. Si puedes generar una respuesta basada en el contenido de los chunks, hazlo e incluye las páginas utilizadas en tu respuesta.
    3. Si **ninguno de los chunks** permite generar una respuesta clara, devuelve:
    - "problem_identified": false
    - "solution_content": ""
    4. En cualquier caso, estima la confianza en tu evaluación entre 0 y 1, y devuélvela como "confidence".

    ⚠️ No inventes ni asumas información que no esté explícitamente en los chunks. Limítate a interpretar su contenido.

    Devuelve únicamente un JSON válido (sin markdown), con esta estructura:

    {format_instructions}

    Ejemplo:

    {{
    "problem_identified": true,
    "confidence": 0.93,
    "solution_content": "Para reiniciar la balanza, presiona el botón rojo durante 5 segundos. (página 4)"
    }}
    """,
            input_variables=["chat_history", "lista_chunks", "top_k"],
            partial_variables={"format_instructions": parser.get_format_instructions()},
        )

        return prompt | self.llm | parser

    # Resto de métodos auxiliares sin cambios...
    def _setup_tools_faq(self) -> List[Tool]:
        """Configura herramientas para FAQ."""
        def identify_problem_wrapper(query: str) -> str:
            """Wrapper para identificación de problemas."""
            try:
                result = self.faq_problem_tool.identify_problem(query, "general")
                return json.dumps(result, ensure_ascii=False)
            except Exception as e:
                return f"Error en identificación: {str(e)}"
        
        return [
            Tool(
                name="identify_problem_faq",
                description="Identifica problemas usando FAQ",
                func=identify_problem_wrapper
            )
        ]
    
    def _setup_tools(self) -> List[Tool]:
        """Configura herramientas básicas."""
        return self._setup_tools_manual() + self._setup_tools_faq()
    
    def _setup_agent(self):
        """Configura agente básico."""
        prompt = ChatPromptTemplate.from_messages([
            ("system", "Eres un asistente técnico. Usa las herramientas disponibles para ayudar al usuario."),
            ("user", "{input}"),
            ("assistant", "{agent_scratchpad}")
        ])
        
        agent = create_react_agent(self.llm, self.tools, prompt)
        return AgentExecutor(agent=agent, tools=self.tools, verbose=True)
    
    def _setup_agent_faq(self) -> Runnable:
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
            3. Devuelve el problema más parecido en el campo `"problem_name"` y la solución asociada en `"solution_content"`.
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
    
    def _setup_identificacion_solucion_chain(self) -> RunnableSequence:
        """Crea una cadena que analiza si el usuario ha descrito un problema técnico claro."""

        parser = JsonOutputParser(pydantic_object=IdentificacionSolucion)
        
        prompt = PromptTemplate(
            template="""Eres un asistente técnico de Eroski.

        Tu tarea es leer la conversación reciente y decidir si el usuario ha descrito un problema técnico **con suficiente claridad**.

        TIPO DE EQUIPO: {incident_type}

        Si el usuario **no ha dado detalles concretos**, devuelve un mensaje amable pidiendo más información.

        Si el usuario **describe claramente el problema** (por ejemplo: "la balanza no imprime etiquetas"), extrae el problema identificado y su confianza.

        Si el usuario menciona expresamente que quiere hablar con un supervisor, o si da a entender que el problema no se ha resuelto adecuadamente, o que necesita ayuda adicional, entonces devuelve `"escalation_needed": true`.
        En todos los demás casos, devuelve `"escalation_needed": false`.

        ⚠️ NO busques soluciones todavía. Solo analiza si hay un problema identificado. 

        Analiza el historial de mensajes {chat_history} para mantener una conversación fluida con el usuario.
        Si le has pedido confirmación sobre algún punto del problema y el usuario no lo ha confirmado devuelve "problem_identified": false y vuelve a preguntarle nuevamente.
        Si el usuario no responde o no responde con una respuesta clara, devuelve "problem_identified": false y vuelve a preguntarle amablemente.

        Ejemplo de json valido:


        Devuelve un JSON en este formato (sin markdown):

        {format_instructions}

        Ejemplo de json valido:
        {{
        "problem_identified": true,
        "confidence": 0.95,
        "problem_description": "La balanza no imprime etiquetas",
        "requires_confirmation": false,
        "message_to_user": "Gracias por la información. Ahora intentaré ayudarte con este problema.",
        "escalation_needed": false
        }}


        CONVERSACIÓN RECIENTE:
        {chat_history}
        """,
            input_variables=["chat_history", "incident_type"],
            partial_variables={"format_instructions": parser.get_format_instructions()}
        )

        return prompt | self.llm | parser
    
    def _setup_solution_fusion_chain(self):
        """Configura chain de fusión de soluciones."""
        return RunnableLambda(lambda x: f"Solución fusionada: {x}")

    def _mostrar_ejemplos_frecuentes(self, incident_type: str) -> str:
        """Muestra ejemplos de problemas frecuentes al usuario."""
        ejemplos = self.incidents_manager.get_ejemplos_frecuentes(incident_type, 3)
        
        if not ejemplos:
            return f"¿Podrías describir el problema que tienes con {incident_type}?"
        
        ejemplos_text = "\n".join([f"• {ej}" for ej in ejemplos])
        
        return f"""Algunos problemas frecuentes con {incident_type} son:

{ejemplos_text}

¿Cuál de estos se parece a tu problema o podrías describir qué está ocurriendo?"""
    
# Mantener compatibilidad con código existente
EroskiKnowledgeBase = OptimizedEroskiKnowledgeBase