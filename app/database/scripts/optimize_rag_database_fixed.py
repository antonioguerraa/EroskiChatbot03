# =====================================================
# scripts/optimize_rag_database_fixed.py - Versión corregida sin columnas GENERATED
# =====================================================
"""
Script optimizado para configurar RAG sin usar columnas GENERATED que pueden causar bloqueos.
Versión compatible con diferentes versiones de PostgreSQL y pgvector.
"""

import asyncio
import asyncpg
import logging
import os
import sys
from pathlib import Path
from typing import Dict, Any

# Setup path
ROOT_DIR = Path(__file__).parent.parent  # Subir dos niveles: scripts -> raíz
sys.path.insert(0, str(ROOT_DIR))

from config.settings import get_settings

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("OptimizeRAG")

class RAGDatabaseOptimizer:
    """Optimizador de base de datos para RAG sin columnas problemáticas"""
    
    def __init__(self):
        self.settings = get_settings()
        
    @property
    def connection_string(self) -> str:
        """Construir string de conexión"""
        db_config = self.settings.database
        return (
            f"postgresql://{db_config.user}:{db_config.password}"
            f"@{db_config.host}:{db_config.port}/{db_config.name}"
        )
    
    async def optimize_database(self):
        """Proceso completo de optimización"""
        try:
            logger.info("🚀 Iniciando optimización de base de datos RAG...")
            
            # 1. Verificar conexión
            await self._verify_connection()
            
            # 2. Verificar y habilitar extensiones
            await self._ensure_extensions()
            
            # 3. Optimizar tabla knowledge_base (versión segura)
            await self._optimize_knowledge_base_table_safe()
            
            # 4. Crear índices optimizados
            await self._create_optimized_indexes()
            
            # 5. Configurar parámetros de búsqueda
            await self._configure_search_parameters()
            
            # 6. Verificar configuración final
            await self._verify_optimization()
            
            logger.info("✅ Optimización completada exitosamente")
            
        except Exception as e:
            logger.error(f"❌ Error en optimización: {e}")
            raise
    
    async def _verify_connection(self):
        """Verificar conexión a la base de datos"""
        logger.info("🔌 Verificando conexión...")
        
        try:
            conn = await asyncpg.connect(self.connection_string)
            await conn.close()
            logger.info("   ✅ Conexión establecida")
        except Exception as e:
            logger.error(f"   ❌ Error de conexión: {e}")
            raise
    
    async def _ensure_extensions(self):
        """Verificar y habilitar extensiones necesarias"""
        logger.info("🔧 Verificando extensiones...")
        
        conn = await asyncpg.connect(self.connection_string)
        
        try:
            # Extensiones necesarias
            extensions = [
                ("vector", "CREATE EXTENSION IF NOT EXISTS vector;"),
                ("pg_trgm", "CREATE EXTENSION IF NOT EXISTS pg_trgm;"),
                ("unaccent", "CREATE EXTENSION IF NOT EXISTS unaccent;")
            ]
            
            for ext_name, ext_sql in extensions:
                try:
                    await conn.execute(ext_sql)
                    logger.info(f"   ✅ {ext_name} habilitada")
                except Exception as e:
                    logger.warning(f"   ⚠️ {ext_name}: {e}")
                    
                    # Si falla vector, continuar sin él
                    if ext_name == "vector":
                        logger.warning("   ⚠️ pgvector no disponible - funcionarán búsquedas de texto")
            
        finally:
            await conn.close()
    
    async def _optimize_knowledge_base_table_safe(self):
        """Optimiza la estructura de knowledge_base de forma segura"""
        logger.info("🏗️ Optimizando tabla knowledge_base (modo seguro)...")
        
        conn = await asyncpg.connect(self.connection_string)
        
        try:
            # Verificar si la tabla existe
            table_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'knowledge_base' 
                    AND table_schema = 'public'
                )
            """)
            
            if not table_exists:
                logger.warning("   ⚠️ Tabla knowledge_base no existe - creándola...")
                await self._create_knowledge_base_table(conn)
                return
            
            # Agregar columnas adicionales simples (SIN GENERATED)
            simple_columns = [
                ("created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
                ("updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
                ("chunk_length", "INTEGER"),  # Sin GENERATED, se actualizará con trigger
                ("tipo_contenido", "VARCHAR(50)"),  # 'texto', 'tabla', 'lista', 'codigo'
                ("relevancia_score", "FLOAT DEFAULT 0.0"),
                ("procesado", "BOOLEAN DEFAULT FALSE")
            ]
            
            for col_name, col_definition in simple_columns:
                try:
                    # Verificar si existe
                    exists = await conn.fetchval("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.columns 
                            WHERE table_name = 'knowledge_base' 
                            AND column_name = $1
                        )
                    """, col_name)
                    
                    if not exists:
                        await conn.execute(f"ALTER TABLE knowledge_base ADD COLUMN {col_name} {col_definition};")
                        logger.info(f"   ✅ Columna {col_name} agregada")
                    else:
                        logger.info(f"   ✅ Columna {col_name} ya existe")
                        
                except Exception as e:
                    logger.warning(f"   ⚠️ Error con columna {col_name}: {e}")
            
            # Crear trigger para actualizar chunk_length automáticamente
            await self._create_length_trigger(conn)
            
        finally:
            await conn.close()
    
    async def _create_knowledge_base_table(self, conn):
        """Crear tabla knowledge_base desde cero"""
        create_table_sql = """
        CREATE TABLE knowledge_base (
            id SERIAL PRIMARY KEY,
            documento_origen VARCHAR(255) NOT NULL,
            chunk_text TEXT NOT NULL,
            chunk_embedding vector(1536),
            chunk_metadata JSONB DEFAULT '{}',
            pagina_numero INTEGER,
            seccion VARCHAR(200),
            capitulo VARCHAR(200),
            palabras_clave TEXT[],
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            chunk_length INTEGER,
            tipo_contenido VARCHAR(50),
            relevancia_score FLOAT DEFAULT 0.0,
            procesado BOOLEAN DEFAULT FALSE,
            
            CONSTRAINT kb_chunk_text_valido CHECK (LENGTH(chunk_text) >= 50)
        );
        """
        
        await conn.execute(create_table_sql)
        logger.info("   ✅ Tabla knowledge_base creada")
    
    async def _create_length_trigger(self, conn):
        """Crear trigger para mantener chunk_length actualizado"""
        try:
            # Crear función de trigger
            trigger_function = """
            CREATE OR REPLACE FUNCTION update_chunk_length()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.chunk_length = LENGTH(NEW.chunk_text);
                NEW.updated_at = CURRENT_TIMESTAMP;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """
            
            await conn.execute(trigger_function)
            
            # Crear trigger
            trigger_sql = """
            DROP TRIGGER IF EXISTS trigger_update_chunk_length ON knowledge_base;
            CREATE TRIGGER trigger_update_chunk_length
                BEFORE INSERT OR UPDATE ON knowledge_base
                FOR EACH ROW
                EXECUTE FUNCTION update_chunk_length();
            """
            
            await conn.execute(trigger_sql)
            logger.info("   ✅ Trigger de longitud creado")
            
        except Exception as e:
            logger.warning(f"   ⚠️ Error creando trigger: {e}")
    
    async def _create_optimized_indexes(self):
        """Crear índices optimizados para búsquedas"""
        logger.info("📋 Creando índices optimizados...")
        
        conn = await asyncpg.connect(self.connection_string)
        
        try:
            # Verificar si pgvector está disponible
            vector_available = await conn.fetchval("""
                SELECT EXISTS (SELECT FROM pg_extension WHERE extname = 'vector')
            """)
            
            indexes = []
            
            # Índices básicos (siempre)
            basic_indexes = [
                "CREATE INDEX IF NOT EXISTS idx_kb_documento ON knowledge_base(documento_origen);",
                "CREATE INDEX IF NOT EXISTS idx_kb_seccion ON knowledge_base(seccion);",
                "CREATE INDEX IF NOT EXISTS idx_kb_pagina ON knowledge_base(pagina_numero);",
                "CREATE INDEX IF NOT EXISTS idx_kb_tipo_contenido ON knowledge_base(tipo_contenido);",
                "CREATE INDEX IF NOT EXISTS idx_kb_relevancia ON knowledge_base(relevancia_score DESC);",
                "CREATE INDEX IF NOT EXISTS idx_kb_procesado ON knowledge_base(procesado);",
                "CREATE INDEX IF NOT EXISTS idx_kb_created_at ON knowledge_base(created_at DESC);",
            ]
            
            indexes.extend(basic_indexes)
            
            # Índices de texto completo
            text_indexes = [
                "CREATE INDEX IF NOT EXISTS idx_kb_texto_spanish ON knowledge_base USING gin(to_tsvector('spanish', chunk_text));",
                "CREATE INDEX IF NOT EXISTS idx_kb_texto_simple ON knowledge_base USING gin(to_tsvector('simple', chunk_text));",
                "CREATE INDEX IF NOT EXISTS idx_kb_palabras_clave ON knowledge_base USING gin(palabras_clave);",
            ]
            
            indexes.extend(text_indexes)
            
            # Índices vectoriales (solo si pgvector disponible)
            if vector_available:
                vector_indexes = [
                    "CREATE INDEX IF NOT EXISTS idx_kb_embedding_cosine ON knowledge_base USING ivfflat (chunk_embedding vector_cosine_ops) WITH (lists = 100);",
                    "CREATE INDEX IF NOT EXISTS idx_kb_embedding_l2 ON knowledge_base USING ivfflat (chunk_embedding vector_l2_ops) WITH (lists = 100);",
                ]
                indexes.extend(vector_indexes)
                logger.info("   ✅ Incluyendo índices vectoriales")
            else:
                logger.info("   ⚠️ Omitiendo índices vectoriales (pgvector no disponible)")
            
            # Crear todos los índices
            for index_sql in indexes:
                try:
                    await conn.execute(index_sql)
                    index_name = index_sql.split()[5]  # Extraer nombre del índice
                    logger.info(f"   ✅ {index_name}")
                except Exception as e:
                    logger.warning(f"   ⚠️ Error creando índice: {e}")
            
        finally:
            await conn.close()
    
    async def _configure_search_parameters(self):
        """Configurar parámetros de búsqueda"""
        logger.info("⚙️ Configurando parámetros de búsqueda...")
        
        conn = await asyncpg.connect(self.connection_string)
        
        try:
            # Configuraciones para mejorar rendimiento
            search_configs = [
                "SET default_text_search_config = 'spanish';",
                "SET shared_preload_libraries = 'vector';",  # Si está disponible
            ]
            
            for config in search_configs:
                try:
                    await conn.execute(config)
                    logger.info(f"   ✅ {config}")
                except Exception as e:
                    logger.warning(f"   ⚠️ {config}: {e}")
            
        finally:
            await conn.close()
    
    async def _verify_optimization(self):
        """Verificar que la optimización fue exitosa"""
        logger.info("🔍 Verificando optimización...")
        
        conn = await asyncpg.connect(self.connection_string)
        
        try:
            # Verificar tabla knowledge_base
            kb_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'knowledge_base'
                )
            """)
            
            if kb_exists:
                # Contar columnas
                columns = await conn.fetch("""
                    SELECT column_name, data_type 
                    FROM information_schema.columns 
                    WHERE table_name = 'knowledge_base'
                    ORDER BY ordinal_position
                """)
                
                logger.info(f"   ✅ knowledge_base: {len(columns)} columnas")
                
                # Verificar índices
                indexes = await conn.fetch("""
                    SELECT indexname FROM pg_indexes 
                    WHERE tablename = 'knowledge_base'
                """)
                
                logger.info(f"   ✅ Índices: {len(indexes)} creados")
                
                # Contar registros
                count = await conn.fetchval("SELECT COUNT(*) FROM knowledge_base")
                logger.info(f"   📊 Chunks almacenados: {count}")
                
            else:
                logger.error("   ❌ Tabla knowledge_base no encontrada")
            
            # Verificar extensiones
            extensions = await conn.fetch("""
                SELECT extname FROM pg_extension 
                WHERE extname IN ('vector', 'pg_trgm', 'unaccent')
            """)
            
            ext_names = [ext['extname'] for ext in extensions]
            logger.info(f"   ✅ Extensiones activas: {ext_names}")
            
        finally:
            await conn.close()

async def main():
    """Entry point del script"""
    print("🚀 OPTIMIZADOR DE BASE DE DATOS RAG")
    print("=" * 50)
    print("🔧 VERSIÓN SEGURA: Sin columnas GENERATED problemáticas")
    print("⚡ OPTIMIZADO: Para búsquedas eficientes")
    print("=" * 50)
    
    # Cargar variables de entorno
    current_dir = Path(__file__).parent
    root_dir = current_dir.parent
    env_file = root_dir / ".env"
    
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                if '=' in line and not line.strip().startswith('#'):
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value.strip('"\'')
    
    optimizer = RAGDatabaseOptimizer()
    
    try:
        await optimizer.optimize_database()
        
        print("\n🎉 ¡Optimización completada exitosamente!")
        print("\n📚 PRÓXIMOS PASOS:")
        print("1. 📖 Colocar manual: docs/Manual Balanza DIBAL Mistral.pdf")
        print("2. 🔄 Vectorizar: python database/scripts/vectorize_manual.py")
        print("3. 🧪 Probar RAG: python database/scripts/test_vector_search.py")
        print("4. 🚀 Ejecutar chatbot: python main.py")
        
    except Exception as e:
        print(f"\n❌ Error en optimización: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())