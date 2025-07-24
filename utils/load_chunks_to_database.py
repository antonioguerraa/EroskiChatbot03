# =====================================================
# load_chunks_to_database.py - Cargar chunks locales a PostgreSQL
# =====================================================
"""
Script específico para cargar chunks desde archivo local y guardarlos en PostgreSQL
usando la tabla knowledge_base estándar (compatible).
"""

import asyncio
import asyncpg
import json
import logging
from pathlib import Path
from typing import List, Dict, Any
import sys

# Agregar el directorio raíz al path
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from config.settings import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatabaseChunkLoader:
    """Carga chunks desde archivo local a PostgreSQL"""
    
    def __init__(self):
        self.settings = get_settings()
    
    def _get_connection_string(self) -> str:
        """Construye string de conexión"""
        return f"postgresql://{self.settings.database.user}:{self.settings.database.password or ''}@{self.settings.database.host}:{self.settings.database.port}/{self.settings.database.name}"
    
    async def load_and_save_chunks(self, filepath: str) -> bool:
        """
        Carga chunks desde archivo JSON y los guarda en PostgreSQL
        """
        try:
            print(f"🔄 CARGANDO CHUNKS DESDE ARCHIVO LOCAL")
            print("=" * 45)
            
            # 1. Cargar datos desde archivo
            chunks_data, doc_metadata = await self._load_chunks_from_file(filepath)
            print(f"📁 Cargados {len(chunks_data)} chunks desde archivo")
            
            # 2. Conectar a PostgreSQL
            conn = await asyncpg.connect(self._get_connection_string())
            
            try:
                # 3. Verificar si ya existen chunks de este documento
                existing_count = await conn.fetchval("""
                    SELECT COUNT(*) FROM knowledge_base 
                    WHERE documento_origen = $1
                """, doc_metadata["filename"])
                
                if existing_count > 0:
                    print(f"⚠️ Ya existen {existing_count} chunks de este documento")
                    response = input("¿Deseas reemplazarlos? (s/n): ").lower().strip()
                    if response in ['s', 'si', 'sí', 'y', 'yes']:
                        await conn.execute("""
                            DELETE FROM knowledge_base 
                            WHERE documento_origen = $1
                        """, doc_metadata["filename"])
                        print("🗑️ Chunks anteriores eliminados")
                    else:
                        print("❌ Operación cancelada")
                        return False
                
                # 4. Insertar chunks uno por uno
                print(f"💾 Guardando {len(chunks_data)} chunks en PostgreSQL...")
                
                successful_inserts = 0
                failed_inserts = 0
                
                for i, chunk_data in enumerate(chunks_data, 1):
                    try:
                        # Progress indicator
                        if i % 25 == 0 or i == len(chunks_data):
                            print(f"   🔄 Progreso: {i}/{len(chunks_data)} ({i/len(chunks_data)*100:.1f}%)")
                        
                        await self._insert_single_chunk(conn, chunk_data, doc_metadata)
                        successful_inserts += 1
                        
                    except Exception as e:
                        failed_inserts += 1
                        logger.warning(f"❌ Error insertando chunk {i}: {e}")
                        
                        # Si fallan muchos, parar
                        if failed_inserts > 5:
                            logger.error("❌ Demasiados errores, deteniendo inserción")
                            break
                
                # 5. Reporte final
                print("\n📊 RESULTADOS:")
                print(f"   ✅ Insertados exitosamente: {successful_inserts}")
                print(f"   ❌ Errores: {failed_inserts}")
                print(f"   📈 Tasa de éxito: {successful_inserts/len(chunks_data)*100:.1f}%")
                
                if successful_inserts > 0:
                    print("✅ Chunks guardados en PostgreSQL")
                    return True
                else:
                    print("❌ No se pudo guardar ningún chunk")
                    return False
                
            finally:
                await conn.close()
                
        except Exception as e:
            logger.error(f"❌ Error en proceso: {e}")
            return False
    
    async def _load_chunks_from_file(self, filepath: str) -> tuple:
        """Carga chunks desde archivo JSON o pickle"""
        filepath = Path(filepath)
        
        # Intentar pickle primero (más rápido)
        pickle_file = filepath.with_suffix('.pkl')
        if pickle_file.exists():
            import pickle
            with open(pickle_file, 'rb') as f:
                data = pickle.load(f)
        else:
            # Cargar JSON
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
        
        chunks_data = data["chunks"]
        doc_metadata = data["metadata"]["documento_metadata"]
        
        return chunks_data, doc_metadata
    
    async def _insert_single_chunk(self, conn, chunk_data: Dict, doc_metadata: Dict):
        """Inserta un chunk individual en PostgreSQL"""
        
        # Extraer datos del chunk
        texto_original = chunk_data["texto_original"]
        embedding = chunk_data["embedding"]
        palabras_clave = chunk_data["palabras_clave"]
        entidades_tecnicas = chunk_data.get("entidades_tecnicas", [])
        
        # Metadatos del chunk
        chunk_metadata_dict = chunk_data["chunk_metadata"]
        pagina_numero = chunk_metadata_dict["pagina_numero"]
        seccion_titulo = chunk_metadata_dict["seccion_titulo"]
        tipo_contenido = chunk_metadata_dict["tipo_contenido"]
        
        # Convertir embedding al formato correcto para pgvector
        embedding_str = self._format_embedding_for_pgvector(embedding)
        
        # Preparar metadata completo para JSON
        metadata_completo = {
            "chunk_id": chunk_data["chunk_id"],
            "tipo_contenido": tipo_contenido,
            "nivel_jerarquia": chunk_metadata_dict.get("nivel_jerarquia", 3),
            "confidence_extraccion": chunk_data.get("confidence_extraccion", 0.5),
            "entidades_tecnicas": entidades_tecnicas,
            "documento_metadata": doc_metadata,
            "posicion_en_pagina": chunk_metadata_dict.get("posicion_en_pagina", {}),
            "numero_linea_inicio": chunk_metadata_dict.get("numero_linea_inicio", 0),
            "numero_linea_fin": chunk_metadata_dict.get("numero_linea_fin", 0)
        }
        
        # Insertar en tabla knowledge_base estándar
        await conn.execute("""
            INSERT INTO knowledge_base (
                documento_origen, chunk_text, chunk_embedding,
                pagina_numero, seccion, capitulo, palabras_clave,
                chunk_metadata, created_at
            ) VALUES ($1, $2, $3::vector, $4, $5, $6, $7, $8, CURRENT_TIMESTAMP)
        """,
            doc_metadata["filename"],
            texto_original,
            embedding_str,
            pagina_numero,
            seccion_titulo,
            seccion_titulo,  # Usar seccion como capitulo también
            palabras_clave,
            json.dumps(metadata_completo)
        )
    
    def _format_embedding_for_pgvector(self, embedding: List[float]) -> str:
        """Convierte embedding al formato string requerido por pgvector"""
        if not embedding:
            return "[]"
        
        # Limpiar valores inválidos
        clean_embedding = []
        for val in embedding:
            if isinstance(val, (int, float)) and not (val != val or val == float('inf') or val == float('-inf')):  # Verificar NaN/Inf
                clean_embedding.append(float(val))
            else:
                clean_embedding.append(0.0)
        
        return f"[{', '.join(map(str, clean_embedding))}]"

# =====================================================
# SCRIPT PRINCIPAL
# =====================================================

async def main():
    """Script principal"""
    
    if len(sys.argv) != 2:
        print("USO:")
        print('  python load_chunks_to_database.py "ruta/al/archivo.json"')
        print("\nEJEMPLO:")
        print('  python load_chunks_to_database.py "data/vectorized_chunks/chunks_balanza_Dibal_Mistral_d2161577.json"')
        return
    
    filepath = sys.argv[1]
    
    # Verificar que el archivo existe
    if not Path(filepath).exists():
        print(f"❌ Archivo no encontrado: {filepath}")
        return
    
    # Cargar y guardar
    loader = DatabaseChunkLoader()
    success = await loader.load_and_save_chunks(filepath)
    
    if success:
        print("\n🎉 ¡CHUNKS CARGADOS EXITOSAMENTE!")
        print("\n🚀 PRÓXIMOS PASOS:")
        print("1. 🧪 Probar búsqueda: python database/scripts/test_vector_search.py")
        print("2. 📊 Verificar chunks: python database/scripts/check_vectors_status.py")
        print("3. 🤖 Ejecutar chatbot: python main.py")
    else:
        print("\n❌ Error cargando chunks a la base de datos")

if __name__ == "__main__":
    asyncio.run(main())