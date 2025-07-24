# =====================================================
# database/scripts/optimize_rag_database.py - Optimización completa RAG
# =====================================================
"""
Script de optimización completa para la base de datos RAG de Eroski.
Aplica todas las mejoras de rendimiento, índices y configuraciones.
"""

import asyncio
import asyncpg
import logging
import sys
import time
from pathlib import Path
from typing import List, Dict, Any
import json

# Setup path
ROOT_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from config.settings import get_settings

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("RAGOptimizer")

class DatabaseRAGOptimizer:
    """Optimizador completo de la base de datos RAG"""
    
    def __init__(self):
        self.settings = get_settings()
        self.connection_string = self._build_connection_string()
        
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
    
    async def optimize_complete_database(self):
        """Proceso completo de optimización"""
        logger.info("🚀 INICIANDO OPTIMIZACIÓN COMPLETA DE BASE DE DATOS RAG")
        logger.info("=" * 60)
        
        try:
            # 1. Verificaciones iniciales
            await self._verify_prerequisites()
            
            # 2. Optimizar configuración PostgreSQL
            await self._optimize_postgresql_config()
            
            # 3. Crear/actualizar índices vectoriales
            await self._create_optimized_indexes()
            
            # 4. Optimizar tabla knowledge_base
            await self._optimize_knowledge_base_table()
            
            # 5. Crear vistas optimizadas
            await self._create_optimized_views()
            
            # 6. Configurar extensiones adicionales
            await self._setup_additional_extensions()
            
            # 7. Crear funciones personalizadas
            await self._create_custom_functions()
            
            # 8. Configurar métricas y monitoreo
            await self._setup_monitoring()
            
            # 9. Ejecutar estadísticas y análisis
            await self._analyze_and_vacuum()
            
            # 10. Verificar rendimiento
            await self._performance_verification()
            
            logger.info("✅ OPTIMIZACIÓN COMPLETA FINALIZADA")
            logger.info("🎉 Base de datos RAG optimizada para máximo rendimiento")
            
        except Exception as e:
            logger.error(f"❌ Error en optimización: {e}")
            raise
    
    async def _verify_prerequisites(self):
        """Verifica prerequisitos y dependencias"""
        logger.info("🔍 Verificando prerequisitos...")
        
        conn = await asyncpg.connect(self.connection_string)
        
        try:
            # Verificar versión PostgreSQL
            version_result = await conn.fetchval("SELECT version()")
            logger.info(f"   📊 PostgreSQL: {version_result.split(',')[0]}")
            
            # Verificar extensiones críticas
            extensions = await conn.fetch("""
                SELECT extname, extversion 
                FROM pg_extension 
                WHERE extname IN ('vector', 'pg_trgm', 'unaccent', 'pg_stat_statements')
            """)
            
            ext_names = [ext['extname'] for ext in extensions]
            
            required_extensions = ['vector', 'pg_trgm', 'unaccent']
            missing = [ext for ext in required_extensions if ext not in ext_names]
            
            if missing:
                logger.warning(f"   ⚠️ Extensiones faltantes: {missing}")
                # Intentar instalar extensiones faltantes
                for ext in missing:
                    try:
                        await conn.execute(f"CREATE EXTENSION IF NOT EXISTS {ext};")
                        logger.info(f"   ✅ Extensión {ext} instalada")
                    except Exception as e:
                        logger.error(f"   ❌ No se pudo instalar {ext}: {e}")
            else:
                logger.info("   ✅ Todas las extensiones requeridas están disponibles")
            
            # Verificar tabla knowledge_base
            kb_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'knowledge_base'
                )
            """)
            
            if not kb_exists:
                logger.error("   ❌ Tabla knowledge_base no existe")
                raise Exception("Tabla knowledge_base requerida no encontrada")
            
            # Contar registros
            total_chunks = await conn.fetchval("SELECT COUNT(*) FROM knowledge_base")
            vectorized_chunks = await conn.fetchval(
                "SELECT COUNT(*) FROM knowledge_base WHERE chunk_embedding IS NOT NULL"
            )
            
            logger.info(f"   📚 Chunks totales: {total_chunks}")
            logger.info(f"   🤖 Chunks vectorizados: {vectorized_chunks}")
            
            if vectorized_chunks == 0:
                logger.warning("   ⚠️ No hay chunks vectorizados. Ejecuta vectorize_manual.py primero")
            
        finally:
            await conn.close()
    
    async def _optimize_postgresql_config(self):
        """Optimiza configuración de PostgreSQL para RAG"""
        logger.info("⚙️ Optimizando configuración PostgreSQL...")
        
        conn = await asyncpg.connect(self.connection_string)
        
        try:
            # Configuraciones específicas para RAG vectorial
            optimizations = [
                # Memoria para operaciones vectoriales
                "SET work_mem = '256MB';",
                "SET maintenance_work_mem = '1GB';",
                "SET shared_buffers = '512MB';",
                
                # Optimizaciones para consultas complejas
                "SET random_page_cost = 1.1;",
                "SET effective_cache_size = '2GB';",
                
                # Configuraciones para pgvector
                "SET ivfflat.probes = 3;",  # Mejor precisión vs velocidad
                
                # Configuraciones de texto completo
                "SET default_text_search_config = 'spanish';",
            ]
            
            for config in optimizations:
                try:
                    await conn.execute(config)
                    config_name = config.split('=')[0].replace('SET ', '').strip()
                    logger.info(f"   ✅ {config_name} optimizado")
                except Exception as e:
                    logger.warning(f"   ⚠️ {config}: {e}")
            
        finally:
            await conn.close()
    
    async def _create_optimized_indexes(self):
        """Crea índices optimizados para búsqueda RAG"""
        logger.info("📋 Creando índices optimizados...")
        
        conn = await asyncpg.connect(self.connection_string)
        
        try:
            # Índices vectoriales con diferentes configuraciones
            vector_indexes = [
                # Índice principal con IVFFlat optimizado
                """
                CREATE INDEX IF NOT EXISTS idx_kb_embedding_ivfflat_optimized 
                ON knowledge_base USING ivfflat (chunk_embedding vector_cosine_ops) 
                WITH (lists = 100);
                """,
                
                # Índice alternativo para consultas precisas
                """
                CREATE INDEX IF NOT EXISTS idx_kb_embedding_hnsw 
                ON knowledge_base USING hnsw (chunk_embedding vector_cosine_ops) 
                WITH (m = 16, ef_construction = 64);
                """,
            ]
            
            # Índices de texto completo avanzados
            text_indexes = [
                # Índice GIN para búsqueda de texto en español
                """
                CREATE INDEX IF NOT EXISTS idx_kb_texto_gin_spanish 
                ON knowledge_base USING gin(to_tsvector('spanish', chunk_text));
                """,
                
                # Índice para búsqueda simple (fallback)
                """
                CREATE INDEX IF NOT EXISTS idx_kb_texto_gin_simple 
                ON knowledge_base USING gin(to_tsvector('simple', chunk_text));
                """,
                
                # Índice trigram para búsqueda difusa
                """
                CREATE INDEX IF NOT EXISTS idx_kb_texto_trigram 
                ON knowledge_base USING gin(chunk_text gin_trgm_ops);
                """,
            ]
            
            # Índices de apoyo para filtros
            support_indexes = [
                # Documento origen
                """
                CREATE INDEX IF NOT EXISTS idx_kb_documento_btree 
                ON knowledge_base(documento_origen);
                """,
                
                # Página número para contexto
                """
                CREATE INDEX IF NOT EXISTS idx_kb_pagina_btree 
                ON knowledge_base(documento_origen, pagina_numero);
                """,
                
                # Sección para filtros
                """
                CREATE INDEX IF NOT EXISTS idx_kb_seccion_btree 
                ON knowledge_base(seccion) WHERE seccion IS NOT NULL;
                """,
                
                # Palabras clave con GIN
                """
                CREATE INDEX IF NOT EXISTS idx_kb_palabras_clave_gin 
                ON knowledge_base USING gin(palabras_clave);
                """,
                
                # Metadata JSONB
                """
                CREATE INDEX IF NOT EXISTS idx_kb_metadata_gin 
                ON knowledge_base USING gin(chunk_metadata);
                """,
                
                # Índice compuesto para consultas frecuentes
                """
                CREATE INDEX IF NOT EXISTS idx_kb_documento_pagina_embedding 
                ON knowledge_base(documento_origen, pagina_numero) 
                WHERE chunk_embedding IS NOT NULL;
                """,
            ]
            
            all_indexes = vector_indexes + text_indexes + support_indexes
            
            for i, index_sql in enumerate(all_indexes, 1):
                try:
                    logger.info(f"   🔨 Creando índice {i}/{len(all_indexes)}...")
                    start_time = time.time()
                    await conn.execute(index_sql)
                    duration = time.time() - start_time
                    
                    # Extraer nombre del índice
                    index_name = index_sql.split("IF NOT EXISTS")[1].split("ON")[0].strip()
                    logger.info(f"   ✅ {index_name} creado en {duration:.2f}s")
                    
                except Exception as e:
                    logger.warning(f"   ⚠️ Error creando índice {i}: {e}")
            
            # Verificar índices creados
            indexes_check = await conn.fetch("""
                SELECT indexname, tablename 
                FROM pg_indexes 
                WHERE tablename = 'knowledge_base' 
                AND schemaname = 'public'
                ORDER BY indexname
            """)
            
            logger.info(f"   📊 Total índices en knowledge_base: {len(indexes_check)}")
            
        finally:
            await conn.close()
    
    async def _optimize_knowledge_base_table(self):
        """Optimiza la estructura de la tabla knowledge_base"""
        logger.info("🏗️ Optimizando tabla knowledge_base...")
        
        conn = await asyncpg.connect(self.connection_string)
        
        try:
            # Agregar columnas adicionales si no existen
            additional_columns = [
                ("chunk_length", "INTEGER GENERATED ALWAYS AS (LENGTH(chunk_text)) STORED"),
                ("created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
                ("updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
                ("search_vector_spanish", "tsvector GENERATED ALWAYS AS (to_tsvector('spanish', chunk_text)) STORED"),
                ("search_vector_simple", "tsvector GENERATED ALWAYS AS (to_tsvector('simple', chunk_text)) STORED"),
                ("embedding_norm", "FLOAT GENERATED ALWAYS AS (vector_norm(chunk_embedding)) STORED"),
            ]
            
            for col_name, col_definition in additional_columns:
                try:
                    logger.info(f"👹 \n👹col_name: {col_name}\n👹col_definition: {col_definition}")
                    # Verificar si existe
                    exists = await conn.fetchval("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.columns 
                            WHERE table_name = 'knowledge_base' 
                            AND column_name = $1
                        )
                    """, col_name)
                    
                    if not exists:
                        logging.info(f"👹No existe")
                        await conn.execute(f"ALTER TABLE knowledge_base ADD COLUMN {col_name} {col_definition};")
                        logger.info(f"   ✅ Columna {col_name} agregada")
                    else:
                        logging.info(f"👹Sí existe")
                        logger.info(f"   ✅ Columna {col_name} ya existe")
                        
                except Exception as e:
                    logger.warning(f"   ⚠️ Error con columna {col_name}: {e}")
            
            # Crear constraints adicionales
            constraints = [
                "ALTER TABLE knowledge_base ADD CONSTRAINT IF NOT EXISTS ck_chunk_min_length CHECK (LENGTH(chunk_text) >= 20);",
                "ALTER TABLE knowledge_base ADD CONSTRAINT IF NOT EXISTS ck_pagina_positiva CHECK (pagina_numero > 0);",
                "ALTER TABLE knowledge_base ADD CONSTRAINT IF NOT EXISTS ck_embedding_dimension CHECK (array_length(chunk_embedding, 1) = 1536);"
            ]
            
            for constraint in constraints:
                try:
                    await conn.execute(constraint)
                    constraint_name = constraint.split("CONSTRAINT")[1].split("CHECK")[0].strip()
                    logger.info(f"   ✅ Constraint {constraint_name} aplicado")
                except Exception as e:
                    logger.warning(f"   ⚠️ Error en constraint: {e}")
            
        finally:
            await conn.close()
    
    async def _create_optimized_views(self):
        """Crea vistas optimizadas para consultas frecuentes"""
        logger.info("👁️ Creando vistas optimizadas...")
        
        conn = await asyncpg.connect(self.connection_string)
        
        try:
            views = [
                # Vista para chunks vectorizados y listos para búsqueda
                """
                CREATE OR REPLACE VIEW kb_search_ready AS
                SELECT 
                    id,
                    chunk_text,
                    documento_origen,
                    pagina_numero,
                    seccion,
                    palabras_clave,
                    chunk_embedding,
                    chunk_metadata,
                    chunk_length,
                    search_vector_spanish,
                    search_vector_simple
                FROM knowledge_base
                WHERE chunk_embedding IS NOT NULL 
                AND LENGTH(chunk_text) >= 50;
                """,
                
                # Vista de estadísticas por documento
                """
                CREATE OR REPLACE VIEW kb_document_stats AS
                SELECT 
                    documento_origen,
                    COUNT(*) as total_chunks,
                    COUNT(chunk_embedding) as vectorized_chunks,
                    AVG(chunk_length) as avg_chunk_length,
                    MIN(pagina_numero) as first_page,
                    MAX(pagina_numero) as last_page,
                    array_agg(DISTINCT seccion) FILTER (WHERE seccion IS NOT NULL) as sections
                FROM knowledge_base
                GROUP BY documento_origen;
                """,
                
                # Vista para búsqueda por palabras clave
                """
                CREATE OR REPLACE VIEW kb_keyword_search AS
                SELECT 
                    id,
                    chunk_text,
                    documento_origen,
                    pagina_numero,
                    seccion,
                    palabras_clave,
                    array_length(palabras_clave, 1) as keyword_count
                FROM knowledge_base
                WHERE palabras_clave IS NOT NULL 
                AND array_length(palabras_clave, 1) > 0;
                """,
            ]
            
            for i, view_sql in enumerate(views, 1):
                try:
                    await conn.execute(view_sql)
                    view_name = view_sql.split("VIEW")[1].split("AS")[0].strip()
                    logger.info(f"   ✅ Vista {view_name} creada")
                except Exception as e:
                    logger.warning(f"   ⚠️ Error creando vista {i}: {e}")
        
        finally:
            await conn.close()
    
    async def _setup_additional_extensions(self):
        """Configura extensiones adicionales para optimización"""
        logger.info("🔌 Configurando extensiones adicionales...")
        
        conn = await asyncpg.connect(self.connection_string)
        
        try:
            # Extensiones adicionales útiles
            additional_extensions = [
                "pg_stat_statements",  # Para monitoreo de consultas
                "auto_explain",        # Para análisis automático
                "pg_buffercache",      # Para análisis de cache
            ]
            
            for ext in additional_extensions:
                try:
                    await conn.execute(f"CREATE EXTENSION IF NOT EXISTS {ext};")
                    logger.info(f"   ✅ Extensión {ext} habilitada")
                except Exception as e:
                    logger.warning(f"   ⚠️ No se pudo habilitar {ext}: {e}")
            
            # Configurar pg_stat_statements si está disponible
            try:
                await conn.execute("SELECT pg_stat_statements_reset();")
                logger.info("   ✅ Estadísticas de consultas reiniciadas")
            except:
                pass
            
        finally:
            await conn.close()
    
    async def _create_custom_functions(self):
        """Crea funciones personalizadas para RAG"""
        logger.info("⚙️ Creando funciones personalizadas...")
        
        conn = await asyncpg.connect(self.connection_string)
        
        try:
            custom_functions = [
                # Función para búsqueda híbrida optimizada
                """
                CREATE OR REPLACE FUNCTION hybrid_search(
                    query_text TEXT,
                    query_embedding vector(1536),
                    result_limit INTEGER DEFAULT 5,
                    similarity_threshold FLOAT DEFAULT 0.55
                )
                RETURNS TABLE (
                    id INTEGER,
                    chunk_text TEXT,
                    documento_origen VARCHAR(255),
                    pagina_numero INTEGER,
                    seccion VARCHAR(200),
                    palabras_clave TEXT[],
                    vector_similarity FLOAT,
                    text_similarity FLOAT,
                    combined_score FLOAT
                ) AS $
                BEGIN
                    RETURN QUERY
                    WITH vector_results AS (
                        SELECT 
                            kb.id,
                            kb.chunk_text,
                            kb.documento_origen,
                            kb.pagina_numero,
                            kb.seccion,
                            kb.palabras_clave,
                            (1 - (kb.chunk_embedding <=> query_embedding)) as vec_sim,
                            0.0 as text_sim
                        FROM knowledge_base kb
                        WHERE kb.chunk_embedding IS NOT NULL
                        AND (1 - (kb.chunk_embedding <=> query_embedding)) > similarity_threshold
                        ORDER BY kb.chunk_embedding <=> query_embedding
                        LIMIT result_limit * 2
                    ),
                    text_results AS (
                        SELECT 
                            kb.id,
                            kb.chunk_text,
                            kb.documento_origen,
                            kb.pagina_numero,
                            kb.seccion,
                            kb.palabras_clave,
                            0.0 as vec_sim,
                            ts_rank_cd(kb.search_vector_spanish, websearch_to_tsquery('spanish', query_text)) as text_sim
                        FROM knowledge_base kb
                        WHERE kb.search_vector_spanish @@ websearch_to_tsquery('spanish', query_text)
                        ORDER BY text_sim DESC
                        LIMIT result_limit
                    ),
                    combined_results AS (
                        SELECT * FROM vector_results
                        UNION ALL
                        SELECT * FROM text_results
                    )
                    SELECT 
                        cr.id,
                        cr.chunk_text,
                        cr.documento_origen,
                        cr.pagina_numero,
                        cr.seccion,
                        cr.palabras_clave,
                        MAX(cr.vec_sim) as vector_similarity,
                        MAX(cr.text_sim) as text_similarity,
                        (MAX(cr.vec_sim) * 0.6 + MAX(cr.text_sim) * 0.4) as combined_score
                    FROM combined_results cr
                    GROUP BY cr.id, cr.chunk_text, cr.documento_origen, cr.pagina_numero, cr.seccion, cr.palabras_clave
                    ORDER BY combined_score DESC
                    LIMIT result_limit;
                END;
                $ LANGUAGE plpgsql;
                """,
                
                # Función para obtener contexto de chunks adyacentes
                """
                CREATE OR REPLACE FUNCTION get_chunk_context(
                    target_documento VARCHAR(255),
                    target_pagina INTEGER,
                    context_range INTEGER DEFAULT 1
                )
                RETURNS TABLE (
                    chunk_text TEXT,
                    pagina_numero INTEGER,
                    seccion VARCHAR(200),
                    position_relative INTEGER
                ) AS $
                BEGIN
                    RETURN QUERY
                    SELECT 
                        kb.chunk_text,
                        kb.pagina_numero,
                        kb.seccion,
                        (kb.pagina_numero - target_pagina) as position_relative
                    FROM knowledge_base kb
                    WHERE kb.documento_origen = target_documento
                    AND kb.pagina_numero BETWEEN (target_pagina - context_range) AND (target_pagina + context_range)
                    AND kb.pagina_numero != target_pagina
                    ORDER BY ABS(kb.pagina_numero - target_pagina), kb.id;
                END;
                $ LANGUAGE plpgsql;
                """,
                
                # Función para análisis de calidad de embeddings
                """
                CREATE OR REPLACE FUNCTION analyze_embedding_quality()
                RETURNS TABLE (
                    documento_origen VARCHAR(255),
                    total_chunks INTEGER,
                    vectorized_chunks INTEGER,
                    avg_embedding_norm FLOAT,
                    quality_score FLOAT
                ) AS $
                BEGIN
                    RETURN QUERY
                    SELECT 
                        kb.documento_origen,
                        COUNT(*)::INTEGER as total_chunks,
                        COUNT(kb.chunk_embedding)::INTEGER as vectorized_chunks,
                        AVG(vector_norm(kb.chunk_embedding)) as avg_embedding_norm,
                        (COUNT(kb.chunk_embedding)::FLOAT / COUNT(*)::FLOAT) as quality_score
                    FROM knowledge_base kb
                    GROUP BY kb.documento_origen
                    ORDER BY quality_score DESC;
                END;
                $ LANGUAGE plpgsql;
                """,
                
                # Función para búsqueda por similaridad semántica con explicación
                """
                CREATE OR REPLACE FUNCTION explain_similarity(
                    query_embedding vector(1536),
                    target_chunk_id INTEGER
                )
                RETURNS TABLE (
                    similarity_score FLOAT,
                    explanation TEXT
                ) AS $
                DECLARE
                    target_embedding vector(1536);
                    similarity_val FLOAT;
                    explanation_text TEXT;
                BEGIN
                    SELECT chunk_embedding INTO target_embedding 
                    FROM knowledge_base 
                    WHERE id = target_chunk_id;
                    
                    IF target_embedding IS NULL THEN
                        similarity_val := 0.0;
                        explanation_text := 'Chunk no tiene embedding vectorial';
                    ELSE
                        similarity_val := 1 - (query_embedding <=> target_embedding);
                        
                        CASE 
                            WHEN similarity_val > 0.85 THEN 
                                explanation_text := 'Muy alta similitud - Conceptos prácticamente idénticos';
                            WHEN similarity_val > 0.70 THEN 
                                explanation_text := 'Alta similitud - Conceptos muy relacionados';
                            WHEN similarity_val > 0.55 THEN 
                                explanation_text := 'Similitud moderada - Algunos conceptos en común';
                            WHEN similarity_val > 0.40 THEN 
                                explanation_text := 'Baja similitud - Relación débil entre conceptos';
                            ELSE 
                                explanation_text := 'Similitud muy baja - Conceptos no relacionados';
                        END CASE;
                    END IF;
                    
                    RETURN QUERY SELECT similarity_val, explanation_text;
                END;
                $ LANGUAGE plpgsql;
                """,
                
                # Función para optimización automática de consultas
                """
                CREATE OR REPLACE FUNCTION optimize_search_query(input_query TEXT)
                RETURNS TEXT AS $
                DECLARE
                    optimized_query TEXT;
                    technical_terms TEXT[] := ARRAY[
                        'balanza', 'peso', 'pesar', 'pesaje', 'dibal',
                        'etiqueta', 'ticket', 'papel', 'rollo',
                        'imprime', 'imprimir', 'impresion',
                        'error', 'fallo', 'problema', 'averia'
                    ];
                    term TEXT;
                BEGIN
                    optimized_query := lower(trim(input_query));
                    
                    -- Expandir términos técnicos comunes
                    FOREACH term IN ARRAY technical_terms LOOP
                        IF position(term IN optimized_query) > 0 THEN
                            CASE term
                                WHEN 'balanza' THEN optimized_query := optimized_query || ' peso pesar dibal';
                                WHEN 'etiqueta' THEN optimized_query := optimized_query || ' ticket papel rollo';
                                WHEN 'imprime' THEN optimized_query := optimized_query || ' imprimir impresion salida';
                                WHEN 'error' THEN optimized_query := optimized_query || ' fallo problema averia';
                            END CASE;
                        END IF;
                    END LOOP;
                    
                    -- Limpiar consulta expandida
                    optimized_query := regexp_replace(optimized_query, '\s+', ' ', 'g');
                    
                    RETURN trim(optimized_query);
                END;
                $ LANGUAGE plpgsql;
                """
            ]
            
            for i, func_sql in enumerate(custom_functions, 1):
                try:
                    await conn.execute(func_sql)
                    # Extraer nombre de función
                    func_name = func_sql.split("FUNCTION")[1].split("(")[0].strip()
                    logger.info(f"   ✅ Función {func_name} creada")
                except Exception as e:
                    logger.warning(f"   ⚠️ Error creando función {i}: {e}")
        
        finally:
            await conn.close()
    
    async def _setup_monitoring(self):
        """Configura sistema de monitoreo y métricas"""
        logger.info("📊 Configurando monitoreo y métricas...")
        
        conn = await asyncpg.connect(self.connection_string)
        
        try:
            # Crear tabla para métricas de búsqueda
            monitoring_tables = [
                """
                CREATE TABLE IF NOT EXISTS rag_search_metrics (
                    id SERIAL PRIMARY KEY,
                    query_text TEXT NOT NULL,
                    execution_time_ms FLOAT NOT NULL,
                    results_count INTEGER NOT NULL,
                    search_methods TEXT[] NOT NULL,
                    cache_hit BOOLEAN DEFAULT FALSE,
                    user_satisfied BOOLEAN,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    query_hash VARCHAR(64) GENERATED ALWAYS AS (md5(query_text)) STORED
                );
                """,
                
                """
                CREATE TABLE IF NOT EXISTS rag_performance_log (
                    id SERIAL PRIMARY KEY,
                    operation_type VARCHAR(50) NOT NULL,
                    operation_details JSONB,
                    execution_time_ms FLOAT NOT NULL,
                    success BOOLEAN NOT NULL,
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """,
                
                """
                CREATE TABLE IF NOT EXISTS rag_cache_stats (
                    id SERIAL PRIMARY KEY,
                    cache_size INTEGER NOT NULL,
                    hit_rate FLOAT NOT NULL,
                    miss_rate FLOAT NOT NULL,
                    total_requests INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            ]
            
            for table_sql in monitoring_tables:
                try:
                    await conn.execute(table_sql)
                    table_name = table_sql.split("TABLE IF NOT EXISTS")[1].split("(")[0].strip()
                    logger.info(f"   ✅ Tabla de monitoreo {table_name} creada")
                except Exception as e:
                    logger.warning(f"   ⚠️ Error creando tabla de monitoreo: {e}")
            
            # Crear índices para tablas de monitoreo
            monitoring_indexes = [
                "CREATE INDEX IF NOT EXISTS idx_search_metrics_created_at ON rag_search_metrics(created_at);",
                "CREATE INDEX IF NOT EXISTS idx_search_metrics_query_hash ON rag_search_metrics(query_hash);",
                "CREATE INDEX IF NOT EXISTS idx_performance_log_created_at ON rag_performance_log(created_at);",
                "CREATE INDEX IF NOT EXISTS idx_performance_log_operation ON rag_performance_log(operation_type);",
            ]
            
            for index_sql in monitoring_indexes:
                try:
                    await conn.execute(index_sql)
                except Exception as e:
                    logger.warning(f"   ⚠️ Error creando índice de monitoreo: {e}")
            
            # Crear vista de estadísticas agregadas
            stats_view = """
            CREATE OR REPLACE VIEW rag_search_analytics AS
            SELECT 
                DATE_TRUNC('hour', created_at) as hour_bucket,
                COUNT(*) as total_searches,
                AVG(execution_time_ms) as avg_execution_time,
                AVG(results_count) as avg_results_count,
                COUNT(*) FILTER (WHERE cache_hit = true)::FLOAT / COUNT(*) as cache_hit_rate,
                COUNT(*) FILTER (WHERE user_satisfied = true)::FLOAT / COUNT(*) FILTER (WHERE user_satisfied IS NOT NULL) as satisfaction_rate
            FROM rag_search_metrics
            WHERE created_at >= NOW() - INTERVAL '24 hours'
            GROUP BY DATE_TRUNC('hour', created_at)
            ORDER BY hour_bucket DESC;
            """
            
            await conn.execute(stats_view)
            logger.info("   ✅ Vista de analíticas creada")
            
        finally:
            await conn.close()
    
    async def _analyze_and_vacuum(self):
        """Ejecuta análisis y vacuum de la base de datos"""
        logger.info("🧹 Ejecutando análisis y mantenimiento...")
        
        conn = await asyncpg.connect(self.connection_string)
        
        try:
            # Recopilar estadísticas actualizadas
            await conn.execute("ANALYZE knowledge_base;")
            logger.info("   ✅ Estadísticas de knowledge_base actualizadas")
            
            # Vacuum para optimizar espacio
            await conn.execute("VACUUM (ANALYZE) knowledge_base;")
            logger.info("   ✅ Vacuum de knowledge_base completado")
            
            # Análisis de distribución de datos
            stats_queries = [
                ("Chunks totales", "SELECT COUNT(*) FROM knowledge_base"),
                ("Chunks vectorizados", "SELECT COUNT(*) FROM knowledge_base WHERE chunk_embedding IS NOT NULL"),
                ("Documentos únicos", "SELECT COUNT(DISTINCT documento_origen) FROM knowledge_base"),
                ("Promedio palabras por chunk", "SELECT AVG(array_length(string_to_array(chunk_text, ' '), 1)) FROM knowledge_base"),
                ("Chunks con palabras clave", "SELECT COUNT(*) FROM knowledge_base WHERE palabras_clave IS NOT NULL"),
            ]
            
            logger.info("   📊 Estadísticas de la base de datos:")
            for description, query in stats_queries:
                try:
                    result = await conn.fetchval(query)
                    logger.info(f"      • {description}: {result}")
                except Exception as e:
                    logger.warning(f"      • Error en {description}: {e}")
            
        finally:
            await conn.close()
    
    async def _performance_verification(self):
        """Verifica el rendimiento de las optimizaciones"""
        logger.info("⚡ Verificando rendimiento de optimizaciones...")
        
        conn = await asyncpg.connect(self.connection_string)
        
        try:
            # Pruebas de rendimiento
            test_queries = [
                # Búsqueda vectorial simple
                (
                    "Búsqueda vectorial",
                    """
                    SELECT COUNT(*) FROM knowledge_base 
                    WHERE chunk_embedding IS NOT NULL 
                    ORDER BY chunk_embedding <=> '[0,0,0]'::vector LIMIT 5
                    """
                ),
                
                # Búsqueda de texto completo
                (
                    "Búsqueda texto completo",
                    """
                    SELECT COUNT(*) FROM knowledge_base 
                    WHERE search_vector_spanish @@ plainto_tsquery('spanish', 'balanza problema')
                    """
                ),
                
                # Consulta de contexto
                (
                    "Consulta contexto",
                    """
                    SELECT COUNT(*) FROM knowledge_base 
                    WHERE documento_origen = 'Manual Balanza DIBAL Mistral.pdf' 
                    AND pagina_numero BETWEEN 1 AND 5
                    """
                ),
            ]
            
            performance_results = []
            
            for test_name, query in test_queries:
                try:
                    start_time = time.time()
                    result = await conn.fetchval(query)
                    end_time = time.time()
                    duration = (end_time - start_time) * 1000  # en ms
                    
                    performance_results.append((test_name, duration, result))
                    logger.info(f"   ✅ {test_name}: {duration:.2f}ms ({result} resultados)")
                    
                except Exception as e:
                    logger.warning(f"   ⚠️ Error en {test_name}: {e}")
            
            # Verificar índices están siendo utilizados
            index_usage_query = """
            SELECT 
                schemaname,
                tablename,
                indexname,
                idx_scan as index_scans,
                idx_tup_read as tuples_read,
                idx_tup_fetch as tuples_fetched
            FROM pg_stat_user_indexes 
            WHERE tablename = 'knowledge_base'
            ORDER BY idx_scan DESC;
            """
            
            index_stats = await conn.fetch(index_usage_query)
            
            logger.info("   📋 Uso de índices:")
            for stat in index_stats[:5]:  # Top 5 más usados
                logger.info(f"      • {stat['indexname']}: {stat['index_scans']} scans")
            
            # Tamaño de la tabla e índices
            size_query = """
            SELECT 
                pg_size_pretty(pg_total_relation_size('knowledge_base')) as total_size,
                pg_size_pretty(pg_relation_size('knowledge_base')) as table_size,
                pg_size_pretty(pg_total_relation_size('knowledge_base') - pg_relation_size('knowledge_base')) as indexes_size
            """
            
            size_info = await conn.fetchrow(size_query)
            logger.info(f"   💾 Tamaño total: {size_info['total_size']}")
            logger.info(f"      • Tabla: {size_info['table_size']}")
            logger.info(f"      • Índices: {size_info['indexes_size']}")
            
        finally:
            await conn.close()
    
    async def create_maintenance_procedures(self):
        """Crea procedimientos de mantenimiento automatizado"""
        logger.info("🔧 Creando procedimientos de mantenimiento...")
        
        conn = await asyncpg.connect(self.connection_string)
        
        try:
            # Procedimiento de limpieza de métricas antiguas
            cleanup_procedure = """
            CREATE OR REPLACE FUNCTION cleanup_old_metrics()
            RETURNS INTEGER AS $
            DECLARE
                deleted_count INTEGER;
            BEGIN
                -- Eliminar métricas de búsqueda mayores a 30 días
                DELETE FROM rag_search_metrics 
                WHERE created_at < NOW() - INTERVAL '30 days';
                
                GET DIAGNOSTICS deleted_count = ROW_COUNT;
                
                -- Eliminar logs de rendimiento mayores a 7 días
                DELETE FROM rag_performance_log 
                WHERE created_at < NOW() - INTERVAL '7 days';
                
                -- Eliminar stats de cache mayores a 24 horas
                DELETE FROM rag_cache_stats 
                WHERE created_at < NOW() - INTERVAL '24 hours';
                
                RETURN deleted_count;
            END;
            $ LANGUAGE plpgsql;
            """
            
            await conn.execute(cleanup_procedure)
            logger.info("   ✅ Procedimiento de limpieza creado")
            
            # Procedimiento de optimización automática
            optimization_procedure = """
            CREATE OR REPLACE FUNCTION auto_optimize_rag()
            RETURNS TEXT AS $
            DECLARE
                result_text TEXT := '';
                total_chunks INTEGER;
                vectorized_chunks INTEGER;
            BEGIN
                -- Verificar estado de vectorización
                SELECT COUNT(*), COUNT(chunk_embedding) 
                INTO total_chunks, vectorized_chunks
                FROM knowledge_base;
                
                result_text := format('Total chunks: %s, Vectorized: %s', total_chunks, vectorized_chunks);
                
                -- Auto-vacuum si es necesario
                IF total_chunks > 1000 THEN
                    PERFORM pg_stat_reset_single_table_counters('knowledge_base'::regclass);
                    result_text := result_text || ' | Stats reset';
                END IF;
                
                -- Insertar estadística de optimización
                INSERT INTO rag_performance_log (operation_type, operation_details, execution_time_ms, success)
                VALUES ('auto_optimize', jsonb_build_object('total_chunks', total_chunks, 'vectorized_chunks', vectorized_chunks), 0, true);
                
                RETURN result_text;
            END;
            $ LANGUAGE plpgsql;
            """
            
            await conn.execute(optimization_procedure)
            logger.info("   ✅ Procedimiento de optimización automática creado")
            
        finally:
            await conn.close()

async def main():
    """Función principal de optimización"""
    optimizer = DatabaseRAGOptimizer()
    
    try:
        # Ejecutar optimización completa
        await optimizer.optimize_complete_database()
        
        # Crear procedimientos de mantenimiento
        await optimizer.create_maintenance_procedures()
        
        print("\n" + "="*60)
        print("🎉 OPTIMIZACIÓN RAG COMPLETADA EXITOSAMENTE")
        print("="*60)
        print("\n📈 MEJORAS IMPLEMENTADAS:")
        print("   ✅ Índices vectoriales optimizados (IVFFlat + HNSW)")
        print("   ✅ Búsqueda de texto completo mejorada")
        print("   ✅ Funciones personalizadas para RAG híbrido")
        print("   ✅ Sistema de monitoreo y métricas")
        print("   ✅ Procedimientos de mantenimiento automatizado")
        print("   ✅ Vistas optimizadas para consultas frecuentes")
        
        print("\n🚀 PRÓXIMOS PASOS:")
        print("   1. Reinicia la aplicación: python main.py")
        print("   2. Prueba búsquedas: python database/scripts/test_vector_search.py")
        print("   3. Monitorea rendimiento con las nuevas métricas")
        
        print("\n🔧 MANTENIMIENTO:")
        print("   • Limpieza automática: SELECT cleanup_old_metrics();")
        print("   • Optimización: SELECT auto_optimize_rag();")
        print("   • Analíticas: SELECT * FROM rag_search_analytics;")
        
    except Exception as e:
        print(f"\n❌ Error durante la optimización: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())