# =====================================================
# test_advanced_rag.py - Probar RAG completo con todas las mejoras
# =====================================================
"""
Script para probar el sistema RAG completo con:
- Diccionario técnico integrado
- Búsqueda híbrida optimizada  
- Expansión de consultas
- Re-ranking inteligente
"""

import asyncio
import logging
from pathlib import Path
import sys
import json

# Agregar el directorio raíz al path
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

# Importar el RAG completo - CORREGIDO
try:
    # Intentar importar RAG optimizado
    from nodes.optimized_eroski_knowledge_base import OptimizedEroskiKnowledgeBase
    print("✅ RAG optimizado importado correctamente")
    OPTIMIZED_RAG_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Error importando RAG optimizado: {e}")
    OPTIMIZED_RAG_AVAILABLE = False

try:
    # Intentar importar RAG con metadatos
    from nodes.improved_eroski_knowledge_base import OptimizedEroskiKnowledgeBaseWithMetadata
    print("✅ RAG con metadatos importado correctamente") 
    METADATA_RAG_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Error importando RAG con metadatos: {e}")
    METADATA_RAG_AVAILABLE = False

# Fallback al RAG básico
try:
    from nodes.buscar_solucion_node import EroskiKnowledgeBase
    BASIC_RAG_AVAILABLE = True
except ImportError:
    BASIC_RAG_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AdvancedRAGTester:
    """Tester para el sistema RAG completo"""
    
    def __init__(self):
        self.rag_system = None
        self.test_queries = [
            # Consultas que aprovechan el diccionario técnico
            "la balanza no funciona",
            "error al imprimir etiquetas", 
            "problema con el menú de configuración",
            "cómo calibrar la balanza",
            "la pantalla no muestra el peso",
            "papel atascado en la impresora",
            "código de error en la balanza",
            "resetear configuración de fábrica"
        ]
    
    async def initialize_rag_system(self):
        """Inicializa el sistema RAG más avanzado disponible"""
        
        print("🚀 INICIALIZANDO SISTEMA RAG AVANZADO")
        print("=" * 50)
        
        # Intentar en orden de preferencia
        if METADATA_RAG_AVAILABLE:
            try:
                print("🎯 Usando RAG con metadatos avanzados")
                self.rag_system = OptimizedEroskiKnowledgeBaseWithMetadata()
                print("✅ RAG con metadatos inicializado")
                return
            except Exception as e:
                print(f"⚠️ Error con RAG de metadatos: {e}")
        
        if OPTIMIZED_RAG_AVAILABLE:
            try:
                print("📊 Usando RAG optimizado estándar")
                self.rag_system = OptimizedEroskiKnowledgeBase()
                print("✅ RAG optimizado inicializado")
                return
            except Exception as e:
                print(f"⚠️ Error con RAG optimizado: {e}")
        
        if BASIC_RAG_AVAILABLE:
            try:
                print("📋 Usando RAG básico como fallback")
                self.rag_system = EroskiKnowledgeBase()
                print("✅ RAG básico inicializado")
                return
            except Exception as e:
                print(f"❌ Error con RAG básico: {e}")
        
        raise Exception("❌ No se pudo inicializar ningún sistema RAG")
    
    async def verify_dictionary_integration(self):
        """Verifica si el diccionario técnico está integrado"""
        
        print("\n🔍 VERIFICANDO INTEGRACIÓN DEL DICCIONARIO")
        print("-" * 45)
        
        # Verificar archivo de diccionario
        dict_files = [
            "config/technical_dictionary_fast.json",
            "config/technical_dictionary_generated.json", 
            "config/technical_dictionary_basic.json"
        ]
        
        dict_found = False
        for dict_file in dict_files:
            dict_path = Path(dict_file)
            if dict_path.exists():
                print(f"✅ Diccionario encontrado: {dict_file}")
                
                # Mostrar algunos términos
                try:
                    with open(dict_path, 'r', encoding='utf-8') as f:
                        dictionary = json.load(f)
                    
                    print(f"   📊 Total términos: {len(dictionary)}")
                    
                    # Mostrar términos más frecuentes
                    if dictionary:
                        sorted_terms = sorted(
                            dictionary.items(), 
                            key=lambda x: x[1].get('frequency', 0), 
                            reverse=True
                        )[:5]
                        
                        print("   🏆 Términos más frecuentes:")
                        for term, data in sorted_terms:
                            freq = data.get('frequency', 0)
                            category = data.get('category', 'general')
                            print(f"      • {term} ({category}): {freq} veces")
                
                except Exception as e:
                    print(f"   ⚠️ Error leyendo diccionario: {e}")
                
                dict_found = True
                break
        
        if not dict_found:
            print("❌ No se encontró diccionario técnico")
            print("💡 Ejecuta: python fast_dictionary_generator.py")
        
        return dict_found
    
    async def test_query_expansion(self):
        """Prueba la expansión de consultas"""
        
        print("\n🔄 PROBANDO EXPANSIÓN DE CONSULTAS")
        print("-" * 40)
        
        test_query = "balanza no imprime"
        
        # Verificar si tiene expansor de consultas
        if hasattr(self.rag_system, 'searcher') and hasattr(self.rag_system.searcher, 'query_expander'):
            try:
                expander = self.rag_system.searcher.query_expander
                
                if hasattr(expander, 'expand_query'):
                    expanded = await expander.expand_query(test_query)
                    
                    print(f"🔍 Consulta original: '{test_query}'")
                    print(f"📈 Consultas expandidas:")
                    for i, expanded_query in enumerate(expanded, 1):
                        print(f"   {i}. {expanded_query}")
                else:
                    print("⚠️ Expansor disponible pero sin método expand_query")
                    
            except Exception as e:
                print(f"❌ Error en expansión: {e}")
        else:
            print("📋 Expansión de consultas no disponible en este RAG")
    
    async def test_advanced_search(self):
        """Prueba búsqueda avanzada con métricas"""
        
        print("\n🎯 PROBANDO BÚSQUEDA AVANZADA")
        print("-" * 35)
        
        for i, query in enumerate(self.test_queries[:4], 1):  # Solo primeras 4 para no saturar
            print(f"\n{i}. 🔍 Consulta: '{query}'")
            print("   " + "-" * 40)
            
            try:
                # Usar método avanzado si está disponible
                if hasattr(self.rag_system, 'buscar_solucion_rag_avanzada'):
                    result = await self.rag_system.buscar_solucion_rag_avanzada(query, top_k=2)
                elif hasattr(self.rag_system, 'buscar_solucion_rag_with_learning'):
                    result, metrics = await self.rag_system.buscar_solucion_rag_with_learning(query, top_k=2)
                    print(f"   📊 Métricas: {metrics}")
                else:
                    # Usar método básico
                    result = await self._basic_search_async(query)
                
                if result:
                    # Mostrar resultado
                    preview = result[:300] + "..." if len(result) > 300 else result
                    print(f"   ✅ Resultado:")
                    print(f"      {preview}")
                else:
                    print("   ❌ Sin resultados")
                
            except Exception as e:
                print(f"   ❌ Error: {e}")
                
            print()  # Línea separadora
    
    async def _basic_search_async(self, query: str) -> str:
        """Búsqueda básica asíncrona"""
        try:
            if hasattr(self.rag_system, 'buscar_solucion_rag'):
                # Si tiene método asíncrono
                if asyncio.iscoroutinefunction(self.rag_system.buscar_solucion_rag):
                    return await self.rag_system.buscar_solucion_rag(query)
                else:
                    # Método síncrono
                    return self.rag_system.buscar_solucion_rag(query)
            else:
                return "Método de búsqueda no disponible"
        except Exception as e:
            return f"Error en búsqueda: {e}"
    
    async def test_performance_comparison(self):
        """Compara rendimiento entre diferentes métodos"""
        
        print("\n⚡ COMPARACIÓN DE RENDIMIENTO")
        print("-" * 35)
        
        test_query = "configurar menú balanza"
        
        import time
        
        # Test básico
        start_time = time.time()
        try:
            result_basic = await self._basic_search_async(test_query)
            basic_time = time.time() - start_time
            print(f"📋 Búsqueda básica: {basic_time:.2f}s")
        except Exception as e:
            print(f"❌ Error búsqueda básica: {e}")
            basic_time = 0
        
        # Test avanzado (si disponible)
        if hasattr(self.rag_system, 'buscar_solucion_rag_avanzada'):
            start_time = time.time()
            try:
                result_advanced = await self.rag_system.buscar_solucion_rag_avanzada(test_query)
                advanced_time = time.time() - start_time
                print(f"🚀 Búsqueda avanzada: {advanced_time:.2f}s")
                
                if basic_time > 0:
                    improvement = ((basic_time - advanced_time) / basic_time) * 100
                    print(f"📈 Mejora: {improvement:.1f}%")
                    
            except Exception as e:
                print(f"❌ Error búsqueda avanzada: {e}")
    
    async def run_comprehensive_test(self):
        """Ejecuta suite de pruebas completa"""
        
        print("🧪 SUITE DE PRUEBAS RAG AVANZADO")
        print("=" * 50)
        
        try:
            # 1. Inicializar sistema
            await self.initialize_rag_system()
            
            # 2. Verificar diccionario
            dict_available = await self.verify_dictionary_integration()
            
            # 3. Probar expansión de consultas
            await self.test_query_expansion()
            
            # 4. Probar búsqueda avanzada
            await self.test_advanced_search()
            
            # 5. Comparar rendimiento
            await self.test_performance_comparison()
            
            # 6. Resumen final
            print("\n📊 RESUMEN DE CAPACIDADES")
            print("-" * 30)
            
            capabilities = []
            
            if dict_available:
                capabilities.append("✅ Diccionario técnico integrado")
            else:
                capabilities.append("❌ Diccionario técnico faltante")
            
            if hasattr(self.rag_system, 'searcher'):
                capabilities.append("✅ Sistema de búsqueda avanzado")
            else:
                capabilities.append("📋 Sistema de búsqueda básico")
            
            if hasattr(self.rag_system, 'buscar_solucion_rag_avanzada'):
                capabilities.append("✅ Búsqueda RAG avanzada")
            else:
                capabilities.append("📋 Búsqueda RAG básica")
            
            for capability in capabilities:
                print(f"   {capability}")
            
            print("\n🎉 PRUEBAS COMPLETADAS")
            print("\n🚀 PRÓXIMO PASO:")
            print("   Ejecutar chatbot completo: python main.py")
            
        except Exception as e:
            print(f"\n❌ Error en pruebas: {e}")
            logger.exception("Error completo:")

async def main():
    """Función principal"""
    
    tester = AdvancedRAGTester()
    await tester.run_comprehensive_test()

if __name__ == "__main__":
    asyncio.run(main())