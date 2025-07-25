# =====================================================
# PASO 4: run_server.py - Script para ejecutar
# =====================================================


"""
run_server.py - Script para ejecutar el servidor PDF
"""

import uvicorn
import os
import sys
from pathlib import Path

def main():
    """Función principal para ejecutar el servidor"""
    
    print("🚀 Iniciando Servidor PDF de Eroski...")
    print("=" * 50)
    
    # Verificar estructura de carpetas
    required_dirs = ["docs", "templates"]
    for dir_name in required_dirs:
        dir_path = Path(dir_name)
        if not dir_path.exists():
            print(f"📁 Creando carpeta: {dir_name}/")
            dir_path.mkdir(exist_ok=True)
        else:
            print(f"✅ Carpeta encontrada: {dir_name}/")
    
    # Verificar template
    template_path = Path("templates/pdf_viewer.html")
    if not template_path.exists():
        print(f"⚠️  Template no encontrado: {template_path}")
        print("   Por favor, crea el archivo templates/pdf_viewer.html")
        return
    
    # Verificar PDFs
    docs_path = Path("docs")
    pdf_count = len(list(docs_path.glob("*.pdf")))
    print(f"📚 PDFs encontrados: {pdf_count}")
    
    print("\n🌐 Iniciando servidor web...")
    print("   URL: http://localhost:8000")
    print("   Documentación: http://localhost:8000/docs")
    print("   PDFs disponibles: http://localhost:8000/list-pdfs")
    print("\n💡 Presiona Ctrl+C para detener el servidor")
    print("=" * 50)
    
    try:
        # Ejecutar servidor
        uvicorn.run(
            "pdf_server:app",
            host="0.0.0.0",
            port=8000,
            reload=True,
            log_level="info"
        )
    except KeyboardInterrupt:
        print("\n👋 Servidor detenido por el usuario")
    except Exception as e:
        print(f"\n❌ Error ejecutando servidor: {e}")

if __name__ == "__main__":
    main()
