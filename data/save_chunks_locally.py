# =====================================================
# save_chunks_locally.py - Guardar chunks vectorizados localmente
# =====================================================
"""
Script para guardar los chunks generados por advanced_document_vectorizer
en un archivo local JSON, permitiendo reintentarlo sin re-vectorizar.
"""

import asyncio
import json
import logging
import hashlib
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Tuple
from datetime import datetime
import pickle

# Imports del proyecto
from app.utils.advanced_document_vectorizer import (
    AdvancedDocumentVectorizer,
    DocumentMetadata,
    EnrichedChunk
)

logger = logging.getLogger(__name__)

class ChunkLocalSaver:
    """Gestiona el guardado y carga de chunks desde archivos locales"""
    
    def __init__(self, base_dir: str = "data/vectorized_chunks"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_filename(self, doc_metadata: DocumentMetadata) -> str:
        """Genera nombre de archivo único basado en el documento"""
        # Crear hash único del documento
        unique_id = f"{doc_metadata.filename}_{doc_metadata.tipo_equipo}_{doc_metadata.marca}_{doc_metadata.modelo}"
        hash_id = hashlib.md5(unique_id.encode()).hexdigest()[:8]
        
        # Nombre limpio para archivo
        clean_name = f"{doc_metadata.tipo_equipo}_{doc_metadata.marca}_{doc_metadata.modelo}_{hash_id}"
        return f"chunks_{clean_name}.json"
    
    def _serialize_chunk(self, chunk: EnrichedChunk) -> Dict[str, Any]:
        """Convierte EnrichedChunk a diccionario serializable"""
        return {
            "chunk_id": chunk.chunk_id,
            "texto_original": chunk.texto_original,
            "texto_procesado": chunk.texto_procesado,
            "embedding": chunk.embedding,  # Lista de floats
            "embedding_con_metadatos": chunk.embedding_con_metadatos,
            "documento_metadata": chunk.documento_metadata.to_dict(),
            "chunk_metadata": chunk.chunk_metadata.to_dict(),
            "palabras_clave": chunk.palabras_clave,
            "entidades_tecnicas": chunk.entidades_tecnicas,
            "confidence_extraccion": chunk.confidence_extraccion,
        }
    
    def save_chunks_to_file(
        self, 
        chunks: List[EnrichedChunk], 
        doc_metadata: DocumentMetadata
    ) -> str:
        """
        Guarda chunks en archivo JSON local
        
        Returns:
            str: Ruta del archivo guardado
        """
        try:
            filename = self._get_filename(doc_metadata)
            filepath = self.base_dir / filename
            
            # Preparar datos para guardar
            save_data = {
                "metadata": {
                    "timestamp": datetime.now().isoformat(),
                    "total_chunks": len(chunks),
                    "documento_metadata": doc_metadata.to_dict(),
                    "vectorizer_version": "advanced_v1.0"
                },
                "chunks": [self._serialize_chunk(chunk) for chunk in chunks]
            }
            
            # Guardar como JSON
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(save_data, f, ensure_ascii=False, indent=2)
            
            # También guardar versión comprimida con pickle (más rápida para cargar)
            pickle_file = filepath.with_suffix('.pkl')
            with open(pickle_file, 'wb') as f:
                pickle.dump(save_data, f)
            
            logger.info(f"✅ Chunks guardados en: {filepath}")
            logger.info(f"✅ Versión pickle en: {pickle_file}")
            
            return str(filepath)
            
        except Exception as e:
            logger.error(f"❌ Error guardando chunks: {e}")
            raise
    
    def load_chunks_from_file(self, filepath: str) -> Tuple[List[Dict], DocumentMetadata]:
        """
        Carga chunks desde archivo local
        
        Returns:
            Tuple[List[Dict], DocumentMetadata]: Chunks deserializados y metadatos del documento
        """
        try:
            filepath = Path(filepath)
            
            # Intentar cargar pickle primero (más rápido)
            pickle_file = filepath.with_suffix('.pkl')
            if pickle_file.exists():
                with open(pickle_file, 'rb') as f:
                    data = pickle.load(f)
            else:
                # Cargar JSON
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            
            chunks_data = data["chunks"]
            doc_metadata_dict = data["metadata"]["documento_metadata"]
            
            # Reconstruir DocumentMetadata
            doc_metadata = DocumentMetadata(
                filename=doc_metadata_dict["filename"],
                tipo_equipo=doc_metadata_dict["tipo_equipo"],
                marca=doc_metadata_dict["marca"],
                modelo=doc_metadata_dict["modelo"],
                version_manual=doc_metadata_dict["version_manual"],
                idioma=doc_metadata_dict["idioma"],
                hash_documento=doc_metadata_dict["hash_documento"]
            )
            
            logger.info(f"✅ Cargados {len(chunks_data)} chunks desde: {filepath}")
            
            return chunks_data, doc_metadata
            
        except Exception as e:
            logger.error(f"❌ Error cargando chunks: {e}")
            raise
    
    def list_saved_chunks(self) -> List[Dict[str, Any]]:
        """Lista todos los archivos de chunks guardados"""
        saved_files = []
        
        for json_file in self.base_dir.glob("chunks_*.json"):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                metadata = data["metadata"]
                doc_meta = metadata["documento_metadata"]
                
                saved_files.append({
                    "filepath": str(json_file),
                    "timestamp": metadata["timestamp"],
                    "total_chunks": metadata["total_chunks"],
                    "documento": doc_meta["filename"],
                    "equipo": f"{doc_meta['tipo_equipo']} {doc_meta['marca']} {doc_meta['modelo']}",
                    "size_mb": json_file.stat().st_size / (1024*1024)
                })
                
            except Exception as e:
                logger.warning(f"Error leyendo {json_file}: {e}")
        
        return sorted(saved_files, key=lambda x: x["timestamp"], reverse=True)

# =====================================================
# VECTORIZADOR MODIFICADO CON GUARDADO LOCAL
# =====================================================

async def vectorize_and_save_locally(
    pdf_path: str,
    tipo_equipo: str,
    marca: str,
    modelo: str,
    version: str = "1.0"
):
    """
    Vectoriza documento y guarda chunks localmente
    """
    
    print(f"🔄 VECTORIZANDO Y GUARDANDO LOCALMENTE")
    print("=" * 50)
    
    try:
        # 1. Preparar metadatos del documento
        pdf_file = Path(pdf_path)
        
        doc_metadata = DocumentMetadata(
            filename=pdf_file.name,
            tipo_equipo=tipo_equipo.lower(),
            marca=marca,
            modelo=modelo,
            version_manual=version,
            idioma="es",
            hash_documento=hashlib.md5(pdf_file.read_bytes()).hexdigest()
        )
        
        print(f"📄 Documento: {doc_metadata.filename}")
        print(f"🔧 Equipo: {doc_metadata.tipo_equipo} {doc_metadata.marca} {doc_metadata.modelo}")
        
        # 2. Vectorizar documento
        vectorizer = AdvancedDocumentVectorizer()
        logging.info("🔄 Iniciando vectorización...")
        enriched_chunks = await vectorizer.vectorize_document_complete(
            pdf_file, doc_metadata
        )
        
        print(f"📊 Chunks generados: {len(enriched_chunks)}")
        
        # 3. Guardar chunks localmente
        saver = ChunkLocalSaver()
        saved_filepath = saver.save_chunks_to_file(enriched_chunks, doc_metadata)
        
        # 4. Mostrar estadísticas
        tipos_contenido = {}
        for chunk in enriched_chunks:
            tipo = chunk.chunk_metadata.tipo_contenido
            tipos_contenido[tipo] = tipos_contenido.get(tipo, 0) + 1
        
        print("\n📊 ESTADÍSTICAS:")
        print(f"   📄 Total chunks: {len(enriched_chunks)}")
        for tipo, count in tipos_contenido.items():
            print(f"   📋 {tipo}: {count} chunks")
        
        avg_confidence = sum(c.confidence_extraccion for c in enriched_chunks) / len(enriched_chunks)
        print(f"   🎯 Confidence promedio: {avg_confidence:.2f}")
        
        print(f"\n✅ CHUNKS GUARDADOS LOCALMENTE")
        print(f"📁 Archivo: {saved_filepath}")
        print(f"💾 Tamaño: {Path(saved_filepath).stat().st_size / (1024*1024):.1f} MB")
        
        print(f"\n🚀 PRÓXIMO PASO:")
        print(f"   python save_chunks_locally.py --load \"{saved_filepath}\"")
        
        return saved_filepath
        
    except Exception as e:
        print(f"❌ Error en vectorización: {e}")
        raise

# =====================================================
# CARGADOR Y GUARDADOR EN BD
# =====================================================

async def load_and_save_to_database(filepath: str):
    """
    Carga chunks desde archivo local y los guarda en BD
    """
    
    print(f"🔄 CARGANDO CHUNKS Y GUARDANDO EN BD")
    print("=" * 45)
    
    try:
        # 1. Cargar chunks desde archivo
        saver = ChunkLocalSaver()
        chunks_data, doc_metadata = saver.load_chunks_from_file(filepath)
        
        print(f"📁 Cargados {len(chunks_data)} chunks desde archivo")
        
        # 2. Importar clase de BD (aquí puedes usar cualquier implementación)
        from app.utils.load_chunks_to_database import DatabaseChunkLoader
        
        # 3. Reconstruir objetos EnrichedChunk si es necesario
        # (o implementar guardado directo desde diccionario)
        
        # 4. Guardar en BD
        # ✅ CAMBIAR POR:
        loader = DatabaseChunkLoader()
        loader.use_enhanced_table = True  # ← CLAVE: forzar tabla enhanced
        success = await loader.load_and_save_chunks(filepath)
        
        # Aquí implementarías un método que tome diccionarios en lugar de objetos
        # success = await db.save_chunks_from_dict(chunks_data, doc_metadata)
        
        if success:
            print("✅ Chunks cargados y guardados en knowledge_base_enhanced exitosamente")
        else:
            print("❌ Error guardando chunks en BD")
        
    except Exception as e:
        print(f"❌ Error cargando/guardando: {e}")
        raise

# =====================================================
# SCRIPT PRINCIPAL
# =====================================================

async def main():
    """Script principal"""
    import sys
    
    if len(sys.argv) < 2:
        print("USO:")
        print("  # Vectorizar y guardar:")
        print('  python save_chunks_locally.py "docs/Manual.pdf" "balanza" "Dibal" "Mistral"')
        print("")
        print("  # Cargar y guardar en BD:")
        print('  python save_chunks_locally.py --load "data/vectorized_chunks/chunks_balanza_dibal_mistral_abc123.json"')
        print("")
        print("  # Listar archivos guardados:")
        print("  python save_chunks_locally.py --list")
        return
    
    if sys.argv[1] == "--list":
        # Listar archivos guardados
        saver = ChunkLocalSaver()
        saved_files = saver.list_saved_chunks()
        
        print("📁 CHUNKS GUARDADOS LOCALMENTE")
        print("=" * 40)
        
        if not saved_files:
            print("❌ No hay archivos guardados")
            return
        
        for file_info in saved_files:
            print(f"📄 {file_info['documento']}")
            print(f"   🔧 {file_info['equipo']}")
            print(f"   📊 {file_info['total_chunks']} chunks")
            print(f"   💾 {file_info['size_mb']:.1f} MB")
            print(f"   📅 {file_info['timestamp']}")
            print(f"   📁 {file_info['filepath']}")
            print()
        
    elif sys.argv[1] == "--load":
        # Cargar desde archivo y guardar en BD
        if len(sys.argv) != 3:
            print("❌ Especifica la ruta del archivo")
            return
        
        await load_and_save_to_database(sys.argv[2])
        
    else:
        # Vectorizar y guardar
        if len(sys.argv) != 5:
            print("❌ Argumentos incorrectos")
            print('Uso: python save_chunks_locally.py "pdf_path" "tipo_equipo" "marca" "modelo"')
            return
        
        await vectorize_and_save_locally(
            sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
        )

if __name__ == "__main__":
    asyncio.run(main())