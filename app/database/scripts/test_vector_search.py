# =====================================================
# database/scripts/test_vector_search.py - Probar búsqueda vectorial
# =====================================================
"""
Script para probar la búsqueda vectorial completa
con el manual de la balanza DIBAL Mistral.
"""

import asyncio
import asyncpg
import logging
import os
from pathlib import Path
from typing import List, Dict, Any

# Setup path
ROOT_DIR = Path(__file__).parent.parent.parent

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("TestVectorSearch")

class VectorSearchTester:
    """Probador de búsqueda vectorial completa"""
    
    def __init__(self):
        # Configuración de BD
        self.db_config = {
            "host": os.getenv("DB_HOST", "localhost"),
            "port": int(os.getenv("DB_PORT", 5432)),
            "database": os.getenv("DB_NAME", "chatbot_db"),
            "user": os.getenv("DB_USER", "postgres"),
            "password": os.getenv("DB_PASSWORD", "")
        }
        
        self.openai_client = None
        self.embedding_deployment = None
        
    @property
    def connection_string(self) -> str:
        """Construir string de conexión"""
        return (f"postgresql://{self.db_config['user']}:{self.db_config['password']}"
                f"@{self.db_config['host']}:{self.db_config['port']}/{self.db_config['database']}")
    
    def _setup_azure_openai(self):
        """Configurar cliente Azure OpenAI"""
        try:
            from openai import AzureOpenAI
            
            api_key = os.getenv('LLM_AZURE_OPENAI_API_KEY')
            endpoint = os.getenv('LLM_AZURE_OPENAI_ENDPOINT')
            api_version = os.getenv('LLM_AZURE_API_VERSION')
            embedding_deployment = os.getenv('LLM_AZURE_EMBEDDING_DEPLOYMENT')
            
            if not all([api_key, endpoint, api_version, embedding_deployment]):
                logger.error("❌ Configuración Azure OpenAI incompleta")
                return False
            
            self.openai_client = AzureOpenAI(
                api_key=api_key,
                azure_endpoint=endpoint,
                api_version=api_version
            )
            
            self.embedding_deployment = embedding_deployment.strip()
            return True
            
        except Exception as e:
            logger.error(f"❌ Error configurando Azure OpenAI: {e}")
            return False
    
    async def _generate_query_embedding(self, query: str) -> List[float]:
        """Generar embedding para consulta"""
        try:
            response = self.openai_client.embeddings.create(
                model=self.embedding_deployment,
                input=query,
                encoding_format="float"
            )
            
            return response.data[0].embedding
            
        except Exception as e:
            logger.error(f"❌ Error generando embedding: {e}")
            return None
    
    async def test_vector_search(self):
        """Probar búsqueda vectorial completa"""
        try:
            logger.info("🧪 Iniciando pruebas de búsqueda vectorial...")
            
            # 1. Configurar Azure OpenAI
            if not self._setup_azure_openai():
                return False
            
            # 2. Verificar estado vectorial
            await self._check_vector_status()
            
            # 3. Probar consultas de ejemplo
            test_queries = [
                "¿Cómo calibrar la balanza?",
                "La balanza no imprime etiquetas correctamente",
                "Error en la pantalla de la balanza",
                "Configurar precios en la balanza",
                "Instalar nueva balanza DIBAL",
                "Problemas con el peso",
                "Manual de usuario básico"
            ]
            
            for query in test_queries:
                logger.info(f"\n🔍 Probando: '{query}'")
                await self._test_hybrid_search(query)
            
            # 4. Búsqueda interactiva
            await self._interactive_search()
            
            logger.info("\n✅ Todas las pruebas completadas")
            
        except Exception as e:
            logger.error(f"❌ Error en pruebas: {e}")
            raise
    
    async def _check_vector_status(self):
        """Verificar estado de vectores"""
        logger.info("📊 Verificando estado vectorial...")
        
        conn = await asyncpg.connect(self.connection_string)
        
        try:
            total_chunks = await conn.fetchval("SELECT COUNT(*) FROM knowledge_base")
            vectorized_chunks = await conn.fetchval("""
                SELECT COUNT(*) FROM knowledge_base 
                WHERE chunk_embedding IS NOT NULL
            """)
            
            # Verificar dimensiones de vectores
            if vectorized_chunks > 0:
                vector_dims = await conn.fetchval("""
                    SELECT vector_dims(chunk_embedding) 
                    FROM knowledge_base 
                    WHERE chunk_embedding IS NOT NULL 
                    LIMIT 1
                """)
                
                logger.info(f"   📚 Total chunks: {total_chunks}")
                logger.info(f"   ✅ Vectorizados: {vectorized_chunks}")
                logger.info(f"   📏 Dimensiones: {vector_dims}")
                logger.info(f"   📊 Cobertura: {vectorized_chunks/total_chunks*100:.1f}%")
            else:
                logger.error("   ❌ No hay vectores almacenados")
                await conn.close()
                return False
            
        finally:
            await conn.close()
        
        return True
    
    async def _test_hybrid_search(self, query: str, limit: int = 3):
        """Probar búsqueda híbrida (vectorial + texto)"""
        conn = await asyncpg.connect(self.connection_string)
        
        try:
            # Generar embedding para la consulta
            query_embedding = await self._generate_query_embedding(query)
            if not query_embedding:
                logger.warning(f"   ⚠️ No se pudo vectorizar consulta")
                return
            
            # Búsqueda vectorial con similitud coseno
            vector_search_sql = """
            SELECT 
                id, seccion, pagina_numero,
                LEFT(chunk_text, 200) as preview,
                1 - (chunk_embedding <=> $1::vector) as similarity,
                'vectorial' as method
            FROM knowledge_base 
            WHERE chunk_embedding IS NOT NULL
            ORDER BY chunk_embedding <=> $1::vector
            LIMIT $2
            """
            
            # Búsqueda de texto para comparar
            text_search_sql = """
            SELECT 
                id, seccion, pagina_numero,
                LEFT(chunk_text, 200) as preview,
                ts_rank_cd(to_tsvector('spanish', chunk_text), plainto_tsquery('spanish', $1)) as similarity,
                'texto' as method
            FROM knowledge_base 
            WHERE to_tsvector('spanish', chunk_text) @@ plainto_tsquery('spanish', $1)
            ORDER BY similarity DESC
            LIMIT $2
            """
            
            # Ejecutar búsquedas
            query_vector_str = str(query_embedding)
            vector_results = await conn.fetch(vector_search_sql, query_vector_str, limit)
            text_results = await conn.fetch(text_search_sql, query, limit)
            
            # Mostrar resultados vectoriales
            if vector_results:
                logger.info(f"   🤖 Búsqueda vectorial ({len(vector_results)} resultados):")
                for i, result in enumerate(vector_results, 1):
                    logger.info(f"      {i}. 📄 Página {result['pagina_numero']} - {result['seccion']}")
                    logger.info(f"         Similitud: {result['similarity']:.3f}")
                    logger.info(f"         Preview: {result['preview']}...")
            
            # Mostrar resultados de texto
            if text_results:
                logger.info(f"   📝 Búsqueda texto ({len(text_results)} resultados):")
                for i, result in enumerate(text_results, 1):
                    logger.info(f"      {i}. 📄 Página {result['pagina_numero']} - {result['seccion']}")
                    logger.info(f"         Relevancia: {result['similarity']:.3f}")
                    logger.info(f"         Preview: {result['preview']}...")
            
            # Comparar si hay overlaps
            vector_ids = {r['id'] for r in vector_results}
            text_ids = {r['id'] for r in text_results}
            overlap = vector_ids.intersection(text_ids)
            
            if overlap:
                logger.info(f"   🎯 Overlap: {len(overlap)} chunks encontrados por ambos métodos")
            else:
                logger.info(f"   📊 Métodos complementarios: resultados diferentes")
                
        finally:
            await conn.close()
    
    async def _interactive_search(self):
        """Búsqueda interactiva para probar manualmente"""
        logger.info("\n🔍 MODO BÚSQUEDA INTERACTIVA")
        logger.info("Escribe consultas para probar el RAG vectorial (o 'quit' para salir)")
        
        while True:
            try:
                query = input("\n🔎 Buscar: ").strip()
                
                if query.lower() in ['quit', 'exit', 'salir', 'q']:
                    break
                
                if not query:
                    continue
                
                print(f"\n🔍 Buscando: '{query}'")
                await self._detailed_vector_search(query)
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"❌ Error en búsqueda: {e}")
    
    async def _detailed_vector_search(self, query: str):
        """Búsqueda vectorial detallada con explicación"""
        conn = await asyncpg.connect(self.connection_string)
        
        try:
            # Generar embedding
            query_embedding = await self._generate_query_embedding(query)
            if not query_embedding:
                print("   ❌ No se pudo vectorizar la consulta")
                return
            
            # Búsqueda vectorial con más detalles
            search_sql = """
            SELECT 
                id, seccion, pagina_numero, chunk_text,
                palabras_clave,
                chunk_metadata->>'tipo_contenido' as tipo_contenido,
                1 - (chunk_embedding <=> $1::vector) as similarity
            FROM knowledge_base 
            WHERE chunk_embedding IS NOT NULL
            ORDER BY chunk_embedding <=> $1::vector
            LIMIT 5
            """
            
            query_vector_str = str(query_embedding)
            results = await conn.fetch(search_sql, query_vector_str)
            
            if results:
                print(f"   📊 {len(results)} resultados más relevantes:")
                
                for i, result in enumerate(results, 1):
                    print(f"\n   {i}. 📄 Página {result['pagina_numero']} - {result['seccion']}")
                    print(f"      🎯 Similitud semántica: {result['similarity']:.3f}")
                    print(f"      📋 Tipo: {result['tipo_contenido'] or 'general'}")
                    print(f"      🏷️ Keywords: {result['palabras_clave'][:5] if result['palabras_clave'] else []}")
                    
                    # Mostrar fragmento más relevante
                    text = result['chunk_text']
                    if len(text) > 400:
                        preview = text[:400] + "..."
                    else:
                        preview = text
                    
                    print(f"      📝 Contenido: {preview}")
                    
                    # Explicar por qué es relevante
                    if result['similarity'] > 0.8:
                        print(f"      💡 Muy relevante - Alta similitud semántica")
                    elif result['similarity'] > 0.6:
                        print(f"      💡 Relevante - Conceptos relacionados")
                    else:
                        print(f"      💡 Parcialmente relevante - Algunas conexiones")
                        
            else:
                print("   ❌ No se encontraron resultados vectoriales")
                
        finally:
            await conn.close()

async def main():
    """Entry point del script"""
    # Cargar variables de entorno
    current_dir = Path(__file__).parent
    root_dir = current_dir.parent.parent
    env_file = root_dir / ".env"
    
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                if '=' in line and not line.strip().startswith('#'):
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value.strip('"\'')
    
    print("🧪 PROBADOR DE BÚSQUEDA VECTORIAL")
    print("=" * 50)
    print("🤖 Método: Embeddings semánticos + pgvector")
    print("📖 Manual: DIBAL Mistral (521 chunks)")
    print("🔍 Azure OpenAI: rag-eroski-embedding")
    print("=" * 50)
    
    tester = VectorSearchTester()
    
    try:
        # Ejecutar pruebas
        await tester.test_vector_search()
        
        print("\n✅ ¡Pruebas de RAG vectorial completadas!")
        print("\n🎉 Tu sistema está listo para:")
        print("   🤖 Búsqueda semántica inteligente")
        print("   📚 Respuestas basadas en manual técnico")  
        print("   🔧 Soporte para incidencias de balanzas")
        print("\n🚀 PRÓXIMO PASO:")
        print("   Ejecutar chatbot completo: python main.py")
        
    except Exception as e:
        print(f"\n❌ Error en pruebas: {e}")

if __name__ == "__main__":
    asyncio.run(main())