# =====================================================
# nodes/identificacion_node.py - Nodo de Identificación de Incidencias
# =====================================================
"""
Nodo conversacional para identificar el tipo de incidencia técnica usando LangGraph.

RESPONSABILIDADES:
- Mostrar ejemplos representativos de tipos comunes al inicio
- Usar recuperación semántica para encontrar problemas similares
- Implementar agente React con Tool de identificación
- Confirmar tipo de incidencia con el usuario
- Actualizar estado EroskiState con el tipo identificado

CARACTERÍSTICAS:
- Recuperación semántica de embeddings
- Agente React con Tool personalizada
- Confirmación inteligente usando ConfirmationTool
- Manejo de estado robusto
- Logging detallado para debugging
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import asyncio
import logging
from datetime import datetime

# LangChain imports
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain.agents import create_react_agent, AgentExecutor
from langchain_core.output_parsers import PydanticOutputParser
from langchain_openai import OpenAIEmbeddings
from pydantic import BaseModel, Field

# LangGraph imports
from langgraph.types import Command

# Project imports
from models.eroski_state import EroskiState
from nodes.base_node import BaseNode
from utils.llm.providers import get_llm
from config.settings import get_settings

# Importar tool de confirmación
try:
    from nodes.tools.confirmation_tool import ConfirmationTool
    CONFIRMATION_AVAILABLE = True
except ImportError:
    CONFIRMATION_AVAILABLE = False
    ConfirmationTool = None

# =============================================================================
# MODELOS PYDANTIC PARA STRUCTURED OUTPUT
# =============================================================================

class IncidentIdentification(BaseModel):
    """Modelo para la respuesta de identificación de incidencia"""
    incident_type: str = Field(description="Tipo de incidencia identificado (balanza, tpv, impresoras, etc.)")
    confidence: float = Field(description="Nivel de confianza de 0.0 a 1.0")
    keywords: List[str] = Field(description="Palabras clave que llevaron a la identificación")
    reasoning: str = Field(description="Explicación del razonamiento")
    problem_description: Optional[str] = Field(description="Descripción específica del problema si se detecta")

# =============================================================================
# SISTEMA DE EMBEDDINGS PARA RECUPERACIÓN SEMÁNTICA
# =============================================================================

class SemanticIncidentRetriever:
    """Sistema de recuperación semántica para problemas de incidencias"""
    
    def __init__(self, incidents_data: Dict[str, Any]):
        self.incidents_data = incidents_data
        self.embeddings_model = None
        self.problem_embeddings = {}
        self.problem_texts = {}
        self._setup_embeddings()
    
    def _setup_embeddings(self):
        """Configurar modelo de embeddings y generar embeddings de problemas"""
        try:
            # Usar OpenAI embeddings si está disponible
            settings = get_settings()
            if hasattr(settings.llm, 'openai') and settings.llm.openai.api_key:
                self.embeddings_model = OpenAIEmbeddings(
                    api_key=settings.llm.openai.api_key,
                    model="text-embedding-3-small"
                )
            else:
                logging.warning("⚠️ OpenAI API key no disponible, usando fallback simple")
                return
                
            # Generar embeddings para todos los problemas
            self._generate_problem_embeddings()
            
        except Exception as e:
            logging.error(f"❌ Error configurando embeddings: {e}")
            self.embeddings_model = None
    
    def _generate_problem_embeddings(self):
        """Generar embeddings para todos los problemas en el JSON"""
        try:
            problem_texts = []
            problem_keys = []
            
            for incident_type, data in self.incidents_data.items():
                if 'problemas' in data:
                    for problem_title, solution in data['problemas'].items():
                        # Combinar título del problema con keywords para mejor matching
                        keywords = data.get('keywords', [])
                        combined_text = f"{problem_title} {' '.join(keywords)}"
                        
                        problem_texts.append(combined_text)
                        problem_keys.append((incident_type, problem_title, solution))
            
            if problem_texts and self.embeddings_model:
                # Generar embeddings en batch
                embeddings = self.embeddings_model.embed_documents(problem_texts)
                
                for i, embedding in enumerate(embeddings):
                    incident_type, problem_title, solution = problem_keys[i]
                    key = f"{incident_type}:{problem_title}"
                    self.problem_embeddings[key] = embedding
                    self.problem_texts[key] = {
                        'incident_type': incident_type,
                        'problem': problem_title,
                        'solution': solution,
                        'text': problem_texts[i]
                    }
                
                logging.info(f"✅ Generados {len(embeddings)} embeddings para problemas")
            
        except Exception as e:
            logging.error(f"❌ Error generando embeddings: {e}")
    
    def find_similar_problems(self, user_query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Encontrar problemas similares usando similitud semántica"""
        try:
            if not self.embeddings_model or not self.problem_embeddings:
                # Fallback: buscar por keywords simples
                return self._fallback_keyword_search(user_query, top_k)
            
            # Generar embedding para la consulta del usuario
            query_embedding = self.embeddings_model.embed_query(user_query)
            
            # Calcular similitudes
            similarities = []
            for key, problem_embedding in self.problem_embeddings.items():
                similarity = self._cosine_similarity(query_embedding, problem_embedding)
                similarities.append((key, similarity))
            
            # Ordenar por similitud y tomar top_k
            similarities.sort(key=lambda x: x[1], reverse=True)
            
            results = []
            for key, similarity in similarities[:top_k]:
                problem_data = self.problem_texts[key].copy()
                problem_data['similarity'] = similarity
                results.append(problem_data)
            
            return results
            
        except Exception as e:
            logging.error(f"❌ Error en búsqueda semántica: {e}")
            return self._fallback_keyword_search(user_query, top_k)
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calcular similitud coseno entre dos vectores"""
        try:
            import numpy as np
            vec1 = np.array(vec1)
            vec2 = np.array(vec2)
            return np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))
        except ImportError:
            # Fallback sin numpy
            dot_product = sum(a * b for a, b in zip(vec1, vec2))
            magnitude1 = sum(a * a for a in vec1) ** 0.5
            magnitude2 = sum(b * b for b in vec2) ** 0.5
            if magnitude1 == 0 or magnitude2 == 0:
                return 0
            return dot_product / (magnitude1 * magnitude2)
    
    def _fallback_keyword_search(self, user_query: str, top_k: int) -> List[Dict[str, Any]]:
        """Búsqueda de fallback basada en keywords"""
        user_query_lower = user_query.lower()
        results = []
        
        for incident_type, data in self.incidents_data.items():
            if 'problemas' not in data:
                continue
                
            # Verificar keywords del tipo de incidencia
            keywords = data.get('keywords', [])
            keyword_matches = sum(1 for kw in keywords if kw.lower() in user_query_lower)
            
            # Buscar en problemas específicos
            for problem_title, solution in data['problemas'].items():
                problem_matches = sum(1 for word in problem_title.lower().split() 
                                    if word in user_query_lower)
                
                total_score = keyword_matches + problem_matches
                if total_score > 0:
                    results.append({
                        'incident_type': incident_type,
                        'problem': problem_title,
                        'solution': solution,
                        'similarity': total_score / 10.0,  # Normalizar
                        'text': f"{problem_title} {' '.join(keywords)}"
                    })
        
        # Ordenar por score y tomar top_k
        results.sort(key=lambda x: x['similarity'], reverse=True)
        return results[:top_k]

# =============================================================================
# TOOL DE IDENTIFICACIÓN DE INCIDENCIAS
# =============================================================================

class IdentifyIncidentTool:
    """Tool para identificar tipo de incidencia usando LLM y recuperación semántica"""
    
    def __init__(self, incidents_data: Dict[str, Any], llm, retriever: SemanticIncidentRetriever):
        self.incidents_data = incidents_data
        self.llm = llm
        self.retriever = retriever
        self.parser = PydanticOutputParser(pydantic_object=IncidentIdentification)
        
        # Crear prompt para identificación
        self.identification_prompt = ChatPromptTemplate.from_messages([
            ("system", """Eres un especialista en identificación de incidencias técnicas para Eroski.

Tu misión es analizar el mensaje del usuario y identificar el tipo de incidencia técnica.

TIPOS DE INCIDENCIAS DISPONIBLES:
{incident_types_summary}

PROBLEMAS SIMILARES ENCONTRADOS (recuperación semántica):
{similar_problems}

REGLAS DE IDENTIFICACIÓN:
1. Analiza las palabras clave en el mensaje del usuario
2. Considera los problemas similares encontrados por el sistema de recuperación
3. Asigna un nivel de confianza basado en la claridad del mensaje
4. Si la confianza es >= 0.75, considera la identificación válida
5. Si la confianza es < 0.75, indica que necesitas más información

FORMATO DE RESPUESTA:
{format_instructions}

Analiza el mensaje del usuario cuidadosamente y proporciona tu identificación."""),
            ("human", "Mensaje del usuario: {user_message}")
        ])
    
    @tool
    def identify_incident_type(self, user_message: str) -> Dict[str, Any]:
        """
        Identificar el tipo de incidencia basado en el mensaje del usuario.
        
        Args:
            user_message: Mensaje del usuario describiendo el problema
            
        Returns:
            Dict con incident_type, confidence, keywords, etc.
        """
        try:
            # 1. Recuperación semántica de problemas similares
            similar_problems = self.retriever.find_similar_problems(user_message, top_k=3)
            
            # 2. Crear resumen de tipos de incidencias
            incident_types_summary = self._create_incident_types_summary()
            
            # 3. Formatear problemas similares para el prompt
            similar_problems_text = self._format_similar_problems(similar_problems)
            
            # 4. Ejecutar prompt de identificación
            formatted_prompt = self.identification_prompt.format(
                user_message=user_message,
                incident_types_summary=incident_types_summary,
                similar_problems=similar_problems_text,
                format_instructions=self.parser.get_format_instructions()
            )
            
            response = self.llm.invoke(formatted_prompt)
            
            # 5. Parsear respuesta estructurada
            identification = self.parser.parse(response.content)
            
            # 6. Convertir a dict para compatibilidad con la tool
            return {
                "incident_type": identification.incident_type,
                "confidence": identification.confidence,
                "keywords": identification.keywords,
                "reasoning": identification.reasoning,
                "problem_description": identification.problem_description,
                "similar_problems": similar_problems  # Info adicional
            }
            
        except Exception as e:
            logging.error(f"❌ Error en identify_incident_type: {e}")
            return {
                "incident_type": "unknown",
                "confidence": 0.0,
                "keywords": [],
                "reasoning": f"Error en identificación: {str(e)}",
                "problem_description": None,
                "similar_problems": []
            }
    
    def _create_incident_types_summary(self) -> str:
        """Crear resumen de tipos de incidencias disponibles"""
        summary_lines = []
        for incident_type, data in self.incidents_data.items():
            name = data.get('name', incident_type)
            description = data.get('description', 'Sin descripción')
            keywords = ', '.join(data.get('keywords', []))
            summary_lines.append(f"- {incident_type.upper()}: {name} - {description} (Keywords: {keywords})")
        
        return '\n'.join(summary_lines)
    
    def _format_similar_problems(self, similar_problems: List[Dict[str, Any]]) -> str:
        """Formatear problemas similares para incluir en el prompt"""
        if not similar_problems:
            return "No se encontraron problemas similares."
        
        formatted_lines = []
        for i, problem in enumerate(similar_problems, 1):
            similarity = problem.get('similarity', 0)
            incident_type = problem.get('incident_type', 'unknown')
            problem_text = problem.get('problem', 'Sin descripción')
            
            formatted_lines.append(
                f"{i}. TIPO: {incident_type.upper()} | PROBLEMA: {problem_text} "
                f"(Similitud: {similarity:.2f})"
            )
        
        return '\n'.join(formatted_lines)

# =============================================================================
# NODO PRINCIPAL DE IDENTIFICACIÓN
# =============================================================================

class IdentificacionNode(BaseNode):
    """
    Nodo principal para identificación de incidencias técnicas.
    
    FUNCIONAMIENTO:
    1. Carga tipos comunes al inicio de la conversación
    2. Usa recuperación semántica para encontrar problemas similares
    3. Implementa agente React con Tool de identificación
    4. Confirma tipo identificado con el usuario
    5. Actualiza estado EroskiState cuando se confirma
    """
    
    def __init__(self):
        super().__init__("IdentificacionIncidencia")
        self.llm = get_llm()
        
        # Configurar tool de confirmación
        self.confirmation_tool = ConfirmationTool() if CONFIRMATION_AVAILABLE else None
        
        # Cargar datos de incidencias
        self.incidents_data = self._load_incidents_data()
        
        # Configurar sistema de recuperación semántica
        self.semantic_retriever = SemanticIncidentRetriever(self.incidents_data)
        
        # Configurar tool de identificación
        self.identify_tool = IdentifyIncidentTool(
            self.incidents_data, 
            self.llm, 
            self.semantic_retriever
        )
        
        # Configurar agente React
        self.agent = self._setup_react_agent()
        
    def get_required_fields(self) -> List[str]:
        return ["authenticated", "messages"]
    
    def get_actor_description(self) -> str:
        return "Identifico tipos de incidencias técnicas usando IA conversacional y recuperación semántica"
    
    def _load_incidents_data(self) -> Dict[str, Any]:
        """Cargar datos de incidencias desde el archivo JSON"""
        try:
            # Buscar archivo en diferentes ubicaciones
            possible_paths = [
                Path("data/eroski_incidents.json"),
            ]
            
            for json_path in possible_paths:
                if json_path.exists():
                    with open(json_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        
                        # Verificar estructura del JSON
                        if "incident_types" in data:
                            self.logger.info(f"✅ Cargados datos de incidencias desde {json_path}")
                            return data["incident_types"]
                        elif "tipo_incidente" in data:
                            self.logger.info(f"✅ Cargados datos de incidencias desde {json_path}")
                            return data["tipo_incidente"]
            
            self.logger.error("❌ No se encontró archivo de incidencias")
            return {}
            
        except Exception as e:
            self.logger.error(f"❌ Error cargando datos de incidencias: {e}")
            return {}
    
    def _setup_react_agent(self) -> AgentExecutor:
        """Configurar agente React con las tools disponibles"""
        try:
            # Lista de tools disponibles
            tools = [self.identify_tool.identify_incident_type]
            
            # Template para el agente React
            react_template = """Eres un asistente especializado en identificación de incidencias técnicas para Eroski.

Tu misión es ayudar al empleado a identificar el tipo de incidencia que está experimentando.

TIPOS COMUNES DE INCIDENCIAS:
- BALANZAS: Problemas con pesado, etiquetado, precios incorrectos
- TPV: Problemas con cajas registradoras, lectores de tarjetas, impresión tickets
- IMPRESORAS: Problemas de impresión, atascos, cartuchos
- RED: Problemas de conectividad, internet, WiFi

HERRAMIENTAS DISPONIBLES:
{tools}

INSTRUCCIONES:
1. Analiza el mensaje del usuario buscando indicios del tipo de incidencia
2. Si no está claro, haz preguntas específicas sobre el equipo o problema
3. Usa la herramienta identify_incident_type cuando tengas suficiente información
4. Si la confianza es >= 0.75, procede a confirmar con el usuario
5. Si la confianza es < 0.75, pide más detalles específicos

FORMATO DE RESPUESTA:
Thought: [tu análisis del mensaje]
Action: [nombre de la herramienta si necesitas usarla]
Action Input: [input para la herramienta]
Observation: [resultado de la herramienta]
Thought: [tu análisis del resultado]
Final Answer: [respuesta final al usuario]

CONVERSACIÓN ACTUAL:
{chat_history}

MENSAJE DEL USUARIO: {input}

HISTORIAL DE PENSAMIENTOS:
{agent_scratchpad}"""

            # Crear prompt template
            react_prompt = PromptTemplate(
                template=react_template,
                input_variables=["tools", "chat_history", "input", "agent_scratchpad"],
                partial_variables={"tools": "\n".join([f"{tool.name}: {tool.description}" for tool in tools])}
            )
            
            # Crear agente React
            agent = create_react_agent(
                llm=self.llm,
                tools=tools,
                prompt=react_prompt
            )
            
            # Crear AgentExecutor
            agent_executor = AgentExecutor(
                agent=agent,
                tools=tools,
                verbose=True,
                max_iterations=5,
                handle_parsing_errors=True
            )
            
            return agent_executor
            
        except Exception as e:
            self.logger.error(f"❌ Error configurando agente React: {e}")
            return None
    
    def _get_common_examples(self) -> str:
        """Obtener ejemplos representativos de tipos comunes"""
        examples = []
        common_types = ['balanza', 'balanzas', 'tpv', 'impresoras']  # Tipos más comunes
        
        for incident_type in common_types:
            if incident_type in self.incidents_data:
                data = self.incidents_data[incident_type]
                name = data.get('name', incident_type)
                description = data.get('description', '')
                examples.append(f"🔧 **{name}**: {description}")
        
        if examples:
            return "Estos son algunos tipos comunes de incidencias:\n\n" + '\n'.join(examples)
        else:
            return "Por favor, describe el problema que estás experimentando."
    
    async def execute(self, state: EroskiState) -> Command:
        """Ejecutar lógica principal del nodo de identificación"""
        try:
            self.logger.info("🔍 Iniciando identificación de incidencia")
            
            # Verificar autenticación
            if not state.get("authenticated"):
                self.logger.warning("⚠️ Usuario no autenticado")
                return Command(update={
                    "messages": state["messages"] + [
                        AIMessage(content="Necesitas estar autenticado para reportar incidencias.")
                    ],
                    "current_node": "authenticate",
                    "awaiting_user_input": True
                })
            
            # Obtener último mensaje del usuario
            messages = state.get("messages", [])
            last_message = None
            for msg in reversed(messages):
                if isinstance(msg, HumanMessage):
                    last_message = msg.content
                    break
            
            # Si es la primera vez en este nodo, mostrar ejemplos comunes
            if not state.get("identification_started"):
                common_examples = self._get_common_examples()
                response_text = f"""¡Hola! Voy a ayudarte a identificar el tipo de incidencia técnica.

{common_examples}

Por favor, describe el problema que estás experimentando o menciona qué equipo está dando problemas."""
                
                return Command(update={
                    "messages":[AIMessage(content=response_text)],
                    "identification_started": True,
                    "current_node": "identificacion",
                    "awaiting_user_input": True
                })
            
            # Procesar confirmación pendiente
            if state.get("pending_confirmation"):
                return await self._handle_confirmation(state, last_message)
            
            # Procesar mensaje con agente React
            if last_message and self.agent:
                return await self._process_with_agent(state, last_message, messages)
            
            # Fallback si no hay agente
            return await self._fallback_identification(state, last_message, messages)
            
        except Exception as e:
            self.logger.error(f"❌ Error en execute: {e}")
            return Command(update={
                "messages": messages + [
                    AIMessage(content="Disculpa, ha ocurrido un error. ¿Puedes describir tu problema de nuevo?")
                ],
                "error_count": state.get("error_count", 0) + 1,
                "awaiting_user_input": True
            })
    
    async def _handle_confirmation(self, state: EroskiState, last_message: str) -> Command:
        """Manejar confirmación de tipo de incidencia"""
        try:
            if not self.confirmation_tool or not last_message:
                # Sin tool de confirmación, asumir "sí" si es positivo
                confirmation = "si" if any(word in last_message.lower() 
                                         for word in ["sí", "si", "correcto", "exacto", "afirmativo"]) else "no"
            else:
                confirmation = self.confirmation_tool.check_raw(last_message)
            
            incident_type = state.get("pending_incident_type")
            
            if confirmation == "si":
                # Confirmado - actualizar estado y avanzar
                response_text = f"¡Perfecto! He confirmado que el problema es con **{incident_type}**. Ahora vamos a recopilar más detalles sobre la incidencia."
                
                return Command(update={
                    "messages": state["messages"] + [AIMessage(content=response_text)],
                    "incident_type": incident_type,
                    "pending_confirmation": False,
                    "pending_incident_type": None,
                    "current_node": "collect_incident_details",  # Siguiente nodo
                    "awaiting_user_input": True
                })
            
            elif confirmation == "no":
                # No confirmado - continuar buscando
                response_text = "Entendido, no es ese tipo de problema. Por favor, describe con más detalle qué equipo o sistema está fallando."
                
                return Command(update={
                    "messages": state["messages"] + [AIMessage(content=response_text)],
                    "pending_confirmation": False,
                    "pending_incident_type": None,
                    "awaiting_user_input": True
                })
            
            else:
                # Respuesta ambigua - pedir clarificación
                incident_type = state.get("pending_incident_type", "problema")
                response_text = f"No estoy seguro de tu respuesta. ¿Confirmas que el problema es con **{incident_type}**? Por favor responde 'sí' o 'no'."
                
                return Command(update={
                    "messages": state["messages"] + [AIMessage(content=response_text)],
                    "awaiting_user_input": True
                })
                
        except Exception as e:
            self.logger.error(f"❌ Error en confirmación: {e}")
            return Command(update={
                "messages": state["messages"] + [
                    AIMessage(content="Ha ocurrido un error. ¿Puedes confirmar de nuevo el tipo de problema?")
                ],
                "error_count": state.get("error_count", 0) + 1,
                "awaiting_user_input": True
            })
    
    async def _process_with_agent(self, state: EroskiState, user_message: str, messages: List) -> Command:
        """Procesar mensaje usando el agente React"""
        try:
            # Preparar historial para el agente
            chat_history = self._format_chat_history(messages)
            
            # Ejecutar agente
            result = await asyncio.to_thread(
                self.agent.invoke,
                {
                    "input": user_message,
                    "chat_history": chat_history
                }
            )
            
            agent_response = result.get("output", "No pude procesar tu mensaje.")
            
            # Verificar si el agente identificó algo con alta confianza
            if hasattr(result, 'intermediate_steps') and result['intermediate_steps']:
                last_step = result['intermediate_steps'][-1]
                if last_step[0].tool == "identify_incident_type":
                    tool_output = last_step[1]
                    if isinstance(tool_output, dict) and tool_output.get("confidence", 0) >= 0.75:
                        # Alta confianza - proceder a confirmación
                        incident_type = tool_output["incident_type"]
                        keywords = ", ".join(tool_output.get("keywords", []))
                        
                        confirmation_text = f"""He identificado que tu problema parece ser con **{incident_type}** (basado en: {keywords}).

¿Es correcto que el problema es con {incident_type}?"""
                        
                        return Command(update={
                            "messages": messages + [AIMessage(content=confirmation_text)],
                            "pending_confirmation": True,
                            "pending_incident_type": incident_type,
                            "identification_confidence": tool_output["confidence"],
                            "identification_keywords": tool_output.get("keywords", []),
                            "awaiting_user_input": True
                        })
            
            # Respuesta normal del agente
            return Command(update={
                "messages": messages + [AIMessage(content=agent_response)],
                "awaiting_user_input": True
            })
            
        except Exception as e:
            self.logger.error(f"❌ Error procesando con agente: {e}")
            return await self._fallback_identification(state, user_message, messages)
    
    async def _fallback_identification(self, state: EroskiState, user_message: str, messages: List) -> Command:
        """Identificación de fallback sin agente React"""
        try:
            # Usar directamente la tool de identificación
            tool_result = self.identify_tool.identify_incident_type(user_message)
            
            if tool_result["confidence"] >= 0.75:
                # Alta confianza - confirmar
                incident_type = tool_result["incident_type"]
                reasoning = tool_result.get("reasoning", "")
                
                response_text = f"""He identificado que tu problema parece ser con **{incident_type}**.

{reasoning}

¿Es correcto que el problema es con {incident_type}?"""
                
                return Command(update={
                    "messages": messages + [AIMessage(content=response_text)],
                    "pending_confirmation": True,
                    "pending_incident_type": incident_type,
                    "identification_confidence": tool_result["confidence"],
                    "awaiting_user_input": True
                })
            
            else:
                # Baja confianza - pedir más información
                response_text = """No estoy completamente seguro del tipo de problema. ¿Puedes ser más específico?

Por ejemplo:
- ¿Qué equipo está fallando? (balanza, caja registradora, impresora, ordenador...)
- ¿Cuál es el síntoma exacto? (no enciende, no imprime, error en pantalla...)
- ¿En qué sección de la tienda ocurre?"""
                
                return Command(update={
                    "messages": messages + [AIMessage(content=response_text)],
                    "awaiting_user_input": True
                })
                
        except Exception as e:
            self.logger.error(f"❌ Error en fallback: {e}")
            return Command(update={
                "messages": messages + [
                    AIMessage(content="Disculpa, no pude procesar tu mensaje. ¿Puedes describir el problema de otra manera?")
                ],
                "error_count": state.get("error_count", 0) + 1,
                "awaiting_user_input": True
            })
    
    def _format_chat_history(self, messages: List) -> str:
        """Formatear historial de mensajes para el agente"""
        try:
            formatted_lines = []
            for msg in messages[-10:]:  # Últimos 10 mensajes
                if isinstance(msg, HumanMessage):
                    formatted_lines.append(f"Usuario: {msg.content}")
                elif isinstance(msg, AIMessage):
                    formatted_lines.append(f"Asistente: {msg.content}")
            
            return '\n'.join(formatted_lines) if formatted_lines else "No hay historial previo."
        
        except Exception as e:
            self.logger.error(f"❌ Error formateando historial: {e}")
            return "Error al cargar historial."

# =============================================================================
# FUNCIÓN FACTORY PARA EL NODO
# =============================================================================

def identificacion_node() -> IdentificacionNode:
    """Factory function para crear el nodo de identificación"""
    return IdentificacionNode()

# =============================================================================
# PUNTO DE ENTRADA PARA TESTING
# =============================================================================

if __name__ == "__main__":
    # Test rápido del nodo
    import asyncio
    from models.eroski_state import create_initial_eroski_state
    
    async def test_node():
        node = identificacion_node()
        
        # Estado de prueba
        test_state = create_initial_eroski_state("test-session")
        test_state["authenticated"] = True
        test_state["employee_name"] = "Juan Pérez"
        test_state["messages"] = [
            HumanMessage(content="Hola, tengo un problema con la balanza")
        ]
        
        # Ejecutar nodo
        result = await node.execute(test_state)
        
        print("✅ Test completado:")
        print(f"Mensajes: {len(result.update.get('messages', []))}")
        print(f"Último mensaje: {result.update.get('messages', [])[-1].content if result.update.get('messages') else 'N/A'}")
    
    asyncio.run(test_node())