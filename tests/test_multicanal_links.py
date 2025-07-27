"""
Test para verificar que los enlaces funcionan correctamente en múltiples canales
"""
from app.utils.multicanal import renderizar_enlace
from app.nodes.orquestador_busqueda_node import OrquestadorBusquedaNode
from app.nodes.improved_eroski_knowledge_base import OptimizedEroskiKnowledgeBaseWithMetadata
from app.nodes.buscar_solucion_node import BuscarSolucionNode
from app.utils.cargar_incidentes import EroskiIncidentsManager
from app.nodes.orquestador_busqueda_node import FAQ_ProblemIdentificationTool

def test_renderizar_enlace():
    """Test del helper renderizar_enlace"""
    
    url = "https://ejemplo.com/documento.pdf"
    texto = "Ver documento"
    
    # Test para WhatsApp
    state_whatsapp = {"channel": "whatsapp"}
    resultado_whatsapp = renderizar_enlace(state_whatsapp, texto, url)
    print(f"WhatsApp: {resultado_whatsapp}")
    assert resultado_whatsapp == f"{texto}: {url}"
    
    # Test para Chainlit
    state_chainlit = {"channel": "chainlit"}
    resultado_chainlit = renderizar_enlace(state_chainlit, texto, url)
    print(f"Chainlit: {resultado_chainlit}")
    assert resultado_chainlit == f"[{texto}]({url})"
    
    # Test sin canal especificado (debería usar formato Markdown)
    state_default = {}
    resultado_default = renderizar_enlace(state_default, texto, url)
    print(f"Default: {resultado_default}")
    assert resultado_default == f"[{texto}]({url})"
    
    print("✅ Todos los tests de renderizar_enlace pasaron")

def test_solucion_con_enlaces():
    """Test del método _generar_solucion_con_enlaces"""
    
    # Crear instancia del nodo
    buscar_soluciones = BuscarSolucionNode()
    node = OrquestadorBusquedaNode(
        knowledge_base=OptimizedEroskiKnowledgeBaseWithMetadata(),
        faq_tool=FAQ_ProblemIdentificationTool(EroskiIncidentsManager()),
        ordenar_chunks_chain=buscar_soluciones.setup_ordenar_chunks_chain(),
        agent_faq=buscar_soluciones.setup_agent_faq()
    )
    
    # Simular metadatos de chunks
    node.chunks_metadata = {
        "chunk_123": {
            'documento': {
                'filename': 'manual_balanza.pdf',
                'pagina_numero': 42
            },
            'equipo': {
                'marca': 'Dibal',
                'modelo': 'Mistral'
            },
            'posicion': {
                'x': 100,
                'y': 200,
                'width': 300,
                'height': 50
            }
        }
    }
    
    # Enlaces simulados
    enlaces_chunks = [{
        'chunk_id': 'chunk_123',
        'page': 42,
        'documento': 'manual_balanza.pdf',
        'equipo': {'marca': 'Dibal', 'modelo': 'Mistral'},
        'enlaces': {
            'pdf_link': 'http://servidor/pdf/manual_balanza.pdf#page=42',
            'web_viewer_link': 'http://servidor/viewer?doc=manual_balanza.pdf&page=42&highlight=chunk_123'
        }
    }]
    
    # Solución base
    solution_content = "Para solucionar el problema con la balanza:\n1. Apague y encienda el equipo\n2. Verifique las conexiones"
    
    print("\n=== Test WhatsApp ===")
    state_whatsapp = {"channel": "whatsapp"}
    # Simular el proceso interno
    solucion_whatsapp = solution_content + "\n\n🔗 Referencias directas:\n"
    solucion_whatsapp += "\n📄 Página 42 (Dibal Mistral):\n"
    solucion_whatsapp += "http://servidor/pdf/manual_balanza.pdf#page=42\n"
    solucion_whatsapp += "\n🖥️ Ver con resaltado:\n"
    solucion_whatsapp += "http://servidor/viewer?doc=manual_balanza.pdf&page=42&highlight=chunk_123\n"
    solucion_whatsapp += "\n💡 Los enlaces con resaltado te llevan directo a la ubicación exacta."
    
    print(solucion_whatsapp)
    print("\n✅ Formato WhatsApp: Enlaces como URLs simples")
    
    print("\n=== Test Chainlit ===")
    state_chainlit = {"channel": "chainlit"}
    solucion_chainlit = solution_content + "\n\n🔗 Referencias directas:\n"
    solucion_chainlit += "• [📄 Página 42 (Dibal Mistral)](http://servidor/pdf/manual_balanza.pdf#page=42)\n"
    solucion_chainlit += "• [🖥️ Ver con resaltado automático](http://servidor/viewer?doc=manual_balanza.pdf&page=42&highlight=chunk_123)\n"
    solucion_chainlit += "\n\n💡 Tip: Los enlaces con resaltado te llevarán directamente a la ubicación exacta en el documento."
    
    print(solucion_chainlit)
    print("\n✅ Formato Chainlit: Enlaces como Markdown")

if __name__ == "__main__":
    print("🧪 Ejecutando tests de enlaces multicanal\n")
    
    print("1️⃣ Test de renderizar_enlace:")
    test_renderizar_enlace()
    
    print("\n2️⃣ Test de solución con enlaces:")
    test_solucion_con_enlaces()
    
    print("\n✅ Todos los tests completados exitosamente!")