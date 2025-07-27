

# =====================================================
# PASO 3: pdf_server.py - Servidor principal
# =====================================================


"""
pdf_server.py - Servidor FastAPI para mostrar PDFs con resaltado
"""

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
import json
from urllib.parse import unquote
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Crear aplicación FastAPI
app = FastAPI(title="Eroski PDF Viewer", version="1.0.0")

# Configurar templates
templates = Jinja2Templates(directory="templates")

# Ruta de documentos PDF
DOCS_PATH = Path("docs")

# Crear carpeta docs si no existe
DOCS_PATH.mkdir(exist_ok=True)

@app.get("/", response_class=HTMLResponse)
async def home():
    """Página de inicio simple"""
    
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Eroski PDF Viewer</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                max-width: 800px;
                margin: 50px auto;
                padding: 20px;
                background-color: #f5f5f5;
            }
            .container {
                background: white;
                padding: 30px;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }
            h1 { color: #2c3e50; }
            .status { 
                padding: 10px; 
                border-radius: 5px; 
                margin: 10px 0;
            }
            .success { background: #d4edda; color: #155724; }
            .warning { background: #fff3cd; color: #856404; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔧 Eroski PDF Viewer</h1>
            <p>Servidor de visualización de PDFs con resaltado automático</p>
            
            <div class="status success">
                ✅ Servidor funcionando correctamente
            </div>
            
            <h3>URLs de ejemplo:</h3>
            <ul>
                <li><strong>Listar PDFs:</strong> <a href="/list-pdfs">/list-pdfs</a></li>
                <li><strong>Ver PDF:</strong> /viewer/nombre_del_archivo.pdf</li>
                <li><strong>PDF con resaltado:</strong> /viewer/archivo.pdf?page=1&highlight={"x":100,"y":200,"width":300,"height":20}</li>
            </ul>
            
            <div class="status warning">
                📁 Coloca tus archivos PDF en la carpeta: <code>docs/</code>
            </div>
        </div>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)

@app.get("/list-pdfs")
async def list_pdfs():
    """Lista todos los PDFs disponibles"""
    
    pdf_files = list(DOCS_PATH.glob("*.pdf"))
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>PDFs Disponibles</title>
        <style>
            body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; }}
            .pdf-item {{ 
                background: white; 
                padding: 15px; 
                margin: 10px 0; 
                border-radius: 8px; 
                box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            }}
            .pdf-item a {{ color: #007bff; text-decoration: none; }}
            .pdf-item a:hover {{ text-decoration: underline; }}
        </style>
    </head>
    <body>
        <h1>📚 PDFs Disponibles ({len(pdf_files)})</h1>
        
        {chr(10).join([f'''
        <div class="pdf-item">
            <strong>📄 {pdf.name}</strong><br>
            <a href="/viewer/{pdf.name}">Ver PDF</a> | 
            <a href="/docs/{pdf.name}">Descargar</a>
        </div>
        ''' for pdf in pdf_files]) if pdf_files else '<p>No hay PDFs en la carpeta docs/</p>'}
        
        <br><a href="/">← Volver al inicio</a>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)

@app.get("/viewer/{document_name}", response_class=HTMLResponse)
async def pdf_viewer(request: Request, document_name: str):
    """
    Visor PDF con resaltado automático
    """
    
    try:
        # Decodificar nombre del documento
        document_name = unquote(document_name)
        logger.info(f"Solicitando visor para: {document_name}")
        
        # Verificar que el PDF existe
        pdf_path = DOCS_PATH / document_name
        if not pdf_path.exists():
            logger.error(f"PDF no encontrado: {pdf_path}")
            raise HTTPException(status_code=404, detail=f"Documento no encontrado: {document_name}")
        
        # Obtener parámetros de la URL
        page = request.query_params.get('page', 1)
        highlight = request.query_params.get('highlight')
        multi_highlight = request.query_params.get('multi_highlight')
        
        logger.info(f"Parámetros: page={page}, highlight={bool(highlight)}")
        
        # Decodificar información de resaltado
        highlight_data = None
        multi_highlight_data = None
        
        if highlight:
            try:
                highlight_data = json.loads(highlight)
                logger.info(f"Highlight data: {highlight_data}")
            except Exception as e:
                logger.warning(f"Error decodificando highlight: {e}")
        
        if multi_highlight:
            try:
                multi_highlight_data = json.loads(multi_highlight)
                logger.info(f"Multi-highlight data: {len(multi_highlight_data)} elementos")
            except Exception as e:
                logger.warning(f"Error decodificando multi_highlight: {e}")
        
        # Contexto para el template
        context = {
            "request": request,
            "document_name": document_name,
            "pdf_url": f"/docs/{document_name.replace(' ', '%20')}",
            "page": page,
            "highlight_data": highlight_data,
            "multi_highlight_data": multi_highlight_data,
            "chunk_id": highlight_data.get('chunk_id') if highlight_data else None,
            "equipment_type": "Equipo Técnico",
            "brand": "Marca",
            "model": "Modelo"
        }
        
        return templates.TemplateResponse("pdf_viewer.html", context)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error en pdf_viewer: {e}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")

@app.get("/docs/{document_name}")
async def serve_pdf(document_name: str):
    """
    Sirve los archivos PDF directamente
    """
    
    try:
        document_name = unquote(document_name)
        pdf_path = DOCS_PATH / document_name
        
        if not pdf_path.exists():
            logger.error(f"PDF no encontrado para descarga: {pdf_path}")
            raise HTTPException(status_code=404, detail="Documento no encontrado")
        
        logger.info(f"Sirviendo PDF: {document_name}")
        
        return FileResponse(
            pdf_path,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"inline; filename={document_name}",
                "Cache-Control": "public, max-age=3600"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sirviendo PDF: {e}")
        raise HTTPException(status_code=500, detail="Error sirviendo archivo")

@app.get("/test-highlight/{document_name}")
async def test_highlight(document_name: str):
    """
    URL de prueba con resaltado de ejemplo
    """
    
    # Coordenadas de ejemplo (varias pruebas)
    test_highlights = [
        {
            "name": "Esquina superior izquierda",
            "data": {
                "x": 50,
                "y": 50,
                "width": 200,
                "height": 30,
                "color": "rgba(255, 0, 0, 0.5)",
                "chunk_id": "test_esquina_superior"
            }
        },
        {
            "name": "Centro de la página",
            "data": {
                "x": 200,
                "y": 400,
                "width": 300,
                "height": 25,
                "color": "rgba(0, 255, 0, 0.5)",
                "chunk_id": "test_centro"
            }
        },
        {
            "name": "Parte inferior",
            "data": {
                "x": 100,
                "y": 700,
                "width": 400,
                "height": 20,
                "color": "rgba(0, 0, 255, 0.5)",
                "chunk_id": "test_inferior"
            }
        }
    ]
    
    test_urls = []
    for test in test_highlights:
        highlight_json = json.dumps(test["data"])
        test_urls.append({
            "name": test["name"],
            "url": f"/viewer/{document_name}?page=1&highlight={highlight_json}",
            "coordinates": test["data"]
        })
    
    return {
        "message": "URLs de prueba generadas",
        "document": document_name,
        "test_urls": test_urls
    }

# Manejo de errores
@app.exception_handler(404)
async def not_found_handler(request: Request, exc: HTTPException):
    return HTMLResponse(
        content=f"""
        <html>
        <body style="font-family: Arial, sans-serif; text-align: center; margin-top: 100px;">
            <h1>❌ Error 404</h1>
            <p>{exc.detail}</p>
            <a href="/">← Volver al inicio</a>
        </body>
        </html>
        """,
        status_code=404
    )

@app.exception_handler(500)
async def server_error_handler(request: Request, exc: HTTPException):
    return HTMLResponse(
        content=f"""
        <html>
        <body style="font-family: Arial, sans-serif; text-align: center; margin-top: 100px;">
            <h1>⚠️ Error del Servidor</h1>
            <p>{exc.detail}</p>
            <a href="/">← Volver al inicio</a>
        </body>
        </html>
        """,
        status_code=500
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)



# =====================================================
# PASO 6: Instrucciones de instalación
# =====================================================

INSTALLATION_INSTRUCTIONS = """
# =====================================================
# INSTRUCCIONES DE INSTALACIÓN PASO A PASO
# =====================================================

## 📋 PASO 1: Crear estructura de carpetas
mkdir tu_chatbot_eroski
cd tu_chatbot_eroski
mkdir docs templates static utils

## 📋 PASO 2: Instalar dependencias
pip install fastapi uvicorn jinja2 python-multipart aiofiles

## 📋 PASO 3: Crear archivos
# Crear cada archivo con el contenido correspondiente:
# - pdf_server.py
# - run_server.py  
# - utils/document_link_generator.py
# - templates/pdf_viewer.html (siguiente paso)

## 📋 PASO 4: Copiar tus PDFs
# Copia tus archivos PDF a la carpeta docs/
cp /ruta/a/tus/pdfs/*.pdf docs/

## 📋 PASO 5: Ejecutar servidor
python run_server.py

## 📋 PASO 6: Probar
# Visitar: http://localhost:8000
# Ver PDFs: http://localhost:8000/list-pdfs

## 🔗 PASO 7: URLs de ejemplo
# PDF simple: http://localhost:8000/viewer/tu_archivo.pdf
# PDF con resaltado: http://localhost:8000/viewer/tu_archivo.pdf?page=1&highlight={"x":100,"y":200,"width":300,"height":20}
"""