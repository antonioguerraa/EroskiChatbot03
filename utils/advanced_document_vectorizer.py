# =====================================================
# utils/advanced_document_vectorizer.py - Sistema Avanzado de Vectorización
# =====================================================
"""
Sistema completo de vectorización de documentos con:
- Embeddings enriquecidos con metadatos
- Trazabilidad completa (documento → página → posición)
- Enlaces directos a ubicaciones específicas en PDFs
- Metadatos estructurados (tipo equipo, marca, modelo)
- Chunking inteligente con preservación de contexto
"""

import asyncio
import asyncpg
import fitz  # PyMuPDF
import logging
import json
import re
import hashlib
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
import numpy as np
from urllib.parse import quote
from langchain.text_splitter import RecursiveCharacterTextSplitter

from config.settings import get_settings
from utils.llm.providers import get_vectorizer, get_llm

logger = logging.getLogger(__name__)

# Al inicio del archivo advanced_document_vectorizer.py, después de los imports:
def convert_embedding_for_pgvector(embedding):
    """Convierte embedding al formato correcto para pgvector"""
    if not embedding:
        return "[]"
    clean_embedding = [float(val) if isinstance(val, (int, float)) and not (np.isnan(val) or np.isinf(val)) else 0.0 for val in embedding]
    return f"[{', '.join(map(str, clean_embedding))}]"

@dataclass
class DocumentMetadata:
    """Metadatos estructurados del documento"""
    filename: str
    tipo_equipo: str           # balanza, tpv, impresora, escaner
    marca: str                 # DIBAL, Epson, HP, etc.
    modelo: str                # Mistral, Serie_500, etc.
    version_manual: str        # v1.2, 2024.1, etc.
    idioma: str                # es, en, fr
    fecha_creacion: Optional[datetime] = None
    total_paginas: int = 0
    hash_documento: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte a diccionario serializable"""
        result = asdict(self)
        if self.fecha_creacion:
            result['fecha_creacion'] = self.fecha_creacion.isoformat()
        return result

@dataclass 
class ChunkMetadata:
    """Metadatos específicos del chunk"""
    chunk_id: str
    pagina_numero: int
    posicion_en_pagina: Dict[str, float]  # {"x": 100, "y": 200, "width": 400, "height": 50}
    seccion_titulo: str
    tipo_contenido: str        # texto, tabla, imagen_con_texto, codigo, procedimiento
    nivel_jerarquia: int       # 1=título, 2=subtítulo, 3=contenido
    numero_linea_inicio: int
    numero_linea_fin: int
    chunk_anterior_id: Optional[str] = None
    chunk_siguiente_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte a diccionario serializable"""
        return asdict(self)

@dataclass
class EnrichedChunk:
    """Chunk enriquecido con todo el contexto"""
    chunk_id: str
    texto_original: str
    texto_procesado: str       # Texto limpio para embeddings
    embedding: List[float]
    embedding_con_metadatos: List[float]  # Embedding que incluye metadatos
    documento_metadata: DocumentMetadata
    chunk_metadata: ChunkMetadata
    palabras_clave: List[str]
    entidades_tecnicas: List[str]
    confidence_extraccion: float
    
class AdvancedDocumentVectorizer:
    """
    Vectorizador avanzado que genera embeddings enriquecidos con metadatos
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.vectorizer = get_vectorizer()
        self.llm = get_llm()
        self.chunk_size = 800
        self.chunk_overlap = 100
        self.min_chunk_size = 50
        self.kk = 0
        # Configurar text splitter inteligente
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separators=[
                "\n\n",    # Párrafos dobles
                "\n",      # Líneas simples  
                ". ",      # Oraciones
                ", ",      # Comas
                " ",       # Palabras
                ""         # Caracteres
            ],
            length_function=len,
            keep_separator=True
        )
    async def vectorize_document_complete(
        self, 
        pdf_path: Path, 
        doc_metadata: DocumentMetadata
    ) -> List[EnrichedChunk]:
        """
        Vectorización completa de un documento PDF con metadatos
        """
        logger.info(f"🔄 Vectorizando documento: {pdf_path.name}")
        
        try:
            # 1. Extraer texto con posiciones precisas
            pages_data = await self._extract_text_with_positions(pdf_path)
            
            # 2. Detectar estructura del documento
            document_structure = await self._analyze_document_structure(pages_data)
            
            # 3. Crear chunks inteligentes con contexto
            raw_chunks = await self._create_intelligent_chunks(pages_data, document_structure)
            
            # 4. Enriquecer chunks con metadatos
            enriched_chunks = await self._enrich_chunks_with_metadata(
                raw_chunks, doc_metadata, document_structure
            )
            
            # 5. Generar embeddings dobles (texto + metadatos)
            final_chunks = await self._generate_enriched_embeddings(enriched_chunks)
            
            # 6. Validar y filtrar chunks
            validated_chunks = await self._validate_chunks(final_chunks)
            
            logger.info(f"✅ Documento vectorizado: {len(validated_chunks)} chunks generados")
            return validated_chunks
            
        except Exception as e:
            logger.error(f"❌ Error vectorizando {pdf_path.name}: {e}")
            raise
    
    async def _extract_text_with_positions(self, pdf_path: Path) -> List[Dict[str, Any]]:
        """
        Extrae texto con posiciones exactas usando PyMuPDF
        """
        doc = fitz.open(pdf_path)
        pages_data = []
        
        try:
            for page_num in range(doc.page_count):
                page = doc.load_page(page_num)
                
                # Extraer texto con posiciones
                text_dict = page.get_text("dict")
                
                # Procesar bloques de texto
                page_blocks = []
                for block in text_dict["blocks"]:
                    if "lines" in block:  # Bloque de texto
                        block_info = {
                            "bbox": block["bbox"],  # [x0, y0, x1, y1]
                            "lines": [],
                            "tipo": "texto"
                        }
                        
                        for line in block["lines"]:
                            line_text = ""
                            line_bbox = line["bbox"]
                            
                            for span in line["spans"]:
                                line_text += span["text"]
                            
                            if line_text.strip():
                                block_info["lines"].append({
                                    "text": line_text.strip(),
                                    "bbox": line_bbox,
                                    "font_size": line["spans"][0]["size"] if line["spans"] else 12,
                                    "font_flags": line["spans"][0]["flags"] if line["spans"] else 0
                                })
                        
                        if block_info["lines"]:
                            page_blocks.append(block_info)
                
                pages_data.append({
                    "page_number": page_num + 1,
                    "page_bbox": page.rect,
                    "blocks": page_blocks,
                    "full_text": page.get_text()
                })
        
        finally:
            doc.close()
        
        return pages_data
    
    async def _analyze_document_structure(self, pages_data: List[Dict]) -> Dict[str, Any]:
        """
        Analiza la estructura del documento para detectar secciones, títulos, etc.
        """
        structure = {
            "sections": [],
            "font_hierarchy": {},
            "page_headers": [],
            "page_footers": [],
            "tables_detected": [],
            "figures_detected": []
        }
        
        # Detectar jerarquía de fuentes
        font_sizes = []
        for page_data in pages_data:
            for block in page_data["blocks"]:
                for line in block["lines"]:
                    font_sizes.append(line["font_size"])
        
        # Crear jerarquía basada en tamaños de fuente
        unique_sizes = sorted(set(font_sizes), reverse=True)
        for i, size in enumerate(unique_sizes[:5]):  # Top 5 tamaños
            structure["font_hierarchy"][size] = i + 1
        
        # Detectar secciones principales
        current_section = None
        for page_data in pages_data:
            for block in page_data["blocks"]:
                for line in block["lines"]:
                    font_size = line["font_size"]
                    text = line["text"]
                    
                    # Detectar títulos principales (fuente grande + formato)
                    if (font_size in list(unique_sizes[:2]) and 
                        len(text) < 100 and 
                        self._is_likely_section_title(text)):
                        
                        current_section = {
                            "title": text,
                            "page_start": page_data["page_number"],
                            "font_size": font_size,
                            "bbox": line["bbox"]
                        }
                        structure["sections"].append(current_section)
        
        return structure
    
    def _is_likely_section_title(self, text: str) -> bool:
        """Detecta si un texto es probablemente un título de sección"""
        # Patrones comunes de títulos
        title_patterns = [
            r'^\d+\.\s+[A-Z]',           # "1. CONFIGURACIÓN"
            r'^[A-Z\s]{5,50}$',          # "PROCEDIMIENTOS BÁSICOS"
            r'^\w+\s+\w+\s*$',           # "Instalación Inicial"
        ]
        
        for pattern in title_patterns:
            if re.match(pattern, text.strip()):
                return True
        
        return False
    
    async def _create_intelligent_chunks(
        self, 
        pages_data: List[Dict], 
        document_structure: Dict
    ) -> List[Dict[str, Any]]:
        """
        Crea chunks inteligentes respetando la estructura del documento
        """
        chunks = []
        chunk_counter = 0
        
        for page_data in pages_data:
            page_num = page_data["page_number"]
            
            # Combinar todo el texto de la página
            page_text = ""
            page_positions = []
            
            for block in page_data["blocks"]:
                for line in block["lines"]:
                    page_text += line["text"] + "\n"
                    page_positions.append({
                        "text": line["text"],
                        "bbox": line["bbox"],
                        "font_size": line["font_size"]
                    })
            
            # Crear chunks manteniendo coherencia semántica
            if len(page_text.strip()) >= self.min_chunk_size:
                page_chunks = self._split_page_intelligently(
                    page_text, page_positions, page_num
                )
                
                for chunk_data in page_chunks:
                    chunk_counter += 1
                    chunk_data["chunk_id"] = f"chunk_{chunk_counter:06d}"
                    chunks.append(chunk_data)
        
        # Enlazar chunks anteriores y siguientes
        for i, chunk in enumerate(chunks):
            if i > 0:
                chunk["chunk_anterior_id"] = chunks[i-1]["chunk_id"]
            if i < len(chunks) - 1:
                chunk["chunk_siguiente_id"] = chunks[i+1]["chunk_id"]
        
        return chunks
    
    def _split_page_intelligently(
        self, 
        page_text: str, 
        positions: List[Dict], 
        page_num: int
    ) -> List[Dict[str, Any]]:
        """
        Divide una página usando RecursiveCharacterTextSplitter
        """
        chunks = []
        
        # Usar text splitter inteligente
        text_chunks = self.text_splitter.split_text(page_text)
        self.kk = self.kk + len(text_chunks)
        print(f"👹 Página {page_num}: {len(text_chunks)} chunks generados. Total: {self.kk}")
         
        for i, chunk_text in enumerate(text_chunks):
            if len(chunk_text.strip()) >= self.min_chunk_size:
                chunks.append(self._create_chunk_data(
                    chunk_text.strip(),
                    page_num,
                    positions,  # Usar todas las posiciones de la página
                    0,          # Línea inicio aproximada
                    chunk_text.count('\n')  # Línea fin aproximada
                ))
        
        return chunks

    def _split_page_intelligently_kk(
        self, 
        page_text: str, 
        positions: List[Dict], 
        page_num: int
    ) -> List[Dict[str, Any]]:
        """
        Divide una página en chunks respetando párrafos y secciones
        """
        chunks = []
        
        # Dividir por párrafos primero
        paragraphs = [p.strip() for p in page_text.split('\n\n') if p.strip()]
        
        print(f"👹 len(paragraphs) = {len(paragraphs)}")

        current_chunk = ""
        current_positions = []
        chunk_start_line = 0
        line_counter = 0
        
        for paragraph in paragraphs:
            print(f"👹 len(paragraph) = {len(paragraph)}")
            print(f"👹 len(current_chunk + paragraph) = {len(current_chunk + paragraph)}")
            # Si agregar este párrafo excede el tamaño máximo
            if len(current_chunk + paragraph) > self.chunk_size and current_chunk:
                # Guardar chunk actual
                if len(current_chunk.strip()) >= self.min_chunk_size:
                    chunks.append(self._create_chunk_data(
                        current_chunk.strip(),
                        page_num,
                        current_positions,
                        chunk_start_line,
                        line_counter - 1
                    ))
                
                # Iniciar nuevo chunk
                current_chunk = paragraph
                current_positions = []
                chunk_start_line = line_counter
            else:
                current_chunk += "\n" + paragraph if current_chunk else paragraph
            
            line_counter += paragraph.count('\n') + 1
        
        # Agregar último chunk si tiene contenido
        if len(current_chunk.strip()) >= self.min_chunk_size:
            chunks.append(self._create_chunk_data(
                current_chunk.strip(),
                page_num,
                current_positions,
                chunk_start_line,
                line_counter
            ))
        
        return chunks
    
    def _create_chunk_data(
        self, 
        text: str, 
        page_num: int, 
        positions: List[Dict], 
        start_line: int, 
        end_line: int
    ) -> Dict[str, Any]:
        """Crea estructura de datos del chunk"""
        
        # Calcular posición promedio en la página
        if positions:
            avg_bbox = self._calculate_average_bbox(positions)
        else:
            avg_bbox = {"x": 0, "y": 0, "width": 0, "height": 0}
        
        return {
            "texto_original": text,
            "pagina_numero": page_num,
            "posicion_en_pagina": avg_bbox,
            "numero_linea_inicio": start_line,
            "numero_linea_fin": end_line,
            "tipo_contenido": self._classify_content_type(text),
            "nivel_jerarquia": self._determine_hierarchy_level(positions),
            "chunk_anterior_id": None,
            "chunk_siguiente_id": None
        }
    
    def _calculate_average_bbox(self, positions: List[Dict]) -> Dict[str, float]:
        """Calcula la posición promedio de un chunk en la página"""
        if not positions:
            return {"x": 0, "y": 0, "width": 0, "height": 0}
        
        x_coords = []
        y_coords = []
        widths = []
        heights = []
        
        for pos in positions:
            bbox = pos["bbox"]  # [x0, y0, x1, y1]
            x_coords.append(bbox[0])
            y_coords.append(bbox[1])
            widths.append(bbox[2] - bbox[0])
            heights.append(bbox[3] - bbox[1])
        
        return {
            "x": sum(x_coords) / len(x_coords),
            "y": sum(y_coords) / len(y_coords),
            "width": sum(widths) / len(widths),
            "height": sum(heights) / len(heights)
        }
    
    def _classify_content_type(self, text: str) -> str:
        """Clasifica el tipo de contenido del chunk"""
        
        # Detectar código o comandos
        if re.search(r'[A-Z_]{3,}\s*[:=]|\bMENU\s*→|\bCTRL\+', text):
            return "codigo_comando"
        
        # Detectar procedimientos (listas numeradas)
        if re.search(r'^\s*\d+\.\s+', text, re.MULTILINE):
            return "procedimiento"
        
        # Detectar tablas (múltiples líneas con separadores)
        if text.count('|') > 3 or text.count('\t') > 3:
            return "tabla"
        
        # Detectar títulos (texto corto, mayúsculas)
        if len(text) < 100 and text.isupper():
            return "titulo"
        
        # Detectar advertencias o notas
        warning_keywords = ['nota:', 'advertencia:', 'importante:', 'cuidado:']
        if any(keyword in text.lower() for keyword in warning_keywords):
            return "advertencia"
        
        return "texto"
    
    def _determine_hierarchy_level(self, positions: List[Dict]) -> int:
        """Determina el nivel jerárquico basado en el tamaño de fuente"""
        if not positions:
            return 3
        
        max_font_size = max(pos["font_size"] for pos in positions)
        
        if max_font_size >= 18:
            return 1  # Título principal
        elif max_font_size >= 14:
            return 2  # Subtítulo
        else:
            return 3  # Contenido normal
    
    async def _enrich_chunks_with_metadata(
        self, 
        raw_chunks: List[Dict], 
        doc_metadata: DocumentMetadata,
        document_structure: Dict
    ) -> List[Dict[str, Any]]:
        """
        Enriquece chunks con metadatos adicionales
        """
        enriched_chunks = []
        
        for chunk_data in raw_chunks:
            # Detectar sección a la que pertenece
            seccion_titulo = self._find_section_for_chunk(
                chunk_data, document_structure["sections"]
            )
            
            # Extraer palabras clave específicas
            palabras_clave = await self._extract_technical_keywords(
                chunk_data["texto_original"], doc_metadata.tipo_equipo
            )
            
            # Detectar entidades técnicas
            entidades_tecnicas = await self._extract_technical_entities(
                chunk_data["texto_original"], doc_metadata
            )
            
            # Crear metadatos del chunk
            chunk_metadata = ChunkMetadata(
                chunk_id=chunk_data["chunk_id"],
                pagina_numero=chunk_data["pagina_numero"],
                posicion_en_pagina=chunk_data["posicion_en_pagina"],
                seccion_titulo=seccion_titulo,
                tipo_contenido=chunk_data["tipo_contenido"],
                nivel_jerarquia=chunk_data["nivel_jerarquia"],
                numero_linea_inicio=chunk_data["numero_linea_inicio"],
                numero_linea_fin=chunk_data["numero_linea_fin"],
                chunk_anterior_id=chunk_data.get("chunk_anterior_id"),
                chunk_siguiente_id=chunk_data.get("chunk_siguiente_id")
            )
            
            enriched_chunk = {
                "chunk_id": chunk_data["chunk_id"],
                "texto_original": chunk_data["texto_original"],
                "documento_metadata": doc_metadata,
                "chunk_metadata": chunk_metadata,
                "palabras_clave": palabras_clave,
                "entidades_tecnicas": entidades_tecnicas
            }
            
            enriched_chunks.append(enriched_chunk)
        
        return enriched_chunks
    
    def _find_section_for_chunk(self, chunk_data: Dict, sections: List[Dict]) -> str:
        """Encuentra la sección a la que pertenece un chunk"""
        
        chunk_page = chunk_data["pagina_numero"]
        
        # Buscar la sección más cercana anterior
        applicable_section = "Sin sección"
        
        for section in sections:
            if section["page_start"] <= chunk_page:
                applicable_section = section["title"]
            else:
                break
        
        return applicable_section
    
    async def _extract_technical_keywords(self, text: str, tipo_equipo: str) -> List[str]:
        """Extrae palabras clave técnicas usando LLM"""
        
        extraction_prompt = f"""
Extrae palabras clave técnicas específicas de este texto sobre {tipo_equipo}.

TEXTO:
{text[:500]}...

INSTRUCCIONES:
- Solo términos técnicos relevantes para {tipo_equipo}
- Incluir códigos, procedimientos, componentes
- Máximo 10 palabras clave
- En minúsculas

FORMATO: ["palabra1", "palabra2", "palabra3"]

RESPUESTA:
"""
        
        try:
            response = await self.llm.ainvoke(extraction_prompt)
            
            if hasattr(response, 'content'):
                response_text = response.content
            else:
                response_text = str(response)
            
            # Extraer lista JSON
            import json
            json_match = re.search(r'\[.*?\]', response_text)
            if json_match:
                keywords = json.loads(json_match.group())
                return [kw.lower().strip() for kw in keywords if isinstance(kw, str)]
            
        except Exception as e:
            logger.warning(f"Error extrayendo keywords: {e}")
        
        # Fallback: extracción básica
        return self._extract_keywords_basic(text)
    
    def _extract_keywords_basic(self, text: str) -> List[str]:
        """Extracción básica de palabras clave como fallback"""
        
        # Patrones técnicos comunes
        technical_patterns = [
            r'\b[A-Z]{2,}\b',           # Códigos en mayúsculas
            r'\b\w+[_-]\w+\b',          # Términos con guiones/underscores
            r'\bmenu\w*\b',             # Términos de menú
            r'\bconfig\w*\b',           # Términos de configuración
            r'\berror\w*\b',            # Términos de error
        ]
        
        keywords = []
        for pattern in technical_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            keywords.extend(matches)
        
        # Eliminar duplicados y limitar
        unique_keywords = list(set(kw.lower() for kw in keywords))
        return unique_keywords[:8]
    
    async def _extract_technical_entities(
        self, 
        text: str, 
        doc_metadata: DocumentMetadata
    ) -> List[str]:
        """Extrae entidades técnicas específicas del contexto"""
        
        entities = []
        
        # Entidades específicas por tipo de equipo
        entity_patterns = {
            "balanza": [
                r'\bDIBAL\w*\b', r'\bMistral\b', r'\btara\b', r'\bcalibr\w*\b'
            ],
            "tpv": [
                r'\bTPV\b', r'\bterminal\b', r'\btarjeta\b', r'\bticket\b'
            ],
            "impresora": [
                r'\bEpson\b', r'\bHP\b', r'\bpapel\b', r'\brollo\b', r'\btinta\b'
            ]
        }
        
        patterns = entity_patterns.get(doc_metadata.tipo_equipo.lower(), [])
        
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            entities.extend(matches)
        
        # Agregar marca y modelo del documento
        entities.append(doc_metadata.marca)
        entities.append(doc_metadata.modelo)
        
        return list(set(entity.lower() for entity in entities if entity))
    
    async def _generate_enriched_embeddings(
        self, 
        enriched_chunks: List[Dict]
    ) -> List[EnrichedChunk]:
        """
        Genera embeddings dobles: solo texto + texto con metadatos
        """
        final_chunks = []
        
        for chunk_data in enriched_chunks:
            try:
                # 1. Embedding solo del texto
                texto_limpio = self._clean_text_for_embedding(
                    chunk_data["texto_original"]
                )
                embedding_texto = self.vectorizer.embed(texto_limpio)
                
                # 2. Texto enriquecido con metadatos
                texto_con_metadatos = self._create_metadata_enriched_text(chunk_data)
                embedding_con_metadatos = self.vectorizer.embed(texto_con_metadatos)
                
                # 3. Calcular confidence de extracción
                confidence = self._calculate_extraction_confidence(chunk_data)
                
                # 4. Crear chunk final
                final_chunk = EnrichedChunk(
                    chunk_id=chunk_data["chunk_id"],
                    texto_original=chunk_data["texto_original"],
                    texto_procesado=texto_limpio,
                    embedding=embedding_texto,
                    embedding_con_metadatos=embedding_con_metadatos,
                    documento_metadata=chunk_data["documento_metadata"],
                    chunk_metadata=chunk_data["chunk_metadata"],
                    palabras_clave=chunk_data["palabras_clave"],
                    entidades_tecnicas=chunk_data["entidades_tecnicas"],
                    confidence_extraccion=confidence
                )
                
                final_chunks.append(final_chunk)
                
            except Exception as e:
                logger.error(f"Error generando embeddings para {chunk_data['chunk_id']}: {e}")
                continue
        
        return final_chunks
    
    def _clean_text_for_embedding(self, text: str) -> str:
        """Limpia texto para optimizar embeddings"""
        
        # Normalizar espacios
        cleaned = re.sub(r'\s+', ' ', text)
        
        # Eliminar caracteres especiales problemáticos
        cleaned = re.sub(r'[^\w\s\.\,\;\:\!\?\-\(\)]', ' ', cleaned)
        
        # Normalizar puntuación
        cleaned = re.sub(r'\.{2,}', '.', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned)
        
        return cleaned.strip()
    
    def _create_metadata_enriched_text(self, chunk_data: Dict) -> str:
        """Crea texto enriquecido con metadatos para embedding contextual"""
        
        doc_meta = chunk_data["documento_metadata"]
        chunk_meta = chunk_data["chunk_metadata"]
        
        # Construir contexto de metadatos
        metadata_context = f"""
Equipo: {doc_meta.tipo_equipo} {doc_meta.marca} {doc_meta.modelo}
Sección: {chunk_meta.seccion_titulo}
Tipo: {chunk_meta.tipo_contenido}
Página: {chunk_meta.pagina_numero}
Keywords: {', '.join(chunk_data['palabras_clave'][:5])}

Contenido: {chunk_data['texto_original']}
"""
        
        return metadata_context.strip()
    
    def _calculate_extraction_confidence(self, chunk_data: Dict) -> float:
        """Calcula confidence de la extracción del chunk"""
        
        confidence = 0.5  # Base
        
        # Factor 1: Longitud del texto
        text_length = len(chunk_data["texto_original"])
        if 100 <= text_length <= 1000:
            confidence += 0.2
        elif text_length > 1000:
            confidence += 0.1
        
        # Factor 2: Palabras clave detectadas
        if len(chunk_data["palabras_clave"]) >= 3:
            confidence += 0.2
        elif len(chunk_data["palabras_clave"]) >= 1:
            confidence += 0.1
        
        # Factor 3: Entidades técnicas
        if len(chunk_data["entidades_tecnicas"]) >= 2:
            confidence += 0.1
        
        # Factor 4: Tipo de contenido
        if chunk_data["chunk_metadata"].tipo_contenido in ["procedimiento", "codigo_comando"]:
            confidence += 0.15
        
        return min(confidence, 1.0)
    
    async def _validate_chunks(self, chunks: List[EnrichedChunk]) -> List[EnrichedChunk]:
        """Valida y filtra chunks de baja calidad"""
        
        validated = []
        
        for chunk in chunks:
            # Criterios de validación
            is_valid = (
                len(chunk.texto_original.strip()) >= self.min_chunk_size and
                chunk.confidence_extraccion >= 0.3 and
                len(chunk.palabras_clave) > 0 and
                chunk.embedding is not None and
                len(chunk.embedding) > 0
            )
            
            if is_valid:
                validated.append(chunk)
            else:
                logger.debug(f"Chunk {chunk.chunk_id} filtrado por baja calidad")
        
        return validated

class DocumentLinkGenerator:
    """
    Genera enlaces directos a ubicaciones específicas en PDFs
    """
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
    
    def generate_pdf_link(
        self, 
        filename: str, 
        page_number: int,
        position: Optional[Dict[str, float]] = None
    ) -> str:
        """
        Genera enlace directo a una página específica del PDF
        """
        # URL base del PDF
        pdf_url = f"{self.base_url}/documents/{quote(filename)}"
        
        # Agregar parámetros de navegación
        params = [f"page={page_number}"]
        
        # Si hay posición específica, agregar coordenadas
        if position:
            # Formato: #page=5&zoom=100,x,y
            x = int(position.get("x", 0))
            y = int(position.get("y", 0))
            params.append(f"zoom=100,{x},{y}")
        
        return f"{pdf_url}#{','.join(params)}"
    
    def generate_web_viewer_link(
        self, 
        filename: str, 
        chunk_id: str,
        page_number: int,
        position: Optional[Dict[str, float]] = None
    ) -> str:
        """
        Genera enlace al visor web con resaltado del chunk específico
        """
        base_viewer_url = f"{self.base_url}/viewer"
        
        params = [
            f"doc={quote(filename)}",
            f"page={page_number}",
            f"chunk={chunk_id}"
        ]
        
        if position:
            params.append(f"highlight={position['x']},{position['y']},{position['width']},{position['height']}")
        
        return f"{base_viewer_url}?{'&'.join(params)}"

class EnhancedVectorizationDatabase:
    """
    Gestiona el almacenamiento de chunks enriquecidos en la base de datos
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.link_generator = DocumentLinkGenerator()
    
    async def save_enriched_chunks(self, chunks: List[EnrichedChunk]) -> bool:
        """
        Guarda chunks enriquecidos en la base de datos
        """
        conn = await asyncpg.connect(self._build_connection_string())
        
        try:
            # Crear tabla mejorada si no existe
            await self._create_enhanced_tables(conn)
            
            # Guardar chunks con metadatos completos
            for chunk in chunks:
                await self._save_single_chunk(conn, chunk)
            
            logger.info(f"✅ Guardados {len(chunks)} chunks enriquecidos")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error guardando chunks: {e}")
            return False
        finally:
            await conn.close()
    
    async def _create_enhanced_tables(self, conn):
        """Crea tablas mejoradas con soporte completo para metadatos"""
        
        # Tabla principal mejorada
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_base_enhanced (
                id SERIAL PRIMARY KEY,
                chunk_id VARCHAR(50) UNIQUE NOT NULL,
                
                -- Contenido
                chunk_text TEXT NOT NULL,
                chunk_text_processed TEXT NOT NULL,
                chunk_embedding vector(1536),
                chunk_embedding_with_metadata vector(1536),
                
                -- Metadatos del documento
                documento_origen VARCHAR(255) NOT NULL,
                tipo_equipo VARCHAR(50) NOT NULL,
                marca VARCHAR(100) NOT NULL,
                modelo VARCHAR(100) NOT NULL,
                version_manual VARCHAR(50),
                idioma VARCHAR(10) DEFAULT 'es',
                hash_documento VARCHAR(64),
                
                -- Metadatos del chunk
                pagina_numero INTEGER NOT NULL,
                posicion_x FLOAT DEFAULT 0,
                posicion_y FLOAT DEFAULT 0,
                posicion_width FLOAT DEFAULT 0,
                posicion_height FLOAT DEFAULT 0,
                seccion_titulo VARCHAR(200),
                tipo_contenido VARCHAR(50),
                nivel_jerarquia INTEGER DEFAULT 3,
                numero_linea_inicio INTEGER,
                numero_linea_fin INTEGER,
                
                -- Relaciones
                chunk_anterior_id VARCHAR(50),
                chunk_siguiente_id VARCHAR(50),
                
                -- Análisis
                palabras_clave TEXT[],
                entidades_tecnicas TEXT[],
                confidence_extraccion FLOAT DEFAULT 0.5,
                
                -- Enlaces
                pdf_link TEXT,
                web_viewer_link TEXT,
                
                -- Timestamps
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                
                -- Constraints
                CONSTRAINT ck_confidence CHECK (confidence_extraccion BETWEEN 0.0 AND 1.0),
                CONSTRAINT ck_pagina_positiva CHECK (pagina_numero > 0)
            );
        """)
        
        # Índices optimizados
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_kbe_embedding ON knowledge_base_enhanced USING ivfflat (chunk_embedding vector_cosine_ops);",
            "CREATE INDEX IF NOT EXISTS idx_kbe_embedding_meta ON knowledge_base_enhanced USING ivfflat (chunk_embedding_with_metadata vector_cosine_ops);",
            "CREATE INDEX IF NOT EXISTS idx_kbe_documento ON knowledge_base_enhanced(documento_origen);",
            "CREATE INDEX IF NOT EXISTS idx_kbe_equipo ON knowledge_base_enhanced(tipo_equipo, marca, modelo);",
            "CREATE INDEX IF NOT EXISTS idx_kbe_pagina ON knowledge_base_enhanced(documento_origen, pagina_numero);",
            "CREATE INDEX IF NOT EXISTS idx_kbe_keywords ON knowledge_base_enhanced USING gin(palabras_clave);",
            "CREATE INDEX IF NOT EXISTS idx_kbe_entities ON knowledge_base_enhanced USING gin(entidades_tecnicas);",
            "CREATE INDEX IF NOT EXISTS idx_kbe_content_type ON knowledge_base_enhanced(tipo_contenido);",
            "CREATE INDEX IF NOT EXISTS idx_kbe_confidence ON knowledge_base_enhanced(confidence_extraccion DESC);",
        ]
        
        for index_sql in indexes:
            try:
                await conn.execute(index_sql)
            except Exception as e:
                logger.warning(f"Error creando índice: {e}")
    
    async def _save_single_chunk(self, conn, chunk: EnrichedChunk):
        """Guarda un chunk individual con todos sus metadatos"""
        
        # Generar enlaces
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
        
        await conn.execute("""
            INSERT INTO knowledge_base_enhanced (
                chunk_id, chunk_text, chunk_text_processed,
                $4::vector, $5::vector,
                documento_origen, tipo_equipo, marca, modelo, version_manual, idioma, hash_documento,
                pagina_numero, posicion_x, posicion_y, posicion_width, posicion_height,
                seccion_titulo, tipo_contenido, nivel_jerarquia,
                numero_linea_inicio, numero_linea_fin,
                chunk_anterior_id, chunk_siguiente_id,
                palabras_clave, entidades_tecnicas, confidence_extraccion,
                pdf_link, web_viewer_link
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24,
                $25, $26, $27, $28, $29
            ) ON CONFLICT (chunk_id) DO UPDATE SET
                updated_at = CURRENT_TIMESTAMP
        """,
        chunk.chunk_id,
        chunk.texto_original,
        chunk.texto_procesado,
        convert_embedding_for_pgvector(chunk.embedding),
        convert_embedding_for_pgvector(chunk.embedding_con_metadatos),
        chunk.documento_metadata.filename,
        chunk.documento_metadata.tipo_equipo,
        chunk.documento_metadata.marca,
        chunk.documento_metadata.modelo,
        chunk.documento_metadata.version_manual,
        chunk.documento_metadata.idioma,
        chunk.documento_metadata.hash_documento,
        chunk.chunk_metadata.pagina_numero,
        chunk.chunk_metadata.posicion_en_pagina.get("x", 0),
        chunk.chunk_metadata.posicion_en_pagina.get("y", 0),
        chunk.chunk_metadata.posicion_en_pagina.get("width", 0),
        chunk.chunk_metadata.posicion_en_pagina.get("height", 0),
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
    
    def _build_connection_string(self) -> str:
        """Construye string de conexión"""
        return f"postgresql://{self.settings.database.user}:{self.settings.database.password or ''}@{self.settings.database.host}:{self.settings.database.port}/{self.settings.database.name}"

# =====================================================
# Script principal de vectorización completa
# =====================================================

async def vectorize_document_with_metadata(
    pdf_path: str,
    tipo_equipo: str,
    marca: str, 
    modelo: str,
    version: str = "1.0"
):
    """
    Función principal para vectorizar un documento con metadatos completos
    """
    
    print(f"🔄 VECTORIZANDO DOCUMENTO CON METADATOS AVANZADOS")
    print("=" * 60)
    
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
        logging.info("👹 vectorizador instanciado")
        enriched_chunks = await vectorizer.vectorize_document_complete(
            pdf_file, doc_metadata
        )
        
        print(f"📊 Chunks generados: {len(enriched_chunks)}")
        
        # 3. Guardar en base de datos
        db = EnhancedVectorizationDatabase()
        success = await db.save_enriched_chunks(enriched_chunks)
        
        if success:
            print("✅ Documento vectorizado y guardado exitosamente")
            
            # Estadísticas
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
            
            # Mostrar enlace de ejemplo
            if enriched_chunks:
                example_chunk = enriched_chunks[0]
                print(f"\n🔗 EJEMPLO DE ENLACE:")
                print(f"   📄 PDF: {example_chunk.chunk_metadata}")
                
        else:
            print("❌ Error guardando en base de datos")
            
    except Exception as e:
        print(f"❌ Error en vectorización: {e}")
        raise

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) != 5:
        print("Uso: python advanced_document_vectorizer.py <pdf_path> <tipo_equipo> <marca> <modelo>")
        print("Ejemplo: python advanced_document_vectorizer.py manual_dibal.pdf balanza DIBAL Mistral")
        sys.exit(1)
    
    asyncio.run(vectorize_document_with_metadata(
        sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
    ))