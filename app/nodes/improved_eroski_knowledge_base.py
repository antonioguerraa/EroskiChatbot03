# =====================================================
# nodes/improved_eroski_knowledge_base.py - RAG Optimizado
# =====================================================
"""
Sistema RAG optimizado para el chatbot de Eroski con múltiples mejoras:
- Búsqueda híbrida (vectorial + texto)
- Re-ranking inteligente
- Cache de consultas
- Pool de conexiones asíncrono
- Expansión de consultas técnicas
- Contextualización de resultados
"""

import asyncio
import asyncpg
import psycopg2
import logging
import json
import re
import time
import hashlib
from typing import List, Dict, Any, Optional, Tuple, Union
from dataclasses import dataclass, asdict
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
from app.utils.technical_dictionary_generator import DynamicTechnicalQueryExpander
from urllib.parse import quote
from collections import defaultdict


from config.settings import get_settings
from langchain_openai import AzureOpenAIEmbeddings
from app.utils.llm.providers import get_vectorizer

logger = logging.getLogger(__name__)

@dataclass
class RAGResult:
    """Estructura de resultado RAG mejorada"""
    chunk_text: str
    documento_origen: str
    pagina_numero: int
    similarity: float
    palabras_clave: List[str]
    seccion: str = ""
    contexto_adicional: str = ""
    confidence: float = 0.0
    chunk_id: Optional[int] = None
    metadata: Dict[str, Any] = None
    search_method: str = "hybrid"  # vectorial, text, hybrid
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

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

class QueryCache:
    """Cache inteligente para consultas RAG"""
    
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
            
            # Verificar TTL
            if datetime.now() - timestamp < self.ttl:
                self._access_count[key] = self._access_count.get(key, 0) + 1
                return result
            else:
                # Eliminar entrada expirada
                del self._cache[key]
                if key in self._access_count:
                    del self._access_count[key]
        
        return None
    
    def set(self, query: str, result: str, **params):
        """Guarda resultado en cache"""
        key = self._make_key(query, params)
        
        # Limpieza LRU si está lleno
        if len(self._cache) >= self.max_size:
            self._evict_least_used()
        
        self._cache[key] = (result, datetime.now())
        self._access_count[key] = 1
    
    def _evict_least_used(self):
        """Elimina elementos menos usados"""
        # Ordenar por uso y eliminar el 20% menos usado
        sorted_keys = sorted(
            self._access_count.items(), 
            key=lambda x: x[1]
        )
        
        evict_count = max(1, len(sorted_keys) // 5)
        for key, _ in sorted_keys[:evict_count]:
            if key in self._cache:
                del self._cache[key]
            del self._access_count[key]

class EnhancedTechnicalQueryExpander(DynamicTechnicalQueryExpander):
    """
    Expansor mejorado que combina diccionario dinámico con aprendizaje en tiempo real
    """
    
    def __init__(self):
        super().__init__()
        self.learned_patterns = {}
        self.feedback_cache = {}
    
    async def expand_query_with_learning(self, query: str, user_context: Dict = None) -> List[str]:
        """
        Expansión de consulta con aprendizaje de patrones de uso
        """
        # 1. Expansión base usando diccionario dinámico
        base_expansions = await self.expand_query(query)
        
        # 2. Aprendizaje de patrones específicos del usuario/contexto
        learned_expansions = await self._apply_learned_patterns(query, user_context)
        
        # 3. Combinar expansiones
        all_expansions = base_expansions + learned_expansions
        
        # 4. Eliminar duplicados manteniendo orden
        unique_expansions = list(dict.fromkeys(all_expansions))
        
        return unique_expansions[:6]  # Máximo 6 consultas
    
    async def _apply_learned_patterns(self, query: str, user_context: Dict = None) -> List[str]:
        """Aplica patrones aprendidos de uso exitoso"""
        
        learned_expansions = []
        
        # Buscar patrones similares exitosos
        similar_patterns = await self._find_similar_successful_patterns(query)
        
        for pattern in similar_patterns:
            if pattern['success_rate'] > 0.7:  # Solo patrones exitosos
                learned_expansions.append(pattern['expansion'])
        
        return learned_expansions[:2]  # Máximo 2 expansiones aprendidas
    
    async def _find_similar_successful_patterns(self, query: str) -> List[Dict]:
        """Encuentra patrones similares que han tenido éxito"""
        
        # Implementación simplificada - en producción usaría embeddings
        similar_patterns = []
        
        query_words = set(query.lower().split())
        
        for learned_query, pattern_data in self.learned_patterns.items():
            learned_words = set(learned_query.lower().split())
            
            # Calcular similitud por palabras comunes
            overlap = len(query_words.intersection(learned_words))
            if overlap >= 2:  # Al menos 2 palabras en común
                similar_patterns.append(pattern_data)
        
        return sorted(similar_patterns, key=lambda x: x['success_rate'], reverse=True)
    
    async def learn_from_feedback(self, original_query: str, expanded_queries: List[str], 
                                  success: bool, user_satisfaction: float):
        """
        Aprende de feedback de usuario para mejorar expansiones futuras
        """
        
        if success and user_satisfaction > 0.7:
            # Guardar patrón exitoso
            best_expansion = expanded_queries[0] if expanded_queries else original_query
            
            pattern_key = original_query.lower().strip()
            
            if pattern_key in self.learned_patterns:
                # Actualizar patrón existente
                pattern = self.learned_patterns[pattern_key]
                pattern['usage_count'] += 1
                pattern['total_satisfaction'] += user_satisfaction
                pattern['success_rate'] = pattern['total_satisfaction'] / pattern['usage_count']
            else:
                # Nuevo patrón
                self.learned_patterns[pattern_key] = {
                    'expansion': best_expansion,
                    'usage_count': 1,
                    'total_satisfaction': user_satisfaction,
                    'success_rate': user_satisfaction,
                    'last_used': datetime.now()
                }
        
        # Limpiar patrones antiguos ocasionalmente
        if len(self.learned_patterns) > 1000:
            await self._cleanup_old_patterns()
    
    async def _cleanup_old_patterns(self):
        """Limpia patrones antiguos o poco exitosos"""
        
        current_time = datetime.now()
        
        # Mantener solo patrones recientes y exitosos
        filtered_patterns = {}
        
        for key, pattern in self.learned_patterns.items():
            days_old = (current_time - pattern['last_used']).days
            
            # Mantener si es reciente O muy exitoso
            if days_old < 30 or pattern['success_rate'] > 0.8:
                filtered_patterns[key] = pattern
        
        self.learned_patterns = filtered_patterns

class TechnicalQueryExpander:
    """Expansor de consultas técnicas específico para Eroski"""
    
    def __init__(self):
        # Diccionario de expansiones técnicas actualizado
        self.technical_terms = {
            # Equipos principales
            'balanza': ['balanza', 'peso', 'pesar', 'pesaje', 'dibal', 'mistral', 'bascula'],
            'tpv': ['tpv', 'caja', 'registradora', 'terminal', 'punto de venta'],
            'impresora': ['impresora', 'imprimir', 'impresion', 'ticket', 'factura'],
            'escaner': ['escaner', 'lector', 'codigo de barras', 'scanner'],
            
            # Problemas comunes
            'no funciona': ['error', 'fallo', 'problema', 'averia', 'dañado', 'roto'],
            'no imprime': ['no imprime', 'no sale', 'sin papel', 'atasco', 'bloqueado'],
            'no enciende': ['no enciende', 'apagado', 'sin corriente', 'no alimentacion'],
            'pantalla negra': ['pantalla negra', 'sin imagen', 'display apagado', 'monitor'],
            
            # Componentes
            'etiqueta': ['etiqueta', 'ticket', 'papel', 'rollo', 'bobina'],
            'teclado': ['teclado', 'teclas', 'botones', 'input', 'digitacion'],
            'pantalla': ['pantalla', 'display', 'monitor', 'visor', 'led'],
            'cable': ['cable', 'conexion', 'conector', 'alimentacion'],
            
            # Acciones técnicas
            'calibrar': ['calibrar', 'ajustar', 'configurar', 'parametros'],
            'reiniciar': ['reiniciar', 'resetear', 'apagar', 'encender'],
            'limpiar': ['limpiar', 'mantenimiento', 'limpieza', 'suciedad'],
            
            # Estados y condiciones
            'lento': ['lento', 'demora', 'tardanza', 'velocidad'],
            'ruidoso': ['ruidoso', 'ruido', 'sonido', 'vibracion'],
            'caliente': ['caliente', 'temperatura', 'sobrecalentamiento'],
        }
        
        # Patrones de consulta comunes
        self.query_patterns = {
            r'no (.*?)': 'problema con {}',
            r'(.*?) no funciona': 'error en {}',
            r'como (.*?)': 'procedimiento para {}',
            r'donde (.*?)': 'ubicacion de {}',
        }
    
    def expand_query(self, query: str) -> List[str]:
        """
        Expande una consulta con sinónimos técnicos
        
        Args:
            query: Consulta original
            
        Returns:
            Lista de consultas expandidas
        """
        queries = [query.strip()]
        query_lower = query.lower().strip()
        
        # 1. Normalización básica
        normalized = re.sub(r'[^\w\s]', ' ', query_lower)
        normalized = ' '.join(normalized.split())
        if normalized != query_lower:
            queries.append(normalized)
        
        # 2. Expansión por términos técnicos
        expanded_terms = set()
        for term, synonyms in self.technical_terms.items():
            if term in query_lower:
                expanded_terms.update(synonyms)
        
        if expanded_terms:
            # Crear consulta expandida con términos adicionales
            expanded_query = f"{normalized} {' '.join(expanded_terms)}"
            queries.append(expanded_query)
        
        # 3. Patrones de consulta específicos
        for pattern, replacement in self.query_patterns.items():
            match = re.search(pattern, query_lower)
            if match:
                extracted = match.group(1) if match.groups() else ""
                pattern_query = replacement.format(extracted)
                queries.append(pattern_query)
        
        # 4. Consultas específicas por contexto
        context_queries = self._generate_context_queries(query_lower)
        queries.extend(context_queries)
        
        # Eliminar duplicados manteniendo orden
        unique_queries = []
        seen = set()
        for q in queries:
            if q not in seen and len(q.strip()) > 2:
                unique_queries.append(q)
                seen.add(q)
        
        return unique_queries[:5]  # Máximo 5 consultas
    
    def _generate_context_queries(self, query: str) -> List[str]:
        """Genera consultas específicas por contexto"""
        context_queries = []
        
        # Si es sobre balanza, agregar consultas específicas
        if any(term in query for term in ['balanza', 'peso', 'pesar']):
            context_queries.extend([
                'calibracion balanza dibal',
                'mantenimiento balanza',
                'etiquetas balanza problema'
            ])
        
        # Si es sobre impresión
        if any(term in query for term in ['imprime', 'etiqueta', 'ticket']):
            context_queries.extend([
                'papel impresora problema',
                'configuracion impresion',
                'cambiar rollo papel'
            ])
        
        # Si es sobre errores
        if any(term in query for term in ['error', 'problema', 'fallo']):
            context_queries.extend([
                'solucion errores comunes',
                'diagnostico problemas',
                'reiniciar equipo'
            ])
        
        return context_queries

class HybridRAGSearcher:
    """Motor de búsqueda RAG híbrido optimizado"""
    
    def __init__(self, settings, vectorizer):
        self.settings = settings
        self.vectorizer = vectorizer
        self.query_expander = TechnicalQueryExpander()
        self.cache = QueryCache(max_size=200, ttl_minutes=60)
        self.metrics: List[SearchMetrics] = []
        
        # Configuración de búsqueda
        self.min_similarity_threshold = 0.40  # PARCHEADO  # Más permisivo
        self.vector_weight = 0.6
        self.text_weight = 0.4
        self.max_results_per_method = 8
        
        # Pool de conexiones
        self._connection_pool = None
    
    async def _get_connection_pool(self):
        """Obtiene pool de conexiones asíncrono"""
        if self._connection_pool is None:
            try:
                # Use connection string for Supabase compatibility
                connection_string = self.settings.database.connection_string
                
                if 'supabase.co' in connection_string or 'pooler.supabase.com' in connection_string:
                    # Supabase pooler connection
                    self._connection_pool = await asyncpg.create_pool(
                        connection_string,
                        min_size=3,
                        max_size=15,
                        command_timeout=45,
                        statement_cache_size=0,  # Disable for pooler compatibility
                        server_settings={
                            'application_name': 'eroski_rag_searcher',
                            'statement_timeout': '30s',
                            'jit': 'off'
                        }
                    )
                    logger.info("✅ Pool de conexiones RAG creado (Supabase)")
                else:
                    # Local connection
                    self._connection_pool = await asyncpg.create_pool(
                        host=self.settings.database.host,
                        database=self.settings.database.name,
                        user=self.settings.database.user,
                        password=self.settings.database.password or "",
                        port=self.settings.database.port,
                        min_size=3,
                        max_size=15,
                        command_timeout=45,
                        server_settings={
                            'application_name': 'eroski_rag_searcher',
                            'statement_timeout': '30s'
                        }
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
        search_methods: List[str] = ["vector", "text"]
    ) -> Tuple[List[RAGResult], SearchMetrics]:
        """
        Búsqueda híbrida principal
        
        Args:
            query: Consulta del usuario
            top_k: Número de resultados finales
            include_context: Si incluir contexto de chunks adyacentes
            filter_by_document: Filtro por documento específico
            search_methods: Métodos a usar ["vector", "text", "keyword"]
            
        Returns:
            Tupla con resultados y métricas
        """
        start_time = time.time()
        
        # Parámetros para cache
        cache_params = {
            'top_k': top_k,
            'include_context': include_context,
            'filter_by_document': filter_by_document,
            'search_methods': sorted(search_methods)
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
                timestamp=datetime.now()
            )
            return json.loads(cached_result), metrics
        
        try:
            pool = await self._get_connection_pool()
            
            async with pool.acquire() as conn:
                # 1. Expandir consulta
                expanded_queries = self.query_expander.expand_query(query)
                logger.info(f"🔍 Consultas expandidas: {len(expanded_queries)}")
                
                # 2. Ejecutar búsquedas paralelas
                all_results = []
                methods_used = []
                
                # Búsqueda vectorial
                if "vector" in search_methods:
                    vector_results = await self._vector_search_parallel(
                        conn, expanded_queries, self.max_results_per_method, filter_by_document
                    )
                    all_results.extend(vector_results)
                    methods_used.append("vector")
                
                # Búsqueda de texto completo
                if "text" in search_methods:
                    text_results = await self._text_search_enhanced(
                        conn, expanded_queries, self.max_results_per_method, filter_by_document
                    )
                    all_results.extend(text_results)
                    methods_used.append("text")
                
                # Búsqueda por palabras clave
                if "keyword" in search_methods:
                    keyword_results = await self._keyword_search(
                        conn, query, self.max_results_per_method, filter_by_document
                    )
                    all_results.extend(keyword_results)
                    methods_used.append("keyword")
                
                # 3. Fusionar, deduplicar y re-rankear
                unique_results = self._deduplicate_results(all_results)
                ranked_results = self._advanced_rerank(unique_results, query, expanded_queries)
                
                # 4. Seleccionar top_k resultados
                final_results = ranked_results[:top_k]
                
                # 5. Agregar contexto si se solicita
                if include_context and final_results:
                    final_results = await self._enrich_with_context(conn, final_results)
                
                # 6. Guardar en cache
                serializable_results = [asdict(r) for r in final_results]
                self.cache.set(query, json.dumps(serializable_results), **cache_params)
                
                # 7. Métricas
                execution_time = time.time() - start_time
                metrics = SearchMetrics(
                    query=query,
                    execution_time=execution_time,
                    results_count=len(final_results),
                    cache_hit=False,
                    search_methods_used=methods_used,
                    timestamp=datetime.now()
                )
                
                self.metrics.append(metrics)
                logger.info(f"✅ Búsqueda completada: {len(final_results)} resultados en {execution_time:.2f}s")
                
                return final_results, metrics
                
        except Exception as e:
            logger.error(f"❌ Error en búsqueda híbrida: {e}")
            # Fallback básico
            return await self._fallback_search(query, top_k), SearchMetrics(
                query=query,
                execution_time=time.time() - start_time,
                results_count=0,
                cache_hit=False,
                search_methods_used=["fallback"],
                timestamp=datetime.now()
            )
    
    async def _vector_search_parallel(
        self,
        conn,
        queries: List[str],
        limit: int,
        filter_doc: Optional[str] = None
    ) -> List[RAGResult]:
        """Búsqueda vectorial paralela para múltiples consultas"""
        all_vector_results = []
        
        # Ejecutar búsquedas vectoriales en paralelo
        tasks = []
        for query in queries[:3]:  # Máximo 3 consultas para evitar sobrecarga
            task = self._single_vector_search(conn, query, limit, filter_doc)
            tasks.append(task)
        
        results_lists = await asyncio.gather(*tasks, return_exceptions=True)
        
        for results in results_lists:
            if isinstance(results, list):
                all_vector_results.extend(results)
        
        return all_vector_results
    
    async def _single_vector_search(
        self,
        conn,
        query: str,
        limit: int,
        filter_doc: Optional[str] = None
    ) -> List[RAGResult]:
        """Búsqueda vectorial individual optimizada"""
        try:
            # Generar embedding
            query_embedding = await self.vectorizer.aembed(query)
            query_vector = str(query_embedding)
            
            # SQL optimizada con índices
            base_sql = """
            SELECT 
                id,
                chunk_text,
                documento_origen,
                pagina_numero,
                palabras_clave,
                COALESCE(seccion, '') as seccion,
                chunk_metadata,
                1 - (chunk_embedding <=> $1::vector) as similarity
            FROM knowledge_base
            WHERE chunk_embedding IS NOT NULL
            """
            
            params = [query_vector]
            param_count = 1
            
            # Filtros
            if filter_doc:
                param_count += 1
                base_sql += f" AND documento_origen ILIKE ${param_count}"
                params.append(f"%{filter_doc}%")
            
            # Umbral de similitud
            param_count += 1
            base_sql += f" AND 1 - (chunk_embedding <=> $1::vector) > ${param_count}"
            params.append(self.min_similarity_threshold)
            
            # Ordenar y limitar
            param_count += 1
            base_sql += f" ORDER BY chunk_embedding <=> $1::vector LIMIT ${param_count}"
            params.append(limit)
            
            results = await conn.fetch(base_sql, *params)
            
            return [
                RAGResult(
                    chunk_id=result['id'],
                    chunk_text=result['chunk_text'],
                    documento_origen=result['documento_origen'],
                    pagina_numero=result['pagina_numero'],
                    similarity=float(result['similarity']),
                    palabras_clave=result['palabras_clave'] or [],
                    seccion=result['seccion'],
                    metadata=result['chunk_metadata'] or {},
                    search_method="vector"
                )
                for result in results
            ]
            
        except Exception as e:
            logger.error(f"Error en búsqueda vectorial individual: {e}")
            return []
    
    async def _text_search_enhanced(
        self,
        conn,
        queries: List[str],
        limit: int,
        filter_doc: Optional[str] = None
    ) -> List[RAGResult]:
        """Búsqueda de texto completo mejorada"""
        all_text_results = []
        
        for query in queries[:2]:  # Máximo 2 consultas de texto
            try:
                # Preparar consulta para diferentes idiomas
                search_configs = ['spanish', 'simple']
                
                for config in search_configs:
                    base_sql = f"""
                    SELECT 
                        id,
                        chunk_text,
                        documento_origen,
                        pagina_numero,
                        palabras_clave,
                        COALESCE(seccion, '') as seccion,
                        chunk_metadata,
                        ts_rank_cd(
                            to_tsvector('{config}', chunk_text),
                            websearch_to_tsquery('{config}', $1)
                        ) as similarity
                    FROM knowledge_base
                    WHERE to_tsvector('{config}', chunk_text) @@ websearch_to_tsquery('{config}', $1)
                    """
                    
                    params = [query]
                    param_count = 1
                    
                    if filter_doc:
                        param_count += 1
                        base_sql += f" AND documento_origen ILIKE ${param_count}"
                        params.append(f"%{filter_doc}%")
                    
                    param_count += 1
                    base_sql += f" ORDER BY similarity DESC LIMIT ${param_count}"
                    params.append(limit // 2)  # Dividir límite entre configuraciones
                    
                    results = await conn.fetch(base_sql, *params)
                    
                    for result in results:
                        all_text_results.append(
                            RAGResult(
                                chunk_id=result['id'],
                                chunk_text=result['chunk_text'],
                                documento_origen=result['documento_origen'],
                                pagina_numero=result['pagina_numero'],
                                similarity=float(result['similarity']),
                                palabras_clave=result['palabras_clave'] or [],
                                seccion=result['seccion'],
                                metadata=result['chunk_metadata'] or {},
                                search_method="text"
                            )
                        )
                        
            except Exception as e:
                logger.warning(f"Error en búsqueda de texto: {e}")
                continue
        
        return all_text_results
    
    async def _keyword_search(
        self,
        conn,
        query: str,
        limit: int,
        filter_doc: Optional[str] = None
    ) -> List[RAGResult]:
        """Búsqueda por palabras clave usando arrays"""
        try:
            # Extraer palabras clave de la consulta
            keywords = [word.strip().lower() for word in re.findall(r'\b\w+\b', query) if len(word) > 2]
            
            if not keywords:
                return []
            
            base_sql = """
            SELECT 
                id,
                chunk_text,
                documento_origen,
                pagina_numero,
                palabras_clave,
                COALESCE(seccion, '') as seccion,
                chunk_metadata,
                COALESCE(array_length(palabras_clave & $1, 1), 0) as keyword_matches
            FROM knowledge_base
            WHERE palabras_clave && $1
            """
            
            params = [keywords]
            param_count = 1
            
            if filter_doc:
                param_count += 1
                base_sql += f" AND documento_origen ILIKE ${param_count}"
                params.append(f"%{filter_doc}%")
            
            param_count += 1
            base_sql += f" ORDER BY keyword_matches DESC, pagina_numero LIMIT ${param_count}"
            params.append(limit)
            
            results = await conn.fetch(base_sql, *params)
            
            return [
                RAGResult(
                    chunk_id=result['id'],
                    chunk_text=result['chunk_text'],
                    documento_origen=result['documento_origen'],
                    pagina_numero=result['pagina_numero'],
                    similarity=float(result['keyword_matches']) / len(keywords),
                    palabras_clave=result['palabras_clave'] or [],
                    seccion=result['seccion'],
                    metadata=result['chunk_metadata'] or {},
                    search_method="keyword"
                )
                for result in results
            ]
            
        except Exception as e:
            logger.error(f"Error en búsqueda por palabras clave: {e}")
            return []
    
    def _deduplicate_results(self, results: List[RAGResult]) -> List[RAGResult]:
        """Elimina duplicados inteligentemente"""
        if not results:
            return []
        
        unique_results = []
        seen_ids = set()
        seen_content_hashes = set()
        
        for result in results:
            # Deduplicar por ID si existe
            if result.chunk_id and result.chunk_id in seen_ids:
                continue
            
            # Deduplicar por contenido similar
            content_hash = hashlib.md5(
                result.chunk_text[:200].encode()
            ).hexdigest()
            
            if content_hash in seen_content_hashes:
                continue
            
            # Agregar a únicos
            unique_results.append(result)
            if result.chunk_id:
                seen_ids.add(result.chunk_id)
            seen_content_hashes.add(content_hash)
        
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
            base_similarity = result.similarity if result.similarity else 0.0
            score += base_similarity * 0.3
            
            # Factor 2: Coincidencias exactas con consulta original (25%)
            if query_terms:
                exact_matches = len(query_terms.intersection(text_terms))
                exact_ratio = exact_matches / len(query_terms)
                score += exact_ratio * 0.25
            
            # Factor 3: Coincidencias con consultas expandidas (15%)
            if all_query_terms:
                expanded_matches = len(all_query_terms.intersection(text_terms))
                expanded_ratio = expanded_matches / len(all_query_terms)
                score += expanded_ratio * 0.15
            
            # Factor 4: Palabras clave relevantes (15%)
            if result.palabras_clave:
                keyword_set = set(kw.lower() for kw in result.palabras_clave)
                keyword_matches = len(query_terms.intersection(keyword_set))
                if query_terms:
                    keyword_ratio = keyword_matches / len(query_terms)
                    score += keyword_ratio * 0.15
            
            # Factor 5: Longitud óptima del chunk (10%)
            text_length = len(result.chunk_text)
            if 200 <= text_length <= 800:
                score += 0.1
            elif 100 <= text_length < 200 or 800 < text_length <= 1200:
                score += 0.05
            
            # Factor 6: Bonus por método de búsqueda (5%)
            method_bonus = {
                'vector': 0.05,
                'text': 0.03,
                'keyword': 0.02,
                'hybrid': 0.05
            }
            score += method_bonus.get(result.search_method, 0.0)
            
            # Factor 7: Bonus por sección específica
            if result.seccion:
                useful_sections = ['procedimiento', 'solucion', 'error', 'problema', 'mantenim']
                if any(section in result.seccion.lower() for section in useful_sections):
                    score += 0.03
            
            result.confidence = min(score, 1.0)
        
        # Ordenar por confidence score
        return sorted(results, key=lambda x: x.confidence, reverse=True)
    
    async def _enrich_with_context(
        self,
        conn,
        results: List[RAGResult]
    ) -> List[RAGResult]:
        """Enriquece resultados con contexto de chunks adyacentes"""
        enriched_results = []
        
        for result in results:
            try:
                # Buscar contexto de chunks adyacentes
                context_sql = """
                SELECT chunk_text, pagina_numero, seccion
                FROM knowledge_base
                WHERE documento_origen = $1 
                AND pagina_numero BETWEEN $2 AND $3
                AND id != $4
                ORDER BY pagina_numero, id
                LIMIT 3
                """
                
                context_chunks = await conn.fetch(
                    context_sql,
                    result.documento_origen,
                    max(1, result.pagina_numero - 1),
                    result.pagina_numero + 1,
                    result.chunk_id or 0
                )
                
                if context_chunks:
                    context_parts = []
                    for chunk in context_chunks:
                        preview = chunk['chunk_text'][:150]
                        if chunk['seccion']:
                            preview = f"[{chunk['seccion']}] {preview}"
                        context_parts.append(preview + "...")
                    
                    result.contexto_adicional = "\n".join(context_parts)
                
                enriched_results.append(result)
                
            except Exception as e:
                logger.warning(f"Error enriqueciendo contexto: {e}")
                enriched_results.append(result)
        
        return enriched_results
    
    async def _fallback_search(self, query: str, top_k: int) -> List[RAGResult]:
        """Búsqueda de fallback básica"""
        try:
            # Buscar términos clave básicos
            basic_terms = re.findall(r'\b\w{4,}\b', query.lower())
            if not basic_terms:
                return []
            
            pool = await self._get_connection_pool()
            async with pool.acquire() as conn:
                # Búsqueda simple por LIKE
                sql = """
                SELECT chunk_text, documento_origen, pagina_numero, 
                       palabras_clave, COALESCE(seccion, '') as seccion
                FROM knowledge_base
                WHERE """ + " OR ".join([f"chunk_text ILIKE '%{term}%'" for term in basic_terms[:3]]) + f"""
                ORDER BY pagina_numero
                LIMIT {top_k}
                """
                
                results = await conn.fetch(sql)
                
                return [
                    RAGResult(
                        chunk_text=result['chunk_text'],
                        documento_origen=result['documento_origen'],
                        pagina_numero=result['pagina_numero'],
                        similarity=0.5,
                        palabras_clave=result['palabras_clave'] or [],
                        seccion=result['seccion'],
                        search_method="fallback"
                    )
                    for result in results
                ]
                
        except Exception as e:
            logger.error(f"Error en fallback: {e}")
            return []
    
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
            logger.info("✅ Pool de conexiones RAG cerrado")

class OptimizedEroskiKnowledgeBase:
    """
    Clase principal optimizada que mantiene compatibilidad con la interfaz original
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.vectorizer = get_async_vectorizer()
        self.searcher = HybridRAGSearcher(self.settings, self.vectorizer)
        
        # Configuración de resultados
        self.default_top_k = 3
        self.include_analytics = True
        
    def buscar_solucion_rag(self, query: str, top_k: int = 3) -> str:
        """
        Método principal compatible con la interfaz original
        
        Args:
            query: Consulta del usuario
            top_k: Número de resultados
            
        Returns:
            Texto formateado con las mejores soluciones
        """
        try:
            # Detectar si estamos en contexto asíncrono
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Si hay loop ejecutándose, crear tarea
                task = asyncio.create_task(self._async_search(query, top_k))
                return asyncio.run_coroutine_threadsafe(task, loop).result(timeout=30)
            else:
                # Crear nuevo loop
                return asyncio.run(self._async_search(query, top_k))
                
        except Exception as e:
            logger.error(f"Error en búsqueda optimizada: {e}")
            return self._fallback_sync_search(query, top_k)
    
    async def _async_search(self, query: str, top_k: int) -> str:
        """Búsqueda asíncrona interna"""
        try:
            results, metrics = await self.searcher.search(
                query=query,
                top_k=top_k,
                include_context=True,
                search_methods=["vector", "text", "keyword"]
            )
            
            if not results:
                return self._get_no_results_message(query)
            
            # Formatear resultados
            formatted_result = self._format_results(results, metrics)
            
            # Log de métricas si está habilitado
            if self.include_analytics:
                analytics = self.searcher.get_search_analytics()
                logger.info(f"📊 Métricas RAG: {analytics}")
            
            return formatted_result
            
        except Exception as e:
            logger.error(f"Error en búsqueda async: {e}")
            return self._get_error_message(query, str(e))
    
    def _format_results(self, results: List[RAGResult], metrics: SearchMetrics) -> str:
        """Formatea resultados en texto legible"""
        if not results:
            return "No se encontraron soluciones relevantes."
        
        formatted_parts = []
        
        # Header con información de la búsqueda
        header = f"🔍 **Resultados de búsqueda** ({len(results)} soluciones encontradas)\n"
        header += f"*Tiempo de búsqueda: {metrics.execution_time:.2f}s | Métodos: {', '.join(metrics.search_methods_used)}*\n\n"
        formatted_parts.append(header)
        
        # Formatear cada resultado
        for i, result in enumerate(results, 1):
            solution_block = []
            
            # Título del resultado
            title = f"**💡 Solución {i}**"
            if result.confidence > 0.8:
                title += " ⭐ *Alta relevancia*"
            elif result.confidence > 0.6:
                title += " ✅ *Relevante*"
            
            solution_block.append(title)
            
            # Metadatos
            meta_info = f"📋 *{result.documento_origen}"
            if result.pagina_numero:
                meta_info += f", Página {result.pagina_numero}"
            if result.seccion:
                meta_info += f", {result.seccion}"
            meta_info += f" | Confianza: {result.confidence:.2f}*"
            solution_block.append(meta_info)
            
            # Contenido principal
            solution_block.append("")  # Línea en blanco
            solution_block.append(result.chunk_text.strip())
            
            # Contexto adicional si está disponible
            if result.contexto_adicional:
                solution_block.append("")
                solution_block.append("**📖 Contexto relacionado:**")
                solution_block.append(result.contexto_adicional)
            
            # Palabras clave
            if result.palabras_clave:
                keywords = ", ".join(result.palabras_clave[:5])
                solution_block.append("")
                solution_block.append(f"*🏷️ Palabras clave: {keywords}*")
            
            # Separador
            solution_block.append("")
            solution_block.append("---")
            solution_block.append("")
            
            formatted_parts.append("\n".join(solution_block))
        
        return "".join(formatted_parts)
    
    def _fallback_sync_search(self, query: str, top_k: int) -> str:
        """Búsqueda de fallback síncrona básica"""
        try:
            # Implementación básica síncrona
            conn_params = {
                "host": self.settings.database.host,
                "database": self.settings.database.name,
                "user": self.settings.database.user,
                "port": self.settings.database.port
            }
            
            if self.settings.database.password:
                conn_params["password"] = self.settings.database.password
            
            conn = psycopg2.connect(**conn_params)
            
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                # Búsqueda simple por texto
                sql = """
                SELECT chunk_text, documento_origen, pagina_numero, palabras_clave
                FROM knowledge_base
                WHERE chunk_text ILIKE %s
                ORDER BY pagina_numero
                LIMIT %s
                """
                
                cursor.execute(sql, (f"%{query}%", top_k))
                results = cursor.fetchall()
                
                if not results:
                    return self._get_no_results_message(query)
                
                # Formatear resultados básicos
                formatted_results = []
                for i, result in enumerate(results, 1):
                    formatted_results.append(f"""
**Solución {i}** ({result['documento_origen']}, Página {result['pagina_numero']})

{result['chunk_text']}

*Palabras clave: {', '.join(result['palabras_clave'][:3]) if result['palabras_clave'] else 'N/A'}*

---
""")
                
                return "\n".join(formatted_results)
            
        except Exception as e:
            logger.error(f"Error en fallback síncrono: {e}")
            return self._get_error_message(query, str(e))
        finally:
            if 'conn' in locals():
                conn.close()
    
    def _get_no_results_message(self, query: str) -> str:
        """Mensaje cuando no hay resultados"""
        return f"""
🔍 **No se encontraron soluciones específicas para:** "{query}"

**💡 Sugerencias para mejorar la búsqueda:**
• Usa términos más específicos (ej: "balanza no imprime etiquetas" en lugar de "problema balanza")
• Incluye el modelo del equipo si lo conoces (ej: "DIBAL Mistral")
• Describe síntomas específicos (ej: "pantalla negra", "error en display")

**🔧 Pasos básicos de diagnóstico:**
1. Verifica que el equipo esté encendido y conectado
2. Revisa las conexiones de cables
3. Consulta si hay mensajes de error en pantalla
4. Intenta reiniciar el equipo

**🆘 ¿Necesitas ayuda adicional?**
Proporciona más detalles sobre:
- Tipo de equipo específico
- Síntomas exactos que observas
- Cuándo comenzó el problema
- Qué estabas haciendo cuando ocurrió

¡Estoy aquí para ayudarte a encontrar la solución! 🤖
"""
    
    def _get_error_message(self, query: str, error: str) -> str:
        """Mensaje de error amigable"""
        return f"""
⚠️ **Hubo un problema técnico al buscar soluciones**

**Tu consulta:** "{query}"
**Error técnico:** {error}

**🔄 Mientras tanto, puedes intentar:**
1. Reformular tu consulta con términos diferentes
2. Ser más específico sobre el problema
3. Contactar directamente al técnico de mantenimiento

**🔧 Para problemas urgentes:**
- Reinicia el equipo y prueba nuevamente
- Verifica conexiones básicas
- Consulta el manual físico del equipo

Disculpa las molestias. El sistema se está recuperando automáticamente.
"""
    
    async def get_analytics(self) -> Dict[str, Any]:
        """Obtiene analíticas del sistema RAG"""
        return self.searcher.get_search_analytics()
    
    async def close(self):
        """Cierra recursos del sistema"""
        await self.searcher.close()
    
    def __del__(self):
        """Limpieza automática"""
        loop = asyncio.get_event_loop()
        if not loop.is_closed():
            loop.create_task(self.close())

class RAGFeedbackSystem:
    """Sistema de feedback para aprendizaje continuo"""
    
    def __init__(self):
        self.settings = get_settings()
    
    async def record_feedback(self, query: str, response: str, satisfied: bool, 
                            satisfaction_score: float):
        """Registra feedback del usuario en la base de datos"""
        
        conn = await asyncpg.connect(self._build_connection_string(), statement_cache_size=0)
        
        try:
            await conn.execute("""
                INSERT INTO rag_user_feedback 
                (query, response_preview, user_satisfied, satisfaction_score, created_at)
                VALUES ($1, $2, $3, $4, NOW())
            """, 
            query,
            response[:500],  # Solo preview de la respuesta
            satisfied,
            satisfaction_score
            )
            
        except Exception as e:
            logger.error(f"Error guardando feedback: {e}")
        finally:
            try:
                await asyncio.wait_for(conn.close(), timeout=2.0)
            except (asyncio.TimeoutError, Exception):
                pass  # Ignore close errors
    
    def _build_connection_string(self) -> str:
        """Construye string de conexión"""
        conn_params = {
            'host': self.settings.database.host,
            'port': self.settings.database.port,
            'database': self.settings.database.name,
            'user': self.settings.database.user,
        }
        
        if self.settings.database.password:
            conn_params['password'] = self.settings.database.password
        
        return f"postgresql://{conn_params['user']}{':%s' % conn_params.get('password', '') if conn_params.get('password') else ''}@{conn_params['host']}:{conn_params['port']}/{conn_params['database']}"

class OptimizedEroskiKnowledgeBaseWithDynamicDict(OptimizedEroskiKnowledgeBase):
    """
    Versión del RAG que usa diccionario técnico dinámico
    """
    
    def __init__(self):
        super().__init__()
        # Reemplazar expansor estático por dinámico
        if hasattr(self.searcher, 'query_expander'):
            self.searcher.query_expander = EnhancedTechnicalQueryExpander()
        
        # Sistema de feedback para aprendizaje
        self.feedback_system = RAGFeedbackSystem()
    
    async def buscar_solucion_rag_with_learning(
        self, 
        query: str, 
        top_k: int = 3,
        user_context: Dict = None
    ) -> Tuple[str, Dict]:
        """
        Búsqueda RAG con aprendizaje automático
        """
        
        try:
            # Expandir consulta con aprendizaje
            if hasattr(self.searcher.query_expander, 'expand_query_with_learning'):
                expanded_queries = await self.searcher.query_expander.expand_query_with_learning(
                    query, user_context
                )
            else:
                expanded_queries = self.searcher.query_expander.expand_query(query)
            
            # Búsqueda híbrida normal
            results, metrics = await self.searcher.search(
                query=query,
                top_k=top_k,
                include_context=True,
                search_methods=["vector", "text", "keyword"]
            )
            
            # Formatear respuesta
            formatted_response = self._format_results(results, metrics)
            
            # Métricas extendidas
            extended_metrics = {
                **metrics.__dict__,
                'expanded_queries': expanded_queries,
                'dictionary_terms_used': await self._get_dictionary_terms_used(query),
                'learning_patterns_applied': getattr(self.searcher.query_expander, 'learned_patterns', {})
            }
            
            return formatted_response, extended_metrics
            
        except Exception as e:
            logger.error(f"Error en búsqueda con aprendizaje: {e}")
            # Fallback a método original
            return self.buscar_solucion_rag(query, top_k), {}
    
    async def _get_dictionary_terms_used(self, query: str) -> List[str]:
        """Obtiene términos del diccionario técnico que se usaron en la expansión"""
        
        if not hasattr(self.searcher.query_expander, 'dictionary_cache'):
            return []
        
        query_words = query.lower().split()
        used_terms = []
        
        for word in query_words:
            if word in self.searcher.query_expander.dictionary_cache:
                used_terms.append(word)
        
        return used_terms
    
    async def provide_feedback(self, query: str, response: str, user_satisfied: bool, 
                             satisfaction_score: float = None):
        """
        Permite al usuario proporcionar feedback para mejorar el sistema
        """
        
        # Registrar feedback
        await self.feedback_system.record_feedback(
            query=query,
            response=response,
            satisfied=user_satisfied,
            satisfaction_score=satisfaction_score or (1.0 if user_satisfied else 0.0)
        )
        
        # Aprender de feedback
        if hasattr(self.searcher.query_expander, 'learn_from_feedback'):
            await self.searcher.query_expander.learn_from_feedback(
                original_query=query,
                expanded_queries=[],  # Se obtendría del contexto
                success=user_satisfied,
                user_satisfaction=satisfaction_score or (1.0 if user_satisfied else 0.0)
            )

# =====================================================
# Enhanced RAG Search with Metadata and PDF Links
# =====================================================
"""
Extensión del RAG optimizado para usar embeddings con metadatos
y generar enlaces directos a documentos fuente
"""



logger = logging.getLogger(__name__)

@dataclass
class MetadataSearchResult:
    """Resultado de búsqueda enriquecido con metadatos y enlaces"""
    chunk_id: str
    chunk_text: str
    similarity: float
    confidence: float
    
    # Metadatos del documento
    documento_origen: str
    tipo_equipo: str
    marca: str
    modelo: str
    version_manual: str
    
    # Metadatos del chunk
    pagina_numero: int
    seccion_titulo: str
    tipo_contenido: str
    nivel_jerarquia: int
    
    # Posición y enlaces
    posicion_en_pagina: Dict[str, float]
    pdf_link: str
    web_viewer_link: str
    
    # Análisis
    palabras_clave: List[str]
    entidades_tecnicas: List[str]
    
    # Contexto
    chunk_anterior_id: Optional[str] = None
    chunk_siguiente_id: Optional[str] = None
    contexto_adicional: str = ""

# =====================================================
# GENERADOR DE ENLACES A DOCUMENTOS
# =====================================================

# Async vectorizer wrapper for improved_eroski_knowledge_base.py
from typing import List
from langchain_openai import AzureOpenAIEmbeddings
import os
from config.settings import get_settings

class AsyncEmbeddingVectorizer:
    """Async wrapper for embeddings generation"""
    
    def __init__(self):
        settings = get_settings()
        self.embeddings = AzureOpenAIEmbeddings(
            azure_endpoint=settings.llm.azure_openai_endpoint,
            api_key=settings.llm.azure_openai_api_key,
            azure_deployment=os.getenv('LLM_AZURE_EMBEDDING_DEPLOYMENT', 'text-embedding-ada-002'),
            api_version=settings.llm.azure_api_version
        )
    
    async def aembed(self, text: str) -> List[float]:
        """Generate embedding asynchronously"""
        result = await self.embeddings.aembed_query(text)
        # Ensure it's a list of floats
        if isinstance(result, list):
            return result
        return list(result)
    
    def embed(self, text: str) -> List[float]:
        """Sync method for backward compatibility - runs async in sync context"""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're already in an async context, create a task
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, self.aembed(text))
                    return future.result()
            else:
                return loop.run_until_complete(self.aembed(text))
        except RuntimeError:
            # No event loop, create one
            return asyncio.run(self.aembed(text))

_async_vectorizer = None

def get_async_vectorizer():
    global _async_vectorizer
    if _async_vectorizer is None:
        _async_vectorizer = AsyncEmbeddingVectorizer()
    return _async_vectorizer


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


class MetadataEnhancedRAGSearcher:
    """
    Buscador RAG que utiliza embeddings con metadatos y genera enlaces
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.vectorizer = get_async_vectorizer()
        self.link_generator = DocumentLinkGenerator()
        self.min_similarity_threshold = 0.4  # Add missing threshold
        
    async def search_with_metadata_filters(
        self,
        query: str,
        top_k: int = 5,
        tipo_equipo: Optional[str] = None,
        marca: Optional[str] = None,
        modelo: Optional[str] = None,
        tipo_contenido: Optional[str] = None,
        use_metadata_embedding: bool = True,
        include_links: bool = True,
        include_context: bool = True
    ) -> List[MetadataSearchResult]:
        """
        Búsqueda avanzada con filtros de metadatos
        """
        
        conn = await asyncpg.connect(self._build_connection_string(), statement_cache_size=0)
        
        try:
            # 1. Generar embeddings de la consulta
            # Always use chunk_embedding for now (chunk_embedding_with_metadata may have different vectors)
            query_embedding = await self.vectorizer.aembed(query)
            embedding_column = "chunk_embedding"
            
            # Original logic commented out for reference:
            # if use_metadata_embedding:
            #     enriched_query = self._create_enriched_query(query, tipo_equipo, marca, modelo)
            #     query_embedding = await self.vectorizer.aembed(enriched_query)
            #     embedding_column = "chunk_embedding_with_metadata"
            
            # 2. Construir SQL con filtros
            base_sql = f"""
                SELECT 
                    chunk_id, chunk_text, documento_origen,
                    tipo_equipo, marca, modelo, version_manual,
                    pagina_numero, seccion_titulo, tipo_contenido, nivel_jerarquia,
                    posicion_x, posicion_y, posicion_width, posicion_height,
                    palabras_clave, entidades_tecnicas, confidence_extraccion,
                    pdf_link, web_viewer_link,
                    chunk_anterior_id, chunk_siguiente_id,
                    1 - ({embedding_column} <=> $1::vector) as similarity
                FROM knowledge_base_enhanced
                WHERE {embedding_column} IS NOT NULL
            """
            
            # 3. Agregar filtros de metadatos
            params = [str(query_embedding)]
            param_count = 1
            
            if tipo_equipo:
                param_count += 1
                base_sql += f" AND LOWER(tipo_equipo) = LOWER(${param_count})"
                params.append(tipo_equipo)
            
            if marca:
                param_count += 1
                base_sql += f" AND LOWER(marca) = LOWER(${param_count})"
                params.append(marca)
            
            if modelo:
                param_count += 1
                base_sql += f" AND LOWER(modelo) LIKE LOWER(${param_count})"
                params.append(f"%{modelo}%")
            
            if tipo_contenido:
                param_count += 1
                base_sql += f" AND tipo_contenido = ${param_count}"
                params.append(tipo_contenido)
            
            # 4. Filtros de calidad
            param_count += 1
            base_sql += f" AND confidence_extraccion >= ${param_count}"
            params.append(0.3)
            
            param_count += 1
            base_sql += f" AND 1 - ({embedding_column} <=> $1::vector) >= ${param_count}"
            params.append(0.4)  # Lowered from 0.5 for better recall
            
            # 5. Ordenar y limitar
            param_count += 1
            base_sql += f" ORDER BY {embedding_column} <=> $1::vector LIMIT ${param_count}"
            params.append(top_k * 2)  # Buscar más para luego re-rankear
            
            # 6. Ejecutar búsqueda
            results = await conn.fetch(base_sql, *params)
            
            # 7. Convertir a objetos estructurados
            search_results = []
            for result in results:
                search_result = MetadataSearchResult(
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
                    seccion_titulo=result['seccion_titulo'] or "Sin sección",
                    tipo_contenido=result['tipo_contenido'],
                    nivel_jerarquia=result['nivel_jerarquia'],
                    posicion_en_pagina={
                        "x": result['posicion_x'],
                        "y": result['posicion_y'],
                        "width": result['posicion_width'],
                        "height": result['posicion_height']
                    },
                    pdf_link=result['pdf_link'] or "",
                    web_viewer_link=result['web_viewer_link'] or "",
                    palabras_clave=result['palabras_clave'] or [],
                    entidades_tecnicas=result['entidades_tecnicas'] or [],
                    chunk_anterior_id=result['chunk_anterior_id'],
                    chunk_siguiente_id=result['chunk_siguiente_id']
                )
                search_results.append(search_result)
            
            # 8. Re-ranking contextual
            reranked_results = await self._rerank_with_context(
                search_results, query, top_k
            )
            
            # 9. Agregar contexto adicional si se solicita
            if include_context:
                reranked_results = await self._add_context_to_results(
                    conn, reranked_results
                )
            
            # 10. Regenerar enlaces si es necesario
            if include_links:
                reranked_results = self._ensure_links_generated(reranked_results)
            
            return reranked_results[:top_k]
            
        finally:
            try:
                await asyncio.wait_for(conn.close(), timeout=2.0)
            except (asyncio.TimeoutError, Exception):
                pass  # Ignore close errors
    
    def _create_enriched_query(
        self, 
        query: str, 
        tipo_equipo: Optional[str],
        marca: Optional[str], 
        modelo: Optional[str]
    ) -> str:
        """Crea consulta enriquecida con contexto de metadatos"""
        
        enriched_parts = [query]
        
        if tipo_equipo:
            enriched_parts.append(f"Equipo: {tipo_equipo}")
        
        if marca:
            enriched_parts.append(f"Marca: {marca}")
        
        if modelo:
            enriched_parts.append(f"Modelo: {modelo}")
        
        return " ".join(enriched_parts)
    
    async def _rerank_with_context(
        self,
        results: List[MetadataSearchResult],
        original_query: str,
        top_k: int
    ) -> List[MetadataSearchResult]:
        """Re-ranking considerando metadatos y contexto"""
        
        query_words = set(original_query.lower().split())
        
        for result in results:
            # Score base de similitud
            score = result.similarity * 0.4
            
            # Bonus por coincidencias de palabras clave
            if result.palabras_clave:
                keyword_matches = len(
                    set(kw.lower() for kw in result.palabras_clave).intersection(query_words)
                )
                if keyword_matches > 0:
                    score += (keyword_matches / len(query_words)) * 0.2
            
            # Bonus por entidades técnicas relevantes
            if result.entidades_tecnicas:
                entity_matches = len(
                    set(ent.lower() for ent in result.entidades_tecnicas).intersection(query_words)
                )
                if entity_matches > 0:
                    score += (entity_matches / len(query_words)) * 0.15
            
            # Bonus por tipo de contenido útil
            content_type_bonus = {
                "procedimiento": 0.15,
                "codigo_comando": 0.10,
                "advertencia": 0.05,
                "texto": 0.0
            }
            score += content_type_bonus.get(result.tipo_contenido, 0.0)
            
            # Bonus por confidence de extracción
            score += result.confidence * 0.1
            
            # Penalty por chunks muy cortos o muy largos
            text_length = len(result.chunk_text)
            if 200 <= text_length <= 1000:
                score += 0.05
            elif text_length < 100:
                score -= 0.05
            
            # Actualizar similarity con score calculado
            result.similarity = min(score, 1.0)
        
        # Ordenar por nuevo score
        return sorted(results, key=lambda x: x.similarity, reverse=True)
    
    async def _add_context_to_results(
        self,
        conn,
        results: List[MetadataSearchResult]
    ) -> List[MetadataSearchResult]:
        """Agrega contexto de chunks adyacentes"""
        
        for result in results:
            context_parts = []
            
            # Obtener chunk anterior
            if result.chunk_anterior_id:
                anterior = await conn.fetchrow("""
                    SELECT chunk_text, seccion_titulo 
                    FROM knowledge_base_enhanced 
                    WHERE chunk_id = $1
                """, result.chunk_anterior_id)
                
                if anterior:
                    context_parts.append(f"[Anterior] {anterior['chunk_text'][:150]}...")
            
            # Obtener chunk siguiente
            if result.chunk_siguiente_id:
                siguiente = await conn.fetchrow("""
                    SELECT chunk_text, seccion_titulo 
                    FROM knowledge_base_enhanced 
                    WHERE chunk_id = $1
                """, result.chunk_siguiente_id)
                
                if siguiente:
                    context_parts.append(f"[Siguiente] {siguiente['chunk_text'][:150]}...")
            
            # Obtener chunks de la misma página
            pagina_chunks = await conn.fetch("""
                SELECT chunk_text, tipo_contenido
                FROM knowledge_base_enhanced 
                WHERE documento_origen = $1 
                AND pagina_numero = $2
                AND chunk_id != $3
                AND tipo_contenido IN ('advertencia', 'codigo_comando')
                LIMIT 2
            """, result.documento_origen, result.pagina_numero, result.chunk_id)
            
            for chunk in pagina_chunks:
                context_parts.append(f"[{chunk['tipo_contenido'].title()}] {chunk['chunk_text'][:100]}...")
            
            result.contexto_adicional = "\n".join(context_parts)
        
        return results
    
    def _ensure_links_generated(
        self, 
        results: List[MetadataSearchResult]
    ) -> List[MetadataSearchResult]:
        """Asegura que todos los resultados tengan enlaces válidos"""
        
        for result in results:
            # Regenerar PDF link si no existe
            if not result.pdf_link:
                result.pdf_link = self.link_generator.generate_pdf_link(
                    result.documento_origen,
                    result.pagina_numero,
                    result.posicion_en_pagina
                )
            
            # Regenerar web viewer link si no existe
            if not result.web_viewer_link:
                result.web_viewer_link = self.link_generator.generate_web_viewer_link(
                    result.documento_origen,
                    result.chunk_id,
                    result.pagina_numero,
                    result.posicion_en_pagina
                )
        
        return results
    
    async def search_by_equipment_specific(
        self,
        query: str,
        tipo_equipo: str,
        marca: Optional[str] = None,
        top_k: int = 3
    ) -> List[MetadataSearchResult]:
        """Búsqueda específica por tipo de equipo"""
        
        return await self.search_with_metadata_filters(
            query=query,
            top_k=top_k,
            tipo_equipo=tipo_equipo,
            marca=marca,
            use_metadata_embedding=True,
            include_links=True,
            include_context=True
        )
    
    async def search_by_document_section(
        self,
        query: str,
        documento: str,
        seccion: Optional[str] = None,
        top_k: int = 3
    ) -> List[MetadataSearchResult]:
        """Búsqueda dentro de un documento o sección específica"""
        
        conn = await asyncpg.connect(self._build_connection_string(), statement_cache_size=0)
        
        try:
            query_embedding = await self.vectorizer.aembed(query)
            
            base_sql = """
                SELECT 
                    chunk_id, chunk_text, documento_origen,
                    tipo_equipo, marca, modelo, version_manual,
                    pagina_numero, seccion_titulo, tipo_contenido, nivel_jerarquia,
                    posicion_x, posicion_y, posicion_width, posicion_height,
                    palabras_clave, entidades_tecnicas, confidence_extraccion,
                    pdf_link, web_viewer_link,
                    chunk_anterior_id, chunk_siguiente_id,
                    1 - (chunk_embedding <=> $1::vector) as similarity
                FROM knowledge_base_enhanced
                WHERE documento_origen ILIKE $2
            """
            
            params = [str(query_embedding), f"%{documento}%"]
            
            if seccion:
                base_sql += " AND seccion_titulo ILIKE $3"
                params.append(f"%{seccion}%")
                limit_param = "$4"
            else:
                limit_param = "$3"
            
            base_sql += f" ORDER BY chunk_embedding <=> $1::vector LIMIT {limit_param}"
            params.append(top_k)
            
            results = await conn.fetch(base_sql, *params)
            
            # Convertir a MetadataSearchResult (similar al método anterior)
            search_results = []
            for result in results:
                search_result = MetadataSearchResult(
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
                    seccion_titulo=result['seccion_titulo'] or "Sin sección",
                    tipo_contenido=result['tipo_contenido'],
                    nivel_jerarquia=result['nivel_jerarquia'],
                    posicion_en_pagina={
                        "x": result['posicion_x'],
                        "y": result['posicion_y'],
                        "width": result['posicion_width'],
                        "height": result['posicion_height']
                    },
                    pdf_link=result['pdf_link'] or "",
                    web_viewer_link=result['web_viewer_link'] or "",
                    palabras_clave=result['palabras_clave'] or [],
                    entidades_tecnicas=result['entidades_tecnicas'] or []
                )
                search_results.append(search_result)
            
            return search_results
            
        finally:
            try:
                await asyncio.wait_for(conn.close(), timeout=2.0)
            except (asyncio.TimeoutError, Exception):
                pass  # Ignore close errors
    
    def _build_connection_string(self) -> str:
        """Construye string de conexión usando la configuración correcta de Supabase"""
        return self.settings.database.connection_string

class EnhancedRAGResponseFormatter:
    """
    Formateador de respuestas que incluye enlaces y metadatos ricos
    """
    
    def format_results_as_json(
        self, 
        results: List[MetadataSearchResult],
        query: str,
        include_debug_info: bool = False
    ) -> Dict[str, Any]:
        """
        Formatea resultados como JSON con todos los metadatos
        """
        
        if not results:
            return {
                "query": query,
                "total_results": 0,
                "results": [],
                "status": "no_results",
                "message": "No se encontraron resultados relevantes"
            }
        
        formatted_results = []
        
        for i, result in enumerate(results, 1):
            result_json = {
                "index": i,
                "chunk_id": result.chunk_id,
                "similarity": round(result.similarity, 4),
                "confidence": round(result.confidence, 4),
                
                # Información del documento
                "documento": {
                    "filename": result.documento_origen,
                    "pagina_numero": result.pagina_numero,
                    "seccion_titulo": result.seccion_titulo,
                    "tipo_contenido": result.tipo_contenido,
                    "nivel_jerarquia": result.nivel_jerarquia
                },
                
                # Información del equipo
                "equipo": {
                    "tipo_equipo": result.tipo_equipo,
                    "marca": result.marca,
                    "modelo": result.modelo,
                    "version_manual": result.version_manual
                },
                
                # Posición y coordenadas
                "posicion": {
                    "x": result.posicion_en_pagina.get("x", 0),
                    "y": result.posicion_en_pagina.get("y", 0),
                    "width": result.posicion_en_pagina.get("width", 0),
                    "height": result.posicion_en_pagina.get("height", 0)
                },
                
                # Contenido
                "contenido": {
                    "texto": result.chunk_text,
                    "texto_length": len(result.chunk_text),
                    "palabras_clave": result.palabras_clave or [],
                    "entidades_tecnicas": result.entidades_tecnicas or []
                },
                
                # Enlaces
                "enlaces": {
                    "pdf_link": result.pdf_link or "",
                    "web_viewer_link": result.web_viewer_link or ""
                },
                
                # Navegación entre chunks
                "navegacion": {
                    "chunk_anterior_id": result.chunk_anterior_id,
                    "chunk_siguiente_id": result.chunk_siguiente_id
                }
            }
            
            # Información debug opcional
            if include_debug_info:
                result_json["debug"] = {
                    "chunk_anterior_id": result.chunk_anterior_id,
                    "chunk_siguiente_id": result.chunk_siguiente_id,
                    "contexto_adicional": getattr(result, 'contexto_adicional', None)
                }
            
            formatted_results.append(result_json)
        
        return {
            "query": query,
            "total_results": len(results),
            "results": formatted_results,
            "status": "success",
            "execution_info": {
                "top_similarity": max([r.similarity for r in results]) if results else 0,
                "avg_confidence": sum([r.confidence for r in results]) / len(results) if results else 0
            }
        }

    def format_results_with_links(
        self, 
        results: List[MetadataSearchResult],
        query: str,
        include_debug_info: bool = False
    ) -> str:
        """
        Formatea resultados con enlaces y metadatos completos
        """
        
        if not results:
            return self._format_no_results_message(query)
        
        formatted_parts = []
        
        # Header
        header = f"🔍 **Resultados para:** \"{query}\"\n"
        header += f"📊 *{len(results)} soluciones encontradas*\n\n"
        formatted_parts.append(header)
        
        # Formatear cada resultado
        for i, result in enumerate(results, 1):
            result_block = self._format_single_result(result, i, include_debug_info)
            formatted_parts.append(result_block)
        
        return "\n".join(formatted_parts)
    
    def _format_single_result(
        self, 
        result: MetadataSearchResult, 
        index: int,
        include_debug: bool = False
    ) -> str:
        """Formatea un resultado individual con todos los metadatos"""
        
        # Determinar iconos y calidad
        confidence_icon = "⭐" if result.confidence > 0.8 else "✅" if result.confidence > 0.6 else "🔍"
        content_type_icon = {
            "procedimiento": "📋",
            "codigo_comando": "⌨️",
            "advertencia": "⚠️",
            "tabla": "📊",
            "titulo": "📌",
            "texto": "📄"
        }.get(result.tipo_contenido, "📄")
        
        # Header del resultado
        result_parts = []
        
        # Título principal
        title = f"**{confidence_icon} Solución {index}** {content_type_icon} *{result.tipo_contenido.title()}*"
        if result.similarity > 0.85:
            title += " 🎯 *Alta relevancia*"
        result_parts.append(title)
        
        # Información del documento y equipo
        doc_info = f"📋 **{result.marca} {result.modelo}** - {result.documento_origen}"
        if result.version_manual != "1.0":
            doc_info += f" (v{result.version_manual})"
        result_parts.append(doc_info)
        
        # Ubicación específica
        location_info = f"📍 *Página {result.pagina_numero}"
        if result.seccion_titulo and result.seccion_titulo != "Sin sección":
            location_info += f" - {result.seccion_titulo}"
        location_info += f" | Relevancia: {result.similarity:.2%}*"
        result_parts.append(location_info)
        
        # Enlaces directos
        links_section = "🔗 **Enlaces directos:**\n"
        links_section += f"   📄 [Abrir PDF en página {result.pagina_numero}]({result.pdf_link})\n"
        links_section += f"   🖥️ [Ver en navegador con resaltado]({result.web_viewer_link})"
        result_parts.append(links_section)
        
        # Separador antes del contenido
        result_parts.append("")
        
        # Contenido principal
        content = result.chunk_text.strip()
        
        # Truncar si es muy largo
        if len(content) > 1500:
            content = content[:1500] + "..."
            content += f"\n\n*[Contenido truncado - [Ver completo]({result.web_viewer_link})]*"
        
        result_parts.append(content)
        
        # Contexto adicional si está disponible
        if result.contexto_adicional:
            result_parts.append("")
            result_parts.append("**📖 Contexto relacionado:**")
            result_parts.append(result.contexto_adicional)
        
        # Metadatos técnicos
        if result.palabras_clave or result.entidades_tecnicas:
            result_parts.append("")
            
            if result.palabras_clave:
                keywords_text = ", ".join(result.palabras_clave[:5])
                result_parts.append(f"*🏷️ Palabras clave:* {keywords_text}")
            
            if result.entidades_tecnicas:
                entities_text = ", ".join(result.entidades_tecnicas[:3])
                result_parts.append(f"*🔧 Entidades técnicas:* {entities_text}")
        
        # Información de debug si se solicita
        if include_debug:
            result_parts.append("")
            debug_info = f"*🔍 Debug: ID={result.chunk_id}, Conf={result.confidence:.3f}, "
            debug_info += f"Pos=({result.posicion_en_pagina['x']:.0f},{result.posicion_en_pagina['y']:.0f})*"
            result_parts.append(debug_info)
        
        # Separador final
        result_parts.append("")
        result_parts.append("---")
        result_parts.append("")
        
        return "\n".join(result_parts)
    
    def _format_no_results_message(self, query: str) -> str:
        """Mensaje cuando no hay resultados"""
        return f"""
🔍 **No se encontraron resultados para:** "{query}"

**💡 Sugerencias para mejorar la búsqueda:**
• Usa términos más específicos del equipo (ej: "DIBAL Mistral calibración")
• Incluye el modelo exacto del equipo
• Prueba sinónimos técnicos (ej: "retroiluminación" o "backlight")
• Verifica la ortografía de términos técnicos

**🔧 Búsquedas sugeridas:**
• "configuración [nombre del equipo]"
• "procedimiento [acción específica]"
• "error [código o descripción]"
• "mantenimiento [tipo de equipo]"

¿Puedes proporcionar más detalles sobre el equipo específico o el problema?
"""

class IntegratedMetadataRAG:
    """
    Integración completa del RAG con metadatos en el sistema principal
    """
    
    def __init__(self):
        self.searcher = MetadataEnhancedRAGSearcher()
        self.formatter = EnhancedRAGResponseFormatter()
    
    async def buscar_con_metadatos(
        self,
        query: str,
        top_k: int = 3,
        equipo_context: Optional[Dict[str, str]] = None,
        include_links: bool = True,
        formato_debug: bool = False,
        return_format: str = "text"  # ← NUEVO PARÁMETRO
        ) -> Union[str, Dict[str, Any]]:  # ← CAMBIO TIPO RETORNO
        """
        Método principal para búsqueda con metadatos
        
        Args:
            query: Consulta del usuario
            top_k: Número de resultados
            equipo_context: {"tipo": "balanza", "marca": "DIBAL", "modelo": "Mistral"}
            include_links: Si incluir enlaces directos
            formato_debug: Si incluir información de debug
            return_format: "text" para string formateado, "json" para diccionario
        """
        
        try:
            # Extraer parámetros del contexto de equipo
            filters = {}
            if equipo_context:
                filters = {
                    "tipo_equipo": equipo_context.get("tipo"),
                    "marca": equipo_context.get("marca"),
                    "modelo": equipo_context.get("modelo")
                }
            
            # Realizar búsqueda con metadatos
            results = await self.searcher.search_with_metadata_filters(
                query=query,
                top_k=top_k,
                **filters,
                include_links=include_links,
                include_context=True
            )
            if return_format == "json":
                return self.formatter.format_results_as_json(
                    results=results,
                    query=query,
                    include_debug_info=formato_debug
                )
            else: 
            
                return self.formatter.format_results_with_links(
                    results=results,
                    query=query,
                    include_debug_info=formato_debug
                )
            
            
        except Exception as e:
            error_response = f"Error en búsqueda con metadatos: {str(e)}"
            
            if return_format == "json":
                return {
                    "query": query,
                    "status": "error",
                    "error": str(e),
                    "results": []
                }
            else:
                return error_response
    
    async def buscar_por_equipo_especifico(
        self,
        query: str,
        tipo_equipo: str,
        marca: Optional[str] = None,
        modelo: Optional[str] = None
    ) -> str:
        """Búsqueda específica para un tipo de equipo"""
        
        results = await self.searcher.search_by_equipment_specific(
            query=query,
            tipo_equipo=tipo_equipo,
            marca=marca,
            top_k=3
        )
        
        return self.formatter.format_results_with_links(results, query)
    
    async def buscar_en_documento(
        self,
        query: str,
        documento: str,
        seccion: Optional[str] = None
    ) -> str:
        """Búsqueda dentro de un documento específico"""
        
        results = await self.searcher.search_by_document_section(
            query=query,
            documento=documento,
            seccion=seccion,
            top_k=5
        )
        
        return self.formatter.format_results_with_links(results, query)
    
    async def obtener_estadisticas_documentos(self) -> Dict[str, Any]:
        """Obtiene estadísticas de documentos vectorizados"""
        
        conn = await asyncpg.connect(self.searcher._build_connection_string(), statement_cache_size=0)
        
        try:
            # Estadísticas generales
            general_stats = await conn.fetchrow("""
                SELECT 
                    COUNT(*) as total_chunks,
                    COUNT(DISTINCT documento_origen) as total_documentos,
                    COUNT(DISTINCT CONCAT(tipo_equipo, marca, modelo)) as equipos_unicos,
                    AVG(confidence_extraccion) as confidence_promedio
                FROM knowledge_base_enhanced
            """)
            
            # Estadísticas por tipo de equipo
            equipment_stats = await conn.fetch("""
                SELECT 
                    tipo_equipo,
                    marca,
                    COUNT(*) as chunks_count,
                    COUNT(DISTINCT documento_origen) as documentos_count,
                    AVG(confidence_extraccion) as avg_confidence
                FROM knowledge_base_enhanced
                GROUP BY tipo_equipo, marca
                ORDER BY chunks_count DESC
            """)
            
            # Estadísticas por tipo de contenido
            content_stats = await conn.fetch("""
                SELECT 
                    tipo_contenido,
                    COUNT(*) as count,
                    AVG(confidence_extraccion) as avg_confidence
                FROM knowledge_base_enhanced
                GROUP BY tipo_contenido
                ORDER BY count DESC
            """)
            
            return {
                "general": dict(general_stats),
                "por_equipo": [dict(row) for row in equipment_stats],
                "por_tipo_contenido": [dict(row) for row in content_stats]
            }
            
        finally:
            try:
                await asyncio.wait_for(conn.close(), timeout=2.0)
            except (asyncio.TimeoutError, Exception):
                pass  # Ignore close errors

# =====================================================
# Actualización del RAG principal para usar metadatos
# =====================================================

# Modificar la clase OptimizedEroskiKnowledgeBase original:

class OptimizedEroskiKnowledgeBaseWithMetadata(OptimizedEroskiKnowledgeBase):
    """
    RAG optimizado extendido con soporte completo para metadatos
    """
    
    def __init__(self):
        super().__init__()
        self.metadata_rag = IntegratedMetadataRAG()
        self.rag_searcher = MetadataEnhancedRAGSearcher()

        
    
    async def buscar_solucion_rag_avanzada(
        self,
        query: str,
        top_k: int = 3,
        equipo_context: Optional[Dict[str, str]] = None,
        incluir_enlaces: bool = True,
        return_formato: str = "json"
    ) -> str:
        """
        Búsqueda RAG avanzada con metadatos y enlaces
        
        Args:
            query: Consulta del usuario
            top_k: Número de resultados
            equipo_context: Contexto del equipo {"tipo": "balanza", "marca": "DIBAL"}
            incluir_enlaces: Si incluir enlaces directos al PDF
        """

        # Primero intentar búsqueda con metadatos
        try:
            resultado = await self.metadata_rag.buscar_con_metadatos(
                query=query,
                top_k=top_k,
                equipo_context=equipo_context,
                include_links=incluir_enlaces,
                return_format=return_formato
            )


            #print(f" 👹 resultado: {resultado}")
            return resultado
        except Exception as e:
            logger.warning(f"Fallback a búsqueda estándar: {e}")
            # Fallback a búsqueda original
            return self.buscar_solucion_rag(query, top_k)
    
    async def get_chunk_with_context(
        self,
        chunk_id: str,
        include_previous: bool = True,
        include_next: bool = True
    ) -> Dict[str, Any]:
        """
        Obtiene un chunk específico junto con el anterior y posterior
        
        Args:
            chunk_id: ID del chunk a buscar
            include_previous: Si incluir chunk anterior
            include_next: Si incluir chunk siguiente
            
        Returns:
            Dict con chunk_actual, chunk_anterior, chunk_siguiente
        """
        
        conn = await asyncpg.connect(self.rag_searcher._build_connection_string(), statement_cache_size=0)
        
        try:
            # 1. Obtener el chunk principal
            chunk_actual = await self._get_single_chunk(conn, chunk_id)
            
            if not chunk_actual:
                return {
                    "status": "error",
                    "message": f"Chunk {chunk_id} no encontrado",
                    "chunk_actual": None,
                    "chunk_anterior": None,
                    "chunk_siguiente": None
                }
            
            result = {
                "status": "success",
                "chunk_actual": chunk_actual,
                "chunk_anterior": None,
                "chunk_siguiente": None
            }
            print(f"👹chunk_actual, {chunk_actual['navegacion']}")
            # 2. Obtener chunk anterior si existe y se solicita
            if include_previous and chunk_actual['navegacion']['chunk_anterior_id']:
                result["chunk_anterior"] = await self._get_single_chunk(
                    conn, chunk_actual['navegacion']['chunk_anterior_id']
                )
            
            # 3. Obtener chunk siguiente si existe y se solicita
            if include_next and chunk_actual['navegacion']['chunk_siguiente_id']:
                result["chunk_siguiente"] = await self._get_single_chunk(
                    conn, chunk_actual['navegacion']['chunk_siguiente_id']
                )
            
            return result
            
        finally:
            try:
                await asyncio.wait_for(conn.close(), timeout=2.0)
            except (asyncio.TimeoutError, Exception):
                pass  # Ignore close errors

    async def _get_single_chunk(self, conn, chunk_id: str) -> Optional[Dict[str, Any]]:
        """Obtiene un chunk individual por ID"""
        
        try:
            # Intentar tabla enhanced primero
            result = await conn.fetchrow("""
                SELECT 
                    chunk_id, chunk_text, documento_origen,
                    tipo_equipo, marca, modelo, version_manual,
                    pagina_numero, seccion_titulo, tipo_contenido, nivel_jerarquia,
                    posicion_x, posicion_y, posicion_width, posicion_height,
                    numero_linea_inicio, numero_linea_fin,
                    chunk_anterior_id, chunk_siguiente_id,
                    palabras_clave, entidades_tecnicas, confidence_extraccion,
                    pdf_link, web_viewer_link,
                    created_at
                FROM knowledge_base_enhanced
                WHERE chunk_id = $1
            """, chunk_id)
            
            if result:
                return {
                    "chunk_id": result["chunk_id"],
                    "chunk_text": result["chunk_text"],
                    "documento_origen": result["documento_origen"],
                    "equipo": {
                        "tipo_equipo": result["tipo_equipo"],
                        "marca": result["marca"],
                        "modelo": result["modelo"],
                        "version_manual": result["version_manual"]
                    },
                    "ubicacion": {
                        "pagina_numero": result["pagina_numero"],
                        "seccion_titulo": result["seccion_titulo"],
                        "tipo_contenido": result["tipo_contenido"],
                        "nivel_jerarquia": result["nivel_jerarquia"]
                    },
                    "posicion": {
                        "x": result["posicion_x"],
                        "y": result["posicion_y"],
                        "width": result["posicion_width"],
                        "height": result["posicion_height"]
                    },
                    "lineas": {
                        "inicio": result["numero_linea_inicio"],
                        "fin": result["numero_linea_fin"]
                    },
                    "navegacion": {
                        "chunk_anterior_id": result["chunk_anterior_id"],
                        "chunk_siguiente_id": result["chunk_siguiente_id"]
                    },
                    "metadatos": {
                        "palabras_clave": result["palabras_clave"] or [],
                        "entidades_tecnicas": result["entidades_tecnicas"] or [],
                        "confidence_extraccion": result["confidence_extraccion"]
                    },
                    "enlaces": {
                        "pdf_link": result["pdf_link"] or "",
                        "web_viewer_link": result["web_viewer_link"] or ""
                    },
                    "created_at": result["created_at"]
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error obteniendo chunk {chunk_id}: {e}")
            return None

    async def get_chunks_by_page(
        self,
        documento_origen: str,
        pagina_numero: int,
        tipo_equipo: Optional[str] = None,
        marca: Optional[str] = None,
        modelo: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Obtiene todos los chunks de una página específica ordenados
        """
        
        conn = await asyncpg.connect(self._build_connection_string(), statement_cache_size=0)
        
        try:
            # Construir filtros
            base_sql = """
                SELECT 
                    chunk_id, chunk_text, documento_origen,
                    tipo_equipo, marca, modelo, version_manual,
                    pagina_numero, seccion_titulo, tipo_contenido,
                    posicion_x, posicion_y, posicion_width, posicion_height,
                    numero_linea_inicio, numero_linea_fin,
                    chunk_anterior_id, chunk_siguiente_id,
                    confidence_extraccion
                FROM knowledge_base_enhanced
                WHERE documento_origen = $1 AND pagina_numero = $2
            """
            
            params = [documento_origen, pagina_numero]
            param_count = 2
            
            # Añadir filtros opcionales
            if tipo_equipo:
                param_count += 1
                base_sql += f" AND LOWER(tipo_equipo) = LOWER(${param_count})"
                params.append(tipo_equipo)
            
            if marca:
                param_count += 1
                base_sql += f" AND LOWER(marca) = LOWER(${param_count})"
                params.append(marca)
            
            if modelo:
                param_count += 1
                base_sql += f" AND LOWER(modelo) = LOWER(${param_count})"
                params.append(modelo)
            
            # Ordenar por posición en la página
            base_sql += " ORDER BY posicion_y, posicion_x, numero_linea_inicio"
            
            results = await conn.fetch(base_sql, *params)
            
            chunks = []
            for result in results:
                chunks.append({
                    "chunk_id": result["chunk_id"],
                    "chunk_text": result["chunk_text"],
                    "posicion": {
                        "x": result["posicion_x"],
                        "y": result["posicion_y"],
                        "width": result["posicion_width"],
                        "height": result["posicion_height"]
                    },
                    "lineas": {
                        "inicio": result["numero_linea_inicio"],
                        "fin": result["numero_linea_fin"]
                    },
                    "navegacion": {
                        "chunk_anterior_id": result["chunk_anterior_id"],
                        "chunk_siguiente_id": result["chunk_siguiente_id"]
                    },
                    "seccion_titulo": result["seccion_titulo"],
                    "tipo_contenido": result["tipo_contenido"]
                })
            
            return chunks
            
        finally:
            try:
                await asyncio.wait_for(conn.close(), timeout=2.0)
            except (asyncio.TimeoutError, Exception):
                pass  # Ignore close errors

    async def navigate_chunks(
        self,
        chunk_id: str,
        direction: str = "next",  # "next", "previous", "both"
        steps: int = 1
    ) -> Dict[str, Any]:
        """
        Navega entre chunks relacionados
        
        Args:
            chunk_id: ID del chunk de inicio
            direction: "next", "previous", "both"
            steps: Número de pasos a navegar
            
        Returns:
            Dict con los chunks encontrados
        """
        
        conn = await asyncpg.connect(self._build_connection_string(), statement_cache_size=0)
        
        try:
            current_chunk = await self._get_single_chunk(conn, chunk_id)
            
            if not current_chunk:
                return {"error": f"Chunk {chunk_id} no encontrado"}
            
            result = {
                "current_chunk": current_chunk,
                "navigation": {
                    "previous_chunks": [],
                    "next_chunks": []
                }
            }
            
            # Navegar hacia atrás
            if direction in ["previous", "both"]:
                prev_id = current_chunk["navegacion"]["chunk_anterior_id"]
                for i in range(steps):
                    if prev_id:
                        prev_chunk = await self._get_single_chunk(conn, prev_id)
                        if prev_chunk:
                            result["navigation"]["previous_chunks"].append(prev_chunk)
                            prev_id = prev_chunk["navegacion"]["chunk_anterior_id"]
                        else:
                            break
                    else:
                        break
            
            # Navegar hacia adelante
            if direction in ["next", "both"]:
                next_id = current_chunk["navegacion"]["chunk_siguiente_id"]
                for i in range(steps):
                    if next_id:
                        next_chunk = await self._get_single_chunk(conn, next_id)
                        if next_chunk:
                            result["navigation"]["next_chunks"].append(next_chunk)
                            next_id = next_chunk["navegacion"]["chunk_siguiente_id"]
                        else:
                            break
                    else:
                        break
            
            return result
            
        finally:
            try:
                await asyncio.wait_for(conn.close(), timeout=2.0)
            except (asyncio.TimeoutError, Exception):
                pass  # Ignore close errors
    # Mantener compatibilidad con método original
    def buscar_solucion_rag(self, query: str, top_k: int = 3) -> str:
        """Método original para compatibilidad"""
        try:
            # Intentar primero con metadatos
            loop = asyncio.get_event_loop()
            if loop.is_running():
                task = asyncio.create_task(
                    self.metadata_rag.buscar_con_metadatos(query, top_k)
                )
                return asyncio.run_coroutine_threadsafe(task, loop).result(timeout=30)
            else:
                return asyncio.run(
                    self.metadata_rag.buscar_con_metadatos(query, top_k)
                )
        except Exception:
            # Fallback completo al método padre
            return super().buscar_solucion_rag(query, top_k)

# =====================================================
# Ejemplo de uso completo
# =====================================================

async def ejemplo_uso_completo():
    """Ejemplo de uso del sistema completo con metadatos"""
    
    # 1. Inicializar RAG con metadatos
    rag = OptimizedEroskiKnowledgeBaseWithMetadata()
    
    # 2. Búsqueda básica con enlaces
    print("=" * 50)
    print("BÚSQUEDA BÁSICA CON ENLACES")
    print("=" * 50)
    
    resultado_basico = await rag.buscar_solucion_rag_avanzada(
        query="configuración retroiluminación",
        top_k=2,
        incluir_enlaces=True
    )
    print(resultado_basico)
    
    # 3. Búsqueda específica por equipo
    print("\n" + "=" * 50)
    print("BÚSQUEDA ESPECÍFICA POR EQUIPO")
    print("=" * 50)
    
    resultado_equipo = await rag.buscar_solucion_rag_avanzada(
        query="calibración peso",
        equipo_context={
            "tipo": "balanza",
            "marca": "DIBAL",
            "modelo": "Mistral"
        },
        top_k=3
    )
    print(resultado_equipo)
    
    # 4. Búsqueda en documento específico
    print("\n" + "=" * 50)
    print("BÚSQUEDA EN DOCUMENTO ESPECÍFICO")
    print("=" * 50)
    
    resultado_documento = await rag.metadata_rag.buscar_en_documento(
        query="procedimiento mantenimiento",
        documento="Manual Balanza DIBAL Mistral.pdf",
        seccion="Mantenimiento"
    )
    print(resultado_documento)
    
    # 5. Estadísticas del sistema
    print("\n" + "=" * 50)
    print("ESTADÍSTICAS DEL SISTEMA")
    print("=" * 50)
    
    stats = await rag.metadata_rag.obtener_estadisticas_documentos()
    print(f"📊 Total documentos: {stats['general']['total_documentos']}")
    print(f"📄 Total chunks: {stats['general']['total_chunks']}")
    print(f"🔧 Equipos únicos: {stats['general']['equipos_unicos']}")
    print(f"🎯 Confidence promedio: {stats['general']['confidence_promedio']:.2f}")
    
    print("\nPor tipo de equipo:")
    for equipo in stats['por_equipo'][:3]:
        print(f"  {equipo['tipo_equipo']} {equipo['marca']}: {equipo['chunks_count']} chunks")


# =====================================================
# Búsqueda RAG con Contexto Parcial de Equipo
# =====================================================
"""
Extensión del RAG para manejar contexto parcial de equipos:
- Solo tipo de equipo conocido
- Búsqueda en múltiples marcas/modelos
- Respuestas agrupadas por marca/modelo
- Comparativa automática entre equipos
"""



logger = logging.getLogger(__name__)

@dataclass
class MultiEquipmentSearchResult:
    """Resultado de búsqueda que incluye múltiples equipos"""
    query: str
    results_by_equipment: Dict[str, List[MetadataSearchResult]]  # "DIBAL_Mistral": [resultados]
    total_results: int
    equipment_coverage: Dict[str, int]  # Cuántos resultados por equipo
    best_match_equipment: str  # Equipo con mejor resultado
    confidence_by_equipment: Dict[str, float]  # Confidence promedio por equipo

class PartialContextRAGSearcher:
    """
    Buscador RAG que maneja contexto parcial de equipos
    """
    
    def __init__(self):
        self.settings = get_settings()
    
    async def search_with_partial_context(
        self,
        query: str,
        tipo_equipo: str,
        marca: Optional[str] = None,
        modelo: Optional[str] = None,
        top_k_per_equipment: int = 2,
        max_equipment_variants: int = 5
    ) -> MultiEquipmentSearchResult:
        """
        Búsqueda con contexto parcial - busca en todos los equipos del tipo especificado
        
        Args:
            query: Consulta del usuario
            tipo_equipo: Tipo de equipo conocido (balanza, tpv, etc.)
            marca: Marca específica (opcional)
            modelo: Modelo específico (opcional)
            top_k_per_equipment: Resultados por equipo
            max_equipment_variants: Máximo número de equipos diferentes a incluir
        """
        
        conn = await asyncpg.connect(self._build_connection_string(), statement_cache_size=0)
        
        try:
            # 1. Obtener todos los equipos disponibles del tipo especificado
            available_equipment = await self._get_available_equipment(
                conn, tipo_equipo, marca, modelo
            )
            
            logger.info(f"🔍 Buscando en {len(available_equipment)} equipos de tipo '{tipo_equipo}'")
            
            # 2. Realizar búsqueda para cada equipo
            results_by_equipment = {}
            confidence_by_equipment = {}
            
            for equipment_info in available_equipment[:max_equipment_variants]:
                equipment_key = f"{equipment_info['marca']}_{equipment_info['modelo']}"
                
                # Búsqueda específica para este equipo
                equipment_results = await self._search_specific_equipment(
                    conn, query, equipment_info, top_k_per_equipment
                )
                
                if equipment_results:
                    results_by_equipment[equipment_key] = equipment_results
                    
                    # Calcular confidence promedio para este equipo
                    avg_confidence = sum(r.confidence for r in equipment_results) / len(equipment_results)
                    confidence_by_equipment[equipment_key] = avg_confidence
            
            # 3. Determinar el mejor equipo match
            best_equipment = max(confidence_by_equipment.items(), key=lambda x: x[1])[0] if confidence_by_equipment else ""
            
            # 4. Calcular estadísticas
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
            try:
                await asyncio.wait_for(conn.close(), timeout=2.0)
            except (asyncio.TimeoutError, Exception):
                pass  # Ignore close errors
    
    async def _get_available_equipment(
        self,
        conn,
        tipo_equipo: str,
        marca: Optional[str],
        modelo: Optional[str]
    ) -> List[Dict[str, Any]]:
        """Obtiene lista de equipos disponibles que coinciden con los criterios"""
        
        # Construir query para obtener equipos únicos
        base_sql = """
            SELECT DISTINCT 
                tipo_equipo, marca, modelo,
                COUNT(*) as total_chunks,
                AVG(confidence_extraccion) as avg_confidence,
                COUNT(DISTINCT documento_origen) as total_documents
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
            HAVING COUNT(*) >= 10  -- Solo equipos con suficiente documentación
            ORDER BY AVG(confidence_extraccion) DESC, COUNT(*) DESC
        """
        
        equipment_list = await conn.fetch(base_sql, *params)
        
        return [dict(equipment) for equipment in equipment_list]
    
    async def _search_specific_equipment(
        self,
        conn,
        query: str,
        equipment_info: Dict[str, Any],
        top_k: int
    ) -> List[MetadataSearchResult]:
        """Realiza búsqueda específica para un equipo particular"""
        
        from app.utils.llm.providers import get_vectorizer
        vectorizer = get_vectorizer()
        
        # Crear consulta enriquecida con contexto del equipo específico
        enriched_query = f"""
        Equipo: {equipment_info['tipo_equipo']} {equipment_info['marca']} {equipment_info['modelo']}
        Consulta: {query}
        """
        
        query_embedding = vectorizer.embed(enriched_query)
        
        # SQL específica para este equipo
        search_sql = """
            SELECT 
                chunk_id, chunk_text, documento_origen,
                tipo_equipo, marca, modelo, version_manual,
                pagina_numero, seccion_titulo, tipo_contenido, nivel_jerarquia,
                posicion_x, posicion_y, posicion_width, posicion_height,
                palabras_clave, entidades_tecnicas, confidence_extraccion,
                pdf_link, web_viewer_link,
                chunk_anterior_id, chunk_siguiente_id,
                1 - (chunk_embedding_with_metadata <=> $1::vector) as similarity
            FROM knowledge_base_enhanced
            WHERE LOWER(tipo_equipo) = LOWER($2)
            AND LOWER(marca) = LOWER($3)
            AND LOWER(modelo) = LOWER($4)
            AND chunk_embedding_with_metadata IS NOT NULL
            AND confidence_extraccion >= 0.4
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
        
        # Convertir a MetadataSearchResult
        search_results = []
        for result in results:
            if result['similarity'] >= 0.5:  # Solo resultados con buena similitud
                search_result = MetadataSearchResult(
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
                    seccion_titulo=result['seccion_titulo'] or "Sin sección",
                    tipo_contenido=result['tipo_contenido'],
                    nivel_jerarquia=result['nivel_jerarquia'],
                    posicion_en_pagina={
                        "x": result['posicion_x'],
                        "y": result['posicion_y'],
                        "width": result['posicion_width'],
                        "height": result['posicion_height']
                    },
                    pdf_link=result['pdf_link'] or "",
                    web_viewer_link=result['web_viewer_link'] or "",
                    palabras_clave=result['palabras_clave'] or [],
                    entidades_tecnicas=result['entidades_tecnicas'] or []
                )
                search_results.append(search_result)
        
        return search_results
    
    def _build_connection_string(self) -> str:
        """Construye string de conexión usando la configuración correcta de Supabase"""
        return self.settings.database.connection_string

class MultiEquipmentResponseFormatter:
    """
    Formateador de respuestas para búsquedas multi-equipo
    """
    
    def format_multi_equipment_response(
        self,
        search_result: MultiEquipmentSearchResult,
        show_comparisons: bool = True,
        show_equipment_summary: bool = True
    ) -> str:
        """
        Formatea respuesta que incluye resultados de múltiples equipos
        """
        
        if not search_result.results_by_equipment:
            return self._format_no_equipment_found(search_result.query)
        
        formatted_parts = []
        
        # Header principal
        header = f"🔍 **Resultados para:** \"{search_result.query}\"\n"
        header += f"🔧 **Tipo de equipo:** {list(search_result.results_by_equipment.values())[0][0].tipo_equipo}\n"
        header += f"📊 **{search_result.total_results} resultados encontrados en {len(search_result.results_by_equipment)} equipos**\n"
        
        # Mostrar mejor match
        if search_result.best_match_equipment:
            best_confidence = search_result.confidence_by_equipment[search_result.best_match_equipment]
            header += f"🎯 **Mejor coincidencia:** {search_result.best_match_equipment.replace('_', ' ')} (Relevancia: {best_confidence:.1%})\n"
        
        formatted_parts.append(header)
        
        # Resumen de equipos si se solicita
        if show_equipment_summary:
            summary = self._format_equipment_summary(search_result)
            formatted_parts.append(summary)
        
        # Resultados por equipo, ordenados por confidence
        sorted_equipment = sorted(
            search_result.results_by_equipment.items(),
            key=lambda x: search_result.confidence_by_equipment[x[0]],
            reverse=True
        )
        
        for equipment_key, results in sorted_equipment:
            equipment_section = self._format_equipment_section(equipment_key, results)
            formatted_parts.append(equipment_section)
        
        # Comparación entre equipos si se solicita
        if show_comparisons and len(search_result.results_by_equipment) > 1:
            comparison = self._format_equipment_comparison(search_result)
            formatted_parts.append(comparison)
        
        return "\n".join(formatted_parts)
    
    def _format_equipment_summary(self, search_result: MultiEquipmentSearchResult) -> str:
        """Formatea resumen de equipos encontrados"""
        
        summary_parts = ["\n📋 **Equipos analizados:**"]
        
        for equipment_key, confidence in sorted(
            search_result.confidence_by_equipment.items(),
            key=lambda x: x[1],
            reverse=True
        ):
            marca, modelo = equipment_key.split('_', 1)
            result_count = search_result.equipment_coverage[equipment_key]
            
            # Icono basado en confidence
            if confidence >= 0.8:
                icon = "🟢"
            elif confidence >= 0.6:
                icon = "🟡"
            else:
                icon = "🔴"
            
            summary_parts.append(
                f"   {icon} **{marca} {modelo}**: {result_count} resultados (Relevancia: {confidence:.1%})"
            )
        
        summary_parts.append("")
        return "\n".join(summary_parts)
    
    def _format_equipment_section(self, equipment_key: str, results: List[MetadataSearchResult]) -> str:
        """Formatea sección para un equipo específico"""
        
        marca, modelo = equipment_key.split('_', 1)
        
        # Header de la sección
        section_parts = [f"\n## 🔧 {marca} {modelo}"]
        
        # Estadísticas rápidas
        avg_similarity = sum(r.similarity for r in results) / len(results)
        best_similarity = max(r.similarity for r in results)
        
        stats = f"*{len(results)} resultados | Relevancia promedio: {avg_similarity:.1%} | Mejor: {best_similarity:.1%}*\n"
        section_parts.append(stats)
        
        # Formatear cada resultado
        for i, result in enumerate(results, 1):
            result_block = self._format_single_equipment_result(result, i)
            section_parts.append(result_block)
        
        section_parts.append("---")
        return "\n".join(section_parts)
    
    def _format_single_equipment_result(self, result: MetadataSearchResult, index: int) -> str:
        """Formatea un resultado individual dentro de una sección de equipo"""
        
        # Iconos por confidence
        confidence_icon = "⭐" if result.confidence > 0.8 else "✅" if result.confidence > 0.6 else "🔍"
        
        result_parts = []
        
        # Título compacto
        title = f"**{confidence_icon} Resultado {index}** *({result.tipo_contenido})*"
        result_parts.append(title)
        
        # Ubicación
        location = f"📍 *{result.documento_origen}, Página {result.pagina_numero}"
        if result.seccion_titulo != "Sin sección":
            location += f" - {result.seccion_titulo}"
        location += f" | {result.similarity:.1%}*"
        result_parts.append(location)
        
        # Enlaces
        links = f"🔗 [PDF]({result.pdf_link}) | [Visor]({result.web_viewer_link})"
        result_parts.append(links)
        
        # Contenido (truncado)
        content = result.chunk_text.strip()
        if len(content) > 300:
            content = content[:300] + f"... [Ver completo]({result.web_viewer_link})"
        
        result_parts.append("")
        result_parts.append(content)
        
        # Keywords si son relevantes
        if result.palabras_clave:
            keywords = ", ".join(result.palabras_clave[:3])
            result_parts.append(f"\n*🏷️ {keywords}*")
        
        result_parts.append("")
        return "\n".join(result_parts)
    
    def _format_equipment_comparison(self, search_result: MultiEquipmentSearchResult) -> str:
        """Formatea comparación entre equipos"""
        
        comparison_parts = ["\n## 📊 **Comparación entre Equipos**\n"]
        
        # Tabla de comparación
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
            
            # Encontrar mejor resultado para este equipo
            equipment_results = search_result.results_by_equipment[equipment_key]
            best_result = max(equipment_results, key=lambda x: x.similarity)
            
            comparison_parts.append(
                f"| **{marca} {modelo}** | {result_count} | {avg_conf:.1%} | {best_result.similarity:.1%} |"
            )
        
        comparison_parts.append("")
        
        # Recomendación
        best_equipment = search_result.best_match_equipment.replace('_', ' ')
        comparison_parts.append(f"💡 **Recomendación:** Los mejores resultados se encontraron en **{best_equipment}**")
        
        return "\n".join(comparison_parts)
    
    def _format_no_equipment_found(self, query: str) -> str:
        """Mensaje cuando no se encuentran equipos"""
        return f"""
🔍 **No se encontraron resultados para:** "{query}"

**💡 Posibles causas:**
• No hay manuales vectorizados para este tipo de equipo
• La consulta es muy específica para el equipamiento disponible
• Los términos técnicos no coinciden con la documentación

**🔧 Sugerencias:**
• Verifica que el tipo de equipo sea correcto
• Usa términos más generales
• Consulta qué equipos están disponibles en el sistema

¿Te gustaría ver qué equipos tenemos documentados?
"""

class EnhancedRAGWithPartialContext:
    """
    RAG principal extendido para manejar contexto parcial de equipos
    """
    
    def __init__(self):
        self.partial_searcher = PartialContextRAGSearcher()
        self.formatter = MultiEquipmentResponseFormatter()
    
    async def buscar_con_contexto_parcial(
        self,
        query: str,
        equipo_context: Dict[str, Optional[str]],
        incluir_comparacion: bool = True,
        max_equipos: int = 3
    ) -> str:
        """
        Búsqueda principal con contexto parcial de equipo
        
        Args:
            query: Consulta del usuario
            equipo_context: {"tipo": "balanza", "marca": None, "modelo": None}
            incluir_comparacion: Si incluir comparación entre equipos
            max_equipos: Máximo número de equipos a analizar
        """
        
        tipo_equipo = equipo_context.get("tipo")
        if not tipo_equipo:
            return "❌ Error: Debe especificar al menos el tipo de equipo"
        
        try:
            # Realizar búsqueda multi-equipo
            search_result = await self.partial_searcher.search_with_partial_context(
                query=query,
                tipo_equipo=tipo_equipo,
                marca=equipo_context.get("marca"),
                modelo=equipo_context.get("modelo"),
                top_k_per_equipment=2,
                max_equipment_variants=max_equipos
            )
            
            # Formatear respuesta
            formatted_response = self.formatter.format_multi_equipment_response(
                search_result=search_result,
                show_comparisons=incluir_comparacion,
                show_equipment_summary=True
            )
            
            return formatted_response
            
        except Exception as e:
            logger.error(f"Error en búsqueda con contexto parcial: {e}")
            return f"❌ Error en la búsqueda: {str(e)}"
    
    async def listar_equipos_disponibles(self, tipo_equipo: Optional[str] = None) -> str:
        """Lista todos los equipos disponibles en el sistema"""
        
        conn = await asyncpg.connect(self.partial_searcher._build_connection_string(), statement_cache_size=0)
        
        try:
            base_sql = """
                SELECT 
                    tipo_equipo, marca, modelo,
                    COUNT(*) as total_chunks,
                    COUNT(DISTINCT documento_origen) as total_documents,
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
            
            # Agrupar por tipo de equipo
            by_type = defaultdict(list)
            for equipment in equipment_list:
                by_type[equipment['tipo_equipo']].append(equipment)
            
            # Formatear lista
            formatted_parts = ["📋 **Equipos Disponibles en el Sistema:**\n"]
            
            for equipo_tipo, equipos in sorted(by_type.items()):
                formatted_parts.append(f"## 🔧 {equipo_tipo.title()}")
                
                for equipo in equipos:
                    quality_icon = "🟢" if equipo['avg_confidence'] > 0.7 else "🟡" if equipo['avg_confidence'] > 0.5 else "🔴"
                    formatted_parts.append(
                        f"   {quality_icon} **{equipo['marca']} {equipo['modelo']}** - "
                        f"{equipo['total_chunks']} chunks, {equipo['total_documents']} documentos "
                        f"(Calidad: {equipo['avg_confidence']:.1%})"
                    )
                
                formatted_parts.append("")
            
            return "\n".join(formatted_parts)
            
        finally:
            try:
                await asyncio.wait_for(conn.close(), timeout=2.0)
            except (asyncio.TimeoutError, Exception):
                pass  # Ignore close errors

# =====================================================
# Integración con el RAG principal
# =====================================================

# Actualizar la clase principal del RAG:
class OptimizedEroskiKnowledgeBaseWithPartialContext(OptimizedEroskiKnowledgeBase):
    """
    RAG optimizado que maneja contexto parcial de equipos
    """
    
    def __init__(self):
        super().__init__()
        self.partial_context_rag = EnhancedRAGWithPartialContext()
    
    async def buscar_solucion_rag_avanzada(
        self,
        query: str,
        top_k: int = 3,
        equipo_context: Optional[Dict[str, str]] = None,
        incluir_enlaces: bool = True
    ) -> str:
        """
        Búsqueda RAG avanzada que maneja contexto completo y parcial
        """
        
        if not equipo_context:
            # Sin contexto de equipo - búsqueda general
            return await super().buscar_solucion_rag_avanzada(query, top_k, None, incluir_enlaces)
        
        # Verificar si tenemos información completa o parcial
        tipo_equipo = equipo_context.get("tipo")
        marca = equipo_context.get("marca")
        modelo = equipo_context.get("modelo")
        
        if tipo_equipo and marca and modelo:
            # Contexto completo - usar búsqueda específica
            return await super().buscar_solucion_rag_avanzada(query, top_k, equipo_context, incluir_enlaces)
        
        elif tipo_equipo:
            # Contexto parcial - buscar en todos los equipos del tipo
            logger.info(f"🔍 Búsqueda con contexto parcial: tipo={tipo_equipo}, marca={marca}, modelo={modelo}")
            
            return await self.partial_context_rag.buscar_con_contexto_parcial(
                query=query,
                equipo_context=equipo_context,
                incluir_comparacion=True,
                max_equipos=5
            )
        
        else:
            # Sin información suficiente
            return "❌ Error: Debe especificar al menos el tipo de equipo para búsquedas contextuales"

# =====================================================
# Ejemplo de uso
# =====================================================

async def ejemplo_contexto_parcial():
    """Ejemplo de uso con contexto parcial de equipo"""
    
    rag = OptimizedEroskiKnowledgeBaseWithPartialContext()
    
    print("=" * 60)
    print("EJEMPLO: BÚSQUEDA CON CONTEXTO PARCIAL")
    print("=" * 60)
    
    # Caso 1: Solo sabemos que es una balanza
    print("\n🔍 CASO 1: Solo conocemos el tipo de equipo")
    print("-" * 40)
    
    resultado1 = await rag.buscar_solucion_rag_avanzada(
        query="problema calibración",
        equipo_context={
            "tipo": "balanza",     # ✅ Conocido
            "marca": None,         # ❌ Desconocido  
            "modelo": None         # ❌ Desconocido
        }
    )
    
    print(resultado1)
    
    # Caso 2: Conocemos tipo y marca, pero no modelo
    print("\n\n🔍 CASO 2: Conocemos tipo y marca")
    print("-" * 40)
    
    resultado2 = await rag.buscar_solucion_rag_avanzada(
        query="configuración retroiluminación",
        equipo_context={
            "tipo": "balanza",     # ✅ Conocido
            "marca": "DIBAL",      # ✅ Conocido
            "modelo": None         # ❌ Desconocido
        }
    )
    
    print(resultado2)
    
    # Caso 3: Ver equipos disponibles
    print("\n\n📋 EQUIPOS DISPONIBLES EN EL SISTEMA")
    print("-" * 40)
    
    equipos_disponibles = await rag.partial_context_rag.listar_equipos_disponibles("balanza")
    print(equipos_disponibles)


if __name__ == "__main__":
    asyncio.run(ejemplo_uso_completo())
    asyncio.run(ejemplo_contexto_parcial())

# Alias para compatibilidad
EroskiKnowledgeBase = OptimizedEroskiKnowledgeBase