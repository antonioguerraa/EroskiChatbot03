# =====================================================
# quick_rag_test.py - Prueba rápida de RAG con threshold bajo
# =====================================================

import asyncio
import asyncpg
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR))

from config.settings import get_settings
from utils.llm.providers import get_vectorizer

async def quick_test():
    settings = get_settings()
    vectorizer = get_vectorizer()
    
    # Conectar a BD
    conn_string = f"postgresql://{settings.database.user}:{settings.database.password or ''}@{settings.database.host}:{settings.database.port}/{settings.database.name}"
    conn = await asyncpg.connect(conn_string)
    
    try:
        # Probar consultas con threshold muy bajo
        test_queries = [
            "menú configuración",
            "calibrar balanza", 
            "menu",
            "calibrar"
        ]
        
        for query in test_queries:
            print(f"\n🔍 Probando: '{query}'")
            
            # Generar embedding
            embedding = vectorizer.embed(query)
            embedding_str = str(embedding)
            
            # Búsqueda con threshold muy bajo (0.3)
            results = await conn.fetch("""
                SELECT 
                    chunk_text,
                    pagina_numero,
                    seccion,
                    palabras_clave,
                    1 - (chunk_embedding <=> $1::vector) as similarity
                FROM knowledge_base 
                WHERE chunk_embedding IS NOT NULL
                AND 1 - (chunk_embedding <=> $1::vector) > 0.3
                ORDER BY chunk_embedding <=> $1::vector
                LIMIT 3
            """, embedding_str)
            
            if results:
                print(f"   ✅ {len(results)} resultados encontrados:")
                for i, result in enumerate(results, 1):
                    sim = result['similarity']
                    text_preview = result['chunk_text'][:100] + "..."
                    print(f"      {i}. Similitud: {sim:.3f}")
                    print(f"         Página: {result['pagina_numero']}")
                    print(f"         Keywords: {result['palabras_clave'][:3] if result['palabras_clave'] else []}")
                    print(f"         Texto: {text_preview}")
            else:
                print("   ❌ Sin resultados (incluso con threshold 0.3)")
                
                # Verificar si hay chunks con esas palabras clave
                keyword_check = await conn.fetch("""
                    SELECT COUNT(*) as count, array_agg(DISTINCT pagina_numero) as paginas
                    FROM knowledge_base 
                    WHERE $1 = ANY(palabras_clave) OR chunk_text ILIKE $2
                """, query.split()[0], f"%{query.split()[0]}%")
                
                if keyword_check[0]['count'] > 0:
                    print(f"      💡 Pero HAY {keyword_check[0]['count']} chunks con '{query.split()[0]}'")
                    print(f"         En páginas: {keyword_check[0]['paginas']}")
    
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(quick_test())