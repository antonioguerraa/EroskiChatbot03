"""
Nodo de búsqueda de soluciones para el chatbot de soporte técnico de Eroski.
Este nodo identifica problemas específicos y proporciona soluciones desde múltiples fuentes.
"""

import sys
import os

# Añade la raíz del proyecto al sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor
import numpy as np
from langchain.agents import create_react_agent, AgentExecutor
from langchain_core.tools import Tool
from langchain.prompts import PromptTemplate
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain.schema import BaseMessage
from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langgraph.types import Command
from langchain_core.runnables import Runnable
from pydantic import BaseModel, Field

from models.eroski_state import EroskiState
from utils.llm.providers import get_llm, get_vectorizer
from config.settings import get_settings
from nodes.tools.confirmation_tool import ConfirmationTool
from utils.incident_manager import get_incident_manager
from nodes.verifiers.agent_output_llm_verifier import AgentOutputLLMVerifier
from langchain_core.prompts import ChatPromptTemplate

from langchain_core.runnables import RunnableSequence
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from models.indentificacion_solucion import ManualSearchResponse



# Configuración de logging
logger = logging.getLogger(__name__)

# =============================================================================
# MODELOS PYDANTIC PARA STRUCTURED OUTPUT
# =============================================================================

class FAQProblemInput(BaseModel):
    mensaje_usuario: str = Field(..., description="Mensaje original del usuario con el problema")
    tipo_incidencia: str = Field(..., description="Tipo de incidencia, por ejemplo: TPV, caja, báscula")

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
                    return "No se encontraron soluciones relevantes en los manuales. (Manual)"
                
                # Formatear resultados
                soluciones = []
                for i, result in enumerate(results, 1):
                    solucion = f"""
**Solución {i} (Manual)** (Fuente: {result['documento_origen']}, Página: {result['pagina_numero']})
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
                carga_datos = json.load(f)
                return carga_datos
        except Exception as e:
            logger.error(f"Error cargando incidencias: {e}")
            return {"incident_types": {}}


    
    def get_problemas_soluciones(self, incident_type: str, limit: int = None) -> List[str]:
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
            #print("👹"*100)
            #print(f"👹incident_data: {incident_data} \nincident_type: {incident_type}")
            problemas = incident_data.get("problemas", {})
            #print(f"👹problemas: {problemas}")
            #print(f"👹problmeas_type: {type(problemas)}")
            
            return problemas
        except Exception as e:
            logger.error(f"Error obteniendo ejemplos: {e}")
            return []
    


    def get_ejemplos_frecuentes(self, incident_type: str, limit: int = None) -> List[str]:
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
            #print("👹"*100)
            #print(f"👹incident_data: {incident_data} \nincident_type: {incident_type}")
            problemas = incident_data.get("problemas", {})
            #print(f"👹problemas: {problemas}")
            
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

class FAQ_ProblemIdentificationTool:
    """Tool para identificar problemas específicos usando LLM con JSON output estructurado.
    Utiliza como entrada un archivo JSON con las problemas y soluciones asociadas más frecuentes.
    
    """
    
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
    
    def faq_problem(self, user_message: str, incident_type: str) -> Dict[str, Any]:
        """
        Identifica el problema específico del usuario usando LLM con JSON estructurado.
        Utiliza un archivo JSON con problemas y soluciones frecuentes predefinidos.
        
        Args:
            user_message: Mensaje del usuario
            incident_type: Tipo de incidencia
            
        Returns:
            Dict con problema, solución, confidence, keywords, etc.
        """
        try:
            # Obtener ejemplos del JSON
            #print(f"👹check incident_type: {incident_type}")
            ejemplos = self.incidents_manager.get_ejemplos_frecuentes(incident_type, 5)
            #print("👹"*100)
            #print(f"👹faq_json: {ejemplos}")
            #print("👹"*100)
            
            # Formatear ejemplos para incluir en el prompt
            ejemplos_text = "\n".join([f"• {ej}" for ej in ejemplos]) if ejemplos else "No hay ejemplos disponibles"
            #print(f"👹faq_json: {ejemplos_text}")
            
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
        #self.agent_manual = self._setup_agent_manual()
        self.chain_manual = self._setup_manual_chain()
        self.agent_faq = self._setup_agent_faq()


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
            """Wrapper para búsqueda en manuales."""
            try:
                return self.knowledge_base.buscar_solucion_rag(query)
            except Exception as e:
                return f"Error en búsqueda de manual: {str(e)}"
        
        return [
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
    
    def _setup_tools_faq(self) -> List[Tool]:
        """Configura las herramientas disponibles para el agente.
            Devuelve una Tool que ejecuta `faq_problem` con validación robusta de input.
        """
        
        def FAQ_problem_wrapper(input_dict: dict) -> str:
            """Wrapper para la herramienta de identificación de problemas.
                Envuelve la función self.faq_problem y devuelve un JSON serializado como string.
            """
            try:
                mensaje = input_dict.get("mensaje_usuario", "")
                incident_type = input_dict.get("tipo_incidencia", "")
                #print(f"👹 mensaje: ", mensaje)
                #print(f"👹 tipo_incidencia: ", incident_type)
                
                logger.info(f"📥 Ejecutando FAQ Tool con mensaje='{mensaje}' | tipo_incidencia='{tipo}'")

                result: Dict[str, Any] = self.faq_problem_tool.faq_problem(mensaje, tipo)

                return json.dumps(result, indent=2, ensure_ascii=False)

            except Exception as e:
                logger.error(f"❌ Error en FAQ Tool: {e}")
                fallback = {
                    "error": f"Error interno: {str(e)}",
                    "problema": "Error interno",
                    "confidence": 0.0,
                    "keywords": [],
                    "solucion": "",
                    "similar_a_ejemplo": False,
                    "requiere_mas_info": True
                }
                return json.dumps(fallback, indent=2, ensure_ascii=False)

        return [
            Tool(
                name="faq_problem",
                description="""
                Identifica el problema específico del usuario usando LLM con JSON estructurado.
                Requiere: mensaje_usuario y tipo_incidencia.
                """,
                func=FAQ_problem_wrapper,
                args_schema=FAQProblemInput
        )]
    
    def _setup_tools(self) -> List[Tool]:
        """Configura las herramientas disponibles para el agente."""
        
        def FAQ_problem_wrapper(input_str: str) -> str:
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
                result = self.faq_problem_tool.faq_problem(mensaje.strip(), incident_type.strip())
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
                name="faq_problem",
                description="""
                Identifica el problema específico del usuario usando LLM con JSON estructurado. 
                Input: 'mensaje_usuario|tipo_incidencia'
                Output: JSON con problema, confidence, keywords, solución y flags adicionales.
                Confidence >= 0.75 indica alta confianza en la identificación.
                """,
                func=FAQ_problem_wrapper
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
        """Configura el agente ReAct con orientación proactiva a buscar solución directamente."""
        
        prompt_template = PromptTemplate.from_template("""
    Eres un asistente de soporte técnico de Eroski especializado en resolver incidencias en tiendas.

    Tu objetivo es analizar el historial reciente del usuario y ofrecer una posible solución con la información disponible.

    Tienes acceso a las siguientes herramientas:
    {tools}

    Herramientas disponibles: {tool_names}

    Historial reciente del usuario:
    {user_history}

    Tu proceso:
    1. Si necesitas extraer detalles del problema, puedes usar la herramienta "faq_problem".
    2. Si ya tienes una idea razonable, busca directamente soluciones en los manuales o responde con tu conocimiento.
    3. Siempre que des una solución, termina con: **¿Esta solución resuelve tu problema?**

    IMPORTANTE:
    - No esperes confirmación previa del usuario.
    - Etiqueta cada paso con su fuente: (FAQ), (Manual), (Otros)
    - Si no encuentras solución, pide más detalles de forma amable.

    Formato de respuesta:
    Thought: [tu razonamiento]
    Action: [herramienta a usar]
    Action Input: [entrada para la herramienta]
    Observation: [resultado de la herramienta]
    ... (repite si es necesario)
    Final Answer: [respuesta clara al usuario con etiquetas y pregunta de confirmación]

    Pregunta: {input}
    Contexto del agente: {agent_scratchpad}
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
    

    def _setup_manual_chain(self) -> RunnableSequence:
        """Configura un chain que detecta si el usuario describe un problema real y responde en consecuencia."""
        
        parser = JsonOutputParser(pydantic_object=ManualSearchResponse)

        prompt = PromptTemplate(
            template="""Eres un asistente de soporte técnico de Eroski.

    Tu tarea es analizar los últimos mensajes del usuario para ver si describen claramente un problema técnico.

    - Si el usuario **no describe un problema concreto** (por ejemplo, solo dice "tengo un problema con la balanza"), pide más detalles amablemente.
    - Si el usuario **describe un problema claro** (ej. "la balanza no imprime etiquetas"), genera una respuesta útil y clara.
    - Sé flexible, educado y evita sonar repetitivo si el usuario pasa varias veces por aquí.

    Devuelve solo un JSON con la siguiente estructura:

    {format_instructions}

    MENSAJES DEL USUARIO:
    {user_history}
    """,
            input_variables=["user_history"],
            partial_variables={"format_instructions": parser.get_format_instructions()}
        )

        return prompt | self.llm | parser



    def _setup_agent_manual(self) -> AgentExecutor:
        """Configura el agente ReAct con orientación proactiva a buscar solución directamente."""
        
        prompt_template = PromptTemplate.from_template("""
    Eres un asistente de soporte técnico de Eroski especializado en resolver incidencias en tiendas.

    Tu objetivo es analizar el historial reciente del usuario y ofrecer una posible solución con la información disponible.

    Tienes acceso a las siguientes herramientas:
    {tools}

    Herramientas disponibles: {tool_names}

    Historial reciente del usuario:
    {user_history}

    Tu proceso:
    1. Si necesitas extraer detalles del problema, puedes usar la herramienta "faq_problem".
    2. Si ya tienes una idea razonable, busca directamente soluciones en los manuales o responde con tu conocimiento.
    3. Siempre que des una solución, termina con: **¿Esta solución resuelve tu problema?**

    IMPORTANTE:
    - No esperes confirmación previa del usuario.
    - Etiqueta cada paso con su fuente: (FAQ), (Manual), (Otros)
    - Si no encuentras solución, pide más detalles de forma amable.

    Formato de respuesta:
    Thought: [tu razonamiento]
    Action: [herramienta a usar]
    Action Input: [entrada para la herramienta]
    Observation: [resultado de la herramienta]
    ... (repite si es necesario)
    Final Answer: [respuesta clara al usuario con etiquetas y pregunta de confirmación]

    Pregunta: {input}
    Contexto del agente: {agent_scratchpad}
    """)

        agent = create_react_agent(
            llm=self.llm,
            tools=self.tools_manual,
            prompt=prompt_template
        )

        return AgentExecutor(
            agent=agent,
            tools=self.tools_manual,
            verbose=True,
            max_iterations=5,
            early_stopping_method="generate"
        )
    
    def _setup_agent_faq_v01(self) -> AgentExecutor:
        """Configura el agente ReAct con orientación proactiva a buscar solución directamente."""
        
        prompt_template = PromptTemplate.from_template("""
    Eres un asistente de soporte técnico de Eroski especializado en resolver incidencias en tiendas.

    Tu objetivo es analizar el historial reciente del usuario y ofrecer una posible solución con la información disponible.

    Tienes acceso a las siguientes herramientas:
    {tools}

    Herramientas disponibles: {tool_names}

    El input para la herramienta es:
        mensaje_usuario:{user_history}
        tipo_incidencia: {incident_type}

    Historial reciente del usuario:
    {user_history}

    Tu proceso:
    1. Si necesitas extraer detalles del problema, puedes usar la herramienta "faq_problem".
    2. Si ya tienes una idea razonable, busca directamente soluciones en los manuales o responde con tu conocimiento.
    3. Siempre que des una solución, termina con: **¿Esta solución resuelve tu problema?**

    IMPORTANTE:
    - No esperes confirmación previa del usuario.
    - Etiqueta cada paso con su fuente: (FAQ), (Manual), (Otros)
    - Si no encuentras solución, pide más detalles de forma amable.

    Formato de respuesta:
    Thought: [tu razonamiento]
    Action: [herramienta a usar]
    Action Input: [entrada para la herramienta]
    Observation: [resultado de la herramienta]
    ... (repite si es necesario)
    Final Answer: [respuesta clara al usuario con etiquetas y pregunta de confirmación]

    Pregunta: {input}
    Contexto del agente: {agent_scratchpad}
    """)

        agent = create_react_agent(
            llm=self.llm,
            tools=self.tools_faq,
            prompt=prompt_template
        )

        return AgentExecutor(
            agent=agent,
            tools=self.tools_faq,
            verbose=True,
            max_iterations=5,
            early_stopping_method="generate"
        )

#-------------------------------------------
    
    
    
    
    def _setup_agent_faq(self) -> Runnable:

        
        """Configura el agente para buscar la solución en el archivo json que guarda los problemas más frecuentes.
        Misión:
        1. Identificar el problema dentro del listado de problemas para el tipo de incidente que hay en el json
        2. Recuperar la solución más adecuada a ese problema.
        
        """
        
        prompt_template = PromptTemplate.from_template("""
                Eres un asistente técnico que ayuda a identificar el problema más probable en función del historial de mensajes de un usuario y una lista de problemas conocidos.

                ### Instrucciones:

                1. Lee los mensajes del usuario.
                2. Compara el contenido con los problemas disponibles.
                3. Devuelve el problema más parecido y su solución.
                4. Estima una confianza (entre 0.0 y 1.0).
                5. La salida debe tener exactamente este formato:

                {format_instructions}

                Mensajes del usuario:
                {mensajes_usuario}

                Problemas conocidos:
                {problemas_json}
                """)
        parser = JsonOutputParser()

        prompt = prompt_template.partial(format_instructions=parser.get_format_instructions())
        chain = prompt | self.llm | parser

        return chain



#-------------------------------------------

    def _fusionador_soluciones(self, llm_manual: dict, llm_faq: dict) -> dict:
        """
        Fusiona dos respuestas dict (que pueden incluir AIMessage) en un único JSON estructurado.

        Args:
            llm_manual (dict): Respuesta del LLM manual.
            llm_faq (dict): Respuesta del LLM faq.

        Returns:
            dict: Respuesta fusionada con estructura normalizada.
        """

        def to_serializable(obj: dict) -> dict:
            """
            Convierte cualquier instancia de AIMessage en un diccionario plano { "content": str }.
            """
            obj_copy = obj.copy()
            if "messages" in obj_copy and isinstance(obj_copy["messages"], list):
                obj_copy["messages"] = [
                    {"content": m.content} if isinstance(m, AIMessage)
                    else {"content": m.get("content", str(m))}
                    for m in obj_copy["messages"]
                ]
            return obj_copy

        fusion_prompt_template = """
        Fusiona las siguientes dos respuestas JSON generadas por modelos diferentes (`llm_manual` y `llm_faq`) en un único JSON con la siguiente estructura:

        {{
        "problem_description": string,
        "problem_identified": boolean,
        "pending_confirmation": boolean,
        "messages": [
            {{
            "content": string
            }}
        ],
        "solution_content": string,
        "awaiting_user_input": boolean,
        "confidence": float
        }}

        Reglas:
        1. `problem_description`: combinar o unificar las descripciones de ambos modelos.
        2. `problem_identified`: true si alguno de los modelos lo tiene como true.
        3. `pending_confirmation`: true si alguno de los modelos lo tiene como true.
        4. `messages`: un único mensaje con la solución fusionada, indicando origen (manual o faq). Si hay URL, añade la referencia: (manual - ver: URL) o (faq - ver: URL).
        5. `solution_content`: mismo texto que en messages pero como string plano.
        6. `awaiting_user_input`: true si alguno de los modelos lo tiene como true.
        7. `confidence`: el mayor valor de los dos.

        Solo devuelve el JSON, sin comentarios ni explicaciones.

        - LLM Manual:
        {llm_manual}

        - LLM FAQ:
        {llm_faq}
        """.strip()

        prompt = PromptTemplate.from_template(fusion_prompt_template)
        parser = JsonOutputParser()
        chain = prompt | self.llm | parser

        # Asegura serialización válida de los mensajes
        llm_manual_serializable = json.dumps(to_serializable(llm_manual), indent=2, ensure_ascii=False)
        llm_faq_serializable = json.dumps(to_serializable(llm_faq), indent=2, ensure_ascii=False)

        # Invocar el LLM
        result = chain.invoke({
            "llm_manual": llm_manual_serializable,
            "llm_faq": llm_faq_serializable
        })

        # Reconstruir los messages como AIMessage si es necesario
        if isinstance(result.get("messages"), list):
            result["messages"] = [AIMessage(content=m["content"]) for m in result["messages"]]

        return result


    def _mostrar_ejemplos_frecuentes(self, incident_type: str) -> str:
        """Muestra ejemplos de problemas frecuentes al usuario."""
        ejemplos = self.incidents_manager.get_ejemplos_frecuentes(incident_type, 3)
        
        if not ejemplos:
            return f"¿Podrías describir el problema que tienes con {incident_type}?"
        
        ejemplos_text = "\n".join([f"• {ej}" for ej in ejemplos])
        
        return f"""Algunos problemas frecuentes con {incident_type} son:

{ejemplos_text}

¿Cuál de estos se parece a tu problema o podrías describir qué está ocurriendo?"""
    
    def _extraer_historial_usuario(self, state: EroskiState, max_mensajes: int = 4) -> str:
        """
        Extrae los últimos mensajes del usuario para dar más contexto al agente.
        """
        mensajes_usuario = [
            m.content for m in state.get("messages", []) if isinstance(m, HumanMessage)
        ]
        return "\n".join(mensajes_usuario[-max_mensajes:]).strip()

    async def _procesar_confirmacion_pendiente(self, state: EroskiState) -> Dict[str, Any]:
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
            confirmacion = self.confirmation_tool.check_with_state(last_message, state)
            #print(f"👹 confirmación: {confirmacion}")


            if confirmacion == "si":
                # Usuario confirmó - proceder a buscar soluciones
                problema = state.get("problem_description", "")
                incident_type = state.get("incident_type", "")
                
                # Buscar en JSON
                json_solution = self.incidents_manager.buscar_solucion_json(incident_type, problema)
                json_text = ""
                if json_solution:
                # Etiquetar cada línea/paso del JSON con (FAQ)
                    solution_lines = json_solution[0].split('\n')
                    tagged_lines = []
                    for line in solution_lines:
                        if line.strip() and not line.strip().startswith('**'):
                            tagged_lines.append(f"{line.strip()} (FAQ)")
                        else:
                            tagged_lines.append(line)
                    json_text = f"**Solución de problemas frecuentes:**\n{chr(10).join(tagged_lines)}\n\n"
                
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
                    "messages": [AIMessage(content=solucion_completa)],
                    "awaiting_user_input": True
                }

            elif confirmacion == "no":
                # Usuario dijo que no - ¿pero dio detalles útiles?
                last_message = None
                for msg in reversed(state.get("messages", [])):
                    if isinstance(msg, HumanMessage):
                        last_message = msg.content
                        break

                # Llama al verificador LLM para ver si hay información adicional útil
                from nodes.verifiers.additional_info_llm_verifier import AdditionalInfoLLMVerifier
                verifier = AdditionalInfoLLMVerifier()
                info_util = verifier.analyze(last_message, state)

                if info_util:  # Si el LLM cree que hay info útil
                    
                    return Command(update={
                        "extra_info_provided": True,
                        "problem_identified": False,
                        "pending_confirmation": False,
                        "messages": state.get("messages", []) + [
                            AIMessage(content="Gracias por la información adicional. Intentemos identificar de nuevo el problema.")
                        ],
                        "awaiting_user_input": False
                    })
                else:
                    # No hay info útil → pedirle al usuario más contexto
                    response = "Entiendo. " + self._mostrar_ejemplos_frecuentes(state.get("incident_type", ""))
                    return Command(update={
                        "pending_confirmation": False,
                        "problem_identified": False,
                        "problem_description": "",
                        "messages": state.get("messages", []) + [AIMessage(content=response)],
                        "awaiting_user_input": True
                    })

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
            confirmacion = self.confirmation_tool.check_with_state(last_message, state)
            #print(f"👹confirmacion : {confirmacion}, --line 759")
            if confirmacion == "si":
                # Solución exitosa
                return {
                    "solution_found": True,
                    "awaiting_user_input": False,
                    "current_node": "resolucion_exitosa",
                    "messages": state.get("messages", []) + [
                        AIMessage(content="¡Perfecto! Me alegra que hayamos resuelto tu problema. ¿Hay algo más en lo que pueda ayudarte?")
                    ]
                }
                
            elif confirmacion == "no":
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
        #print(f"👹Entrada en el nodo {self.__class__.__name__}👹")
        #print(f"👹confirmación incidente {state.get('incident_type_confirmed')}👹")
        #print(f"👹pending_confirmation {state.get('pending_confirmation')}👹")
        #print(f"👹awaiting_user_input {state.get('awaiting_user_input')}👹")
        incident_id = state.get("incident_id", None)
        if not incident_id:
            incident_id = get_incident_manager().manage_incident(state)
        #print(f"👹Incidente ID: {incident_id}👹")
        try:
            incident_type = state.get("incident_type")
            if not incident_type:
                return self._handle_missing_incident_type(state)
            
            # Preparar actualización base del estado
            base_update = {
                "incident_id": incident_id,
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
            
            #print(f"👹Solution content: {state.get('solution_contet')}")

            # Manejar evaluación de solución
            if state.get("solution_content") and not state.get("solution_found", False):

                evaluation_update = self._evaluar_solucion(state)
                self._track_incident_state(state, evaluation_update)
                return Command(update={**base_update, **evaluation_update})
            

            # Manejar confirmación pendiente
            if state.get("pending_confirmation", False):
                #print(f"👹Confirmacion: {state.get('pending_confirmation', False)}")
                confirmation_update = await self._procesar_confirmacion_pendiente(state)
                if isinstance(confirmation_update, Command):
                    self._track_incident_state(state, confirmation_update.update)
                    return Command(update={**base_update, **confirmation_update.update})
                else:
                    return Command(update={**base_update, **confirmation_update})

            # Proceso principal de identificación de problemas
            if not state.get("problem_identified", False):
                print("👹 No se identificó el problema.👹")
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
                
                user_history = "\n".join([
                    f"- {m.content}" for m in state.get("messages", [])[-5:] if isinstance(m, HumanMessage)
                ])
                agent_input = "Por favor, ayuda al usuario con base en la información anterior."

                try:

                    ##print("🎗️"*100)
                    #agent_response = self.agent.invoke({"input": agent_input,
                    #                                    "user_history": user_history})
                    agent_response_manual = self.agent_manual.invoke({"input": agent_input,
                                                        "user_history": user_history})
                    
                    ##print(f"👹 user_history: {user_history}\ntipo_incidencia {incident_type}")
                    
                    
                    #Con el incident_type sacamos el diccionario de problemas del json
                    problemas_dict = self.incidents_manager.get_problemas_soluciones(incident_type)

                    agent_response_faq = self.agent_faq.invoke({
                                                        "mensajes_usuario": user_history,
                                                        "problemas_json": json.dumps(problemas_dict, indent=2, ensure_ascii=False)})
                    
                    # 2. Lo convertimos a texto legible para el verificador LLM
                    #print(f"\n\n👹agent_response_faq: {agent_response_faq}\n\n")
                    mensaje_para_verificador_faq = agent_response_faq.get("Solución","No se identificó el problema")
                    ##print(f"👹mensaje_para_verificador: {mensaje_para_verificador_faq}")

                    ##print("👹👹👹Es un dict:", isinstance(agent_response_faq, dict))
                    ##print("👹👹👹Es un string:", isinstance(agent_response_faq, str))
                    ##print("👹👹👹Tipo real de llm_manual:", type(agent_response_faq))


                    ##print(f"👹agent_response: \n{agent_response}\n\n")
                    #for key, valy in agent_response.items():
                    #    #print(f"👹{key} - {valy}")
                    #for key, valy in agent_response_manual.items():
                    #    #print(f"👹{key} - {valy}")
                    #print("-"*100)
                    ##print(f"👹agent_response_faq: \n{agent_response_faq}\n\n")
                    #for key, valy in agent_response_faq.items():
                    #    #print(f"👹{key} - {valy}")


                    verifier = AgentOutputLLMVerifier()
                    #response_update = verifier.analyze(agent_response.get("output", ""), state)
                    response_update_manual = verifier.analyze(agent_response_manual.get("output", ""), state) if state.get("busqueda_manual") else {}
                    response_update_faq = verifier.analyze(mensaje_para_verificador_faq, state) if state.get("busqueda_faq") else {}
                    
                    #print(f"\n\n👹agent_response_manual: \n{agent_response_manual}\n\n")
                    #print(f"\n\n👹response_update_manual: {response_update_manual}\n\n")
                    #print("-"*100)
                    #print(f"\n\n👹agent_response_faq: \n{agent_response_faq}\n\n")
                    #print(f"\n\n👹response_update_faq: {response_update_faq}\n\n")

                    #print("-"*100)

                    ##print(f"mensaje para verificador: \n{mensaje_para_verificador_faq}\n\n")
                    
                    
                    
                    response_update = self._fusionador_soluciones(response_update_manual,response_update_faq)
                    ##print(f"👹response_update: \n{response_update}\n\n")
                    ##print("-"*100)
                    #print(f"👹response_update: \n{response_update}\n\n")
                    #print("-"*100)
                    ##print(f"👹response_update_faq: \n{response_update_faq}\n\n")
                    #for k, v in response_update.items():
                    #    #print(f"👹👹: \n{k}: \n{v}")
                    ##print("🎗️"*100)
                    self._track_incident_state(state, response_update)

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
    
    def _get_incident_manager(self):
        """Obtener instancia singleton del incident manager"""
        if self._incident_manager is None:
            self._incident_manager = get_incident_manager()
        return self._incident_manager
    
    def _track_incident_state(self, state: dict, updates: dict = None) -> str:
        """
        🎯 HELPER METHOD: Actualizar y trackear estado de incidencia
        
        Args:
            state: Estado actual del nodo
            updates: Actualizaciones opcionales al estado
            
        Returns:
            incident_id: ID de la incidencia
        """
        try:
            # Aplicar updates si se proporcionan
            if updates:
                state = {**state, **updates}
            
            # Convertir a EroskiState si no lo es
            eroski_state = dict(state)
            
            # Trackear con incident manager
            incident_id = self._get_incident_manager().manage_incident(eroski_state)
            
            return incident_id
            
        except Exception as e:
            # No fallar si hay error en tracking
            #print(f"⚠️ Error en incident tracking: {e}")
            return state.get("incident_id", "ERROR-TRACKING")


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

    incidents_manager = EroskiIncidentsManager()
    #kk = incidents_manager.get_ejemplos_frecuentes("balanza")
    #print(f"👹 Incidente: {kk}")
    #kk = incidents_manager.buscar_solucion_json("balanza", "La Balanza no se enciende")
    #print(f"👹 Incidente: {kk}")
    #kk = incidents_manager.get_problemas_soluciones("balanza")
    #print(f"👹 Incidente: {kk}")
    exit()
    
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
            incident_user_name="Test User"
        )
        
        # Ejecutar nodo
        try:
            incidents_manager = EroskiIncidentsManager()
            
            test_state.incident = kk
            result = await buscar_solucion_node(test_state)
            #print("✅ Test completado:")
            #print(f"Comando: {type(result)}")
            #print(f"Actualizaciones: {list(result.update.keys())}")
            if "messages" in result.update:
                last_msg = result.update["messages"][-1] if result.update["messages"] else None
                #if last_msg:
                    #print(f"Último mensaje: {last_msg.content[:100]}...")
                    
            # Test adicional del FAQ_ProblemIdentificationTool
            #print("\n🔧 Test del FAQ_ProblemIdentificationTool:")
            problem_tool = FAQ_ProblemIdentificationTool(incidents_manager)
            
            test_result = problem_tool.faq_problem(
                "La balanza no imprime etiquetas", 
                "balanza"
            )
            #print(f"Resultado: {test_result}")
            #print(f"Confidence: {test_result.get('confidence', 0)}")
            #print(f"Keywords: {test_result.get('keywords', [])}")
            
        except Exception as e:
            #print(f"❌ Error en test: {e}")
            import traceback
            traceback.print_exc()
    
    asyncio.run(test_node())




