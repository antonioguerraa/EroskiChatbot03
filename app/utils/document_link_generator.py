# =====================================================
# utils/document_link_generator.py - Sistema de Enlaces con Resaltado
# =====================================================
"""
Sistema para generar enlaces directos a documentos PDF con resaltado
automático de los chunks específicos usando coordenadas almacenadas.
"""

import logging
from typing import List, Dict, Any, Optional
from urllib.parse import quote, urlencode
from pathlib import Path
import json
import base64

logger = logging.getLogger(__name__)

class DocumentLinkGenerator_kk:
    """
    Genera enlaces directos a ubicaciones específicas en PDFs con resaltado de chunks
    """
    
    def __init__(self, base_url: str = "http://localhost:8000", docs_path: str = "/docs"):
        self.base_url = base_url
        self.docs_path = docs_path
        
    def generate_chunk_link(
        self,
        documento_origen: str,
        pagina_numero: int,
        chunk_coordinates: Dict[str, float],
        chunk_id: str = None,
        highlight_color: str = "rgba(255, 255, 0, 0.3)"
    ) -> Dict[str, str]:
        """
        Genera enlaces robustos con validación de datos
        """
        
        try:
            # Validar datos de entrada
            if not documento_origen:
                raise ValueError("documento_origen es requerido")
            
            if not isinstance(pagina_numero, int) or pagina_numero < 1:
                pagina_numero = 1
            
            # Validar coordenadas
            required_coords = ['x', 'y', 'width', 'height']
            if not all(coord in chunk_coordinates for coord in required_coords):
                # Coordenadas por defecto si faltan
                chunk_coordinates = {
                    'x': chunk_coordinates.get('x', 0),
                    'y': chunk_coordinates.get('y', 0), 
                    'width': chunk_coordinates.get('width', 100),
                    'height': chunk_coordinates.get('height', 20)
                }
            
            # Limpiar nombre del documento
            doc_name = documento_origen.replace(' ', '%20')
            
            # Enlace PDF básico
            pdf_link = f"{self.base_url}{self.docs_path}/{doc_name}#page={pagina_numero}"
            
            # Enlace web viewer con resaltado
            highlight_params = {
                'page': pagina_numero,
                'highlight': json.dumps({
                    'x': float(chunk_coordinates['x']),
                    'y': float(chunk_coordinates['y']),
                    'width': float(chunk_coordinates['width']),
                    'height': float(chunk_coordinates['height']),
                    'color': highlight_color,
                    'chunk_id': chunk_id or ''
                })
            }
            
            from urllib.parse import urlencode
            web_viewer_link = f"{self.base_url}/viewer/{doc_name}?{urlencode(highlight_params)}"
            
            return {
                'pdf_link': pdf_link,
                'web_viewer_link': web_viewer_link,
                'direct_download': f"{self.base_url}{self.docs_path}/{doc_name}"
            }
            
        except Exception as e:
            # Fallback a enlace básico si algo falla
            doc_name = documento_origen.replace(' ', '%20') if documento_origen else 'documento.pdf'
            basic_link = f"{self.base_url}{self.docs_path}/{doc_name}#page={pagina_numero}"
            
            return {
                'pdf_link': basic_link,
                'web_viewer_link': basic_link,
                'direct_download': basic_link,
                'error': str(e)
            }

    def generate_multi_chunk_link(
        self,
        documento_origen: str,
        chunks_data: List[Dict[str, Any]],
        base_page: int = None
    ) -> str:
        """
        Genera enlace para múltiples chunks en el mismo documento
        
        Args:
            documento_origen: Nombre del archivo PDF
            chunks_data: Lista con datos de chunks y coordenadas
            base_page: Página base (si no se especifica, usa la primera)
            
        Returns:
            URL del web viewer con múltiples resaltados
        """
        
        if not chunks_data:
            return self.generate_chunk_link(documento_origen, 1, {})['pdf_link']
        
        # Determinar página base
        if base_page is None:
            base_page = chunks_data[0].get('pagina_numero', 1)
        
        # Preparar datos de múltiples highlights
        highlights = []
        for chunk in chunks_data:
            if 'posicion' in chunk:
                highlights.append({
                    'page': chunk.get('pagina_numero', base_page),
                    'x': chunk['posicion'].get('x', 0),
                    'y': chunk['posicion'].get('y', 0),
                    'width': chunk['posicion'].get('width', 100),
                    'height': chunk['posicion'].get('height', 20),
                    'color': 'rgba(255, 255, 0, 0.3)',
                    'chunk_id': chunk.get('chunk_id', ''),
                    'title': f"Chunk {chunk.get('chunk_id', '')}"
                })
        
        # Generar parámetros
        doc_name = documento_origen.replace(' ', '%20')
        multi_highlight_params = {
            'page': base_page,
            'multi_highlight': json.dumps(highlights)
        }
        
        return f"{self.base_url}/viewer/{doc_name}?{urlencode(multi_highlight_params)}"






# =====================================================
# PASO 5: utils/document_link_generator.py
# =====================================================


"""
utils/document_link_generator.py - Generador de enlaces PDF con resaltado
"""

import logging
from typing import List, Dict, Any, Optional
from urllib.parse import quote, urlencode
from pathlib import Path
import json

logger = logging.getLogger(__name__)

class DocumentLinkGenerator:
    """
    Genera enlaces directos a ubicaciones específicas en PDFs con resaltado de chunks
    """
    
    def __init__(self, base_url: str = "http://localhost:8000", docs_path: str = "/docs"):
        self.base_url = base_url
        self.docs_path = docs_path
        
        logger.info(f"DocumentLinkGenerator inicializado: {base_url}")
        
    def generate_chunk_link(
        self,
        documento_origen: str,
        pagina_numero: int,
        chunk_coordinates: Dict[str, float],
        chunk_id: str = None,
        highlight_color: str = "rgba(255, 255, 0, 0.3)"
    ) -> Dict[str, str]:
        """
        Genera enlaces para un chunk específico con coordenadas de resaltado
        
        Args:
            documento_origen: Nombre del archivo PDF
            pagina_numero: Número de página
            chunk_coordinates: Dict con x, y, width, height
            chunk_id: ID del chunk para tracking
            highlight_color: Color del resaltado en formato RGBA
            
        Returns:
            Dict con enlaces PDF y web viewer
        """
        
        try:
            # Validar datos de entrada
            if not documento_origen:
                raise ValueError("documento_origen es requerido")
            
            if not isinstance(pagina_numero, int) or pagina_numero < 1:
                logger.warning(f"Página inválida {pagina_numero}, usando página 1")
                pagina_numero = 1
            
            # Validar coordenadas
            required_coords = ['x', 'y', 'width', 'height']
            if not all(coord in chunk_coordinates for coord in required_coords):
                logger.warning(f"Coordenadas incompletas para {chunk_id}, usando valores por defecto")
                chunk_coordinates = {
                    'x': chunk_coordinates.get('x', 0),
                    'y': chunk_coordinates.get('y', 0), 
                    'width': chunk_coordinates.get('width', 100),
                    'height': chunk_coordinates.get('height', 20)
                }
            
            # Limpiar nombre del documento
            doc_name_encoded = quote(documento_origen, safe='')
            
            # Enlace PDF básico (para navegadores con PDF.js nativo)
            pdf_link = f"{self.base_url}{self.docs_path}/{doc_name_encoded}#page={pagina_numero}"
            
            # Datos para el resaltado
            highlight_data = {
                'x': float(chunk_coordinates['x']),
                'y': float(chunk_coordinates['y']),
                'width': float(chunk_coordinates['width']),
                'height': float(chunk_coordinates['height']),
                'color': highlight_color,
                'chunk_id': chunk_id or '',
                'page': pagina_numero
            }
            
            # Enlace web viewer con resaltado personalizado
            highlight_params = {
                'page': pagina_numero,
                'highlight': json.dumps(highlight_data)
            }
            
            web_viewer_link = f"{self.base_url}/viewer/{doc_name_encoded}?{urlencode(highlight_params)}"
            
            result = {
                'pdf_link': pdf_link,
                'web_viewer_link': web_viewer_link,
                'direct_download': f"{self.base_url}{self.docs_path}/{doc_name_encoded}",
                'highlight_data': highlight_data
            }
            
            logger.debug(f"Enlaces generados para chunk {chunk_id}: {result}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error generando enlaces para chunk {chunk_id}: {e}")
            
            # Fallback a enlace básico si algo falla
            doc_name_encoded = quote(documento_origen if documento_origen else 'documento.pdf', safe='')
            basic_link = f"{self.base_url}{self.docs_path}/{doc_name_encoded}#page={pagina_numero}"
            
            return {
                'pdf_link': basic_link,
                'web_viewer_link': basic_link,
                'direct_download': basic_link,
                'error': str(e)
            }
    
    def generate_multi_chunk_link(
        self,
        documento_origen: str,
        chunks_data: List[Dict[str, Any]],
        base_page: int = None
    ) -> str:
        """
        Genera enlace para múltiples chunks en el mismo documento
        
        Args:
            documento_origen: Nombre del archivo PDF
            chunks_data: Lista con datos de chunks y coordenadas
            base_page: Página base (si no se especifica, usa la primera)
            
        Returns:
            URL del web viewer con múltiples resaltados
        """
        
        try:
            if not chunks_data:
                logger.warning("No hay chunks para generar enlace múltiple")
                return self.generate_chunk_link(documento_origen, 1, {})['pdf_link']
            
            # Determinar página base
            if base_page is None:
                base_page = chunks_data[0].get('pagina_numero', 1)
            
            # Preparar datos de múltiples highlights
            highlights = []
            for chunk in chunks_data:
                if 'posicion' in chunk:
                    highlights.append({
                        'page': chunk.get('pagina_numero', base_page),
                        'x': float(chunk['posicion'].get('x', 0)),
                        'y': float(chunk['posicion'].get('y', 0)),
                        'width': float(chunk['posicion'].get('width', 100)),
                        'height': float(chunk['posicion'].get('height', 20)),
                        'color': 'rgba(255, 255, 0, 0.3)',
                        'chunk_id': chunk.get('chunk_id', ''),
                        'title': f"Chunk {chunk.get('chunk_id', '')}"
                    })
            
            if not highlights:
                logger.warning("No se pudieron extraer highlights de los chunks")
                return self.generate_chunk_link(documento_origen, base_page, {})['pdf_link']
            
            # Generar parámetros
            doc_name_encoded = quote(documento_origen, safe='')
            multi_highlight_params = {
                'page': base_page,
                'multi_highlight': json.dumps(highlights)
            }
            
            result = f"{self.base_url}/viewer/{doc_name_encoded}?{urlencode(multi_highlight_params)}"
            
            logger.info(f"Enlace multi-chunk generado: {len(highlights)} resaltados")
            
            return result
            
        except Exception as e:
            logger.error(f"Error generando enlace multi-chunk: {e}")
            # Fallback a enlace simple
            return self.generate_chunk_link(documento_origen, base_page or 1, {})['pdf_link']

# Función de utilidad para testing
def test_link_generator():
    """Función de prueba para el generador de enlaces"""
    
    generator = DocumentLinkGenerator()
    
    # Datos de prueba
    test_data = {
        'documento_origen': 'Manual Balanza DIBAL Mistral.pdf',
        'pagina_numero': 161,
        'chunk_coordinates': {
            'x': 151.66,
            'y': 441.03,
            'width': 240.45,
            'height': 11.92
        },
        'chunk_id': 'chunk_000522'
    }
    
    # Generar enlaces
    enlaces = generator.generate_chunk_link(**test_data)
    
    print("🔗 Enlaces generados:")
    for key, value in enlaces.items():
        print(f"   {key}: {value}")
    
    return enlaces

if __name__ == "__main__":
    test_link_generator()
