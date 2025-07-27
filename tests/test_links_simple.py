"""
Test simplificado para verificar el formato de enlaces en WhatsApp vs Chainlit
"""

def renderizar_enlace(state, texto, url):
    """Copia de la función para testing"""
    if state.get("channel") == "whatsapp":
        return f"{texto}: {url}"
    return f"[{texto}]({url})"

def test_formato_enlaces():
    """Demostración del formato de enlaces para cada canal"""
    
    # URLs de ejemplo
    pdf_url = "http://servidor/pdf/manual_balanza.pdf#page=42"
    viewer_url = "http://servidor/viewer?doc=manual_balanza.pdf&page=42&highlight=chunk_123"
    
    # Solución base
    solution_content = "Para solucionar el problema con la balanza:\n1. Apague y encienda el equipo\n2. Verifique las conexiones"
    
    print("=== FORMATO WHATSAPP ===")
    print("(Enlaces como URLs simples que WhatsApp convierte automáticamente)\n")
    
    # Simular estado WhatsApp
    state_whatsapp = {"channel": "whatsapp"}
    
    # Construir mensaje para WhatsApp
    mensaje_whatsapp = solution_content
    mensaje_whatsapp += "\n\n🔗 Referencias directas:\n"
    mensaje_whatsapp += "\n📄 Página 42 (Dibal Mistral):\n"
    mensaje_whatsapp += f"{pdf_url}\n"
    mensaje_whatsapp += "\n🖥️ Ver con resaltado:\n"
    mensaje_whatsapp += f"{viewer_url}\n"
    mensaje_whatsapp += "\n💡 Los enlaces con resaltado te llevan directo a la ubicación exacta."
    
    print(mensaje_whatsapp)
    print("\n" + "="*50 + "\n")
    
    print("=== FORMATO CHAINLIT ===")
    print("(Enlaces como Markdown que se renderizan como botones/links)\n")
    
    # Simular estado Chainlit
    state_chainlit = {"channel": "chainlit"}
    
    # Construir mensaje para Chainlit
    mensaje_chainlit = solution_content
    mensaje_chainlit += "\n\n🔗 Referencias directas:\n"
    
    # Usar la función helper
    texto_pdf = "📄 Página 42 (Dibal Mistral)"
    texto_viewer = "🖥️ Ver con resaltado automático"
    
    enlace_pdf = renderizar_enlace(state_chainlit, texto_pdf, pdf_url)
    enlace_viewer = renderizar_enlace(state_chainlit, texto_viewer, viewer_url)
    
    mensaje_chainlit += f"• {enlace_pdf}\n"
    mensaje_chainlit += f"• {enlace_viewer}\n"
    mensaje_chainlit += "\n\n💡 Tip: Los enlaces con resaltado te llevarán directamente a la ubicación exacta en el documento."
    
    print(mensaje_chainlit)
    print("\n" + "="*50 + "\n")
    
    # Mostrar diferencias
    print("DIFERENCIAS CLAVE:")
    print("1. WhatsApp: URL completa en línea separada (se convierte automáticamente en link clickeable)")
    print("2. Chainlit: Formato Markdown [texto](url) que se renderiza como link con el texto personalizado")
    print("\nEjemplos:")
    print(f"  WhatsApp: {renderizar_enlace(state_whatsapp, 'Ver documento', 'http://ejemplo.com')}")
    print(f"  Chainlit: {renderizar_enlace(state_chainlit, 'Ver documento', 'http://ejemplo.com')}")

if __name__ == "__main__":
    test_formato_enlaces()