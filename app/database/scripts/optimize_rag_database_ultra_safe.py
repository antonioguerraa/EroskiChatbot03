# =====================================================
# scripts/optimize_rag_database_ultra_safe.py - Versión ultra segura sin bloqueos
# =====================================================
"""
Script ultra seguro para optimizar RAG que evita todos los bloqueos posibles.
Usa timeouts cortos y manejo robusto de errores.
"""

import asyncio
import asyncpg
import logging
import os
import sys
from pathlib import Path
from typing import Dict, Any, List

# Setup path
ROOT_DIR = Path(__file__).parent.parent  # Subir dos niveles: scripts -> raíz
sys.path.insert(0, str(ROOT_DIR))

from config.settings import get_settings

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("OptimizeRAGUltraSafe")

class RAGDatabaseOptimizerUltraSafe:
    """Optimizador ultra seguro que evita bloqueos"""
    
    def __init__(self):
        self.settings = get_settings()
        self.timeout_seconds = 30  # Timeout corto para evitar bloqueos
        
    @property
    def connection_string(self) -> str:
        """Construir string de conexión"""
        db_config = self.settings.database
        return (
            f"postgresql://{db_config.user}:{db_config.password}"
            f"@{db_config.host}:{db_config.port}/{db_config.name}"
        )
    
    async def optimize_database(self):
        """Proceso completo de optimización ultra seguro"""
        try:
            logger.info("🚀 Iniciando optimización ULTRA SEGURA...")
            
            # 1. Verificación rápida
            await self._quick_verify()
            
            # 2. Extensiones (sin timeout)
            await self._ensure_extensions_safe()
            
            # 3. Verificar estructura actual
            current_structure = await self._analyze_current_structure()
            
            # 4. Solo agregar lo que falta (operaciones mínimas)
            await self._add_missing_components(current_structure)
            
            # 5. Crear índices de forma segura
            await self._create_indexes_safe()
            
            # 6. Verificación final rápida
            await self._final_verification()
            
            logger.info("✅ Optimización ULTRA SEGURA completada")
            
        except Exception as e:
            logger.error(f"❌ Error en optimización: {e}")
            raise
    
    async def _quick_verify(self):
        """Verificación rápida de conexión"""
        logger.info("⚡ Verificación rápida...")
        
        try:
            conn = await asyncio.wait_for(
                asyncpg.connect(self.connection_string),
                timeout=5.0
            )
            await conn.close()
            logger.info("   ✅ Conexión OK")
        except asyncio.TimeoutError:
            logger.error("   ❌ Timeout de conexión")
            raise
        except Exception as e:
            logger.error(f"   ❌ Error de conexión: {e}")
            raise
    
    async def _ensure_extensions_safe(self):
        """Habilitar extensiones de forma segura"""
        logger.info("🔧 Habilitando extensiones (modo seguro)...")
        
        conn = await asyncpg.connect(self.connection_string)
        
        try:
            # Lista de extensiones a verificar/crear
            extensions = ["vector", "pg_trgm", "unaccent"]
            
            for ext_name in extensions:
                try:
                    # Verificar si ya existe
                    exists = await asyncio.wait_for(
                        conn.fetchval(
                            "SELECT EXISTS (SELECT FROM pg_extension WHERE extname = $1)",
                            ext_name
                        ),
                        timeout=5.0
                    )
                    
                    if exists:
                        logger.info(f"   ✅ {ext_name} ya existe")
                    else:
                        # Intentar crear con timeout
                        await asyncio.wait_for(
                            conn.execute(f"CREATE EXTENSION IF NOT EXISTS {ext_name};"),
                            timeout=10.0
                        )
                        logger.info(f"   ✅ {ext_name} creada")
                        
                except asyncio.TimeoutError:
                    logger.warning(f"   ⏰ Timeout creando {ext_name}")
                except Exception as e:
                    logger.warning(f"   ⚠️ {ext_name}: {e}")
            
        finally:
            await conn.close()
    
    async def _analyze_current_structure(self) -> Dict[str, Any]:
        """Analizar estructura actual de forma rápida"""
        logger.info("🔍 Analizando estructura actual...")
        
        conn = await asyncpg.connect(self.connection_string)
        structure = {
            "knowledge_base_exists": False,
            "existing_columns": [],
            "existing_indexes": [],
            "extensions": []
        }
        
        try:
            # Verificar tabla knowledge_base con timeout
            kb_exists = await asyncio.wait_for(
                conn.fetchval("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'knowledge_base' 
                        AND table_schema = 'public'
                    )
                """),
                timeout=10.0
            )
            
            structure["knowledge_base_exists"] = kb_exists
            logger.info(f"   📋 knowledge_base existe: {kb_exists}")
            
            if kb_exists:
                # Obtener columnas existentes con timeout
                columns = await asyncio.wait_for(
                    conn.fetch("""
                        SELECT column_name 
                        FROM information_schema.columns 
                        WHERE table_name = 'knowledge_base'
                        AND table_schema = 'public'
                    """),
                    timeout=10.0
                )
                
                structure["existing_columns"] = [col['column_name'] for col in columns]
                logger.info(f"   📝 Columnas existentes: {len(structure['existing_columns'])}")
            
            # Verificar extensiones
            extensions = await asyncio.wait_for(
                conn.fetch("""
                    SELECT extname FROM pg_extension 
                    WHERE extname IN ('vector', 'pg_trgm', 'unaccent')
                """),
                timeout=5.0
            )
            
            structure["extensions"] = [ext['extname'] for ext in extensions]
            logger.info(f"   🔧 Extensiones: {structure['extensions']}")
            
        except asyncio.TimeoutError:
            logger.warning("   ⏰ Timeout analizando estructura")
        except Exception as e:
            logger.warning(f"   ⚠️ Error analizando: {e}")
        
        finally:
            await conn.close()
        
        return structure
    
    async def _add_missing_components(self, structure: Dict[str, Any]):
        """Agregar solo componentes faltantes"""
        logger.info("➕ Agregando componentes faltantes...")
        
        if not structure["knowledge_base_exists"]:
            logger.info("   🏗️ Creando tabla knowledge_base...")
            await self._create_knowledge_base_table()
            return
        
        # Solo agregar columnas críticas que falten
        critical_columns = [
            ("created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ("updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ("chunk_length", "INTEGER"),
            ("tipo_contenido", "VARCHAR(50)")
        ]
        
        conn = await asyncpg.connect(self.connection_string)
        
        try:
            existing_cols = set(structure["existing_columns"])
            
            for col_name, col_def in critical_columns:
                if col_name not in existing_cols:
                    try:
                        await asyncio.wait_for(
                            conn.execute(f"ALTER TABLE knowledge_base ADD COLUMN {col_name} {col_def};"),
                            timeout=15.0
                        )
                        logger.info(f"   ✅ Columna {col_name} agregada")
                    except asyncio.TimeoutError:
                        logger.warning(f"   ⏰ Timeout agregando {col_name}")
                        break  # Si hay timeout, parar para evitar más bloqueos
                    except Exception as e:
                        logger.warning(f"   ⚠️ Error con {col_name}: {e}")
                else:
                    logger.info(f"   ✅ Columna {col_name} ya existe")
            
        finally:
            await conn.close()
    
    async def _create_knowledge_base_table(self):
        """Crear tabla knowledge_base completa"""
        logger.info("🏗️ Creando tabla knowledge_base...")
        
        conn = await asyncpg.connect(self.connection_string)
        
        try:
            create_table_sql = """
            CREATE TABLE IF NOT EXISTS knowledge_base (
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
            
            await asyncio.wait_for(
                conn.execute(create_table_sql),
                timeout=30.0
            )
            logger.info("   ✅ Tabla knowledge_base creada")
            
        except asyncio.TimeoutError:
            logger.error("   ⏰ Timeout creando tabla")
            raise
        except Exception as e:
            logger.error(f"   ❌ Error creando tabla: {e}")
            raise
        finally:
            await conn.close()
    
    async def _create_indexes_safe(self):
        """Crear índices de forma segura y gradual"""
        logger.info("📋 Creando índices (modo seguro)...")
        
        # Índices prioritarios (crear primero)
        priority_indexes = [
            ("idx_kb_documento", "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_kb_documento ON knowledge_base(documento_origen);"),
            ("idx_kb_seccion", "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_kb_seccion ON knowledge_base(seccion);"),
            ("idx_kb_pagina", "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_kb_pagina ON knowledge_base(pagina_numero);"),
        ]
        
        # Índices de texto (crear después)
        text_indexes = [
            ("idx_kb_texto_spanish", "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_kb_texto_spanish ON knowledge_base USING gin(to_tsvector('spanish', chunk_text));"),
            ("idx_kb_palabras_clave", "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_kb_palabras_clave ON knowledge_base USING gin(palabras_clave);"),
        ]
        
        # Índices vectoriales (solo si vector está disponible)
        vector_indexes = [
            ("idx_kb_embedding_cosine", "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_kb_embedding_cosine ON knowledge_base USING ivfflat (chunk_embedding vector_cosine_ops) WITH (lists = 100);"),
        ]
        
        all_indexes = priority_indexes + text_indexes
        
        # Agregar vectoriales si la extensión está disponible
        conn = await asyncpg.connect(self.connection_string)
        try:
            vector_available = await conn.fetchval(
                "SELECT EXISTS (SELECT FROM pg_extension WHERE extname = 'vector')"
            )
            if vector_available:
                all_indexes.extend(vector_indexes)
                logger.info("   🎯 Incluyendo índices vectoriales")
        finally:
            await conn.close()
        
        # Crear índices uno por uno con timeouts
        for idx_name, idx_sql in all_indexes:
            await self._create_single_index_safe(idx_name, idx_sql)
    
    async def _create_single_index_safe(self, idx_name: str, idx_sql: str):
        """Crear un índice individual de forma segura"""
        conn = await asyncpg.connect(self.connection_string)
        
        try:
            # Verificar si ya existe
            exists = await asyncio.wait_for(
                conn.fetchval("""
                    SELECT EXISTS (
                        SELECT FROM pg_indexes 
                        WHERE indexname = $1
                    )
                """, idx_name),
                timeout=5.0
            )
            
            if exists:
                logger.info(f"   ✅ {idx_name} ya existe")
                return
            
            # Crear con timeout largo para índices complejos
            timeout = 60.0 if "gin" in idx_sql or "ivfflat" in idx_sql else 30.0
            
            await asyncio.wait_for(
                conn.execute(idx_sql),
                timeout=timeout
            )
            logger.info(f"   ✅ {idx_name} creado")
            
        except asyncio.TimeoutError:
            logger.warning(f"   ⏰ Timeout creando {idx_name}")
        except Exception as e:
            logger.warning(f"   ⚠️ Error creando {idx_name}: {e}")
        finally:
            await conn.close()
    
    async def _final_verification(self):
        """Verificación final rápida"""
        logger.info("🔍 Verificación final...")
        
        conn = await asyncpg.connect(self.connection_string)
        
        try:
            # Contar registros
            count = await asyncio.wait_for(
                conn.fetchval("SELECT COUNT(*) FROM knowledge_base"),
                timeout=10.0
            )
            logger.info(f"   📊 Chunks: {count}")
            
            # Contar índices
            indexes = await asyncio.wait_for(
                conn.fetchval("""
                    SELECT COUNT(*) FROM pg_indexes 
                    WHERE tablename = 'knowledge_base'
                """),
                timeout=5.0
            )
            logger.info(f"   📋 Índices: {indexes}")
            
        except asyncio.TimeoutError:
            logger.warning("   ⏰ Timeout en verificación final")
        except Exception as e:
            logger.warning(f"   ⚠️ Error en verificación: {e}")
        finally:
            await conn.close()

async def main():
    """Entry point del script"""
    print("🛡️ OPTIMIZADOR RAG ULTRA SEGURO")
    print("=" * 50)
    print("⚡ RÁPIDO: Timeouts cortos para evitar bloqueos")
    print("🔒 SEGURO: Operaciones mínimas y robustas")
    print("🎯 EFICIENTE: Solo agrega lo que falta")
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
    
    optimizer = RAGDatabaseOptimizerUltraSafe()
    
    try:
        await optimizer.optimize_database()
        
        print("\n🎉 ¡Optimización ULTRA SEGURA completada!")
        print("\n📚 PRÓXIMOS PASOS:")
        print("1. 📖 Colocar manual: docs/Manual Balanza DIBAL Mistral.pdf")
        print("2. 🔄 Vectorizar: python database/scripts/vectorize_manual.py")
        print("3. 🧪 Probar RAG: python database/scripts/test_vector_search.py")
        
    except Exception as e:
        print(f"\n❌ Error en optimización: {e}")
        print("\n💡 ALTERNATIVA:")
        print("   Puedes proceder directamente a vectorizar el manual:")
        print("   python database/scripts/vectorize_manual.py")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())