#!/usr/bin/env python3
"""
Combined application that runs Chainlit, WhatsApp webhook, and PDF server
"""
import os
import sys
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse, HTMLResponse, FileResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from pathlib import Path
import json
from urllib.parse import unquote
import logging
import uvicorn
from datetime import datetime
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import WhatsApp webhook handlers
from app.workflows.incidencia_workflow import procesar_mensaje_whatsapp
import httpx

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# WhatsApp configuration
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "eroski2024")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")

# PDF server configuration
DOCS_PATH = Path("docs")
DOCS_PATH.mkdir(exist_ok=True)
templates = Jinja2Templates(directory="templates")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("🚀 Starting combined Eroski Chatbot application...")
    print("💬 Chainlit interface: /chat")
    print("📱 WhatsApp webhook: /webhook")
    print("📄 PDF viewer: /pdf")
    yield
    # Shutdown
    print("👋 Shutting down...")

# Create FastAPI app
app = FastAPI(title="Eroski Chatbot", lifespan=lifespan)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =====================================================
# WhatsApp Webhook Endpoints
# =====================================================

@app.get("/webhook")
async def verify_webhook(request: Request):
    """Verificación del webhook de WhatsApp"""
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    
    print(f"🔍 Verificación webhook: mode={mode}, token={token}")
    
    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("✅ Webhook verificado correctamente")
        return PlainTextResponse(content=challenge)
    else:
        print("❌ Token de verificación incorrecto")
        return JSONResponse(content={"error": "Token inválido"}, status_code=403)

@app.post("/webhook")
async def handle_webhook(request: Request):
    """Maneja mensajes entrantes de WhatsApp"""
    try:
        data = await request.json()
        print(f"📨 Webhook recibido: {data}")
        
        # Process WhatsApp messages
        entry = data.get("entry", [])
        if entry:
            for item in entry:
                changes = item.get("changes", [])
                for change in changes:
                    value = change.get("value", {})
                    
                    # Handle message
                    if "messages" in value:
                        messages = value.get("messages", [])
                        for message in messages:
                            from_number = message.get("from")
                            msg_type = message.get("type")
                            
                            if msg_type == "text":
                                text = message.get("text", {}).get("body", "")
                                print(f"📱 Mensaje de {from_number}: {text}")
                                
                                # Process message asynchronously
                                asyncio.create_task(
                                    procesar_mensaje_whatsapp(from_number, text)
                                )
                    
                    # Handle status updates
                    elif "statuses" in value:
                        statuses = value.get("statuses", [])
                        for status in statuses:
                            print(f"📊 Estado actualizado: {status}")
        
        return JSONResponse(content={"status": "ok"})
    
    except Exception as e:
        print(f"❌ Error procesando webhook: {str(e)}")
        return JSONResponse(
            content={"error": str(e)},
            status_code=500
        )

# =====================================================
# PDF Server Endpoints (PUBLIC - NO AUTH REQUIRED)
# =====================================================

@app.get("/pdf", response_class=HTMLResponse)
async def pdf_home():
    """Página de inicio del visor PDF"""
    
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
            }
            .header {
                text-align: center;
                margin-bottom: 40px;
            }
            .info-box {
                background-color: #f0f0f0;
                padding: 20px;
                border-radius: 8px;
                margin-bottom: 20px;
            }
            .pdf-list {
                margin-top: 30px;
            }
            .pdf-item {
                padding: 10px;
                margin: 5px 0;
                background-color: #f9f9f9;
                border-radius: 4px;
            }
            .pdf-item a {
                text-decoration: none;
                color: #2563eb;
                font-weight: 500;
            }
            .pdf-item a:hover {
                text-decoration: underline;
            }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>📄 Eroski PDF Viewer</h1>
            <p>Sistema de visualización de documentos con resaltado</p>
        </div>
        
        <div class="info-box">
            <h3>ℹ️ Información</h3>
            <p>Este servidor permite visualizar PDFs con resaltado de texto relevante.</p>
            <p>Para ver un PDF con resaltado, usa:</p>
            <code>/pdf/view/{filename}?highlight=texto&amp;page=1</code>
        </div>
        
        <div class="pdf-list">
            <h3>📁 Documentos disponibles:</h3>
            <div id="pdf-files">
                <p>Cargando documentos...</p>
            </div>
        </div>
        
        <script>
            // Cargar lista de PDFs disponibles
            fetch('/pdf/list')
                .then(response => response.json())
                .then(files => {
                    const container = document.getElementById('pdf-files');
                    if (files.length === 0) {
                        container.innerHTML = '<p>No hay documentos PDF en la carpeta docs/</p>';
                    } else {
                        container.innerHTML = files.map(file => 
                            `<div class="pdf-item">
                                <a href="/pdf/view/${file}" target="_blank">📄 ${file}</a>
                            </div>`
                        ).join('');
                    }
                })
                .catch(error => {
                    document.getElementById('pdf-files').innerHTML = 
                        '<p>Error cargando documentos</p>';
                });
        </script>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)

@app.get("/pdf/list")
async def list_pdfs():
    """Lista todos los PDFs disponibles"""
    try:
        pdf_files = [f.name for f in DOCS_PATH.glob("*.pdf")]
        return JSONResponse(content=pdf_files)
    except Exception as e:
        logger.error(f"Error listando PDFs: {e}")
        return JSONResponse(content=[], status_code=500)

@app.get("/pdf/view/{filename}", response_class=HTMLResponse)
async def view_pdf(request: Request, filename: str):
    """Muestra un PDF con resaltado opcional"""
    
    # Decodificar el nombre del archivo
    filename = unquote(filename)
    pdf_path = DOCS_PATH / filename
    
    # Verificar que el archivo existe
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail=f"PDF no encontrado: {filename}")
    
    # Obtener parámetros de query
    highlight_text = request.query_params.get("highlight", "")
    page_number = request.query_params.get("page", "1")
    
    # Log para depuración
    logger.info(f"Mostrando PDF: {filename}")
    logger.info(f"Texto a resaltar: {highlight_text}")
    logger.info(f"Página: {page_number}")
    
    # Parse highlight data if it's JSON
    highlight_data = None
    if highlight_text:
        try:
            import json
            highlight_data = json.loads(highlight_text)
        except:
            # If not JSON, treat as regular text
            pass
    
    # Renderizar template
    return templates.TemplateResponse("pdf_viewer.html", {
        "request": request,
        "filename": filename,
        "pdf_url": f"/pdf/file/{filename}",
        "page": int(page_number),
        "highlight_data": highlight_data,
        "multi_highlight_data": None
    })

@app.get("/pdf/file/{filename}")
async def serve_pdf(filename: str):
    """Sirve el archivo PDF"""
    filename = unquote(filename)
    pdf_path = DOCS_PATH / filename
    
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF no encontrado")
    
    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"inline; filename={filename}"
        }
    )

# Legacy routes for backward compatibility
@app.get("/docs/{filename}")
async def legacy_serve_pdf(filename: str):
    """Legacy route for serving PDFs - redirects to new route"""
    return RedirectResponse(url=f"/pdf/file/{filename}")

@app.get("/viewer/{filename}")
async def legacy_view_pdf(request: Request, filename: str):
    """Legacy route for viewing PDFs - redirects to new route"""
    query_string = str(request.url).split('?', 1)[1] if '?' in str(request.url) else ''
    return RedirectResponse(url=f"/pdf/view/{filename}?{query_string}")

# =====================================================
# Main API Endpoints
# =====================================================

@app.get("/")
async def root():
    return {
        "message": "Eroski Chatbot API",
        "endpoints": {
            "chainlit": "/chat",
            "whatsapp_webhook": "/webhook",
            "pdf_viewer": "/pdf",
            "api_test": "/api/test"
        },
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/test")
async def test():
    return {
        "server": "funcionando",
        "services": {
            "chainlit": "mounted at /chat",
            "whatsapp": {
                "webhook_url": "/webhook",
                "verify_token": VERIFY_TOKEN,
                "phone_id_configured": bool(PHONE_NUMBER_ID),
                "token_configured": bool(WHATSAPP_TOKEN)
            },
            "pdf_server": "active at /pdf"
        }
    }

# Mount Chainlit app LAST so its auth doesn't affect other routes
from chainlit.utils import mount_chainlit
mount_chainlit(app=app, target="chainlit_app.py", path="/chat")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"🚀 Starting server on port {port}")
    print(f"📱 WhatsApp webhook: http://localhost:{port}/webhook")
    print(f"💬 Chainlit interface: http://localhost:{port}/chat")
    print(f"📄 PDF viewer: http://localhost:{port}/pdf")
    
    uvicorn.run(app, host="0.0.0.0", port=port)