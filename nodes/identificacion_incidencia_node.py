# =====================================================
# nodes/identificacion_node.py - Nodo de Identificación de Incidencias
# =====================================================
"""
Nodo conversacional para identificar el tipo de incidencia técnica usando LangGraph.

RESPONSABILIDADES:
- Mostrar ejemplos representativos de tipos comunes al inicio
- Usar recuperación semántica desde BD PostgreSQL con embeddings precomputados
- Implementar agente React con Tool de identificación
- Confirmar tipo de incidencia con el usuario
- Actualizar estado EroskiState con el tipo identificado

CARACTERÍSTICAS:
- Usa get_vectorizer() del proyecto para consistencia
- LangChain BaseRetriever para búsqueda vectorial
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

import psycopg2
import psycopg2.extras

# LangChain imports
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain.agents import create_react_agent, AgentExecutor
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from pydantic import BaseModel, Field
from pydantic import PrivateAttr
from langchain_core.output_parsers import JsonOutputParser
from nodes.tools.confirmation_tool import add_confirmation_tool_to_node

# LangGraph imports
from langgraph.types import Command

# Project imports
from models.eroski_state import EroskiState
from nodes.base_node import BaseNode
from utils.llm.providers import get_llm, get_vectorizer
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
# RETRIEVER PERSONALIZADO PARA TIPOS DE INCIDENCIA CON BD
# =============================================================================

class EroskiIncidentRetriever(BaseRetriever):
    """
    Retriever personalizado para tipos de incidencia usando LangChain BaseRetriever.
    
    Usa get_vectorizer() del proyecto y base de datos PostgreSQL para búsqueda semántica.
    """
    _incidents_data: Dict[str, Any] = PrivateAttr()
    _vectorizer = PrivateAttr()
    _db_config = PrivateAttr()
    
    def __init__(self, incidents_data: Dict[str, Any], **kwargs):
        super().__init__(**kwargs)
        print("👹👹entra en EroskiIncidentRetriever ")
        self._incidents_data = incidents_data
        self._vectorizer = None
        self._db_config = None
        self._setup_retriever()
    
    def _setup_retriever(self):
        """Configurar vectorizer y conexión a BD"""
        try:
            # Usar get_vectorizer del proyecto (mismo que se usó para generar embeddings)
            self._vectorizer = get_vectorizer()
            
            # Configurar parámetros de BD
            settings = get_settings()

            self._db_config = {
                'host': settings.database.host,
                'port': settings.database.port,
                'database': settings.database.name,  # 'dbname' para psycopg2
                'user': settings.database.user,
                'password': settings.database.password
            }
            
            logging.info("✅ EroskiIncidentRetriever configurado con get_vectorizer()")
            
        except Exception as e:
            logging.error(f"❌ Error configurando EroskiIncidentRetriever: {e}")
            self._vectorizer = None
            self._db_config = None
    
    def _get_relevant_documents(
        self, 
        query: str, 
        *, 
        run_manager: CallbackManagerForRetrieverRun
    ) -> List[Document]:
        """
        Implementación requerida por BaseRetriever.
        Busca documentos relevantes usando embeddings de BD.
        """
        try:
            # Generar embedding usando el mismo vectorizer que se usó para BD
            if not self._vectorizer or not self._db_config:
                return self._fallback_documents(query)
            
            # Usar get_vectorizer() para generar embedding de la query
            query_embedding = self._vectorizer.embed(query)
            
            # Buscar similares en BD (versión síncrona para compatibility con BaseRetriever)
            similar_results = self._search_similar_sync(query_embedding, query, k=5)
            
            # Convertir resultados a Documents de LangChain
            documents = []
            for result in similar_results:
                # Enriquecer con información del JSON local
                incident_type = result['tipo_incidencia']
                similarity = result['similarity']
                
                # Crear contenido del documento
                if incident_type in self._incidents_data:
                    incident_data = self._incidents_data[incident_type]
                    
                    # Agregar problemas específicos si existen
                    problems_text = ""
                    if 'problemas' in incident_data:
                        problems_list = [f"- {prob}: {sol}" for prob, sol in incident_data['problemas'].items()]
                        problems_text = f"\n\nProblemas específicos:\n" + "\n".join(problems_list[:3])  # Máximo 3
                    
                    content = f"""Tipo: {incident_type}
Descripción: {incident_data.get('description', result.get('descripcion', ''))}
Keywords: {', '.join(incident_data.get('keywords', []))}
Urgencia: {incident_data.get('urgency_level', 'N/A')}
Tiempo estimado: {incident_data.get('estimated_resolution_minutes', 'N/A')} min{problems_text}"""
                
                else:
                    content = f"""Tipo: {incident_type}
Descripción: {result.get('descripcion', 'Sin descripción')}"""
                
                # Crear Document de LangChain
                doc = Document(
                    page_content=content,
                    metadata={
                        'incident_type': incident_type,
                        'similarity': similarity,
                        'source': 'database_embeddings',
                        'description': result.get('descripcion', ''),
                        'keywords': incident_data.get('keywords', []) if incident_type in self._incidents_data else []
                    }
                )
                
                documents.append(doc)
            
            logging.info(f"✅ Retriever: Encontrados {len(documents)} documentos relevantes")
            return documents
            
        except Exception as e:
            logging.error(f"❌ Error en _get_relevant_documents: {e}")
            return self._fallback_documents(query)
    
    def _search_similar_sync(self, query_embedding: List[float], query_text: str, k: int = 5) -> List[Dict[str, Any]]:
        """Búsqueda síncrona para compatibilidad con BaseRetriever"""
        import asyncio
        
        try:
            # Ejecutar versión async en bucle síncrono
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        except Exception as e:
            logging.error(f"❌ Error en búsqueda síncrona: {e}")
            return []
    
    
    def _search_similar_sync(self, query_embedding: List[float], query_text: str, k: int = 5) -> List[Dict[str, Any]]:
        """Búsqueda síncrona usando psycopg2"""
        try:
            # Conectar con psycopg2 (SIN LOOPS)
            conn = psycopg2.connect(**self._db_config)
            conn.autocommit = True
            
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    if self._check_pgvector_available_sync(cur):
                        return self._search_with_pgvector_sync(cur, query_embedding, k)
                    return self._search_with_python_similarity_sync(cur, query_embedding, k)
            finally:
                conn.close()
                
        except Exception as e:
            logging.error(f"❌ Error en búsqueda síncrona: {e}")
            return self._search_by_text_fallback_sync(query_text, k)
            
        return []



    def _check_pgvector_available_sync(self, cursor) -> bool:
        """Verificar pgvector síncrono"""
        try:
            cursor.execute("SELECT '[1,2,3]'::vector(3)")
            return True
        except:
            return False



    def _search_with_pgvector_sync(self, cursor, query_embedding: List[float], k: int) -> List[Dict[str, Any]]:
        """Búsqueda con pgvector síncrono"""
        try:
            embedding_str = f"[{','.join(map(str, query_embedding))}]"
            
            query = """
            SELECT 
                tv.tipo_incidencia,
                ti.descripcion,
                1 - (tv.embedding <=> %s::vector) as similarity
            FROM tipo_incidencia_vectorizado tv
            JOIN tipo_incidencia ti ON tv.tipo_incidencia = ti.tipo_incidencia
            ORDER BY tv.embedding <=> %s::vector
            LIMIT %s
            """
            
            cursor.execute(query, (embedding_str, embedding_str, k))
            rows = cursor.fetchall()
            
            return [{
                'tipo_incidencia': row['tipo_incidencia'],
                'descripcion': row['descripcion'],
                'similarity': float(row['similarity'])
            } for row in rows]
            
        except Exception as e:
            logging.error(f"❌ Error con pgvector síncrono: {e}")
            return []


    def _search_with_python_similarity_sync(self, cursor, query_embedding: List[float], k: int) -> List[Dict[str, Any]]:
        """Similitud calculada en Python síncrono"""
        try:
            query = """
            SELECT tv.tipo_incidencia, tv.embedding, ti.descripcion
            FROM tipo_incidencia_vectorizado tv
            JOIN tipo_incidencia ti ON tv.tipo_incidencia = ti.tipo_incidencia
            """
            
            cursor.execute(query)
            rows = cursor.fetchall()
            
            similarities = []
            for row in rows:
                db_embedding = self._parse_embedding_from_db(row['embedding'])
                
                if db_embedding:
                    similarity = self._cosine_similarity(query_embedding, db_embedding)
                    similarities.append({
                        'tipo_incidencia': row['tipo_incidencia'],
                        'descripcion': row['descripcion'],
                        'similarity': similarity
                    })
            
            similarities.sort(key=lambda x: x['similarity'], reverse=True)
            return similarities[:k]
            
        except Exception as e:
            logging.error(f"❌ Error en cálculo Python síncrono: {e}")
            return []


    def _search_by_text_fallback_sync(self, query_text: str, k: int) -> List[Dict[str, Any]]:
        """Fallback por texto síncrono"""
        try:
            conn = psycopg2.connect(**self._db_config)
            conn.autocommit = True
            
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    query = """
                    SELECT 
                        tv.tipo_incidencia,
                        ti.descripcion,
                        CASE 
                            WHEN tv.tipo_incidencia ILIKE %s THEN 0.9
                            WHEN ti.descripcion ILIKE %s THEN 0.7
                            ELSE 0.3
                        END AS similarity
                    FROM tipo_incidencia_vectorizado tv
                    JOIN tipo_incidencia ti ON tv.tipo_incidencia = ti.tipo_incidencia
                    WHERE tv.tipo_incidencia ILIKE %s OR ti.descripcion ILIKE %s
                    ORDER BY similarity DESC
                    LIMIT %s
                    """
                    
                    search_pattern = f"%{query_text.lower()}%"
                    cur.execute(query, (search_pattern, search_pattern, search_pattern, search_pattern, k))
                    rows = cur.fetchall()
                    
                    return [{
                        'tipo_incidencia': row['tipo_incidencia'],
                        'descripcion': row['descripcion'],
                        'similarity': float(row['similarity'])
                    } for row in rows]
                    
            finally:
                conn.close()
                
        except Exception as e:
            logging.error(f"❌ Error en fallback texto síncrono: {e}")
            return []
    
    
    async def _search_with_pgvector(self, conn, query_embedding: List[float], k: int) -> List[Dict[str, Any]]:
        """Búsqueda con pgvector"""
        try:
            embedding_str = f"[{','.join(map(str, query_embedding))}]"
            
            query = """
            SELECT 
                tv.tipo_incidencia,
                ti.descripcion,
                1 - (tv.embedding <=> $1::vector) as similarity
            FROM tipo_incidencia_vectorizado tv
            JOIN tipo_incidencia ti ON tv.tipo_incidencia = ti.tipo_incidencia
            ORDER BY tv.embedding <=> $1::vector
            LIMIT $2
            """
            
            rows = await conn.fetch(query, embedding_str, k)
            
            return [{
                'tipo_incidencia': row['tipo_incidencia'],
                'descripcion': row['descripcion'],
                'similarity': float(row['similarity'])
            } for row in rows]
            
        except Exception as e:
            logging.error(f"❌ Error con pgvector: {e}")
            return []
    
    async def _search_with_python_similarity(self, conn, query_embedding: List[float], k: int) -> List[Dict[str, Any]]:
        """Similitud calculada en Python"""
        try:
            query = """
            SELECT tv.tipo_incidencia, tv.embedding, ti.descripcion
            FROM tipo_incidencia_vectorizado tv
            JOIN tipo_incidencia ti ON tv.tipo_incidencia = ti.tipo_incidencia
            """
            
            rows = await conn.fetch(query)
            
            similarities = []
            for row in rows:
                db_embedding = self._parse_embedding_from_db(row['embedding'])
                
                if db_embedding:
                    similarity = self._cosine_similarity(query_embedding, db_embedding)
                    similarities.append({
                        'tipo_incidencia': row['tipo_incidencia'],
                        'descripcion': row['descripcion'],
                        'similarity': similarity
                    })
            
            similarities.sort(key=lambda x: x['similarity'], reverse=True)
            return similarities[:k]
            
        except Exception as e:
            logging.error(f"❌ Error en cálculo Python: {e}")
            return []
    
    async def _search_by_text_fallback(self, query_text: str, k: int) -> List[Dict[str, Any]]:
        """Fallback por texto"""
        import asyncpg
        
        try:
            conn = await asyncpg.connect(**self._db_config)
            
            try:
                query = """
                SELECT 
                    tv.tipo_incidencia,
                    ti.descripcion,
                    CASE 
                        WHEN tv.tipo_incidencia ILIKE $1 THEN 0.9
                        WHEN ti.descripcion ILIKE $1 THEN 0.7
                        ELSE 0.3
                    END AS similarity
                FROM tipo_incidencia_vectorizado tv
                JOIN tipo_incidencia ti ON tv.tipo_incidencia = ti.tipo_incidencia
                WHERE tv.tipo_incidencia ILIKE $1 OR ti.descripcion ILIKE $1
                ORDER BY similarity DESC
                LIMIT $2
                """
                
                search_pattern = f"%{query_text.lower()}%"
                rows = await conn.fetch(query, search_pattern, k)
                
                return [{
                    'tipo_incidencia': row['tipo_incidencia'],
                    'descripcion': row['descripcion'],
                    'similarity': float(row['similarity'])
                } for row in rows]
                
            finally:
                await conn.close()
                
        except Exception as e:
            logging.error(f"❌ Error en fallback texto: {e}")
            return []
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Similitud coseno"""
        try:
            import numpy as np
            vec1, vec2 = np.array(vec1), np.array(vec2)
            return np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))
        except ImportError:
            dot_product = sum(a * b for a, b in zip(vec1, vec2))
            magnitude1 = sum(a * a for a in vec1) ** 0.5
            magnitude2 = sum(b * b for b in vec2) ** 0.5
            return dot_product / (magnitude1 * magnitude2) if magnitude1 and magnitude2 else 0
    
    def _parse_embedding_from_db(self, embedding_data) -> Optional[List[float]]:
        """Parsear embedding desde BD"""
        try:
            if isinstance(embedding_data, str):
                import json
                return json.loads(embedding_data)
            elif isinstance(embedding_data, list):
                return [float(x) for x in embedding_data]
            elif hasattr(embedding_data, 'tolist'):
                return embedding_data.tolist()
            else:
                return None
        except Exception as e:
            logging.error(f"❌ Error parseando embedding: {e}")
            return None
    
    def _fallback_documents(self, query: str) -> List[Document]:
        """Documentos de fallback usando keywords del JSON"""
        try:
            query_lower = query.lower()
            fallback_docs = []
            
            for incident_type, data in self._incidents_data.items():
                keywords = data.get('keywords', [])
                if any(kw.lower() in query_lower for kw in keywords):
                    content = f"""Tipo: {incident_type}
Descripción: {data.get('description', 'Sin descripción')}
Keywords: {', '.join(keywords)}"""
                    
                    doc = Document(
                        page_content=content,
                        metadata={
                            'incident_type': incident_type,
                            'similarity': 0.5,  # Similarity moderada para fallback
                            'source': 'fallback_keywords',
                            'keywords': keywords
                        }
                    )
                    fallback_docs.append(doc)
            
            return fallback_docs[:3]  # Máximo 3 documentos de fallback
            
        except Exception as e:
            logging.error(f"❌ Error en fallback documents: {e}")
            return []

# =============================================================================
# TOOL DE IDENTIFICACIÓN DE INCIDENCIAS
# =============================================================================

class IdentifyIncidentTool:
    """Tool para identificar tipo de incidencia usando LLM y LangChain Retriever"""
    
    def __init__(self, incidents_data: Dict[str, Any], llm, retriever: EroskiIncidentRetriever):
        self._incidents_data = incidents_data
        self.llm = llm
        self.retriever = retriever  # Usa BaseRetriever de LangChain
        self.parser = PydanticOutputParser(pydantic_object=IncidentIdentification)
        
        # Crear prompt para identificación usando Documents del Retriever
        self.identification_prompt = ChatPromptTemplate.from_messages([
            ("system", """Eres un especialista en identificación de incidencias técnicas para Eroski.

Tu misión es analizar el mensaje del usuario y identificar el tipo de incidencia técnica.

DOCUMENTOS RELEVANTES ENCONTRADOS (desde Retriever con BD):
{relevant_documents}

REGLAS DE IDENTIFICACIÓN:
1. Analiza las palabras clave en el mensaje del usuario
2. Considera los documentos relevantes obtenidos del Retriever (embeddings precomputados en BD)
3. Los documentos incluyen similitud, keywords y problemas específicos
4. Asigna un nivel de confianza basado en la claridad del mensaje y similitud de documentos
5. Si la similitud de documentos es > 0.7 Y el mensaje es claro, asigna confianza >= 0.75
6. Si la confianza es < 0.75, indica que necesitas más información

FORMATO DE RESPUESTA:
{format_instructions}

Analiza el mensaje del usuario cuidadosamente usando los documentos del Retriever."""),
            ("human", "Mensaje del usuario: {user_message}")
        ])
    
    async def identify_incident_type_async(self, user_message: str) -> Dict[str, Any]:
        """
        Versión async que usa LangChain Retriever para buscar documentos relevantes.
        """
        try:
            # Separar mensaje actual de contexto histórico si existe
            if " | HISTORIAL: " in user_message:
                current_message, historical_context = user_message.split(" | HISTORIAL: ", 1)
                combined_text = f"{current_message} {historical_context}"
                analysis_context = f"Mensaje actual: {current_message}\nContexto histórico: {historical_context}"
            else:
                current_message = user_message
                combined_text = user_message
                analysis_context = f"Mensaje a analizar: {user_message}"
            
            # Usar LangChain Retriever para obtener documentos relevantes
            relevant_documents = self.retriever.get_relevant_documents(combined_text)
            
            # Formatear documentos para el prompt
            docs_text = self._format_retriever_documents(relevant_documents)
            
            # Ejecutar prompt de identificación
            formatted_prompt = self.identification_prompt.format(
                user_message=analysis_context,
                relevant_documents=docs_text,
                format_instructions=self.parser.get_format_instructions()
            )
            
            response = await asyncio.to_thread(self.llm.invoke, formatted_prompt)
            
            # Parsear respuesta estructurada
            identification = self.parser.parse(response.content)
            
            # Enriquecer resultado con información del Retriever
            result = {
                "incident_type": identification.incident_type,
                "confidence": identification.confidence,
                "keywords": identification.keywords,
                "reasoning": identification.reasoning,
                "problem_description": identification.problem_description,
                "relevant_documents": [doc.metadata for doc in relevant_documents],  # Metadata de docs
                "analysis_mode": "with_history" if " | HISTORIAL: " in user_message else "single_message",
                "data_source": "langchain_retriever"
            }
            
            # Boost de confianza basado en similitud de documentos del Retriever
            if relevant_documents:
                max_similarity = max(doc.metadata.get('similarity', 0) for doc in relevant_documents)
                if max_similarity > 0.7 and identification.incident_type:
                    # Verificar si el tipo identificado coincide con algún documento relevante
                    matching_docs = [doc for doc in relevant_documents 
                                   if doc.metadata.get('incident_type') == identification.incident_type]
                    if matching_docs:
                        result["confidence"] = min(1.0, result["confidence"] + 0.2)  # Boost mayor con Retriever
                        result["reasoning"] += f" (Reforzado por Retriever - similitud: {max_similarity:.2f})"
            
            return result
            
        except Exception as e:
            logging.error(f"❌ Error en identify_incident_type_async con Retriever: {e}")
            return {
                "incident_type": "unknown",
                "confidence": 0.0,
                "keywords": [],
                "reasoning": f"Error en identificación: {str(e)}",
                "problem_description": None,
                "relevant_documents": [],
                "analysis_mode": "error",
                "data_source": "error"
            }
    
    def _format_retriever_documents(self, documents: List[Document]) -> str:
        """Formatear documentos del Retriever para incluir en el prompt"""
        if not documents:
            return "No se encontraron documentos relevantes."
        
        formatted_lines = []
        for i, doc in enumerate(documents, 1):
            similarity = doc.metadata.get('similarity', 0)
            incident_type = doc.metadata.get('incident_type', 'unknown')
            keywords = ', '.join(doc.metadata.get('keywords', []))
            
            formatted_lines.append(
                f"{i}. TIPO: {incident_type.upper()} | SIMILITUD: {similarity:.3f}\n"
                f"   KEYWORDS: {keywords}\n"
                f"   CONTENIDO: {doc.page_content[:200]}..."  # Primeros 200 chars
            )
        
        return '\n\n'.join(formatted_lines)
    
    @tool
    def identify_incident_type(self, user_message: str) -> Dict[str, Any]:
        """
        Wrapper síncrono para compatibilidad con LangChain Tools.
        Usa LangChain Retriever internamente.
        """
        try:
            # Ejecutar versión async en un bucle de eventos
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(self.identify_incident_type_async(user_message))
                return result
            finally:
                loop.close()
        except Exception as e:
            logging.error(f"❌ Error en wrapper síncrono con Retriever: {e}")
            return {
                "incident_type": "unknown",
                "confidence": 0.0,
                "keywords": [],
                "reasoning": f"Error en wrapper: {str(e)}",
                "problem_description": None,
                "relevant_documents": [],
                "analysis_mode": "error",
                "data_source": "error"
            }

# =============================================================================
# NODO PRINCIPAL DE IDENTIFICACIÓN
# =============================================================================

class IdentificacionNode(BaseNode):
    """
    Nodo principal para identificación de incidencias técnicas.
    
    FUNCIONAMIENTO:
    1. Carga tipos comunes al inicio de la conversación
    2. Usa recuperación semántica desde BD con get_vectorizer()
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
        print("👹Datos cargados👹")
        # Configurar sistema de recuperación semántica con LangChain Retriever
        self.semantic_retriever = EroskiIncidentRetriever(self.incidents_data)
        
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

MENSAJE DEL USUARIO: {{input}}

HISTORIAL DE PENSAMIENTOS:
{agent_scratchpad}"""

            # Crear prompt template
            react_prompt = PromptTemplate(
                template=react_template,
                input_variables=[ "chat_history", "input", "agent_scratchpad"],
                partial_variables={"tools": "\n".join([f"{tool.name}: {tool.description}" for tool in tools]),
                                   "tool_names": ", ".join([tool.name for tool in tools])  # 👈 AÑADIR ESTO
                                   }
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
                    "messages":  [
                        AIMessage(content="Necesitas estar autenticado para reportar incidencias.")
                    ],
                    "current_node": "identificar_incidencia",
                    "awaiting_user_input": True
                })
            
            messages = state.get("messages", [])
            
            # Obtener último mensaje del usuario Y analizar historial completo
            last_message, all_user_messages = self._extract_user_messages(messages)
            # Procesar confirmación pendiente
            if state.get("pending_confirmation"):
                last_message = messages[-1].content if messages and isinstance(messages[-1], HumanMessage) else ""
                return await self._handle_confirmation(state, last_message)



            # Si es la primera vez en este nodo, analizar historial ANTES de mostrar ejemplos
            print(f"👹 identification_starter: {state.get('identification_started')}")
            if not state.get("identification_started"):
                # Análisis histórico completo antes de mostrar ejemplos
                if all_user_messages:
                    self.logger.info(f"📚 Analizando historial: {len(all_user_messages)} mensajes del usuario")
                    historical_analysis = await self._analyze_historical_messages(all_user_messages, state)
                    
                    # Si el análisis histórico encontró una incidencia con alta confianza
                    if historical_analysis.get("incident_found") and historical_analysis.get("confidence", 0) >= 0.75:
                        incident_type = historical_analysis["incident_type"]
                        evidence = historical_analysis.get("evidence", "")
                        
                        response_text = f"""He revisado nuestro historial de conversación y parece que ya mencionaste un problema con **{incident_type}**.

Evidencia encontrada: {evidence}

¿Confirmas que el problema es con {incident_type}?"""
                        
                        return Command(update={
                            "messages": [AIMessage(content=response_text)],
                            "identification_started": True,
                            "pending_confirmation": True,
                            "pending_incident_type": incident_type,
                            "identification_confidence": historical_analysis["confidence"],
                            "identification_source": "historical_analysis",
                            "current_node": "identificar_incidencia",
                            "awaiting_user_input": True
                        })
                
                # Si no hay evidencia clara en historial, mostrar ejemplos comunes
                common_examples = self._get_common_examples()
                
                # Personalizar mensaje según historial
                if all_user_messages:
                    intro_text = "Cuéntame más sobre la incidencia"
                else:
                    intro_text = "¡Hola! Voy a ayudarte a identificar el tipo de incidencia técnica."
                
                response_text = f"""{intro_text}

{common_examples}

Por favor, describe el problema que estás experimentando o menciona qué equipo está dando problemas."""
                
                return Command(update={
                    "messages": messages + [AIMessage(content=response_text)],
                    "identification_started": True,
                    "current_node": "identificar_incidencia",
                    "awaiting_user_input": True
                })
            

            
            # Procesar mensaje considerando TANTO el último mensaje COMO el historial
            if last_message and self.agent:
                return await self._process_with_agent_and_history(state, last_message, all_user_messages, messages)
            
            # Fallback si no hay agente
            return await self._fallback_identification_with_history(state, last_message, all_user_messages, messages)
            
        except Exception as e:
            self.logger.error(f"❌ Error en execute: {e}")
            return Command(update={
                "messages": [
                    AIMessage(content="Disculpa, ha ocurrido un error. ¿Puedes describir tu problema de nuevo?")
                ],
                "current_node": "identificar_incidencia",
                "error_count": state.get("error_count", 0) + 1,
                "awaiting_user_input": True
            })
    
    def _extract_user_messages(self, messages: List) -> Tuple[Optional[str], List[str]]:
        """Extraer último mensaje y todos los mensajes del usuario del historial"""
        try:
            user_messages = []
            last_message = None
            
            for msg in messages:
                if isinstance(msg, HumanMessage) and msg.content.strip():
                    user_messages.append(msg.content.strip())
                    last_message = msg.content.strip()  # El último se sobrescribe
            
            self.logger.info(f"📝 Extraídos {len(user_messages)} mensajes del usuario")
            return last_message, user_messages
            
        except Exception as e:
            self.logger.error(f"❌ Error extrayendo mensajes: {e}")
            return None, []
    
    async def _analyze_historical_messages(self, user_messages: List[str], state: EroskiState) -> Dict[str, Any]:
        """Analizar todo el historial de mensajes del usuario buscando pistas de incidencias"""
        try:
            # Combinar todos los mensajes del usuario en un texto único
            combined_text = " | ".join(user_messages)
            self.logger.info(f"🔍 Analizando historial combinado: {combined_text[:200]}...")
            
            # Usar LangChain Retriever para buscar en todo el historial
            relevant_documents = self.semantic_retriever.get_relevant_documents(combined_text)
            
            # Crear prompt especializado para análisis histórico
            historical_prompt = ChatPromptTemplate.from_messages([
                ("system", """Eres un especialista en análisis de historiales de conversación para identificar incidencias técnicas.

Tu misión es analizar TODO EL HISTORIAL de mensajes del usuario para detectar si ya mencionó un problema técnico.

CONTEXTO DEL EMPLEADO:
- Nombre: {employee_name}
- Tienda: {store_name}
- Sección: {section}

DOCUMENTOS RELEVANTES DEL RETRIEVER:
{relevant_documents}

REGLAS DE ANÁLISIS:
1. Busca menciones de equipos: balanza, TPV, caja, impresora, ordenador, red, wifi
2. Busca síntomas: "no funciona", "error", "problema", "fallo", "no enciende", "no imprime"
3. Considera el contexto de la sección del empleado
4. Analiza mensajes anteriores que podrían indicar frustración o urgencia
5. Busca números de error, códigos, o descripciones técnicas específicas
6. Usa los documentos del Retriever para mejor identificación

FORMATO DE RESPUESTA (JSON):
{{
    "incident_found": boolean,
    "incident_type": "tipo_identificado_o_null",
    "confidence": float_entre_0_y_1,
    "evidence": "texto_que_llevó_a_la_conclusión",
    "keywords_detected": ["lista", "de", "keywords"],
    "reasoning": "explicación_del_análisis",
    "needs_more_info": boolean
}}

Analiza cuidadosamente todo el historial y determina si hay evidencia de una incidencia técnica."""),
                ("human", "HISTORIAL COMPLETO DE MENSAJES DEL USUARIO:\n{user_messages_text}")
            ])
            
            # Preparar datos para el prompt
            employee_name = state.get("employee_name", "Empleado")
            store_name = state.get("store_name", "Tienda")
            section = state.get("section", "Sección")
            
            docs_text = self.identify_tool._format_retriever_documents(relevant_documents)
            user_messages_text = "\n".join([f"{i+1}. {msg}" for i, msg in enumerate(user_messages)])
            
        
            
            class HistoricalAnalysis(BaseModel):
                incident_found: bool = Field(description="Detecta si encontró el incidente")
                incident_type: Optional[str] = Field(description="Typo de incidente encontrado")
                confidence: Optional[float] = Field(description="float_entre_0_y_1")
                evidence: Optional[str] = Field(description="texto_que_llevó_a_la_conclusión")
                keywords_detected: Optional[List[str]] = Field(description="lista de keywords")
                reasoning: Optional[str] = Field(description="explicación_del_análisis")
                needs_more_info: bool = Field(description="Indica si necesita más información")

            parser = JsonOutputParser(pydantic_object=HistoricalAnalysis)

            llm_chain = historical_prompt | self.llm | parser

            response = response = await asyncio.to_thread(llm_chain.invoke, {
                "employee_name":employee_name,
                "store_name":store_name,
                "section":section,
                "relevant_documents":docs_text,
                "user_messages_text":user_messages_text
            })
            
            # Parsear respuesta JSON
            try:
                import json
                print(f"👹 Análisis histórico completado: {response}")
                result = response
                self.logger.info(f"✅ Análisis histórico completado: {result.get('incident_found', False)}")
                return result
            except json.JSONDecodeError:
                # Fallback si no se puede parsear JSON
                self.logger.warning("⚠️ No se pudo parsear respuesta JSON del análisis histórico")
                return self._fallback_historical_analysis(user_messages, relevant_documents)
                
        except Exception as e:
            self.logger.error(f"❌ Error en análisis histórico: {e}")
            return {"incident_found": False, "confidence": 0.0, "reasoning": f"Error: {str(e)}"}
    
    def _fallback_historical_analysis(self, user_messages: List[str], relevant_documents: List[Document]) -> Dict[str, Any]:
        """Análisis de fallback basado en keywords si falla el LLM"""
        try:
            combined_text = " ".join(user_messages).lower()
            
            # Keywords por tipo de incidencia
            keyword_patterns = {
                "balanza": ["balanza", "peso", "etiqueta", "precio", "gramos", "pesado", "bascula"],
                "tpv": ["tpv", "caja", "terminal", "pago", "tarjeta", "ticket", "registradora"],
                "impresoras": ["impresora", "imprimir", "papel", "cartucho", "atasco"],
                "red": ["internet", "wifi", "red", "conexion", "lento", "desconectado"]
            }
            
            best_match = None
            best_score = 0
            best_keywords = []
            
            for incident_type, keywords in keyword_patterns.items():
                score = sum(1 for kw in keywords if kw in combined_text)
                if score > best_score:
                    best_score = score
                    best_match = incident_type
                    best_keywords = [kw for kw in keywords if kw in combined_text]
            
            # También considerar documentos relevantes del retriever
            if relevant_documents and not best_match:
                top_doc = relevant_documents[0]
                if top_doc.metadata.get("similarity", 0) > 0.3:
                    best_match = top_doc.metadata.get("incident_type")
                    best_score = top_doc.metadata.get("similarity") * 5  # Convertir a escala similar
                    best_keywords = top_doc.metadata.get("keywords", [])
            
            confidence = min(best_score / 3.0, 1.0) if best_score > 0 else 0.0
            
            return {
                "incident_found": confidence > 0.3,
                "incident_type": best_match,
                "confidence": confidence,
                "evidence": f"Keywords detectadas: {', '.join(best_keywords)}" if best_keywords else "Sin evidencia clara",
                "keywords_detected": best_keywords,
                "reasoning": "Análisis de fallback basado en keywords",
                "needs_more_info": confidence < 0.5
            }
            
        except Exception as e:
            self.logger.error(f"❌ Error en fallback histórico: {e}")
            return {"incident_found": False, "confidence": 0.0}

    async def _handle_confirmation(self, state: EroskiState, last_message: str) -> Command:
        """
        Manejar confirmación de tipo de incidencia con soporte para confirmación implícita
        """
        try:
            if not self.confirmation_tool or not last_message:
                # Sin tool de confirmación, asumir "sí" si es positivo
                confirmation = "si" if any(word in last_message.lower() 
                                        for word in ["sí", "si", "correcto", "exacto", "afirmativo"]) else "no"
            else:
                # NUEVO: Usar la versión mejorada con estado para confirmación implícita
                messages = state.get("messages", [])
                confirmation = self.confirmation_tool.check_with_history(last_message, messages)
                
                self.logger.info(f"🔍 Confirmación analizada: '{last_message}' -> '{confirmation}'")

            incident_type = state.get("pending_incident_type")
            
            if confirmation == "si":
                # Confirmado - actualizar estado y avanzar
                response_text = f"¡Perfecto! He confirmado que el problema es con **{incident_type}**. Ahora vamos a recopilar más detalles sobre la incidencia."
                
                return Command(update={
                    "messages": [AIMessage(content=response_text)],
                    "incident_type": incident_type,
                    "incident_type_confirmed": True,
                    "pending_confirmation": False,
                    "pending_incident_type": None,
                    "current_node": "identificar_incidencia",  # Siguiente nodo
                    "awaiting_user_input": True
                })
            
            elif confirmation == "no":
                # No confirmado - continuar buscando
                response_text = "Entendido, no es ese tipo de problema. Por favor, describe con más detalle qué equipo o sistema está fallando."
                
                return Command(update={
                    "messages": [AIMessage(content=response_text)],
                    "pending_confirmation": False,
                    "pending_incident_type": None,
                    "identification_started": True,
                    "current_node": "identificar_incidencia",
                    "awaiting_user_input": True
                })
            
            else:
                # Respuesta ambigua - solicitar clarificación
                response_text = f"No estoy seguro de tu respuesta. ¿Confirmas que el problema es con **{incident_type}**? Por favor responde 'sí' o 'no', o describe más detalles del problema."
                
                return Command(update={
                    "messages": [AIMessage(content=response_text)],
                    "current_node": "identificar_incidencia",
                    "awaiting_user_input": True
                })
                
        except Exception as e:
            self.logger.error(f"❌ Error en confirmación: {e}")
            return Command(update={
                "messages": [AIMessage(content="Error al procesar la confirmación. ¿Puedes intentar de nuevo?")],
                "pending_confirmation": False,
                "current_node": "identificar_incidencia",
                "awaiting_user_input": True
            })   

    
    async def _process_with_agent_and_history(self, state: EroskiState, last_message: str, 
                                            all_user_messages: List[str], messages: List) -> Command:
        """Procesar mensaje usando el agente React CON análisis del historial completo y BD"""
        try:
            # Preparar contexto enriquecido con historial
            chat_history = self._format_chat_history(messages)
            historical_context = self._create_historical_context(all_user_messages)
            
            # Input enriquecido para el agente
            enhanced_input = f"""MENSAJE ACTUAL: {last_message}

CONTEXTO HISTÓRICO:
{historical_context}

INSTRUCCIÓN: Analiza tanto el mensaje actual como todo el contexto histórico para identificar la incidencia. Usa los embeddings precomputados de BD para mayor precisión."""
            
            # Ejecutar agente con contexto enriquecido
            result = await asyncio.to_thread(
                self.agent.invoke,
                {
                    "input": enhanced_input,
                    "chat_history": chat_history
                }
            )
            
            agent_response = result.get("output", "No pude procesar tu mensaje.")
            
            # Como el agente usa la tool sync, ejecutar identificación async adicional para verificar
            combined_input = f"{last_message} | HISTORIAL: {' | '.join(all_user_messages[-3:])}" if all_user_messages else last_message
            tool_output = await self.identify_tool.identify_incident_type_async(combined_input)
            
            if isinstance(tool_output, dict) and tool_output.get("confidence", 0) >= 0.75:
                # Alta confianza - proceder a confirmación
                incident_type = tool_output["incident_type"]
                keywords = ", ".join(tool_output.get("keywords", []))
                reasoning = tool_output.get("reasoning", "")
                data_source = tool_output.get("data_source", "")
                
                confirmation_text = f"""He identificado que tu problema parece ser con **{incident_type}** (basado en: {keywords}).

{reasoning}

*Análisis realizado con embeddings de BD: {data_source}*

¿Es correcto que el problema es con {incident_type}?"""
                
                return Command(update={
                    "messages": messages + [AIMessage(content=confirmation_text)],
                    "pending_confirmation": True,
                    "pending_incident_type": incident_type,
                    "identification_confidence": tool_output["confidence"],
                    "identification_keywords": tool_output.get("keywords", []),
                    "identification_source": "agent_with_history_and_db",
                    "awaiting_user_input": True
                })
            
            # Respuesta normal del agente
            return Command(update={
                "messages": messages + [AIMessage(content=agent_response)],
                "awaiting_user_input": True
            })
            
        except Exception as e:
            self.logger.error(f"❌ Error procesando con agente, historial y BD: {e}")
            return await self._fallback_identification_with_history(state, last_message, all_user_messages, messages)
    
    async def _fallback_identification_with_history(self, state: EroskiState, last_message: str, 
                                                  all_user_messages: List[str], messages: List) -> Command:
        """Identificación de fallback SIN agente React pero CON análisis histórico y BD"""
        try:
            # Combinar mensaje actual con historial para análisis
            if all_user_messages:
                # Dar más peso al mensaje actual pero considerar historial
                combined_input = f"{last_message} | HISTORIAL: {' | '.join(all_user_messages[-3:])}"
            else:
                combined_input = last_message
            
            # Usar la versión async de la tool de identificación con contexto histórico
            tool_result = await self.identify_tool.identify_incident_type_async(combined_input)
            
            if tool_result["confidence"] >= 0.75:
                # Alta confianza - confirmar
                incident_type = tool_result["incident_type"]
                reasoning = tool_result.get("reasoning", "")
                keywords = ", ".join(tool_result.get("keywords", []))
                data_source = tool_result.get("data_source", "unknown")
                
                # Mencionar si se usó información histórica y BD
                historical_note = ""
                if len(all_user_messages) > 1:
                    historical_note = "\n\n*He considerado nuestro historial de conversación previo y los embeddings precomputados en BD.*"
                elif data_source == "langchain_retriever":
                    historical_note = "\n\n*Identificación basada en embeddings precomputados de BD.*"
                
                response_text = f"""He identificado que tu problema parece ser con **{incident_type}** (keywords: {keywords}).

{reasoning}{historical_note}

¿Es correcto que el problema es con {incident_type}?"""
                
                return Command(update={
                    "messages": messages + [AIMessage(content=response_text)],
                    "pending_confirmation": True,
                    "pending_incident_type": incident_type,
                    "identification_confidence": tool_result["confidence"],
                    "identification_source": "fallback_with_history_and_db",
                    "awaiting_user_input": True
                })
            
            else:
                # Baja confianza - usar información histórica para hacer preguntas más específicas
                specific_question = self._generate_specific_question_from_history(all_user_messages, tool_result)
                
                return Command(update={
                    "messages": messages + [AIMessage(content=specific_question)],
                    "awaiting_user_input": True
                })
                
        except Exception as e:
            self.logger.error(f"❌ Error en fallback con historial y BD: {e}")
            return Command(update={
                "messages": messages + [
                    AIMessage(content="Disculpa, no pude procesar tu mensaje. ¿Puedes describir el problema de otra manera?")
                ],
                "error_count": state.get("error_count", 0) + 1,
                "awaiting_user_input": True
            })
    
    def _create_historical_context(self, user_messages: List[str]) -> str:
        """Crear contexto histórico legible para el agente"""
        if not user_messages:
            return "Sin historial previo."
        
        context_lines = []
        for i, msg in enumerate(user_messages, 1):
            context_lines.append(f"{i}. {msg}")
        
        return f"Mensajes anteriores del usuario:\n" + "\n".join(context_lines)
    
    def _generate_specific_question_from_history(self, user_messages: List[str], tool_result: Dict) -> str:
        """Generar pregunta específica basada en el historial y resultado de baja confianza"""
        try:
            # Analizar qué tipo de información falta basándose en el historial
            combined_text = " ".join(user_messages).lower()
            
            # Detectar qué información específica podría estar faltando
            missing_equipment = not any(equip in combined_text for equip in 
                                      ["balanza", "tpv", "caja", "impresora", "ordenador", "terminal"])
            missing_symptoms = not any(symp in combined_text for symp in 
                                     ["no funciona", "error", "problema", "fallo", "no enciende"])
            
            if missing_equipment and missing_symptoms:
                return """He revisado nuestro historial pero necesito información más específica.

¿Puedes contarme:
- ¿Qué equipo específico está fallando? (balanza, caja registradora, impresora, ordenador...)
- ¿Cuál es el síntoma exacto? (no enciende, error en pantalla, no imprime...)"""
            
            elif missing_equipment:
                return """Veo que mencionas un problema, pero necesito saber qué equipo específico está fallando.

¿Es problema con:
- 🔢 **Balanza** (pesado, etiquetas, precios)
- 💰 **TPV/Caja** (pagos, tickets, terminal)  
- 🖨️ **Impresora** (no imprime, atascos, cartuchos)
- 🌐 **Red/Internet** (conexión, WiFi, lentitud)
- 💻 **Ordenador** (sistema, aplicaciones)"""
            
            elif missing_symptoms:
                equipment_mentioned = None
                for equip in ["balanza", "tpv", "caja", "impresora", "ordenador"]:
                    if equip in combined_text:
                        equipment_mentioned = equip
                        break
                
                if equipment_mentioned:
                    return f"""Entiendo que es un problema con {equipment_mentioned}. ¿Puedes ser más específico sobre qué está pasando?

Por ejemplo:
- ¿No enciende?
- ¿Muestra algún error en pantalla?
- ¿No responde?
- ¿Funciona mal?"""
            
            # Pregunta genérica si no se puede determinar qué falta
            return """Basándome en nuestro historial, necesito más detalles específicos sobre el problema técnico.

¿Puedes describir:
1. ¿Qué equipo está fallando exactamente?
2. ¿Cuál es el síntoma específico?
3. ¿Cuándo empezó el problema?"""
            
        except Exception as e:
            self.logger.error(f"❌ Error generando pregunta específica: {e}")
            return "¿Puedes darme más detalles sobre el problema técnico que estás experimentando?"
    
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


async def identificacion_node(state: EroskiState) -> Command:
    """
    Función wrapper para LangGraph - Nodo Identificador Incidencia
    
    Args:
        state: Estado actual como EroskiState
        
    Returns:
        Command con las actualizaciones de estado
    """
    # Crear instancia del nodo
    node = IdentificacionNode()
    # Ejecutar el nodo
    return await node.execute(state)


#def identificacion_node() -> IdentificacionNode:
#    """Factory function para crear el nodo de identificación"""
#    await IdentificacionNode()


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