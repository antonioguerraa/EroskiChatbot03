"""
Nodo de búsqueda de soluciones para el chatbot de soporte técnico de Eroski.
Este nodo identifica problemas específicos y proporciona soluciones desde múltiples fuentes.
"""

import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor
import numpy as np
from langchain.agents import create_react_agent, AgentExecutor
from langchain.tools import Tool
from langchain.prompts import PromptTemplate
from langchain_core.messages import HumanMessage, AIMessage
from langchain.schema import BaseMessage
from langchain_core.output_parsers import JsonOutputParser
from langgraph.types import Command
from pydantic import BaseModel, Field

from models.eroski_state import EroskiState
from utils.llm.providers import get_llm, get_vectorizer
from config.settings import get_settings
from nodes.tools.confirmation_tool import ConfirmationTool

# Configuración de logging
logger = logging.getLogger(__name__)

# =============================================================================
# MODELOS PYDANTIC PARA STRUCTURED OUTPUT
# =============================================================================

class ProblemIdentificationResult(BaseModel):
    """Modelo para la respuesta de identificación de problemas."""
    problema: str = Field(description="Descripción clara y específica del problema identificado")
    confidence: float = Field(description="Confianza en la identificación (0.0 a 1.0)", ge=0.0, le=1.0)
    keywords: List[str] = Field(description="Palabras clave relevantes extraídas del mensaje", default_factory=list)
    solucion: str = Field(description="Solución encontrada en ejemplos frecuentes, vacío si no se encuentra", default="")
    similar_a_ejemplo: bool = Field(description="Si el problema es similar a un ejemplo conocido", default=False)
    requiere_mas_info: bool = Field(description="Si se necesita más información para identificar el problema", default=False)
    solution_source: str = Field(description="Fuente de la solución: FAQ, Manual, Otros", default="Otros")

class RobustJsonOutputParser(JsonOutputParser):
    """
    Parser JSON robusto que maneja respuestas LLM con markdown y otros formatos.
    Basado en el patrón usado en authenticate_llm_driven.py
    """
    
    def parse(self, text: str):
        """Parsear respuesta LLM con múltiples estrategias de fallback."""
        try:
            # Estrategia 1: Parser original (JSON directo)
            return super().parse(text)
            
        except Exception as e:
            logger.warning(f"Parser JSON estándar falló: {e}")
            # Si falla, usar estrategias de fallback
            return self._robust_parse(text)
    
    def _robust_parse(self, text: str):
        """Parser robusto con múltiples estrategias de extracción."""
        import re
        
        # Limpiar texto básico
        cleaned_text = text.strip()
        
        # Estrategia 2: Extraer JSON de bloques markdown
        json_patterns = [
            r'```json\s*\n(.*?)\n```',  # ```json ... ```
            r'```\s*\n(.*?)\n```',     # ``` ... ```
            r'\{.*?\}',                 # Buscar primer JSON válido
        ]
        
        for pattern in json_patterns:
            matches = re.findall(pattern, cleaned_text, re.DOTALL | re.IGNORECASE)
            for match in matches:
                try:
                    # Limpiar match si es necesario
                    json_str = match.strip() if isinstance(match, str) else cleaned_text
                    result = json.loads(json_str)
                    
                    # Validar que es un dict
                    if isinstance(result, dict):
                        return result
                except json.JSONDecodeError:
                    continue
        
        # Estrategia 3: Buscar JSON directo en el texto
        try:
            # Intentar parsear todo el texto limpio
            if cleaned_text.startswith('{') and cleaned_text.endswith('}'):
                return json.loads(cleaned_text)
        except json.JSONDecodeError:
            pass
        
        # Estrategia 4: Fallback con valores por defecto
        logger.error(f"No se pudo parsear JSON, usando valores por defecto. Texto: {text[:200]}...")
        return {
            "problema": "Error al procesar la consulta",
            "confidence": 0.0,
            "keywords": [],
            "solucion": "",
            "similar_a_ejemplo": False,
            "requiere_mas_info": True
        }

class EroskiKnowledgeBase:
    """Maneja la conexión y consultas a la base de conocimiento PostgreSQL."""
    
    def __init__(self):
        self.settings = get_settings()
        self.vectorizer = get_vectorizer()
        self._connection = None
    
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

            except Exception as e:
                logger.error(f"Error conectando a PostgreSQL: {e}")
                raise
        return self._connection
    
    def buscar_solucion_rag(self, query: str, top_k: int = 3) -> str:
        """
        Realiza búsqueda semántica en la base de conocimiento usando RAG.
        
        Args:
            query: Consulta del usuario
            top_k: Número de resultados a devolver
            
        Returns:
            str: Texto con las mejores soluciones encontradas
        """
        try:
            # Vectorizar la consulta
            query_embedding = self.vectorizer.embed(query)
            
            # Convertir a formato compatible con PostgreSQL
            query_vector = np.array(query_embedding)
            
            conn = self._get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                # Búsqueda por similitud coseno usando el índice ivfflat
                sql = """
                SELECT 
                    chunk_text,
                    documento_origen,
                    pagina_numero,
                    palabras_clave,
                    1 - (chunk_embedding <=> %s::vector) as similarity
                FROM knowledge_base
                WHERE 1 - (chunk_embedding <=> %s::vector) > 0.7
                ORDER BY chunk_embedding <=> %s::vector
                LIMIT %s;
                """
                
                cursor.execute(sql, (query_vector.tolist(), query_vector.tolist(), 
                                   query_vector.tolist(), top_k))
                results = cursor.fetchall()
                
                if not results:
                    return "No se encontraron soluciones relevantes en los manuales."
                
                # Formatear resultados
                soluciones = []
                for i, result in enumerate(results, 1):
                    solucion = f"""
**Solución {i}** (Fuente: {result['documento_origen']}, Página: {result['pagina_numero']})
Similitud: {result['similarity']:.2f}

{result['chunk_text']}

Palabras clave: {result['palabras_clave']}
---
"""
                    soluciones.append(solucion)
                
                return "\n".join(soluciones)
                
        except Exception as e:
            logger.error(f"Error en búsqueda RAG: {e}")
            return f"Error al buscar en los manuales: {str(e)}"
    
    def close(self):
        """Cierra la conexión a la base de datos."""
        if self._connection and not self._connection.closed:
            self._connection.close()

class EroskiIncidentsManager:
    """Maneja la carga y búsqueda en el archivo JSON de incidencias frecuentes."""
    
    def __init__(self, json_path: str = "data/eroski_incidents.json"):
        self.json_path = Path(json_path)
        self.incidents_data = self._load_incidents()
    
    def _load_incidents(self) -> Dict[str, Any]:
        """Carga el archivo JSON de incidencias."""
        try:
            if not self.json_path.exists():
                logger.warning(f"Archivo de incidencias no encontrado: {self.json_path}")
                return {"incident_types": {}}
            
            with open(self.json_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error cargando incidencias: {e}")
            return {"incident_types": {}}
    
    def get_ejemplos_frecuentes(self, incident_type: str, limit: int = 3) -> List[str]:
        """
        Obtiene ejemplos de problemas frecuentes para un tipo de incidencia.
        
        Args:
            incident_type: Tipo de incidencia (ej: "balanza")
            limit: Número máximo de ejemplos
            
        Returns:
            List[str]: Lista de problemas frecuentes
        """
        try:
            incident_data = self.incidents_data.get("incident_types", {}).get(incident_type, {})
            problemas = incident_data.get("problemas", {})
            
            return list(problemas.keys())[:limit]
        except Exception as e:
            logger.error(f"Error obteniendo ejemplos: {e}")
            return []
    
    def buscar_solucion_json(self, incident_type: str, problema: str) -> Optional[Tuple[str, float]]:
        """
        Busca una solución en el JSON para un problema específico.
        
        Args:
            incident_type: Tipo de incidencia
            problema: Descripción del problema
            
        Returns:
            Tuple[str, float]: (solución, confidence) o None si no encuentra
        """
        try:
            incident_data = self.incidents_data.get("incident_types", {}).get(incident_type, {})
            problemas = incident_data.get("problemas", {})
            
            # Búsqueda exacta
            if problema in problemas:
                return problemas[problema], 1.0
            
            # Búsqueda por similitud de texto simple
            problema_lower = problema.lower()
            for key, solucion in problemas.items():
                if problema_lower in key.lower() or key.lower() in problema_lower:
                    # Calcular confidence básico basado en longitud de coincidencia
                    overlap = len(set(problema_lower.split()) & set(key.lower().split()))
                    total_words = len(set(problema_lower.split()) | set(key.lower().split()))
                    confidence = overlap / total_words if total_words > 0 else 0
                    
                    if confidence >= 0.5:
                        return solucion, confidence
            
            return None
        except Exception as e:
            logger.error(f"Error buscando en JSON: {e}")
            return None

class ProblemIdentificationTool:
    """Tool para identificar problemas específicos usando LLM con JSON output estructurado."""
    
    def __init__(self, incidents_manager: EroskiIncidentsManager):
        self.llm = get_llm()
        self.incidents_manager = incidents_manager
        
        # Configurar parser JSON robusto
        self.parser = RobustJsonOutputParser(pydantic_object=ProblemIdentificationResult)
        
        # Configurar prompt con instrucciones JSON específicas
        self.prompt_template = PromptTemplate(
            template="""Eres un experto en soporte técnico de Eroski. Analiza el siguiente mensaje del usuario 
para identificar el problema específico relacionado con {incident_type}.

Mensaje del usuario: "{user_message}"

Ejemplos de problemas frecuentes para {incident_type}:
{ejemplos_text}

INSTRUCCIONES:
1. Identifica el problema específico que describe el usuario
2. Asigna un nivel de confidence (0.0 a 1.0) basado en qué tan claro es el problema
3. Extrae palabras clave relevantes del mensaje
4. Si encuentras una coincidencia con los ejemplos, marca similar_a_ejemplo como true
5. Si el problema coincide con un ejemplo, incluye la solución correspondiente
6. Si necesitas más información para identificar el problema, marca requiere_mas_info como true

IMPORTANTE: 
- Confidence >= 0.75 indica alta confianza (problema claramente identificado)
- Confidence < 0.75 indica que necesitas más información
- Si hay coincidencia con ejemplos, usa similar_a_ejemplo: true

{format_instructions}

⚠️ CRÍTICO: Responde ÚNICAMENTE con JSON válido. No uses formato Markdown (```json). 
Solo responde con el JSON puro sin texto adicional.""",
            input_variables=["user_message", "incident_type", "ejemplos_text"],
            partial_variables={"format_instructions": self.parser.get_format_instructions()}
        )
    
    def identify_problem(self, user_message: str, incident_type: str) -> Dict[str, Any]:
        """
        Identifica el problema específico del usuario usando LLM con JSON estructurado.
        
        Args:
            user_message: Mensaje del usuario
            incident_type: Tipo de incidencia
            
        Returns:
            Dict con problema, solución, confidence, keywords, etc.
        """
        try:
            # Obtener ejemplos del JSON
            ejemplos = self.incidents_manager.get_ejemplos_frecuentes(incident_type, 5)
            ejemplos_text = "\n".join([f"• {ej}" for ej in ejemplos]) if ejemplos else "No hay ejemplos disponibles"
            
            # Formatear prompt
            formatted_prompt = self.prompt_template.format(
                user_message=user_message,
                incident_type=incident_type,
                ejemplos_text=ejemplos_text
            )
            
            # Invocar LLM
            logger.info(f"🤖 Identificando problema para {incident_type} con mensaje: {user_message[:100]}...")
            response = self.llm.invoke(formatted_prompt)
            
            logger.debug(f"📥 Respuesta cruda LLM: {response.content[:200]}...")
            
            # Parsear con parser robusto
            parsed_result = self.parser.parse(response.content)
            
            # Validar y convertir a ProblemIdentificationResult si es necesario
            if isinstance(parsed_result, dict):
                try:
                    result_model = ProblemIdentificationResult(**parsed_result)
                    # Convertir de vuelta a dict para compatibilidad
                    result = result_model.dict()
                except Exception as e:
                    logger.warning(f"Error validando modelo Pydantic: {e}")
                    # Usar resultado parseado con valores por defecto
                    result = self._ensure_required_fields(parsed_result)
            else:
                result = parsed_result.dict() if hasattr(parsed_result, 'dict') else parsed_result
            
             # Inicializar fuente de la solución
            solution_source = "Otros"  # Por defecto, generado por LLM
           

            # Buscar solución en JSON si hay alta confidence y no se encontró ya
            if result.get("confidence", 0) >= 0.75 and not result.get("solucion"):
                json_result = self.incidents_manager.buscar_solucion_json(
                    incident_type, result["problema"]
                )
                if json_result:
                    solucion, _ = json_result
                    result["solucion"] = solucion
                    result["similar_a_ejemplo"] = True
                    solution_source = "FAQ"
            elif result.get("solucion") and result.get("similar_a_ejemplo"):
                # Si ya tiene solución y es similar a ejemplo, viene del JSON
                solution_source = "FAQ"
            
            # Agregar fuente de la solución al resultado
            result["solution_source"] = solution_source
            
            logger.info(f"✅ Problema identificado: '{result['problema']}' (confidence: {result['confidence']:.2f})")
            
            return result
                
        except Exception as e:
            logger.error(f"❌ Error en identificación de problema: {e}")
            return self._get_fallback_result(user_message, incident_type)
    
    def _ensure_required_fields(self, parsed_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Asegurar que el diccionario parseado tiene todos los campos requeridos."""
        defaults = {
            "problema": parsed_dict.get("problema", "Error al procesar consulta"),
            "confidence": float(parsed_dict.get("confidence", 0.0)),
            "keywords": parsed_dict.get("keywords", []),
            "solucion": parsed_dict.get("solucion", ""),
            "similar_a_ejemplo": bool(parsed_dict.get("similar_a_ejemplo", False)),
            "requiere_mas_info": bool(parsed_dict.get("requiere_mas_info", True)),
            "solution_source": parsed_dict.get("solution_source", "Otros")
        }
        
        # Validar tipos
        if not isinstance(defaults["keywords"], list):
            defaults["keywords"] = []
        
        if not isinstance(defaults["confidence"], (int, float)):
            defaults["confidence"] = 0.0
        
        # Asegurar que confidence esté entre 0 y 1
        defaults["confidence"] = max(0.0, min(1.0, defaults["confidence"]))
        
        return defaults
    
    def _get_fallback_result(self, user_message: str, incident_type: str) -> Dict[str, Any]:
        """Obtener resultado de fallback en caso de error."""
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
    Implementa lógica ReAct con herramientas especializadas.
    """
    
    def __init__(self):
        self.knowledge_base = EroskiKnowledgeBase()
        self.incidents_manager = EroskiIncidentsManager()
        self.problem_tool = ProblemIdentificationTool(self.incidents_manager)
        self.confirmation_tool = ConfirmationTool()
        self.llm = get_llm()
        self.max_attempts = 3
        self.node_name = "buscar_solucion"
        
        # Configurar herramientas para el agente
        self.tools = self._setup_tools()
        self.agent = self._setup_agent()
    
    def _setup_tools(self) -> List[Tool]:
        """Configura las herramientas disponibles para el agente."""
        
        def identify_problem_wrapper(input_str: str) -> str:
            """Wrapper para la herramienta de identificación de problemas."""
            try:
                # Parsear input (formato: "mensaje|incident_type")
                parts = input_str.split("|", 1)
                if len(parts) != 2:
                    return json.dumps({
                        "error": "Formato incorrecto. Use: 'mensaje|tipo_incidencia'",
                        "problema": "Error de formato",
                        "confidence": 0.0,
                        "keywords": []
                    }, ensure_ascii=False, indent=2)
                
                mensaje, incident_type = parts
                result = self.problem_tool.identify_problem(mensaje.strip(), incident_type.strip())
                return json.dumps(result, ensure_ascii=False, indent=2)
            except Exception as e:
                error_result = {
                    "error": f"Error en identificación: {str(e)}",
                    "problema": "Error interno",
                    "confidence": 0.0,
                    "keywords": [],
                    "solucion": "",
                    "similar_a_ejemplo": False,
                    "requiere_mas_info": True
                }
                return json.dumps(error_result, ensure_ascii=False, indent=2)
        
        def buscar_manual_wrapper(query: str) -> str:
            """Wrapper para búsqueda en manuales."""
            try:
                return self.knowledge_base.buscar_solucion_rag(query)
            except Exception as e:
                return f"Error en búsqueda de manual: {str(e)}"
        
        return [
            Tool(
                name="identify_problem",
                description="""
                Identifica el problema específico del usuario usando LLM con JSON estructurado. 
                Input: 'mensaje_usuario|tipo_incidencia'
                Output: JSON con problema, confidence, keywords, solución y flags adicionales.
                Confidence >= 0.75 indica alta confianza en la identificación.
                """,
                func=identify_problem_wrapper
            ),
            Tool(
                name="buscar_solucion_en_manual",
                description="""
                Busca soluciones en los manuales técnicos usando RAG.
                Input: descripción del problema o palabras clave
                Output: Texto con las mejores soluciones encontradas
                """,
                func=buscar_manual_wrapper
            )
        ]
    
    def _setup_agent(self) -> AgentExecutor:
       """Configura el agente ReAct."""
       
       prompt_template = PromptTemplate.from_template("""
            Eres un asistente de soporte técnico de Eroski especializado en resolver incidencias.

            -Tienes acceso a estas herramientas:
            -{tools}
            +Herramientas disponibles: {tool_names}
            +
            +Descripción de herramientas:
            +{tools}

            Tu proceso de trabajo:
            1. Si no se ha identificado el problema, usa identify_problem para analizarlo
            2. Si el problema ya está identificado, usa buscar_solucion_en_manual para encontrar soluciones
            3. Proporciona respuestas claras y estructuradas
            4. Si no encuentras solución, indícalo claramente

            Formato de respuesta:
            Thought: [tu razonamiento]
            Action: [herramienta a usar]
            Action Input: [entrada para la herramienta]
            Observation: [resultado de la herramienta]
            ... (repite si es necesario)
            Final Answer: [respuesta final para el usuario]

            Pregunta: {input}
            Contexto actual: {agent_scratchpad}
            """)
       
       agent = create_react_agent(
           llm=self.llm,
           tools=self.tools,
           prompt=prompt_template
       )
       
       return AgentExecutor(
           agent=agent,
           tools=self.tools,
           verbose=True,
           max_iterations=5,
           early_stopping_method="generate"
       )
    
    def _mostrar_ejemplos_frecuentes(self, incident_type: str) -> str:
        """Muestra ejemplos de problemas frecuentes al usuario."""
        ejemplos = self.incidents_manager.get_ejemplos_frecuentes(incident_type, 3)
        
        if not ejemplos:
            return f"¿Podrías describir el problema que tienes con {incident_type}?"
        
        ejemplos_text = "\n".join([f"• {ej}" for ej in ejemplos])
        
        return f"""Algunos problemas frecuentes con {incident_type} son:

{ejemplos_text}

¿Cuál de estos se parece a tu problema o podrías describir qué está ocurriendo?"""
    
    def _procesar_confirmacion_pendiente(self, state: EroskiState) -> Dict[str, Any]:
        """Procesa cuando hay una confirmación pendiente del usuario."""
        try:
            # Obtener último mensaje del usuario
            last_message = None
            for msg in reversed(state.get("messages", [])):
                if isinstance(msg, HumanMessage):
                    last_message = msg.content
                    break
            
            if not last_message:
                return {
                    "messages": state.get("messages", []) + [
                        AIMessage(content="No pude obtener tu respuesta. ¿Podrías confirmar si he identificado correctamente el problema?")
                    ],
                    "awaiting_user_input": True
                }
            
            # Usar ConfirmationTool para procesar la respuesta
            confirmacion = self.confirmation_tool.process_confirmation(last_message)
            
            if confirmacion["confirmed"]:
                # Usuario confirmó - proceder a buscar soluciones
                problema = state.get("problem_description", "")
                incident_type = state.get("incident_type", "")
                
                # Buscar en JSON
                json_solution = self.incidents_manager.buscar_solucion_json(incident_type, problema)
                json_text = ""
                json_source_label = ""
                if json_solution:
                    json_text = f"**Solución de problemas frecuentes (FAQ):**\n{json_solution[0]}\n\n"
                    json_source_label = " (FAQ)"
                
                # Buscar en manuales
                manual_text = self.knowledge_base.buscar_solucion_rag(problema)
                if manual_text and "No se encontraron" not in manual_text:
                    manual_text = manual_text.replace("**Solución", "**Solución de manuales técnicos (Manual)")
                else:
                    manual_text = ""                
                # Combinar soluciones
                combined_solutions = []
                if json_text:
                    combined_solutions.append(json_text.strip())
                if manual_text:
                    combined_solutions.append(manual_text.strip())
                
                if combined_solutions:
                    solucion_completa = "\n\n".join(combined_solutions) + "\n\n¿Esta solución resuelve tu problema?"
                else:
                    solucion_completa = "No se encontraron soluciones específicas. ¿Podrías proporcionar más detalles del problema?"
                
                return {
                    "problem_identified": True,
                    "pending_confirmation": False,
                    "solution_content": solucion_completa,
                    "messages": state.get("messages", []) + [AIMessage(content=solucion_completa)],
                    "awaiting_user_input": True
                }
                
            elif confirmacion["explicitly_denied"]:
                # Usuario dijo que no - reiniciar identificación
                response = "Entiendo. " + self._mostrar_ejemplos_frecuentes(state.get("incident_type", ""))
                
                return {
                    "pending_confirmation": False,
                    "problem_identified": False,
                    "problem_description": "",
                    "messages": state.get("messages", []) + [AIMessage(content=response)],
                    "awaiting_user_input": True
                }
                
            else:
                # Respuesta ambigua - pedir clarificación
                return {
                    "messages": state.get("messages", []) + [
                        AIMessage(content="No estoy seguro de tu respuesta. ¿Puedes confirmar con 'sí' o 'no' si he identificado correctamente el problema?")
                    ],
                    "awaiting_user_input": True
                }
            
        except Exception as e:
            logger.error(f"Error procesando confirmación: {e}")
            return {
                "messages": state.get("messages", []) + [
                    AIMessage(content="Hubo un error procesando tu confirmación. ¿Podrías intentar de nuevo?")
                ]
            }
    
    def _evaluar_solucion(self, state: EroskiState) -> Dict[str, Any]:
        """Evalúa si la solución proporcionada resuelve el problema."""
        try:
            # Obtener último mensaje del usuario
            last_message = None
            for msg in reversed(state.get("messages", [])):
                if isinstance(msg, HumanMessage):
                    last_message = msg.content
                    break
            
            if not last_message:
                return {
                    "messages": state.get("messages", []) + [
                        AIMessage(content="¿La solución propuesta resuelve tu problema?")
                    ]
                }
            
            # Usar ConfirmationTool
            confirmacion = self.confirmation_tool.process_confirmation(last_message)
            
            if confirmacion["confirmed"]:
                # Solución exitosa
                return {
                    "solution_found": True,
                    "awaiting_user_input": False,
                    "current_node": "resolucion_exitosa",
                    "messages": state.get("messages", []) + [
                        AIMessage(content="¡Perfecto! Me alegra que hayamos resuelto tu problema. ¿Hay algo más en lo que pueda ayudarte?")
                    ]
                }
                
            elif confirmacion["explicitly_denied"]:
                # Solución no funcionó - intentar refinar
                attempts = state.get("solution_attempts", 0) + 1
                
                if attempts >= self.max_attempts:
                    # Activar escalamiento
                    return {
                        "solution_attempts": attempts,
                        "escalation_needed": True,
                        "awaiting_user_input": False,
                        "current_node": "escalation",
                        "messages": state.get("messages", []) + [
                            AIMessage(content="He intentado varias soluciones pero no hemos podido resolver tu problema. Voy a escalarlo a un técnico especializado que te contactará pronto.")
                        ]
                    }
                else:
                    # Permitir refinar el problema
                    response = f"Entiendo que la solución no funcionó. Intentemos identificar mejor el problema. {self._mostrar_ejemplos_frecuentes(state.get('incident_type', ''))}"
                    
                    return {
                        "solution_attempts": attempts,
                        "problem_identified": False,
                        "pending_confirmation": False,
                        "messages": state.get("messages", []) + [AIMessage(content=response)],
                        "awaiting_user_input": True
                    }
            else:
                # Respuesta ambigua
                return {
                    "messages": state.get("messages", []) + [
                        AIMessage(content="¿Podrías confirmar si la solución resolvió tu problema? Responde 'sí' si funcionó o 'no' si necesitas ayuda adicional.")
                    ],
                    "awaiting_user_input": True
                }
            
        except Exception as e:
            logger.error(f"Error evaluando solución: {e}")
            return {
                "messages": state.get("messages", []) + [
                    AIMessage(content="Hubo un error evaluando la solución. ¿Podrías decirme si el problema se resolvió?")
                ]
            }
    
    async def execute(self, state: EroskiState) -> Command:
        """
        Método execute principal para LangGraph que maneja todo el flujo de búsqueda de soluciones.
        
        Args:
            state: Estado actual del chatbot
            
        Returns:
            Command: Comando con las actualizaciones del estado
        """
        print(f"👹Entrada en el nodo {self.__class__.__name__}👹")
        try:
            # Preparar actualización base del estado
            base_update = {
                "current_node": self.node_name,
                "last_activity": datetime.now()
            }
            
            # Verificar que tenemos incident_type
            if not state.get("incident_type"):
                logger.error("No hay incident_type en el estado")
                return Command(update={
                    **base_update,
                    "messages": state.get("messages", []) + [
                        AIMessage(content="Error: No se pudo identificar el tipo de incidencia. Por favor, reinicia la conversación.")
                    ]
                })
            
            # Manejar confirmación pendiente
            if state.get("pending_confirmation", False):
                confirmation_update = self._procesar_confirmacion_pendiente(state)
                return Command(update={**base_update, **confirmation_update})
            
            # Manejar evaluación de solución
            if state.get("solution_content") and not state.get("solution_found", False):
                evaluation_update = self._evaluar_solucion(state)
                return Command(update={**base_update, **evaluation_update})
            
            # Proceso principal de identificación de problemas
            if not state.get("problem_identified", False):
                
                # Obtener último mensaje del usuario
                last_message = None
                for msg in reversed(state.get("messages", [])):
                    if isinstance(msg, HumanMessage):
                        last_message = msg.content
                        break
                
                if not last_message:
                    # Primera vez - mostrar ejemplos
                    response = self._mostrar_ejemplos_frecuentes(state.get("incident_type", ""))
                    return Command(update={
                        **base_update,
                        "messages": state.get("messages", []) + [AIMessage(content=response)],
                        "awaiting_user_input": True
                    })
                
                # Usar agente para identificar el problema
                agent_input = f"Analiza este mensaje del usuario para identificar el problema específico con {state.get('incident_type', '')}: '{last_message}'"
                
                try:
                    agent_response = self.agent.invoke({"input": agent_input})
                    
                    # Extraer información del agente
                    problem_identified = False
                    response_update = {}
                    
                    if "identify_problem" in str(agent_response.get("intermediate_steps", [])):
                        # Buscar resultado JSON en los pasos intermedios
                        for step in agent_response.get("intermediate_steps", []):
                            if hasattr(step, '__len__') and len(step) >= 2:
                                tool_call, tool_result = step[0], step[1]
                                if hasattr(tool_call, 'tool') and tool_call.tool == "identify_problem":
                                    try:
                                        # Parsear resultado JSON del tool
                                        result = json.loads(tool_result)
                                        
                                        # Validar estructura del resultado
                                        if not isinstance(result, dict):
                                            continue
                                        
                                        confidence = result.get("confidence", 0.0)
                                        problema = result.get("problema", "")
                                        requiere_mas_info = result.get("requiere_mas_info", False)
                                        
                                        if confidence >= 0.75 and problema and not requiere_mas_info:
                                            # Alta confianza - pedir confirmación
                                            problem_identified = True
                               
                                            # Agregar etiqueta de fuente a la solución si existe
                                            display_problema = problema
                                            if result.get("solution_source"):
                                                source_label = f" ({result['solution_source']})"
                                                if result.get("solucion"):
                                                    display_problema = f"{problema} - Solución disponible{source_label}"
                                                                          
                                            
                                            
                                            response_update = {
                                                "problem_description": problema,
                                                "pending_confirmation": True,
                                                "awaiting_user_input": True,
                                                "messages": state.get(
                                                    [AIMessage(content=f"Parece que el problema es: **{display_problema}**\n\n¿Es correcto?")]
                                                    )
                                            }
                                        elif confidence < 0.75 or requiere_mas_info:
                                            # Baja confianza o necesita más información
                                            if result.get("keywords"):
                                                hint = f" He detectado palabras clave como: {', '.join(result['keywords'][:3])}"
                                            else:
                                                hint = ""
                                            
                                            response_update = {
                                                "messages": state.get("messages", []) + [
                                                    AIMessage(content=f"No estoy completamente seguro del problema específico.{hint} ¿Podrías dar más detalles sobre qué está ocurriendo exactamente?")
                                                ],
                                                "awaiting_user_input": True
                                            }
                                        else:
                                            # Confidence moderada pero problema identificado
                                            response_update = {
                                                "messages": state.get("messages", []) + [
                                                    AIMessage(content=f"Creo que el problema podría ser: **{problema}**\n\n¿Podrías confirmar si es correcto o dar más detalles?")
                                                ],
                                                "awaiting_user_input": True
                                            }
                                        break
                                        
                                    except (json.JSONDecodeError, KeyError, TypeError) as e:
                                        logger.warning(f"Error parseando resultado del tool: {e}")
                                        continue
                    
                    if not problem_identified:
                        # Usar respuesta final del agente si no se procesó resultado específico
                        response = agent_response.get("output", "No pude procesar tu consulta. ¿Podrías reformular el problema?")
                        response_update = {
                            "messages": state.get("messages", []) + [AIMessage(content=response)],
                            "awaiting_user_input": True
                        }
                    
                    return Command(update={**base_update, **response_update})
                
                except Exception as e:
                    logger.error(f"Error con agente: {e}")
                    return Command(update={
                        **base_update,
                        "messages": state.get("messages", []) + [
                            AIMessage(content="Hubo un problema procesando tu consulta. ¿Podrías describir el problema de forma más específica?")
                        ],
                        "awaiting_user_input": True
                    })
            
            # Si llegamos aquí, mantener estado actual
            return Command(update=base_update)
            
        except Exception as e:
            logger.error(f"Error en buscar_solucion_node: {e}")
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

    def __call__(self, state: EroskiState) -> EroskiState:
        """
        DEPRECADO: Método mantenido para compatibilidad hacia atrás.
        Usar execute() en su lugar.
        """
        import asyncio
        try:
            # Ejecutar de forma síncrona el método async
            command = asyncio.run(self.execute(state))
            # Convertir Command a EroskiState para compatibilidad
            updated_state = {**state}
            updated_state.update(command.update)
            return updated_state
        except Exception as e:
            logger.error(f"Error en __call__: {e}")
            updated_state = {**state}
            updated_state.update({
                "current_node": self.node_name,
                "error": True,
                "messages": state.get("messages", []) + [
                    AIMessage(content="Error ejecutando el nodo.")
                ]
            })
            return updated_state

# Función de entrada para LangGraph siguiendo el patrón del proyecto
async def buscar_solucion_node(state: EroskiState) -> Command:
    """
    Función wrapper para LangGraph - Nodo de Búsqueda de Soluciones
    
    Args:
        state: Estado actual como EroskiState
        
    Returns:
        Command con las actualizaciones de estado
    """
    # Crear instancia del nodo
    node = BuscarSolucionNode()
    
    # Ejecutar el nodo
    return await node.execute(state)

# Para testing y desarrollo
if __name__ == "__main__":
    # Ejemplo de uso para testing
    import asyncio
    from models.eroski_state import EroskiState
    from langchain_core.messages import HumanMessage, AIMessage
    
    async def test_node():
        """Test del nodo de búsqueda de soluciones"""
        
        # Estado de ejemplo
        test_state = EroskiState(
            incident_type="balanza",
            problem_description="",
            problem_identified=False,
            pending_confirmation=False,
            solution_found=False,
            solution_content="",
            messages=[
                HumanMessage(content="La balanza no funciona bien")
            ],
            current_node="buscar_solucion",
            awaiting_user_input=False,
            authenticated=True,
            employee_name="Test User"
        )
        
        # Ejecutar nodo
        try:
            result = await buscar_solucion_node(test_state)
            print("✅ Test completado:")
            print(f"Comando: {type(result)}")
            print(f"Actualizaciones: {list(result.update.keys())}")
            if "messages" in result.update:
                last_msg = result.update["messages"][-1] if result.update["messages"] else None
                if last_msg:
                    print(f"Último mensaje: {last_msg.content[:100]}...")
                    
            # Test adicional del ProblemIdentificationTool
            print("\n🔧 Test del ProblemIdentificationTool:")
            incidents_manager = EroskiIncidentsManager()
            problem_tool = ProblemIdentificationTool(incidents_manager)
            
            test_result = problem_tool.identify_problem(
                "La balanza no imprime etiquetas", 
                "balanza"
            )
            print(f"Resultado: {test_result}")
            print(f"Confidence: {test_result.get('confidence', 0)}")
            print(f"Keywords: {test_result.get('keywords', [])}")
            
        except Exception as e:
            print(f"❌ Error en test: {e}")
            import traceback
            traceback.print_exc()
    
    asyncio.run(test_node())