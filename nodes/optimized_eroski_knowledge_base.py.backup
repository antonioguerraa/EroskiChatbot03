# =====================================================
# nodes/optimized_eroski_knowledge_base.py - RAG Completo Optimizado
# =====================================================
"""
Sistema RAG completo optimizado para Eroski que incluye:
- Embeddings con metadatos enriquecidos
- Búsqueda híbrida (vectorial + texto + keywords)
- Re-ranking inteligente multifactor
- Cache avanzado con TTL
- Pool de conexiones asíncrono
- Expansión automática de consultas técnicas
- Contextualización de resultados
- Enlaces directos a PDFs
- Búsqueda con contexto parcial de equipos
- Sistema de aprendizaje continuo
"""

import asyncio
import asyncpg
import psycopg2
import numpy as np
import logging
import json
import re
import time
import hashlib
from typing import List, Dict, Any, Optional, Tuple, Union
from dataclasses import dataclass, asdict
from psycopg2.extras import RealDictCursor
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from urllib.parse import quote

from config.settings import get_settings
from utils.llm.providers import get_vectorizer, get_llm

logger = logging.getLogger(__name__)

# =====================================================
# ESTRUCTURAS DE DATOS
# =====================================================

@dataclass
class RAGResult:
    """Resultado estructurado de búsqueda RAG"""
    chunk_text: str
    documento_origen: str
    pagina_numero: int
    similarity: float
    palabras_clave: List[str]
    seccion: str = ""
    contexto_adicional: str = ""
    confidence: float = 0.0
    chunk_id: Optional[str] = None
    metadata: Dict[str, Any] = None
    search_method: str = "hybrid"
    
    # Metadatos del equipo
    tipo_equipo: str = ""
    marca: str = ""
    modelo: str = ""
    version_manual: str = ""
    
    # Posición y enlaces
    posicion_en_pagina: Dict[str, float] = None
    pdf_link: str = ""
    web_viewer_link: str = ""
    entidades_tecnicas: List[str] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.posicion_en_pagina is None:
            self.posicion_en_pagina = {"x": 0, "y": 0, "width": 0, "height": 0}
        if self.entidades_tecnicas is None:
            self.entidades_tecnicas = []

@dataclass
class SearchMetrics:
    """Métricas de búsqueda para optimización"""
    query: str
    execution_time: float
    results_count: int
    cache_hit: bool
    search_methods_used: List[str]
    timestamp: datetime
    user_satisfied: Optional[bool] = None
    equipment_context: Optional[Dict[str, str]] = None

@dataclass
class MultiEquipmentSearchResult:
    """Resultado de búsqueda que incluye múltiples equipos"""
    query: str
    results_by_equipment: Dict[str, List[RAGResult]]
    total_results: int
    equipment_coverage: Dict[str, int]
    best_match_equipment: str
    confidence_by_equipment: Dict[str, float]

# =====================================================
# SISTEMA DE CACHE INTELIGENTE
# =====================================================

class QueryCache:
    """Cache inteligente para consultas RAG con TTL y LRU"""
    
    def __init__(self, max_size: int = 200, ttl_minutes: int = 60):
        self.max_size = max_size
        self.ttl = timedelta(minutes=ttl_minutes)
        self._cache: Dict[str, Tuple[str, datetime]] = {}
        self._access_count: Dict[str, int] = {}
    
    def _make_key(self, query: str, params: Dict[str, Any]) -> str:
        """Genera clave única para la consulta"""
        params_str = json.dumps(params, sort_keys=True)
        return hashlib.md5(f"{query}:{params_str}".encode()).hexdigest()
    
    def get(self, query: str, **params) -> Optional[str]:
        """Obtiene resultado del cache si existe y es válido"""
        key = self._make_key(query, params)
        
        if key in self._cache:
            result, timestamp = self._cache[key]
            
            if datetime.now() - timestamp < self.ttl:
                self._access_count[key] = self._access_count.get(key, 0) + 1
                return result
            else:
                del self._cache[key]
                if key in self._access_count:
                    del self._access_count[key]
        
        return None
    
    def set(self, query: str, result: str, **params):
        """Guarda resultado en cache"""
        key = self._make_key(query, params)
        
        if len(self._cache) >= self.max_size:
            self._evict_least_used()
        
        self._cache[key] = (result, datetime.now())
        self._access_count[key] = 1
    
    def _evict_least_used(self):
        """Elimina elementos menos usados"""
        sorted_keys = sorted(self._access_count.items(), key=lambda x: x[1])
        evict_count = max(1, len(sorted_keys) // 5)
        
        for key, _ in sorted_keys[:evict_count]:
            if key in self._cache:
                del self._cache[key]
            del self._access_count[key]

# =====================================================
# EXPANSOR DE CONSULTAS TÉCNICAS
# =====================================================

class TechnicalQueryExpander:
    """Expansor de consultas técnicas específico para Eroski"""
    
    def __init__(self):
        # Diccionario técnico base - será reemplazado por versión dinámica
        self.technical_terms = {
            # Equipos principales
            'balanza': ['balanza', 'peso', 'pesar', 'pesaje', 'dibal', 'mistral', 'bascula'],
            'tpv': ['tpv', 'caja', 'registradora', 'terminal', 'punto_venta'],
            'impresora': ['impresora', 'imprimir', 'impresion', 'ticket', 'factura'],
            'escaner': ['escaner', 'lector', 'codigo_barras', 'scanner'],
            
            # Componentes
            'retroiluminacion': ['retroiluminacion', 'backlight', 'brillo', 'iluminacion', 'luz_pantalla'],
            'etiqueta': ['etiqueta', 'ticket', 'papel', 'rollo', 'bobina'],
            'teclado': ['teclado', 'teclas', 'botones', 'input'],
            'pantalla': ['pantalla', 'display', 'monitor', 'visor', 'led'],
            
            # Problemas comunes
            'no_funciona': ['error', 'fallo', 'problema', 'averia', 'dañado', 'roto'],
            'no_imprime': ['no_imprime', 'no_sale', 'sin_papel', 'atasco', 'bloqueado'],
            'configuracion': ['configuracion', 'config', 'setup', 'ajustes', 'parametros'],
            
            # Acciones
            'calibrar': ['calibrar', 'ajustar', 'configurar', 'parametros'],
            'reiniciar': ['reiniciar', 'resetear', 'apagar', 'encender'],
            'limpiar': ['limpiar', 'mantenimiento', 'limpieza', 'suciedad'],
        }
        
        self.learned_patterns = {}
        self.dictionary_cache = {}
        self.cache_expiry = None
        self.cache_duration = timedelta(hours=6)
    
    async def expand_query(self, query: str) -> List[str]:
        """Expande consulta con sinónimos técnicos"""
        await self._update_cache_if_needed()
        
        clean_query = re.sub(r'[^\w\s]', ' ', query.lower())
        clean_query = ' '.join(clean_query.split())
        
        queries = [query, clean_query]
        
        # Expandir usando diccionario técnico
        expanded_terms = set()
        
        for word in clean_query.split():
            if word in self.technical_terms:
                expanded_terms.update(self.technical_terms[word])
            elif word in self.dictionary_cache:
                term_data = self.dictionary_cache[word]
                expanded_terms.update(term_data.get('synonyms', []))
                expanded_terms.update(term_data.get('related_terms', [])[:3])
        
        if expanded_terms:
            expanded_query = f"{clean_query} {' '.join(expanded_terms)}"
            queries.append(expanded_query)
        
        # Agregar patrones contextuales
        context_queries = self._generate_context_queries(clean_query)
        queries.extend(context_queries)
        
        return list(dict.fromkeys(queries))[:5]
    
    async def _update_cache_if_needed(self):
        """Actualiza cache del diccionario técnico si existe"""
        current_time = datetime.now()
        
        if (not self.dictionary_cache or 
            not self.cache_expiry or 
            current_time > self.cache_expiry):
            
            try:
                await self._load_dictionary_from_database()
                self.cache_expiry = current_time + self.cache_duration
            except Exception as e:
                logger.warning(f"No se pudo cargar diccionario dinámico: {e}")
    
    async def _load_dictionary_from_database(self):
        """Carga diccionario técnico desde base de datos si existe"""
        try:
            settings = get_settings()
            conn_string = f"postgresql://{settings.database.user}:{settings.database.password or ''}@{settings.database.host}:{settings.database.port}/{settings.database.name}"
            conn = await asyncpg.connect(conn_string)
            
            try:
                terms = await conn.fetch("""
                    SELECT term, synonyms, related_terms, confidence
                    FROM technical_dictionary
                    WHERE confidence >= 0.4
                    ORDER BY confidence DESC
                """)
                
                self.dictionary_cache = {}
                
                for term_row in terms:
                    term_data = {
                        'synonyms': json.loads(term_row['synonyms']) if term_row['synonyms'] else [],
                        'related_terms': json.loads(term_row['related_terms']) if term_row['related_terms'] else [],
                        'confidence': term_row['confidence']
                    }
                    
                    self.dictionary_cache[term_row['term']] = term_data
                    
                    for synonym in term_data['synonyms']:
                        self.dictionary_cache[synonym.lower()] = term_data
                
                logger.info(f"Diccionario técnico dinámico cargado: {len(terms)} términos")
                
            finally:
                await conn.close()
                
        except Exception as e:
            logger.debug(f"Diccionario dinámico no disponible: {e}")
    
    def _generate_context_queries(self, query: str) -> List[str]:
        """Genera consultas de contexto específicas"""
        context_queries = []
        
        if any(word in query for word in ['como', 'cómo']):
            context_queries.append(f"procedimiento {query.replace('como', '').replace('cómo', '').strip()}")
        
        if any(word in query for word in ['problema', 'error', 'no funciona']):
            context_queries.append(f"solucion {query}")
            context_queries.append(f"diagnostico {query}")
        
        if any(word in query for word in ['configurar', 'ajustar', 'setup']):
            context_queries.append(f"menu configuracion {query}")
        
        return context_queries

# =====================================================
# GENERADOR DE ENLACES A DOCUMENTOS
# =====================================================

class DocumentLinkGenerator:
    """Genera enlaces directos a ubicaciones específicas en PDFs"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
    
    def generate_pdf_link(self, filename: str, page_number: int, position: Optional[Dict[str, float]] = None) -> str:
        """Genera enlace directo a una página específica del PDF"""
        pdf_url = f"{self.base_url}/documents/{quote(filename)}"
        params = [f"page={page_number}"]
        
        if position:
            x = int(position.get("x", 0))
            y = int(position.get("y", 0))
            params.append(f"zoom=100,{x},{y}")
        
        return f"{pdf_url}#{'&'.join(params)}"
    
    def generate_web_viewer_link(self, filename: str, chunk_id: str, page_number: int, position: Optional[Dict[str, float]] = None) -> str:
        """Genera enlace al visor web con resaltado del chunk específico"""
        base_viewer_url = f"{self.base_url}/viewer"
        
        params = [
            f"doc={quote(filename)}",
            f"page={page_number}",
            f"chunk={chunk_id}"
        ]
        
        if position:
            params.append(f"highlight={position['x']},{position['y']},{position['width']},{position['height']}")
        
        return f"{base_viewer_url}?{'&'.join(params)}"

# =====================================================
# MOTOR DE BÚSQUEDA HÍBRIDO
# =====================================================

class HybridRAGSearcher:
    """Motor de búsqueda RAG híbrido optimizado"""
    
    def __init__(self, settings, vectorizer):
        self.settings = settings
        self.vectorizer = vectorizer
        self.query_expander = TechnicalQueryExpander()
        self.cache = QueryCache(max_size=200, ttl_minutes=60)
        self.link_generator = DocumentLinkGenerator()
        self.metrics: List[SearchMetrics] = []
        
        # Configuración de búsqueda
        self.min_similarity_threshold = 0.55
        self.vector_weight = 0.6
        self.text_weight = 0.4
        self.max_results_per_method = 8
        
        # Pool de conexiones
        self._connection_pool = None
    
    async def _get_connection_pool(self):
        """Obtiene pool de conexiones asíncrono"""
        if self._connection_pool is None:
            try:
                conn_string = f"postgresql://{self.settings.database.user}:{self.settings.database.password or ''}@{self.settings.database.host}:{self.settings.database.port}/{self.settings.database.name}"
                self._connection_pool = await asyncpg.create_pool(
                    conn_string,
                    min_size=3,
                    max_size=15,
                    command_timeout=45
                )
                logger.info("✅ Pool de conexiones RAG creado")
            except Exception as e:
                logger.error(f"❌ Error creando pool: {e}")
                raise
        return self._connection_pool
    
    async def search(
        self, 
        query: str, 
        top_k: int = 5,
        include_context: bool = True,
        filter_by_document: Optional[str] = None,
        search_methods: List[str] = ["vector", "text"],
        equipment_context: Optional[Dict[str, str]] = None
    ) -> Tuple[List[RAGResult], SearchMetrics]:
        """Búsqueda híbrida principal"""
        
        start_time = time.time()
        
        # Parámetros para cache
        cache_params = {
            'top_k': top_k,
            'include_context': include_context,
            'filter_by_document': filter_by_document,
            'search_methods': sorted(search_methods),
            'equipment_context': equipment_context
        }
        
        # Verificar cache
        cached_result = self.cache.get(query, **cache_params)
        if cached_result:
            execution_time = time.time() - start_time
            metrics = SearchMetrics(
                query=query,
                execution_time=execution_time,
                results_count=len(json.loads(cached_result)),
                cache_hit=True,
                search_methods_used=["cache"],
                timestamp=datetime.now(),
                equipment_context=equipment_context
            )
            return json.loads(cached_result), metrics
        
        try:
            pool = await self._get_connection_pool()
            
            async with pool.acquire() as conn:
                # Verificar si usar tabla mejorada
                use_enhanced_table = await self._check_enhanced_table_exists(conn)
                
                if use_enhanced_table:
                    results = await self._search_enhanced_table(
                        conn, query, top_k, equipment_context, search_methods
                    )
                else:
                    results = await self._search_legacy_table(
                        conn, query, top_k, filter_by_document, search_methods
                    )
                
                # Agregar contexto si se solicita
                if include_context and results:
                    results = await self._enrich_with_context(conn, results[:top_k])
                
                # Métricas
                execution_time = time.time() - start_time
                metrics = SearchMetrics(
                    query=query,
                    execution_time=execution_time,
                    results_count=len(results),
                    cache_hit=False,
                    search_methods_used=search_methods,
                    timestamp=datetime.now(),
                    equipment_context=equipment_context
                )
                
                # Guardar en cache
                serializable_results = [asdict(r) for r in results]
                self.cache.set(query, json.dumps(serializable_results), **cache_params)
                
                self.metrics.append(metrics)
                return results[:top_k], metrics
                
        except Exception as e:
            logger.error(f"❌ Error en búsqueda híbrida: {e}")
            return [], SearchMetrics(
                query=query,
                execution_time=time.time() - start_time,
                results_count=0,
                cache_hit=False,
                search_methods_used=["error"],
                timestamp=datetime.now()
            )
    
    async def _check_enhanced_table_exists(self, conn) -> bool:
        """Verifica si existe la tabla mejorada"""
        try:
            result = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'knowledge_base_enhanced'
                )
            """)
            return result
        except:
            return False
    
    async def _search_enhanced_table(
        self, 
        conn, 
        query: str, 
        top_k: int,
        equipment_context: Optional[Dict[str, str]],
        search_methods: List[str]
    ) -> List[RAGResult]:
        """Búsqueda en tabla mejorada con metadatos"""
        
        # Expandir consulta
        expanded_queries = await self.query_expander.expand_query(query)
        
        all_results = []
        
        # Búsqueda vectorial con metadatos
        if "vector" in search_methods:
            vector_results = await self._vector_search_enhanced(
                conn, expanded_queries, equipment_context, self.max_results_per_method
            )
            all_results.extend(vector_results)
        
        # Búsqueda de texto completo
        if "text" in search_methods:
            text_results = await self._text_search_enhanced(
                conn, expanded_queries, equipment_context, self.max_results_per_method
            )
            all_results.extend(text_results)
        
        # Búsqueda por palabras clave
        if "keyword" in search_methods:
            keyword_results = await self._keyword_search_enhanced(
                conn, query, equipment_context, self.max_results_per_method
            )
            all_results.extend(keyword_results)
        
        # Deduplicar y re-rankear
        unique_results = self._deduplicate_results(all_results)
        ranked_results = self._advanced_rerank(unique_results, query, expanded_queries)
        
        return ranked_results
    
    async def _vector_search_enhanced(
        self, 
        conn, 
        queries: List[str], 
        equipment_context: Optional[Dict[str, str]],
        limit: int
    ) -> List[RAGResult]:
        """Búsqueda vectorial en tabla mejorada"""
        
        all_results = []
        
        for query in queries[:3]:
            try:
                # Crear consulta enriquecida si hay contexto de equipo
                if equipment_context:
                    enriched_query = self._create_enriched_query(query, equipment_context)
                    query_embedding = self.vectorizer.embed(enriched_query)
                    embedding_column = "chunk_embedding_with_metadata"
                else:
                    query_embedding = self.vectorizer.embed(query)
                    embedding_column = "chunk_embedding"
                
                # SQL para búsqueda vectorial
                base_sql = f"""
                    SELECT 
                        chunk_id, chunk_text, documento_origen,
                        tipo_equipo, marca, modelo, version_manual,
                        pagina_numero, seccion_titulo, tipo_contenido,
                        posicion_x, posicion_y, posicion_width, posicion_height,
                        palabras_clave, entidades_tecnicas, confidence_extraccion,
                        pdf_link, web_viewer_link,
                        1 - ({embedding_column} <=> $1::vector) as similarity
                    FROM knowledge_base_enhanced
                    WHERE {embedding_column} IS NOT NULL
                """
                
                params = [str(query_embedding)]
                param_count = 1
                
                # Filtros por contexto de equipo
                if equipment_context:
                    if equipment_context.get("tipo"):
                        param_count += 1
                        base_sql += f" AND LOWER(tipo_equipo) = LOWER(${param_count})"
                        params.append(equipment_context["tipo"])
                    
                    if equipment_context.get("marca"):
                        param_count += 1
                        base_sql += f" AND LOWER(marca) = LOWER(${param_count})"
                        params.append(equipment_context["marca"])
                    
                    if equipment_context.get("modelo"):
                        param_count += 1
                        base_sql += f" AND LOWER(modelo) LIKE LOWER(${param_count})"
                        params.append(f"%{equipment_context['modelo']}%")
                
                # Filtros de calidad
                param_count += 1
                base_sql += f" AND 1 - ({embedding_column} <=> $1::vector) > ${param_count}"
                params.append(self.min_similarity_threshold)
                
                param_count += 1
                base_sql += f" ORDER BY {embedding_column} <=> $1::vector LIMIT ${param_count}"
                params.append(limit)
                
                results = await conn.fetch(base_sql, *params)
                
                for result in results:
                    rag_result = self._create_rag_result_from_enhanced(result)
                    all_results.append(rag_result)
                    
            except Exception as e:
                logger.error(f"Error en búsqueda vectorial: {e}")
                continue
        
        return all_results
    
    async def _text_search_enhanced(
        self, 
        conn, 
        queries: List[str], 
        equipment_context: Optional[Dict[str, str]],
        limit: int
    ) -> List[RAGResult]:
        """Búsqueda de texto completo en tabla mejorada"""
        
        all_results = []
        
        for query in queries[:2]:
            try:
                base_sql = """
                    SELECT 
                        chunk_id, chunk_text, documento_origen,
                        tipo_equipo, marca, modelo, version_manual,
                        pagina_numero, seccion_titulo, tipo_contenido,
                        posicion_x, posicion_y, posicion_width, posicion_height,
                        palabras_clave, entidades_tecnicas, confidence_extraccion,
                        pdf_link, web_viewer_link,
                        ts_rank_cd(to_tsvector('spanish', chunk_text), plainto_tsquery('spanish', $1)) as similarity
                    FROM knowledge_base_enhanced
                    WHERE to_tsvector('spanish', chunk_text) @@ plainto_tsquery('spanish', $1)
                """
                
                params = [query]
                param_count = 1
                
                # Filtros por contexto de equipo
                if equipment_context:
                    if equipment_context.get("tipo"):
                        param_count += 1
                        base_sql += f" AND LOWER(tipo_equipo) = LOWER(${param_count})"
                        params.append(equipment_context["tipo"])
                    
                    if equipment_context.get("marca"):
                        param_count += 1
                        base_sql += f" AND LOWER(marca) = LOWER(${param_count})"
                        params.append(equipment_context["marca"])
                
                param_count += 1
                base_sql += f" ORDER BY similarity DESC LIMIT ${param_count}"
                params.append(limit)
                
                results = await conn.fetch(base_sql, *params)
                
                for result in results:
                    rag_result = self._create_rag_result_from_enhanced(result)
                    all_results.append(rag_result)
                    
            except Exception as e:
                logger.error(f"Error en búsqueda de texto: {e}")
                continue
        
        return all_results
    
    async def _keyword_search_enhanced(
        self, 
        conn, 
        query: str, 
        equipment_context: Optional[Dict[str, str]],
        limit: int
    ) -> List[RAGResult]:
        """Búsqueda por palabras clave en tabla mejorada"""
        
        try:
            keywords = [word.strip().lower() for word in re.findall(r'\b\w+\b', query) if len(word) > 2]
            
            if not keywords:
                return []
            
            base_sql = """
                SELECT 
                    chunk_id, chunk_text, documento_origen,
                    tipo_equipo, marca, modelo, version_manual,
                    pagina_numero, seccion_titulo, tipo_contenido,
                    posicion_x, posicion_y, posicion_width, posicion_height,
                    palabras_clave, entidades_tecnicas, confidence_extraccion,
                    pdf_link, web_viewer_link,
                    array_length(palabras_clave & $1, 1) as similarity
                FROM knowledge_base_enhanced
                WHERE palabras_clave && $1
            """
            
            params = [keywords]
            param_count = 1
            
            if equipment_context and equipment_context.get("tipo"):
                param_count += 1
                base_sql += f" AND LOWER(tipo_equipo) = LOWER(${param_count})"
                params.append(equipment_context["tipo"])
            
            param_count += 1
            base_sql += f" ORDER BY similarity DESC LIMIT ${param_count}"
            params.append(limit)
            
            results = await conn.fetch(base_sql, *params)
            
            return [self._create_rag_result_from_enhanced(result) for result in results]
            
        except Exception as e:
            logger.error(f"Error en búsqueda por palabras clave: {e}")
            return []
    
    def _create_rag_result_from_enhanced(self, result) -> RAGResult:
        """Crea RAGResult desde resultado de tabla mejorada"""
        
        return RAGResult(
            chunk_id=result.get('chunk_id', ''),
            chunk_text=result['chunk_text'],
            documento_origen=result['documento_origen'],
            pagina_numero=result['pagina_numero'],
            similarity=float(result['similarity']),
            palabras_clave=result.get('palabras_clave', []) or [],
            seccion=result.get('seccion_titulo', '') or '',
            confidence=float(result.get('confidence_extraccion', 0.5)),
            tipo_equipo=result.get('tipo_equipo', ''),
            marca=result.get('marca', ''),
            modelo=result.get('modelo', ''),
            version_manual=result.get('version_manual', ''),
            posicion_en_pagina={
                "x": result.get('posicion_x', 0) or 0,
                "y": result.get('posicion_y', 0) or 0,
                "width": result.get('posicion_width', 0) or 0,
                "height": result.get('posicion_height', 0) or 0
            },
            pdf_link=result.get('pdf_link', '') or '',
            web_viewer_link=result.get('web_viewer_link', '') or '',
            entidades_tecnicas=result.get('entidades_tecnicas', []) or [],
            search_method="enhanced"
        )
    
    async def _search_legacy_table(
        self, 
        conn, 
        query: str, 
        top_k: int,
        filter_by_document: Optional[str],
        search_methods: List[str]
    ) -> List[RAGResult]:
        """Búsqueda en tabla legacy para compatibilidad"""
        
        expanded_queries = await self.query_expander.expand_query(query)
        all_results = []
        
        # Búsqueda vectorial legacy
        if "vector" in search_methods:
            vector_results = await self._vector_search_legacy(
                conn, expanded_queries, filter_by_document, self.max_results_per_method
            )
            all_results.extend(vector_results)
        
        # Búsqueda de texto legacy
        if "text" in search_methods:
            text_results = await self._text_search_legacy(
                conn, expanded_queries, filter_by_document, self.max_results_per_method
            )
            all_results.extend(text_results)
        
        unique_results = self._deduplicate_results(all_results)
        ranked_results = self._advanced_rerank(unique_results, query, expanded_queries)
        
        return ranked_results
    
    async def _vector_search_legacy(
        self, 
        conn, 
        queries: List[str], 
        filter_doc: Optional[str],
        limit: int
    ) -> List[RAGResult]:
        """Búsqueda vectorial en tabla legacy"""
        
        all_results = []
        
        for query in queries[:3]:
            try:
                query_embedding = self.vectorizer.embed(query)
                
                base_sql = """
                    SELECT 
                        chunk_text, documento_origen, pagina_numero,
                        palabras_clave, seccion,
                        1 - (chunk_embedding <=> $1::vector) as similarity
                    FROM knowledge_base
                    WHERE chunk_embedding IS NOT NULL
                """
                
                params = [str(query_embedding)]
                param_count = 1
                
                if filter_doc:
                    param_count += 1
                    base_sql += f" AND documento_origen ILIKE ${param_count}"
                    params.append(f"%{filter_doc}%")
                
                param_count += 1
                base_sql += f" AND 1 - (chunk_embedding <=> $1::vector) > ${param_count}"
                params.append(self.min_similarity_threshold)
                
                param_count += 1
                base_sql += f" ORDER BY chunk_embedding <=> $1::vector LIMIT ${param_count}"
                params.append(limit)
                
                results = await conn.fetch(base_sql, *params)
                
                for result in results:
                    rag_result = RAGResult(
                        chunk_text=result['chunk_text'],
                        documento_origen=result['documento_origen'],
                        pagina_numero=result['pagina_numero'],
                        similarity=float(result['similarity']),
                        palabras_clave=result.get('palabras_clave', []) or [],
                        seccion=result.get('seccion', '') or '',
                        search_method="vector_legacy"
                    )
                    all_results.append(rag_result)
                    
            except Exception as e:
                logger.error(f"Error en búsqueda vectorial legacy: {e}")
                continue
        
        return all_results
    
    async def _text_search_legacy(
        self, 
        conn, 
        queries: List[str], 
        filter_doc: Optional[str],
        limit: int
    ) -> List[RAGResult]:
        """Búsqueda de texto en tabla legacy"""
        
        all_results = []
        
        for query in queries[:2]:
            try:
                base_sql = """
                    SELECT 
                        chunk_text, documento_origen, pagina_numero,
                        palabras_clave, seccion,
                        ts_rank_cd(to_tsvector('spanish', chunk_text), plainto_tsquery('spanish', $1)) as similarity
                    FROM knowledge_base
                    WHERE to_tsvector('spanish', chunk_text) @@ plainto_tsquery('spanish', $1)
                """
                
                params = [query]
                param_count = 1
                
                if filter_doc:
                    param_count += 1
                    base_sql += f" AND documento_origen ILIKE ${param_count}"
                    params.append(f"%{filter_doc}%")
                
                param_count += 1
                base_sql += f" ORDER BY similarity DESC LIMIT ${param_count}"
                params.append(limit)
                
                results = await conn.fetch(base_sql, *params)
                
                for result in results:
                    rag_result = RAGResult(
                        chunk_text=result['chunk_text'],
                        documento_origen=result['documento_origen'],
                        pagina_numero=result['pagina_numero'],
                        similarity=float(result['similarity']),
                        palabras_clave=result.get('palabras_clave', []) or [],
                        seccion=result.get('seccion', '') or '',
                        search_method="text_legacy"
                    )
                    all_results.append(rag_result)
                    
            except Exception as e:
                logger.error(f"Error en búsqueda de texto legacy: {e}")
                continue
        
        return all_results
    
    def _create_enriched_query(
        self, 
        query: str, 
        equipment_context: Dict[str, str]
    ) -> str:
        """Crea consulta enriquecida con contexto de equipo"""
        
        enriched_parts = [query]
        
        if equipment_context.get("tipo"):
            enriched_parts.append(f"Equipo: {equipment_context['tipo']}")
        
        if equipment_context.get("marca"):
            enriched_parts.append(f"Marca: {equipment_context['marca']}")
        
        if equipment_context.get("modelo"):
            enriched_parts.append(f"Modelo: {equipment_context['modelo']}")
        
        return " ".join(enriched_parts)
    
    def _deduplicate_results(self, results: List[RAGResult]) -> List[RAGResult]:
        """Elimina resultados duplicados"""
        
        if not results:
            return []
        
        unique_results = []
        seen_content_hashes = set()
        
        for result in results:
            content_hash = hashlib.md5(result.chunk_text[:200].encode()).hexdigest()
            
            if content_hash not in seen_content_hashes:
                seen_content_hashes.add(content_hash)
                unique_results.append(result)
        
        return unique_results
    
    def _advanced_rerank(
        self,
        results: List[RAGResult],
        original_query: str,
        expanded_queries: List[str]
    ) -> List[RAGResult]:
        """Re-ranking avanzado con múltiples factores"""
        
        if not results:
            return []
        
        query_terms = set(original_query.lower().split())
        all_query_terms = set()
        for q in expanded_queries:
            all_query_terms.update(q.lower().split())
        
        for result in results:
            score = 0.0
            text_lower = result.chunk_text.lower()
            text_terms = set(text_lower.split())
            
            # Factor 1: Similitud base (30%)
            score += result.similarity * 0.30
            
            # Factor 2: Coincidencias exactas (25%)
            if query_terms:
                exact_matches = len(query_terms.intersection(text_terms))
                exact_ratio = exact_matches / len(query_terms)
                score += exact_ratio * 0.25
            
            # Factor 3: Palabras clave relevantes (15%)
            if result.palabras_clave and query_terms:
                keyword_set = set(kw.lower() for kw in result.palabras_clave)
                keyword_matches = len(query_terms.intersection(keyword_set))
                keyword_ratio = keyword_matches / len(query_terms)
                score += keyword_ratio * 0.15
            
            # Factor 4: Longitud óptima (15%)
            text_length = len(result.chunk_text)
            if 200 <= text_length <= 800:
                score += 0.15
            elif 100 <= text_length < 200 or 800 < text_length <= 1200:
                score += 0.10
            
            # Factor 5: Método de búsqueda (10%)
            method_bonus = {
                'enhanced': 0.10,
                'vector': 0.08,
                'text': 0.06,
                'keyword': 0.04
            }
            score += method_bonus.get(result.search_method, 0.0)
            
            # Factor 6: Confidence del chunk (5%)
            score += result.confidence * 0.05
            
            result.confidence = min(score, 1.0)
        
        return sorted(results, key=lambda x: x.confidence, reverse=True)
    
    async def _enrich_with_context(
        self,
        conn,
        results: List[RAGResult]
    ) -> List[RAGResult]:
        """Enriquece resultados con contexto adicional"""
        
        for result in results:
            try:
                # Determinar tabla a usar
                use_enhanced = await self._check_enhanced_table_exists(conn)
                
                if use_enhanced and result.chunk_id:
                    # Buscar contexto en tabla mejorada
                    context_sql = """
                        SELECT chunk_text, pagina_numero, seccion_titulo, tipo_contenido
                        FROM knowledge_base_enhanced
                        WHERE documento_origen = $1 
                        AND pagina_numero BETWEEN $2 AND $3
                        AND chunk_id != $4
                        ORDER BY pagina_numero, chunk_id
                        LIMIT 3
                    """
                    
                    context_chunks = await conn.fetch(
                        context_sql,
                        result.documento_origen,
                        max(1, result.pagina_numero - 1),
                        result.pagina_numero + 1,
                        result.chunk_id or ''
                    )
                else:
                    # Buscar contexto en tabla legacy
                    context_sql = """
                        SELECT chunk_text, pagina_numero, seccion
                        FROM knowledge_base
                        WHERE documento_origen = $1 
                        AND pagina_numero BETWEEN $2 AND $3
                        AND chunk_text != $4
                        ORDER BY pagina_numero
                        LIMIT 2
                    """
                    
                    context_chunks = await conn.fetch(
                        context_sql,
                        result.documento_origen,
                        max(1, result.pagina_numero - 1),
                        result.pagina_numero + 1,
                        result.chunk_text
                    )
                
                if context_chunks:
                    context_parts = []
                    for chunk in context_chunks:
                        preview = chunk['chunk_text'][:150]
                        seccion = chunk.get('seccion_titulo') or chunk.get('seccion', '')
                        if seccion:
                            preview = f"[{seccion}] {preview}"
                        context_parts.append(preview + "...")
                    
                    result.contexto_adicional = "\n".join(context_parts)
                
            except Exception as e:
                logger.warning(f"Error obteniendo contexto: {e}")
        
        return results
    
    def get_search_analytics(self) -> Dict[str, Any]:
        """Obtiene analíticas de búsqueda"""
        
        if not self.metrics:
            return {}
        
        recent_metrics = [m for m in self.metrics if 
                         datetime.now() - m.timestamp < timedelta(hours=24)]
        
        if not recent_metrics:
            return {}
        
        avg_time = sum(m.execution_time for m in recent_metrics) / len(recent_metrics)
        cache_hit_rate = sum(1 for m in recent_metrics if m.cache_hit) / len(recent_metrics)
        avg_results = sum(m.results_count for m in recent_metrics) / len(recent_metrics)
        
        return {
            'total_searches_24h': len(recent_metrics),
            'avg_execution_time': round(avg_time, 3),
            'cache_hit_rate': round(cache_hit_rate, 2),
            'avg_results_count': round(avg_results, 1),
            'cache_size': len(self.cache._cache)
        }
    
    async def close(self):
        """Cierra recursos"""
        if self._connection_pool:
            await self._connection_pool.close()

# =====================================================
# BÚSQUEDA CON CONTEXTO PARCIAL DE EQUIPOS
# =====================================================

class PartialContextSearcher:
    """Maneja búsquedas con contexto parcial de equipos"""
    
    def __init__(self, settings, vectorizer):
        self.settings = settings
        self.vectorizer = vectorizer
        self.link_generator = DocumentLinkGenerator()
    
    async def search_with_partial_context(
        self,
        query: str,
        tipo_equipo: str,
        marca: Optional[str] = None,
        modelo: Optional[str] = None,
        top_k_per_equipment: int = 2
    ) -> MultiEquipmentSearchResult:
        """Búsqueda con contexto parcial de equipo"""
        
        conn_string = f"postgresql://{self.settings.database.user}:{self.settings.database.password or ''}@{self.settings.database.host}:{self.settings.database.port}/{self.settings.database.name}"
        conn = await asyncpg.connect(conn_string)
        
        try:
            # Obtener equipos disponibles
            equipment_list = await self._get_available_equipment(
                conn, tipo_equipo, marca, modelo
            )
            
            results_by_equipment = {}
            confidence_by_equipment = {}
            
            # Buscar para cada equipo
            for equipment in equipment_list[:5]:  # Máximo 5 equipos
                equipment_key = f"{equipment['marca']}_{equipment['modelo']}"
                
                equipment_results = await self._search_specific_equipment(
                    conn, query, equipment, top_k_per_equipment
                )
                
                if equipment_results:
                    results_by_equipment[equipment_key] = equipment_results
                    avg_confidence = sum(r.confidence for r in equipment_results) / len(equipment_results)
                    confidence_by_equipment[equipment_key] = avg_confidence
            
            # Determinar mejor equipo
            best_equipment = max(confidence_by_equipment.items(), 
                               key=lambda x: x[1])[0] if confidence_by_equipment else ""
            
            total_results = sum(len(results) for results in results_by_equipment.values())
            equipment_coverage = {eq: len(results) for eq, results in results_by_equipment.items()}
            
            return MultiEquipmentSearchResult(
                query=query,
                results_by_equipment=results_by_equipment,
                total_results=total_results,
                equipment_coverage=equipment_coverage,
                best_match_equipment=best_equipment,
                confidence_by_equipment=confidence_by_equipment
            )
            
        finally:
            await conn.close()
    
    async def _get_available_equipment(
        self,
        conn,
        tipo_equipo: str,
        marca: Optional[str],
        modelo: Optional[str]
    ) -> List[Dict[str, Any]]:
        """Obtiene equipos disponibles"""
        
        # Intentar tabla mejorada primero
        try:
            base_sql = """
                SELECT DISTINCT 
                    tipo_equipo, marca, modelo,
                    COUNT(*) as total_chunks,
                    AVG(confidence_extraccion) as avg_confidence
                FROM knowledge_base_enhanced
                WHERE LOWER(tipo_equipo) = LOWER($1)
            """
            
            params = [tipo_equipo]
            param_count = 1
            
            if marca:
                param_count += 1
                base_sql += f" AND LOWER(marca) = LOWER(${param_count})"
                params.append(marca)
            
            if modelo:
                param_count += 1
                base_sql += f" AND LOWER(modelo) LIKE LOWER(${param_count})"
                params.append(f"%{modelo}%")
            
            base_sql += """
                GROUP BY tipo_equipo, marca, modelo
                HAVING COUNT(*) >= 5
                ORDER BY AVG(confidence_extraccion) DESC, COUNT(*) DESC
            """
            
            equipment_list = await conn.fetch(base_sql, *params)
            
            if equipment_list:
                return [dict(equipment) for equipment in equipment_list]
                
        except Exception as e:
            logger.debug(f"Tabla mejorada no disponible: {e}")
        
        # Fallback a tabla legacy
        try:
            base_sql = """
                SELECT DISTINCT documento_origen,
                    COUNT(*) as total_chunks
                FROM knowledge_base
                GROUP BY documento_origen
                HAVING COUNT(*) >= 5
                ORDER BY COUNT(*) DESC
            """
            
            docs = await conn.fetch(base_sql)
            
            # Simular estructura de equipos desde nombres de documentos
            equipment_list = []
            for doc in docs:
                doc_name = doc['documento_origen']
                # Intentar extraer marca/modelo del nombre del archivo
                equipment_info = self._parse_equipment_from_filename(doc_name, tipo_equipo)
                if equipment_info:
                    equipment_info['total_chunks'] = doc['total_chunks']
                    equipment_info['avg_confidence'] = 0.5
                    equipment_list.append(equipment_info)
            
            return equipment_list
            
        except Exception as e:
            logger.error(f"Error obteniendo equipos: {e}")
            return []
    
    def _parse_equipment_from_filename(self, filename: str, tipo_equipo: str) -> Optional[Dict[str, str]]:
        """Intenta extraer información de equipo desde nombre de archivo"""
        
        filename_lower = filename.lower()
        
        # Patrones comunes para balanzas
        if tipo_equipo.lower() == "balanza":
            if "dibal" in filename_lower:
                if "mistral" in filename_lower:
                    return {"tipo_equipo": "balanza", "marca": "DIBAL", "modelo": "Mistral"}
                elif "serie" in filename_lower:
                    return {"tipo_equipo": "balanza", "marca": "DIBAL", "modelo": "Serie_500"}
                else:
                    return {"tipo_equipo": "balanza", "marca": "DIBAL", "modelo": "General"}
            
            elif "epelsa" in filename_lower:
                return {"tipo_equipo": "balanza", "marca": "EPELSA", "modelo": "Digital"}
        
        # Patrón genérico
        return {"tipo_equipo": tipo_equipo, "marca": "Genérica", "modelo": "Estándar"}
    
    async def _search_specific_equipment(
        self,
        conn,
        query: str,
        equipment_info: Dict[str, Any],
        top_k: int
    ) -> List[RAGResult]:
        """Búsqueda específica para un equipo"""
        
        # Crear consulta enriquecida
        enriched_query = f"Equipo: {equipment_info.get('tipo_equipo', '')} {equipment_info.get('marca', '')} {equipment_info.get('modelo', '')} Consulta: {query}"
        query_embedding = self.vectorizer.embed(enriched_query)
        
        try:
            # Intentar tabla mejorada
            search_sql = """
                SELECT 
                    chunk_id, chunk_text, documento_origen,
                    tipo_equipo, marca, modelo, version_manual,
                    pagina_numero, seccion_titulo, tipo_contenido,
                    posicion_x, posicion_y, posicion_width, posicion_height,
                    palabras_clave, entidades_tecnicas, confidence_extraccion,
                    pdf_link, web_viewer_link,
                    1 - (chunk_embedding_with_metadata <=> $1::vector) as similarity
                FROM knowledge_base_enhanced
                WHERE LOWER(tipo_equipo) = LOWER($2)
                AND LOWER(marca) = LOWER($3)
                AND LOWER(modelo) = LOWER($4)
                AND confidence_extraccion >= 0.3
                ORDER BY chunk_embedding_with_metadata <=> $1::vector
                LIMIT $5
            """
            
            results = await conn.fetch(
                search_sql,
                str(query_embedding),
                equipment_info['tipo_equipo'],
                equipment_info['marca'],
                equipment_info['modelo'],
                top_k
            )
            
            search_results = []
            for result in results:
                if result['similarity'] >= 0.5:
                    rag_result = RAGResult(
                        chunk_id=result['chunk_id'],
                        chunk_text=result['chunk_text'],
                        similarity=float(result['similarity']),
                        confidence=float(result['confidence_extraccion']),
                        documento_origen=result['documento_origen'],
                        tipo_equipo=result['tipo_equipo'],
                        marca=result['marca'],
                        modelo=result['modelo'],
                        version_manual=result['version_manual'] or "1.0",
                        pagina_numero=result['pagina_numero'],
                        seccion=result['seccion_titulo'] or "",
                        palabras_clave=result['palabras_clave'] or [],
                        entidades_tecnicas=result['entidades_tecnicas'] or [],
                        posicion_en_pagina={
                            "x": result['posicion_x'] or 0,
                            "y": result['posicion_y'] or 0,
                            "width": result['posicion_width'] or 0,
                            "height": result['posicion_height'] or 0
                        },
                        pdf_link=result['pdf_link'] or "",
                        web_viewer_link=result['web_viewer_link'] or ""
                    )
                    search_results.append(rag_result)
            
            return search_results
            
        except Exception:
            # Fallback a tabla legacy
            return await self._search_equipment_legacy(conn, query, equipment_info, top_k)
    
    async def _search_equipment_legacy(
        self,
        conn,
        query: str,
        equipment_info: Dict[str, Any],
        top_k: int
    ) -> List[RAGResult]:
        """Búsqueda en tabla legacy para equipo específico"""
        
        try:
            query_embedding = self.vectorizer.embed(query)
            
            search_sql = """
                SELECT 
                    chunk_text, documento_origen, pagina_numero,
                    palabras_clave, seccion,
                    1 - (chunk_embedding <=> $1::vector) as similarity
                FROM knowledge_base
                WHERE chunk_embedding IS NOT NULL
                AND 1 - (chunk_embedding <=> $1::vector) > 0.5
                ORDER BY chunk_embedding <=> $1::vector
                LIMIT $2
            """
            
            results = await conn.fetch(search_sql, str(query_embedding), top_k)
            
            search_results = []
            for result in results:
                rag_result = RAGResult(
                    chunk_text=result['chunk_text'],
                    similarity=float(result['similarity']),
                    confidence=0.7,  # Valor por defecto
                    documento_origen=result['documento_origen'],
                    pagina_numero=result['pagina_numero'],
                    seccion=result.get('seccion', '') or '',
                    palabras_clave=result.get('palabras_clave', []) or [],
                    tipo_equipo=equipment_info.get('tipo_equipo', ''),
                    marca=equipment_info.get('marca', ''),
                    modelo=equipment_info.get('modelo', '')
                )
                
                # Generar enlaces básicos
                rag_result.pdf_link = self.link_generator.generate_pdf_link(
                    rag_result.documento_origen, rag_result.pagina_numero
                )
                
                search_results.append(rag_result)
            
            return search_results
            
        except Exception as e:
            logger.error(f"Error en búsqueda legacy: {e}")
            return []

# =====================================================
# FORMATEADORES DE RESPUESTA
# =====================================================

class ResponseFormatter:
    """Formateador de respuestas RAG"""
    
    def format_results(self, results: List[RAGResult], query: str, metrics: SearchMetrics) -> str:
        """Formatea resultados de búsqueda normal"""
        
        if not results:
            return self._format_no_results_message(query)
        
        formatted_parts = []
        
        # Header
        header = f"🔍 **Resultados para:** \"{query}\"\n"
        header += f"📊 *{len(results)} soluciones encontradas en {metrics.execution_time:.2f}s*\n"
        if metrics.cache_hit:
            header += "*⚡ Resultado desde cache*\n"
        header += "\n"
        formatted_parts.append(header)
        
        # Formatear cada resultado
        for i, result in enumerate(results, 1):
            result_block = self._format_single_equipment_result(result, i)
            section_parts.append(result_block)
        
        section_parts.append("---")
        return "\n".join(section_parts)
    
    def _format_single_equipment_result(self, result: RAGResult, index: int) -> str:
        """Formatea resultado individual dentro de sección de equipo"""
        
        confidence_icon = "⭐" if result.confidence > 0.8 else "✅" if result.confidence > 0.6 else "🔍"
        
        result_parts = []
        
        title = f"**{confidence_icon} Resultado {index}**"
        result_parts.append(title)
        
        location = f"📍 *Página {result.pagina_numero}"
        if result.seccion:
            location += f" - {result.seccion}"
        location += f" | {result.similarity:.1%}*"
        result_parts.append(location)
        
        if result.pdf_link or result.web_viewer_link:
            links = "🔗 "
            if result.pdf_link:
                links += f"[PDF]({result.pdf_link}) "
            if result.web_viewer_link:
                links += f"[Visor]({result.web_viewer_link})"
            result_parts.append(links)
        
        content = result.chunk_text.strip()
        if len(content) > 300:
            content = content[:300] + "..."
        
        result_parts.append("")
        result_parts.append(content)
        
        if result.palabras_clave:
            keywords = ", ".join(result.palabras_clave[:3])
            result_parts.append(f"\n*🏷️ {keywords}*")
        
        result_parts.append("")
        return "\n".join(result_parts)
    
    def _format_equipment_comparison(self, search_result: MultiEquipmentSearchResult) -> str:
        """Formatea comparación entre equipos"""
        
        comparison_parts = ["\n## 📊 **Comparación entre Equipos**\n"]
        
        comparison_parts.append("| Equipo | Resultados | Relevancia Promedio | Mejor Resultado |")
        comparison_parts.append("|--------|------------|-------------------|-----------------|")
        
        for equipment_key in sorted(
            search_result.confidence_by_equipment.keys(),
            key=lambda x: search_result.confidence_by_equipment[x],
            reverse=True
        ):
            marca, modelo = equipment_key.split('_', 1)
            result_count = search_result.equipment_coverage[equipment_key]
            avg_conf = search_result.confidence_by_equipment[equipment_key]
            
            equipment_results = search_result.results_by_equipment[equipment_key]
            best_result = max(equipment_results, key=lambda x: x.similarity)
            
            comparison_parts.append(
                f"| **{marca} {modelo}** | {result_count} | {avg_conf:.1%} | {best_result.similarity:.1%} |"
            )
        
        comparison_parts.append("")
        
        best_equipment = search_result.best_match_equipment.replace('_', ' ')
        comparison_parts.append(f"💡 **Recomendación:** Los mejores resultados se encontraron en **{best_equipment}**")
        
        return "\n".join(comparison_parts)
    
    def _format_no_results_message(self, query: str) -> str:
        """Mensaje cuando no hay resultados"""
        return f"""
🔍 **No se encontraron soluciones para:** "{query}"

**💡 Sugerencias para mejorar la búsqueda:**
• Usa términos más específicos del equipo
• Incluye marca y modelo si los conoces
• Prueba sinónimos técnicos
• Verifica la ortografía

**🔧 Búsquedas sugeridas:**
• "configuración [equipo específico]"
• "procedimiento [acción]"
• "error [código o descripción]"

¿Puedes proporcionar más detalles sobre el equipo o problema?
"""
    
    def _format_no_equipment_found(self, query: str) -> str:
        """Mensaje cuando no se encuentran equipos"""
        return f"""
🔍 **No se encontraron equipos para:** "{query}"

**💡 Posibles causas:**
• No hay manuales vectorizados para este tipo de equipo
• La consulta es muy específica
• Los términos no coinciden con la documentación

**🔧 Sugerencias:**
• Verifica el tipo de equipo
• Usa términos más generales
• Consulta equipos disponibles

¿Te gustaría ver qué equipos están documentados?
"""

# =====================================================
# CLASE PRINCIPAL OPTIMIZADA
# =====================================================

class OptimizedEroskiKnowledgeBase:
    """
    Clase principal del RAG optimizado que integra todas las funcionalidades
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.vectorizer = get_vectorizer()
        self.searcher = HybridRAGSearcher(self.settings, self.vectorizer)
        self.partial_searcher = PartialContextSearcher(self.settings, self.vectorizer)
        self.formatter = ResponseFormatter()
        
        # Configuración
        self.default_top_k = 3
        self.include_analytics = True
    
    # =====================================================
    # MÉTODOS PRINCIPALES DE BÚSQUEDA
    # =====================================================
    
    def buscar_solucion_rag(self, query: str, top_k: int = 3) -> str:
        """
        Método principal compatible con interfaz original
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                task = asyncio.create_task(self._async_search_basic(query, top_k))
                return asyncio.run_coroutine_threadsafe(task, loop).result(timeout=30)
            else:
                return asyncio.run(self._async_search_basic(query, top_k))
        except Exception as e:
            logger.error(f"Error en búsqueda básica: {e}")
            return f"❌ Error en la búsqueda: {str(e)}"
    
    async def _async_search_basic(self, query: str, top_k: int) -> str:
        """Búsqueda básica asíncrona"""
        try:
            results, metrics = await self.searcher.search(
                query=query,
                top_k=top_k,
                include_context=True,
                search_methods=["vector", "text"]
            )
            
            return self.formatter.format_results(results, query, metrics)
            
        except Exception as e:
            logger.error(f"Error en búsqueda básica async: {e}")
            return self._get_error_message(query, str(e))
    
    async def buscar_solucion_rag_avanzada(
        self,
        query: str,
        top_k: int = 3,
        equipo_context: Optional[Dict[str, str]] = None,
        incluir_enlaces: bool = True
    ) -> str:
        """
        Búsqueda RAG avanzada con metadatos y enlaces
        """
        try:
            # Determinar tipo de búsqueda según contexto
            if not equipo_context:
                # Búsqueda general
                results, metrics = await self.searcher.search(
                    query=query,
                    top_k=top_k,
                    include_context=True,
                    search_methods=["vector", "text", "keyword"]
                )
                return self.formatter.format_results(results, query, metrics)
            
            # Verificar completitud del contexto
            tipo_equipo = equipo_context.get("tipo")
            marca = equipo_context.get("marca")
            modelo = equipo_context.get("modelo")
            
            if tipo_equipo and marca and modelo:
                # Contexto completo - búsqueda específica
                results, metrics = await self.searcher.search(
                    query=query,
                    top_k=top_k,
                    include_context=True,
                    search_methods=["vector", "text", "keyword"],
                    equipment_context=equipo_context
                )
                return self.formatter.format_results(results, query, metrics)
            
            elif tipo_equipo:
                # Contexto parcial - búsqueda multi-equipo
                multi_result = await self.partial_searcher.search_with_partial_context(
                    query=query,
                    tipo_equipo=tipo_equipo,
                    marca=marca,
                    modelo=modelo,
                    top_k_per_equipment=2
                )
                return self.formatter.format_multi_equipment_results(multi_result)
            
            else:
                return "❌ Error: Debe especificar al menos el tipo de equipo"
                
        except Exception as e:
            logger.error(f"Error en búsqueda avanzada: {e}")
            return self._get_error_message(query, str(e))
    
    async def buscar_por_equipo_especifico(
        self,
        query: str,
        tipo_equipo: str,
        marca: Optional[str] = None,
        modelo: Optional[str] = None
    ) -> str:
        """Búsqueda específica por tipo de equipo"""
        
        equipment_context = {"tipo": tipo_equipo}
        if marca:
            equipment_context["marca"] = marca
        if modelo:
            equipment_context["modelo"] = modelo
        
        return await self.buscar_solucion_rag_avanzada(
            query=query,
            equipo_context=equipment_context,
            top_k=3
        )
    
    async def buscar_en_documento(
        self,
        query: str,
        documento: str,
        seccion: Optional[str] = None
    ) -> str:
        """Búsqueda dentro de un documento específico"""
        
        try:
            results, metrics = await self.searcher.search(
                query=query,
                top_k=5,
                include_context=True,
                filter_by_document=documento,
                search_methods=["vector", "text"]
            )
            
            # Filtrar por sección si se especifica
            if seccion and results:
                filtered_results = [
                    r for r in results 
                    if seccion.lower() in r.seccion.lower()
                ]
                if filtered_results:
                    results = filtered_results
            
            return self.formatter.format_results(results, query, metrics)
            
        except Exception as e:
            logger.error(f"Error en búsqueda por documento: {e}")
            return self._get_error_message(query, str(e))
    
    # =====================================================
    # MÉTODOS DE ANÁLISIS Y ESTADÍSTICAS
    # =====================================================
    
    async def obtener_estadisticas_documentos(self) -> Dict[str, Any]:
        """Obtiene estadísticas de documentos vectorizados"""
        
        conn_string = f"postgresql://{self.settings.database.user}:{self.settings.database.password or ''}@{self.settings.database.host}:{self.settings.database.port}/{self.settings.database.name}"
        conn = await asyncpg.connect(conn_string)
        
        try:
            # Verificar tabla mejorada
            use_enhanced = await self.searcher._check_enhanced_table_exists(conn)
            
            if use_enhanced:
                # Estadísticas de tabla mejorada
                general_stats = await conn.fetchrow("""
                    SELECT 
                        COUNT(*) as total_chunks,
                        COUNT(DISTINCT documento_origen) as total_documentos,
                        COUNT(DISTINCT CONCAT(tipo_equipo, marca, modelo)) as equipos_unicos,
                        AVG(confidence_extraccion) as confidence_promedio
                    FROM knowledge_base_enhanced
                """)
                
                equipment_stats = await conn.fetch("""
                    SELECT 
                        tipo_equipo, marca, modelo,
                        COUNT(*) as chunks_count,
                        AVG(confidence_extraccion) as avg_confidence
                    FROM knowledge_base_enhanced
                    GROUP BY tipo_equipo, marca, modelo
                    ORDER BY chunks_count DESC
                """)
                
                return {
                    "general": dict(general_stats),
                    "por_equipo": [dict(row) for row in equipment_stats],
                    "tabla_utilizada": "knowledge_base_enhanced"
                }
            else:
                # Estadísticas de tabla legacy
                general_stats = await conn.fetchrow("""
                    SELECT 
                        COUNT(*) as total_chunks,
                        COUNT(DISTINCT documento_origen) as total_documentos
                    FROM knowledge_base
                """)
                
                doc_stats = await conn.fetch("""
                    SELECT 
                        documento_origen,
                        COUNT(*) as chunks_count
                    FROM knowledge_base
                    GROUP BY documento_origen
                    ORDER BY chunks_count DESC
                """)
                
                return {
                    "general": dict(general_stats),
                    "por_documento": [dict(row) for row in doc_stats],
                    "tabla_utilizada": "knowledge_base"
                }
                
        finally:
            await conn.close()
    
    async def listar_equipos_disponibles(self, tipo_equipo: Optional[str] = None) -> str:
        """Lista equipos disponibles en el sistema"""
        
        conn_string = f"postgresql://{self.settings.database.user}:{self.settings.database.password or ''}@{self.settings.database.host}:{self.settings.database.port}/{self.settings.database.name}"
        conn = await asyncpg.connect(conn_string)
        
        try:
            use_enhanced = await self.searcher._check_enhanced_table_exists(conn)
            
            if use_enhanced:
                # Usar tabla mejorada
                base_sql = """
                    SELECT 
                        tipo_equipo, marca, modelo,
                        COUNT(*) as total_chunks,
                        AVG(confidence_extraccion) as avg_confidence
                    FROM knowledge_base_enhanced
                """
                
                params = []
                if tipo_equipo:
                    base_sql += " WHERE LOWER(tipo_equipo) = LOWER($1)"
                    params.append(tipo_equipo)
                
                base_sql += """
                    GROUP BY tipo_equipo, marca, modelo
                    ORDER BY tipo_equipo, marca, modelo
                """
                
                equipment_list = await conn.fetch(base_sql, *params)
                
                if not equipment_list:
                    return "📄 No hay equipos vectorizados en el sistema"
                
                # Agrupar por tipo
                by_type = defaultdict(list)
                for equipment in equipment_list:
                    by_type[equipment['tipo_equipo']].append(equipment)
                
                formatted_parts = ["📋 **Equipos Disponibles:**\n"]
                
                for equipo_tipo, equipos in sorted(by_type.items()):
                    formatted_parts.append(f"## 🔧 {equipo_tipo.title()}")
                    
                    for equipo in equipos:
                        quality_icon = "🟢" if equipo['avg_confidence'] > 0.7 else "🟡" if equipo['avg_confidence'] > 0.5 else "🔴"
                        formatted_parts.append(
                            f"   {quality_icon} **{equipo['marca']} {equipo['modelo']}** - "
                            f"{equipo['total_chunks']} chunks "
                            f"(Calidad: {equipo['avg_confidence']:.1%})"
                        )
                    
                    formatted_parts.append("")
                
                return "\n".join(formatted_parts)
                
            else:
                # Tabla legacy - mostrar documentos
                docs = await conn.fetch("""
                    SELECT documento_origen, COUNT(*) as total_chunks
                    FROM knowledge_base
                    GROUP BY documento_origen
                    ORDER BY total_chunks DESC
                """)
                
                if not docs:
                    return "📄 No hay documentos vectorizados"
                
                formatted_parts = ["📋 **Documentos Disponibles:**\n"]
                
                for doc in docs:
                    formatted_parts.append(f"   📄 **{doc['documento_origen']}** - {doc['total_chunks']} chunks")
                
                return "\n".join(formatted_parts)
                
        finally:
            await conn.close()
    
    async def get_analytics(self) -> Dict[str, Any]:
        """Obtiene analíticas del sistema RAG"""
        return self.searcher.get_search_analytics()
    
    # =====================================================
    # MÉTODOS DE UTILIDAD
    # =====================================================
    
    def _get_error_message(self, query: str, error: str) -> str:
        """Mensaje de error amigable"""
        return f"""
⚠️ **Hubo un problema técnico al buscar soluciones**

**Tu consulta:** "{query}"

**🔄 Mientras tanto, puedes intentar:**
1. Reformular tu consulta con términos diferentes
2. Ser más específico sobre el problema
3. Incluir marca y modelo del equipo si los conoces

**🔧 Para problemas urgentes:**
- Reinicia el equipo y prueba nuevamente
- Verifica conexiones básicas
- Consulta el manual físico del equipo

Disculpa las molestias. El sistema se está recuperando automáticamente.
"""
    
    async def close(self):
        """Cierra recursos del sistema"""
        await self.searcher.close()
    
    def __del__(self):
        """Limpieza automática"""
        try:
            loop = asyncio.get_event_loop()
            if not loop.is_closed():
                loop.create_task(self.close())
        except:
            pass

# =====================================================
# EJEMPLO DE USO
# =====================================================

async def ejemplo_uso_completo():
    """Ejemplo de uso del sistema completo"""
    
    # Inicializar RAG optimizado
    rag = OptimizedEroskiKnowledgeBase()
    
    print("=" * 60)
    print("EJEMPLO DE USO COMPLETO - RAG OPTIMIZADO")
    print("=" * 60)
    
    try:
        # 1. Búsqueda básica (compatible con versión original)
        print("\n1️⃣ Búsqueda básica:")
        resultado_basico = rag.buscar_solucion_rag("configuración retroiluminación", 2)
        print(resultado_basico[:500] + "...")
        
        # 2. Búsqueda con contexto completo
        print("\n2️⃣ Búsqueda con contexto completo:")
        resultado_completo = await rag.buscar_solucion_rag_avanzada(
            query="calibración peso",
            equipo_context={
                "tipo": "balanza",
                "marca": "DIBAL", 
                "modelo": "Mistral"
            }
        )
        print(resultado_completo[:500] + "...")
        
        # 3. Búsqueda con contexto parcial (multi-equipo)
        print("\n3️⃣ Búsqueda con contexto parcial:")
        resultado_parcial = await rag.buscar_solucion_rag_avanzada(
            query="problema calibración",
            equipo_context={
                "tipo": "balanza",  # Solo conocemos el tipo
                "marca": None,
                "modelo": None
            }
        )
        print(resultado_parcial[:500] + "...")
        
        # 4. Estadísticas del sistema
        print("\n4️⃣ Estadísticas del sistema:")
        stats = await rag.obtener_estadisticas_documentos()
        print(f"Total chunks: {stats['general'].get('total_chunks', 'N/A')}")
        print(f"Total documentos: {stats['general'].get('total_documentos', 'N/A')}")
        
        # 5. Equipos disponibles
        print("\n5️⃣ Equipos disponibles:")
        equipos = await rag.listar_equipos_disponibles("balanza")
        print(equipos[:300] + "...")
        
    finally:
        await rag.close()


    
    def format_multi_equipment_results(self, search_result: MultiEquipmentSearchResult) -> str:
        """Formatea resultados de múltiples equipos"""
        
        if not search_result.results_by_equipment:
            return self._format_no_equipment_found(search_result.query)
        
        formatted_parts = []
        
        # Header principal
        header = f"🔍 **Resultados para:** \"{search_result.query}\"\n"
        header += f"🔧 **Tipo de equipo:** {list(search_result.results_by_equipment.values())[0][0].tipo_equipo}\n"
        header += f"📊 **{search_result.total_results} resultados en {len(search_result.results_by_equipment)} equipos**\n"
        
        if search_result.best_match_equipment:
            best_confidence = search_result.confidence_by_equipment[search_result.best_match_equipment]
            header += f"🎯 **Mejor coincidencia:** {search_result.best_match_equipment.replace('_', ' ')} ({best_confidence:.1%})\n"
        
        formatted_parts.append(header)
        
        # Resumen de equipos
        summary = self._format_equipment_summary(search_result)
        formatted_parts.append(summary)
        
        # Resultados por equipo
        sorted_equipment = sorted(
            search_result.results_by_equipment.items(),
            key=lambda x: search_result.confidence_by_equipment[x[0]],
            reverse=True
        )
        
        for equipment_key, results in sorted_equipment:
            equipment_section = self._format_equipment_section(equipment_key, results)
            formatted_parts.append(equipment_section)
        
        # Comparación
        if len(search_result.results_by_equipment) > 1:
            comparison = self._format_equipment_comparison(search_result)
            formatted_parts.append(comparison)
        
        return "\n".join(formatted_parts)
    
    def _format_single_result(self, result: RAGResult, index: int) -> str:
        """Formatea un resultado individual"""
        
        confidence_icon = "⭐" if result.confidence > 0.8 else "✅" if result.confidence > 0.6 else "🔍"
        
        result_parts = []
        
        # Título
        title = f"**{confidence_icon} Solución {index}**"
        if result.marca and result.modelo:
            title += f" *({result.marca} {result.modelo})*"
        if result.confidence > 0.85:
            title += " 🎯 *Alta relevancia*"
        result_parts.append(title)
        
        # Información del documento
        doc_info = f"📋 *{result.documento_origen}"
        if result.pagina_numero:
            doc_info += f", Página {result.pagina_numero}"
        if result.seccion:
            doc_info += f" - {result.seccion}"
        doc_info += f" | Relevancia: {result.confidence:.2f}*"
        result_parts.append(doc_info)
        
        # Enlaces si están disponibles
        if result.pdf_link or result.web_viewer_link:
            links = "🔗 **Enlaces directos:**\n"
            if result.pdf_link:
                links += f"   📄 [Abrir PDF]({result.pdf_link})\n"
            if result.web_viewer_link:
                links += f"   🖥️ [Ver en navegador]({result.web_viewer_link})"
            result_parts.append(links)
        
        result_parts.append("")
        
        # Contenido principal
        content = result.chunk_text.strip()
        if len(content) > 1500:
            content = content[:1500] + "..."
            if result.web_viewer_link:
                content += f"\n\n*[Ver contenido completo]({result.web_viewer_link})*"
        
        result_parts.append(content)
        
        # Contexto adicional
        if result.contexto_adicional:
            result_parts.append("")
            result_parts.append("**📖 Contexto relacionado:**")
            result_parts.append(result.contexto_adicional)
        
        # Palabras clave
        if result.palabras_clave:
            keywords_text = ", ".join(result.palabras_clave[:5])
            result_parts.append("")
            result_parts.append(f"*🏷️ Palabras clave: {keywords_text}*")
        
        result_parts.append("")
        result_parts.append("---")
        result_parts.append("")
        
        return "\n".join(result_parts)
    
    def _format_equipment_summary(self, search_result: MultiEquipmentSearchResult) -> str:
        """Formatea resumen de equipos"""
        
        summary_parts = ["\n📋 **Equipos analizados:**"]
        
        for equipment_key, confidence in sorted(
            search_result.confidence_by_equipment.items(),
            key=lambda x: x[1],
            reverse=True
        ):
            marca, modelo = equipment_key.split('_', 1)
            result_count = search_result.equipment_coverage[equipment_key]
            
            icon = "🟢" if confidence >= 0.8 else "🟡" if confidence >= 0.6 else "🔴"
            
            summary_parts.append(
                f"   {icon} **{marca} {modelo}**: {result_count} resultados ({confidence:.1%})"
            )
        
        summary_parts.append("")
        return "\n".join(summary_parts)
    
    def _format_equipment_section(self, equipment_key: str, results: List[RAGResult]) -> str:
        """Formatea sección para un equipo específico"""
        
        marca, modelo = equipment_key.split('_', 1)
        
        section_parts = [f"\n## 🔧 {marca} {modelo}"]
        
        avg_similarity = sum(r.similarity for r in results) / len(results)
        best_similarity = max(r.similarity for r in results)
        
        stats = f"*{len(results)} resultados | Promedio: {avg_similarity:.1%} | Mejor: {best_similarity:.1%}*\n"
        section_parts.append(stats)
        
        for i, result in enumerate(results, 1):
            result_block = self._