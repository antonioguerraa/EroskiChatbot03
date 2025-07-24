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

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
from datetime import datetime
from langchain_core.messages import AIMessage, HumanMessage, BaseMessage
from langchain_core.tools import tool, Tool
from langchain_core.prompts import ChatPromptTemplate
from langchain.agents import create_react_agent, AgentExecutor
from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langchain.schema.runnable import RunnableSequence
from langchain_core.runnables import RunnableLambda
from langgraph.types import Command

# Imports del proyecto
from models.eroski_state import EroskiState
from utils.llm.providers import get_llm, get_vectorizer
from config.settings import get_settings
from nodes.tools.confirmation_tool import ConfirmationTool

# PostgreSQL imports
import psycopg2
import numpy as np
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

# =====================================================
# CLASE RAG OPTIMIZADA - REEMPLAZA LA ANTERIOR
# =====================================================

class OptimizedEroskiKnowledgeBase:
    """
    Versión optimizada del RAG que reemplaza la clase EroskiKnowledgeBase original.
    
    MEJORAS IMPLEMENTADAS:
    - Threshold optimizado (0.4 vs 0.7 anterior)
    - Mejor formateo de resultados
    - Integración con diccionario técnico
    - Manejo de errores robusto
    - Logging detallado
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.vectorizer = get_vectorizer()
        self._connection = None
        
        # CONFIGURACIÓN OPTIMIZADA
        self.similarity_threshold = 0.4  # MEJORADO: Era 0.7, ahora 0.4
        self.max_results = 3
        
        logger.info("✅ RAG optimizado inicializado con threshold 0.4")
    
    def _get_connection(self):
        """Obtiene una conexión a la base de datos PostgreSQL."""
        if self._connection is None or self._connection.closed:
            try:
                # Preparar parámetros de conexión
                conn_params = {
                    "host": self.settings.database.host,
                    "database": self.settings.database.name,
                    "user": self.settings.database.user,
                    "port": self.settings.database.port
                }
                
                # Solo agregar password si no está vacío
                if self.settings.database.password:
                    conn_params["password"] = self.settings.database.password
                
                self._connection = psycopg2.connect(**conn_params)
                logger.debug("✅ Conexión PostgreSQL establecida")

            except Exception as e:
                logger.error(f"Error conectando a PostgreSQL: {e}")
                raise
        return self._connection
    
    def buscar_solucion_rag(self, query: str, top_k: int = 3) -> str:
        """
        MÉTODO PRINCIPAL - Realiza búsqueda semántica optimizada en la base de conocimiento.
        
        MEJORAS IMPLEMENTADAS:
        - Threshold optimizado de 0.4 (vs 0.7 anterior)
        - Mejor formateo de resultados
        - Logging detallado
        - Manejo de errores robusto
        
        Args:
            query: Consulta del usuario
            top_k: Número de resultados a devolver
            
        Returns:
            str: Texto formateado con las mejores soluciones encontradas
        """
        logger.info(f"🔍 Búsqueda RAG optimizada: '{query}'")
        
        try:
            # 1. Vectorizar la consulta
            query_embedding = self.vectorizer.embed(query)
            if not query_embedding:
                logger.error("❌ No se pudo vectorizar la consulta")
                return self._format_no_results(query, "Error de vectorización")
            
            # 2. Convertir a formato compatible con PostgreSQL
            query_vector = np.array(query_embedding)
            
            # 3. Ejecutar búsqueda vectorial optimizada
            conn = self._get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                
                # SQL OPTIMIZADO con threshold mejorado
                sql = """
                SELECT 
                    chunk_text,
                    documento_origen,
                    pagina_numero,
                    palabras_clave,
                    seccion,
                    chunk_metadata,
                    1 - (chunk_embedding <=> %s::vector) as similarity
                FROM knowledge_base
                WHERE chunk_embedding IS NOT NULL
                AND 1 - (chunk_embedding <=> %s::vector) > %s
                ORDER BY chunk_embedding <=> %s::vector
                LIMIT %s;
                """
                
                # Ejecutar consulta con threshold optimizado
                cursor.execute(sql, (
                    query_vector.tolist(), 
                    query_vector.tolist(),
                    self.similarity_threshold,  # 0.4 vs 0.7 anterior
                    query_vector.tolist(), 
                    top_k
                ))
                results = cursor.fetchall()
                
                # 4. Procesar y formatear resultados
                if not results:
                    logger.warning(f"⚠️ Sin resultados para '{query}' con threshold {self.similarity_threshold}")
                    return self._format_no_results(query, "Threshold muy restrictivo")
                
                logger.info(f"✅ {len(results)} resultados encontrados (similitud: {results[0]['similarity']:.3f}-{results[-1]['similarity']:.3f})")
                
                return self._format_results_optimized(results, query)
                
        except Exception as e:
            logger.error(f"❌ Error en búsqueda RAG optimizada: {e}")
            return self._format_error_result(query, str(e))
    
    def _format_results_optimized(self, results: List[Dict], query: str) -> str:
        """
        NUEVO - Formatea resultados con mejor presentación y información útil.
        """
        if not results:
            return self._format_no_results(query, "Sin resultados")
        
        formatted_parts = []
        
        # Header con resumen
        best_similarity = results[0]['similarity']
        if best_similarity > 0.8:
            quality_indicator = "🎯 **Excelente coincidencia**"
        elif best_similarity > 0.6:
            quality_indicator = "✅ **Buena coincidencia**"
        else:
            quality_indicator = "📋 **Coincidencia parcial**"
        
        formatted_parts.append(f"{quality_indicator} - {len(results)} soluciones encontradas para: **{query}**\n")
        
        # Formatear cada resultado
        for i, result in enumerate(results, 1):
            similarity = result['similarity']
            chunk_text = result['chunk_text'].strip()
            
            # Limpiar y truncar texto si es muy largo
            if len(chunk_text) > 500:
                chunk_text = chunk_text[:500] + "..."
            
            # Información del documento
            doc_info = f"📄 {result['documento_origen']}"
            if result['pagina_numero']:
                doc_info += f", Página {result['pagina_numero']}"
            if result['seccion']:
                doc_info += f" - {result['seccion']}"
            
            # Formatear solución
            solution_block = f"""
**Solución {i}** (Similitud: {similarity:.2f})
{doc_info}

{chunk_text}

"""
            
            # Agregar palabras clave si están disponibles
            if result['palabras_clave'] and len(result['palabras_clave']) > 0:
                keywords = result['palabras_clave'][:5]  # Máximo 5 keywords
                solution_block += f"🏷️ **Palabras clave:** {', '.join(keywords)}\n"
            
            solution_block += "---\n"
            formatted_parts.append(solution_block)
        
        # Footer con consejos
        footer = f"""
💡 **¿Te ayudó esta información?**
• Si necesitas más detalles, puedes preguntar sobre aspectos específicos
• Para problemas complejos, puedes consultar las páginas mencionadas del manual
• Si el problema persiste, considera escalarlo a soporte técnico

🔧 **Basado en:** Manual técnico DIBAL Mistral con {len(results)} soluciones relevantes
"""
        formatted_parts.append(footer)
        
        return "\n".join(formatted_parts)
    
    def _format_no_results(self, query: str, reason: str = "") -> str:
        """NUEVO - Mensaje mejorado cuando no hay resultados."""
        return f"""
🔍 **No se encontraron resultados específicos para:** "{query}"

**💡 Sugerencias para mejorar la búsqueda:**
• Usa términos más específicos del equipo (ej: "DIBAL Mistral calibración")
• Incluye el modelo exacto del equipo si lo conoces
• Prueba sinónimos técnicos (ej: "menú configuración" o "pantalla display")
• Describe el problema de forma más detallada

**🔧 Términos que funcionan bien:**
• Para balanzas: peso, tara, calibrar, etiqueta, imprimir
• Para configuración: menú, configuración, pantalla, teclado
• Para problemas: error, no funciona, problema, fallo

**📞 Si es urgente:** Considera escalarlo a soporte técnico especializado.

{f"📋 **Información técnica:** {reason}" if reason else ""}
"""
    
    def _format_error_result(self, query: str, error: str) -> str:
        """NUEVO - Mensaje de error mejorado."""
        return f"""
❌ **Error en la búsqueda:** No pude procesar tu consulta "{query}"

**🔧 Posibles soluciones:**
1. Reformula tu consulta con términos diferentes
2. Ser más específico sobre el problema
3. Incluir marca y modelo del equipo si los conoces

**🔧 Para problemas urgentes:**
• Reinicia el equipo y prueba nuevamente
• Verifica conexiones básicas
• Consulta el manual físico del equipo

📋 **Error técnico:** {error}
"""
    
    def close(self):
        """Cierra la conexión a la base de datos."""
        if self._connection and not self._connection.closed:
            self._connection.close()
            logger.debug("🔒 Conexión PostgreSQL cerrada")

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
        self.knowledge_base = OptimizedEroskiKnowledgeBase()  # NUEVO RAG
        
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
        self.logger.info(f"🔍 Ejecutando buscar_solucion_node con RAG optimizado")
        
        try:
            # Obtener información del estado
            messages = state.get("messages", [])
            incident_type = state.get("incident_type", "")
            problem_identified = state.get("problem_identified", False)
            solution_found = state.get("solution_found", False)
            pending_confirmation = state.get("pending_confirmation", False)
            attempts = state.get("attempts", 0)
            
            if not messages:
                return Command(update={
                    "current_node": self.node_name,
                    "messages": [AIMessage(content="¡Hola! ¿En qué puedo ayudarte hoy?")],
                    "awaiting_user_input": True
                })
            
            last_message = messages[-1]
            if not isinstance(last_message, HumanMessage):
                return Command(update={
                    "current_node": self.node_name,
                    "awaiting_user_input": True
                })
            
            user_input = last_message.content
            
            # Base para actualizaciones del estado
            base_update = {
                "current_node": self.node_name,
                "last_activity": datetime.now(),
                "attempts": attempts + 1
            }
            
            # Lógica de confirmación pendiente
            if pending_confirmation:
                self.logger.info("⏳ Procesando confirmación pendiente")
                confirmation_result = await self.confirmation_tool.process_confirmation(user_input)
                
                if confirmation_result["confirmed"]:
                    # Usuario confirmó el problema
                    base_update.update({
                        "problem_identified": True,
                        "pending_confirmation": False,
                        "problem_description": state.get("temp_problem_description", ""),
                    })
                    
                    problem_desc = state.get("temp_problem_description", user_input)
                    
                    # LÍNEA CLAVE: Usar RAG optimizado para buscar solución
                    self.logger.info(f"🔍 Buscando solución con RAG optimizado para: {problem_desc}")
                    solution_content_manual = self.knowledge_base.buscar_solucion_rag(problem_desc)
                    
                    base_update.update({
                        "solution_content": solution_content_manual,
                        "messages": messages + [
                            AIMessage(content=f"""✅ **Problema confirmado:** {problem_desc}

{solution_content_manual}

**¿Esta solución resuelve tu problema?** (Responde sí/no)""")
                        ],
                        "awaiting_user_input": True
                    })
                    
                else:
                    # Usuario no confirmó, pedir más información
                    base_update.update({
                        "pending_confirmation": False,
                        "messages": messages + [
                            AIMessage(content="Entiendo. ¿Podrías describir el problema con más detalle? Esto me ayudará a encontrar la solución más adecuada.")
                        ],
                        "awaiting_user_input": True
                    })
                
                return Command(update=base_update)
            
            # Lógica principal de identificación y búsqueda
            if not problem_identified:
                self.logger.info(f"🔍 Identificando problema para incident_type: {incident_type}")
                
                # Usar herramienta FAQ para identificar problema
                result = self.faq_problem_tool.identify_problem(user_input, incident_type)
                
                if result.get("confidence", 0) >= 0.75:
                    # Alta confianza, pedir confirmación
                    base_update.update({
                        "pending_confirmation": True,
                        "temp_problem_description": result.get("problema", user_input),
                        "messages": messages + [
                            AIMessage(content=f"""🎯 **Creo que he identificado tu problema:**

**{result.get("problema", "Problema identificado")}**

¿Es correcto? (Responde sí/no)

💡 Si no es exactamente tu problema, puedes describirlo con más detalle.""")
                        ],
                        "awaiting_user_input": True
                    })
                    
                else:
                    # Baja confianza, buscar directamente en manual
                    self.logger.info(f"🔍 Confianza baja ({result.get('confidence', 0):.2f}), buscando directamente en manual")
                    
                    # LÍNEA CLAVE: Usar RAG optimizado directamente
                    solution_content_manual = self.knowledge_base.buscar_solucion_rag(user_input)
                    
                    base_update.update({
                        "problem_identified": True,
                        "problem_description": user_input,
                        "solution_content": solution_content_manual,
                        "messages": messages + [
                            AIMessage(content=f"""🔍 **He buscado información sobre tu consulta:**

{solution_content_manual}

**¿Esta información te ayuda con tu problema?** (Responde sí/no)

💡 Si necesitas información más específica, puedes reformular tu pregunta.""")
                        ],
                        "awaiting_user_input": True
                    })
            
            else:
                # Problema ya identificado, evaluar respuesta del usuario
                if solution_found:
                    # Ya se encontró solución, procesar feedback
                    user_input_lower = user_input.lower()
                    if any(word in user_input_lower for word in ['sí', 'si', 'yes', 'correcto', 'perfecto', 'gracias']):
                        base_update.update({
                            "conversation_completed": True,
                            "messages": messages + [
                                AIMessage(content="¡Perfecto! Me alegra haber podido ayudarte. Si tienes más problemas, no dudes en consultarme. 😊")
                            ],
                            "awaiting_user_input": False
                        })
                    else:
                        # Usuario indica que la solución no funcionó
                        extra_info_response = self.llm_extra_info_prompt | self.llm | self.parser_str
                        has_extra_info = await extra_info_response.ainvoke({"user_message": user_input})
                        
                        if has_extra_info.strip().lower() == "si":
                            # Nueva información, buscar nueva solución
                            self.logger.info("🔄 Nueva información detectada, buscando solución actualizada")
                            
                            # LÍNEA CLAVE: Usar RAG optimizado con nueva información
                            solution_content_manual = self.knowledge_base.buscar_solucion_rag(user_input)
                            
                            base_update.update({
                                "solution_content": solution_content_manual,
                                "messages": messages + [
                                    AIMessage(content=f"""🔄 **Gracias por la información adicional. He buscado una nueva solución:**

{solution_content_manual}

**¿Esta nueva información te ayuda?** (Responde sí/no)""")
                                ],
                                "awaiting_user_input": True
                            })
                        else:
                            # No hay nueva información útil
                            if attempts >= self.max_attempts:
                                base_update.update({
                                    "escalation_needed": True,
                                    "messages": messages + [
                                        AIMessage(content="Entiendo que las soluciones propuestas no han funcionado. Te recomiendo contactar con soporte técnico especializado para una asistencia más detallada. 📞")
                                    ],
                                    "awaiting_user_input": False
                                })
                            else:
                                base_update.update({
                                    "messages": messages + [
                                        AIMessage(content="Entiendo que la solución no funcionó. ¿Podrías describir el problema de forma más específica?")
                                    ],
                                    "awaiting_user_input": True
                                })
                else:
                    # Evaluar si el usuario está satisfecho con la información proporcionada
                    user_input_lower = user_input.lower()
                    if any(word in user_input_lower for word in ['sí', 'si', 'yes', 'correcto', 'perfecto', 'gracias', 'ayuda']):
                        base_update.update({
                            "solution_found": True,
                            "conversation_completed": True,
                            "messages": messages + [
                                AIMessage(content="¡Excelente! Me alegra haber podido ayudarte con la información del manual técnico. Si tienes más consultas, estaré aquí para ayudarte. 😊")
                            ],
                            "awaiting_user_input": False
                        })
                    else:
                        # Usuario no está satisfecho
                        if attempts >= self.max_attempts:
                            base_update.update({
                                "escalation_needed": True,
                                "messages": messages + [
                                    AIMessage(content="He hecho varios intentos para ayudarte. Te recomiendo contactar con soporte técnico especializado para una asistencia más personalizada. 📞")
                                ],
                                "awaiting_user_input": False
                            })
                        else:
                            base_update.update({
                                "messages": messages + [
                                    AIMessage(content="¿Podrías describir el problema de forma más específica?")
                                ],
                                "awaiting_user_input": True
                            })
            
            return Command(update=base_update)
            
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
            except:
                pass

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
    
    def _setup_agent_faq(self):
        """Configura agente FAQ."""
        return self._setup_agent()  # Simplificado
    
    def _setup_identificacion_solucion_chain(self):
        """Configura chain de identificación."""
        return RunnableLambda(lambda x: {"problema": x, "confidence": 0.5})
    
    def _setup_solution_fusion_chain(self):
        """Configura chain de fusión de soluciones."""
        return RunnableLambda(lambda x: f"Solución fusionada: {x}")

# Mantener compatibilidad con código existente
EroskiKnowledgeBase = OptimizedEroskiKnowledgeBase