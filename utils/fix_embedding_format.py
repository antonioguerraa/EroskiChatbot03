# =====================================================
# fix_embedding_format.py - Solución para el error de formato de embeddings
# =====================================================
"""
Parche para corregir el error de formato de embeddings en EnhancedVectorizationDatabase.
El error ocurre porque los embeddings se pasan como lista de Python en lugar 
del formato correcto para pgvector.
"""

import asyncpg
import numpy as np
from typing import List

class EmbeddingFormatFixer:
    """Herramientas para convertir embeddings al formato correcto para pgvector"""
    
    @staticmethod
    def convert_embedding_for_pgvector(embedding: List[float]) -> str:
        """
        Convierte una lista de floats al formato string requerido por pgvector
        
        Args:
            embedding: Lista de números float del embedding
            
        Returns:
            str: Embedding en formato string para pgvector: "[0.1, 0.2, 0.3]"
        """
        if not embedding:
            return "[]"
        
        # Asegurar que todos son float y manejar NaN/Inf
        clean_embedding = []
        for val in embedding:
            if isinstance(val, (int, float)) and not (np.isnan(val) or np.isinf(val)):
                clean_embedding.append(float(val))
            else:
                clean_embedding.append(0.0)  # Valor por defecto para valores inválidos
        
        # Formatear como string para pgvector
        return f"[{', '.join(map(str, clean_embedding))}]"
    
    @staticmethod
    def convert_embedding_for_asyncpg(embedding: List[float]) -> List[float]:
        """
        Convierte embedding para usar directamente con asyncpg y la extensión vector
        
        Args:
            embedding: Lista de números float del embedding
            
        Returns:
            List[float]: Embedding limpio como lista de floats
        """
        if not embedding:
            return []
        
        # Limpiar valores inválidos
        clean_embedding = []
        for val in embedding:
            if isinstance(val, (int, float)) and not (np.isnan(val) or np.isinf(val)):
                clean_embedding.append(float(val))
            else:
                clean_embedding.append(0.0)
        
        return clean_embedding

# =====================================================
# PARCHE PARA ENHANCED_VECTORIZATION_DATABASE
# =====================================================

def patch_save_single_chunk_method():
    """
    Función que contiene el método _save_single_chunk corregido.
    Reemplaza el método original en EnhancedVectorizationDatabase.
    """
    
    async def _save_single_chunk_fixed(self, conn, chunk):
        """Guarda un chunk individual con formato de embedding corregido"""
        
        # Generar enlaces (si el link_generator está disponible)
        pdf_link = ""
        web_viewer_link = ""
        
        if hasattr(self, 'link_generator') and self.link_generator:
            try:
                pdf_link = self.link_generator.generate_pdf_link(
                    chunk.documento_metadata.filename,
                    chunk.chunk_metadata.pagina_numero,
                    chunk.chunk_metadata.posicion_en_pagina
                )
                
                web_viewer_link = self.link_generator.generate_web_viewer_link(
                    chunk.documento_metadata.filename,
                    chunk.chunk_id,
                    chunk.chunk_metadata.pagina_numero,
                    chunk.chunk_metadata.posicion_en_pagina
                )
            except Exception as e:
                print(f"⚠️ Error generando enlaces: {e}")
        
        # CORRECCIÓN: Convertir embeddings al formato correcto
        embedding_str = EmbeddingFormatFixer.convert_embedding_for_pgvector(chunk.embedding)
        embedding_metadata_str = EmbeddingFormatFixer.convert_embedding_for_pgvector(chunk.embedding_con_metadatos)
        
        try:
            await conn.execute("""
                INSERT INTO knowledge_base_enhanced (
                    chunk_id, chunk_text, chunk_text_processed,
                    chunk_embedding, chunk_embedding_with_metadata,
                    documento_origen, tipo_equipo, marca, modelo, version_manual, idioma, hash_documento,
                    pagina_numero, posicion_x, posicion_y, posicion_width, posicion_height,
                    seccion_titulo, tipo_contenido, nivel_jerarquia,
                    numero_linea_inicio, numero_linea_fin,
                    chunk_anterior_id, chunk_siguiente_id,
                    palabras_clave, entidades_tecnicas, confidence_extraccion,
                    pdf_link, web_viewer_link
                ) VALUES (
                    $1, $2, $3, $4::vector, $5::vector, $6, $7, $8, $9, $10, $11, $12,
                    $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24,
                    $25, $26, $27, $28, $29
                ) ON CONFLICT (chunk_id) DO UPDATE SET
                    chunk_text = EXCLUDED.chunk_text,
                    chunk_text_processed = EXCLUDED.chunk_text_processed,
                    chunk_embedding = EXCLUDED.chunk_embedding,
                    chunk_embedding_with_metadata = EXCLUDED.chunk_embedding_with_metadata,
                    confidence_extraccion = EXCLUDED.confidence_extraccion
            """, 
                chunk.chunk_id,
                chunk.texto_original,
                chunk.texto_procesado,
                embedding_str,  # Convertido a string
                embedding_metadata_str,  # Convertido a string
                chunk.documento_metadata.filename,
                chunk.documento_metadata.tipo_equipo,
                chunk.documento_metadata.marca,
                chunk.documento_metadata.modelo,
                chunk.documento_metadata.version_manual or "1.0",
                chunk.documento_metadata.idioma,
                chunk.documento_metadata.hash_documento,
                chunk.chunk_metadata.pagina_numero,
                chunk.chunk_metadata.posicion_en_pagina.get('x', 0),
                chunk.chunk_metadata.posicion_en_pagina.get('y', 0),
                chunk.chunk_metadata.posicion_en_pagina.get('width', 0),
                chunk.chunk_metadata.posicion_en_pagina.get('height', 0),
                chunk.chunk_metadata.seccion_titulo,
                chunk.chunk_metadata.tipo_contenido,
                chunk.chunk_metadata.nivel_jerarquia,
                chunk.chunk_metadata.numero_linea_inicio,
                chunk.chunk_metadata.numero_linea_fin,
                chunk.chunk_metadata.chunk_anterior_id,
                chunk.chunk_metadata.chunk_siguiente_id,
                chunk.palabras_clave,
                chunk.entidades_tecnicas,
                chunk.confidence_extraccion,
                pdf_link,
                web_viewer_link
            )
            
        except Exception as e:
            # Si falla con knowledge_base_enhanced, intentar con knowledge_base estándar
            print(f"⚠️ Error con tabla enhanced, intentando tabla estándar: {e}")
            
            await conn.execute("""
                INSERT INTO knowledge_base (
                    documento_origen, chunk_text, chunk_embedding,
                    pagina_numero, seccion, capitulo, palabras_clave,
                    chunk_metadata
                ) VALUES ($1, $2, $3::vector, $4, $5, $6, $7, $8)
                ON CONFLICT DO NOTHING
            """,
                chunk.documento_metadata.filename,
                chunk.texto_original,
                embedding_str,
                chunk.chunk_metadata.pagina_numero,
                chunk.chunk_metadata.seccion_titulo,
                chunk.chunk_metadata.seccion_titulo,  # Usar sección como capítulo
                chunk.palabras_clave,
                chunk.chunk_metadata.to_dict()
            )
    
    return _save_single_chunk_fixed

# =====================================================
# SCRIPT DE APLICACIÓN DEL PARCHE
# =====================================================

def apply_embedding_format_patch():
    """
    Aplica el parche al sistema de vectorización.
    Llama a esta función antes de usar AdvancedDocumentVectorizer.
    """
    
    try:
        # Importar la clase que necesita el parche
        from utils.advanced_document_vectorizer import EnhancedVectorizationDatabase
        
        # Aplicar el parche
        EnhancedVectorizationDatabase._save_single_chunk = patch_save_single_chunk_method()
        
        print("✅ Parche de formato de embeddings aplicado correctamente")
        return True
        
    except ImportError as e:
        print(f"❌ Error importando clase para parche: {e}")
        return False
    except Exception as e:
        print(f"❌ Error aplicando parche: {e}")
        return False

if __name__ == "__main__":
    print("🔧 APLICANDO PARCHE DE FORMATO DE EMBEDDINGS")
    print("=" * 50)
    
    if apply_embedding_format_patch():
        print("✅ Parche aplicado exitosamente")
        print("💡 Ahora puedes ejecutar el vectorizador sin errores de formato")
    else:
        print("❌ Error aplicando parche")
        print("💡 Revisa los errores y la estructura del proyecto")