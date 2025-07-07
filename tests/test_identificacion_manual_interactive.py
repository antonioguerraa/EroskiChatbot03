#!/usr/bin/env python3
# =====================================================
# tests/test_identificacion_manual_interactive.py - Tests Interactivos
# =====================================================
"""
Test interactivo para verificar el funcionamiento del nodo IdentificacionManualNode.

FUNCIONALIDADES:
- Simulación completa de conversación
- Tests de casos de uso reales
- Verificación de integración con BD
- Debugging en tiempo real
- Casos edge y manejo de errores

USO:
    python tests/test_identificacion_manual_interactive.py

CASOS DE TEST:
1. Flujo completo exitoso
2. Corrección de datos
3. Confirmación de tienda
4. Manejo de errores
5. Datos incompletos
"""

import asyncio
import sys
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List
from langchain_core.messages import HumanMessage, AIMessage

# Setup path para imports
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

# Setup logging más detallado para testing
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("TestIdentificacionManual")

# Imports del proyecto
try:
    from models.eroski_state import EroskiState, create_initial_eroski_state
    from nodes.identificacion_manual import IdentificacionManualNode, identificacion_manual_node
    from config.settings import get_settings
    from utils.llm.providers import get_llm
    IMPORTS_OK = True
except ImportError as e:
    print(f"❌ Error importando módulos: {e}")
    print("💡 Asegúrate de estar en el directorio raíz del proyecto")
    IMPORTS_OK = False


class TestIdentificacionManualInteractive:
    """Tester interactivo para el nodo de identificación manual"""
    
    def __init__(self):
        self.node = None
        self.test_results = []
        self.current_state = None
        
        # Casos de test predefinidos
        self.test_cases = {
            "flujo_completo": [
                "Hola, soy Juan Pérez",
                "Mi número es 1234", 
                "Trabajo en el Hipermercado Bilbondo",
                "Sí",  # Confirmación de tienda
                "En la sección de pescadería"
            ],
            "todo_junto": [
                "Hola, soy María García, número 5678, trabajo en Center Durango en panadería"
            ],
            "con_correccion": [
                "Me llamo Pedro López, número 9999",
                "Quiero cambiar mi número, es 0001",
                "Trabajo en City Baracaldo en carnicería"
            ],
            "tienda_ambigua": [
                "Soy Ana Ruiz, número 2222",
                "Trabajo en el Eroski de Bilbao",
                "No, no es esa tienda",  # Rechaza sugerencia
                "Hipermercado Bilbondo",
                "Sí, esa es correcta",  # Confirma nueva tienda
                "En caja"
            ],
            "confirmacion_explicita": [
                "Juan Martínez, empleado 3333",
                "Eroski Durango",
                "Sí, es correcto",  # Confirmación explícita
                "Departamento de panadería"
            ],
            "correccion_multiple": [
                "Soy Luis García, número 4444",
                "Trabajo en Bilbao", 
                "No está bien",  # Rechaza
                "Center Durango",
                "Perfecto",  # Confirma
                "Quiero cambiar mi nombre, es Luis Fernández",  # Corrección
                "Sección de carnicería"
            ]
        }
    
    async def setup(self):
        """Configurar entorno de test"""
        print("🔧 Configurando entorno de test...")
        
        if not IMPORTS_OK:
            print("❌ No se pueden ejecutar tests - faltan imports")
            return False
        
        try:
            # Verificar configuración
            settings = get_settings()
            print(f"✅ Settings cargados: DB={settings.database.name}")
            
            # Inicializar nodo
            self.node = IdentificacionManualNode()
            print("✅ Nodo inicializado correctamente")
            
            # Test de conexión LLM
            llm = get_llm()
            print("✅ LLM disponible")
            
            # Verificar tool de confirmación
            if hasattr(self.node, 'confirmation_tool') and self.node.confirmation_tool:
                print("✅ Tool de confirmación disponible")
            else:
                print("⚠️ Tool de confirmación no disponible (usará fallback)")
            
            return True
            
        except Exception as e:
            print(f"❌ Error en setup: {e}")
            return False
    
    async def crear_estado_inicial(self, session_id: str = None) -> EroskiState:
        """Crear estado inicial para test"""
        if not session_id:
            session_id = f"test_{datetime.now().strftime('%H%M%S')}"
        
        return {
            "session_id": session_id,
            "messages": [],
            "current_node": "identificacion_manual",
            "start_time": datetime.now().isoformat(),
            "attempts": 0,
            "error_count": 0
        }
    
    def mostrar_estado_actual(self, state: EroskiState):
        """Mostrar estado actual de forma legible"""
        print("\n" + "="*50)
        print("📊 ESTADO ACTUAL")
        print("="*50)
        
        # Datos de identificación
        print("🔍 DATOS DE IDENTIFICACIÓN:")
        print(f"   👤 Nombre: {state.get('employee_name', '❌ No definido')}")
        print(f"   🆔 Nº Empleado: {state.get('employee_id', '❌ No definido')}")
        print(f"   🏬 Tienda: {state.get('incident_store_name', '❌ No definido')}")
        print(f"   📍 Código Tienda: {state.get('store_id', '❌ No definido')}")
        print(f"   🧭 Sección: {state.get('incident_department', '❌ No definido')}")
        
        # Estado del proceso
        print(f"\n🔄 ESTADO DEL PROCESO:")
        print(f"   🎯 Nodo actual: {state.get('current_node', 'N/A')}")
        print(f"   ✅ Identificación completa: {state.get('identification_complete', False)}")
        print(f"   🔐 Autenticado: {state.get('authenticated', False)}")
        print(f"   ⚠️ Errores: {state.get('error_count', 0)}")
        
        # Flags especiales
        flags_especiales = []
        if state.get('pending_store_confirmation'):
            flags_especiales.append("⏳ Confirmación de tienda pendiente")
        if state.get('pending_store_selection'):
            flags_especiales.append("🏬 Selección de tienda pendiente")
        if state.get('identification_started'):
            flags_especiales.append("🚀 Identificación iniciada")
        
        if flags_especiales:
            print(f"\n🏃 FLAGS ACTIVOS:")
            for flag in flags_especiales:
                print(f"   {flag}")
        
        # DEBUG: Mostrar todas las claves del estado
        print(f"\n🔧 DEBUG - TODAS LAS CLAVES DEL ESTADO:")
        for key, value in state.items():
            if key != "messages":  # Omitir messages para no saturar
                print(f"   {key}: {value}")
        
        # Último mensaje del bot
        messages = state.get('messages', [])
        if messages:
            ultimo_mensaje = messages[-1]
            if isinstance(ultimo_mensaje, AIMessage):
                print(f"\n🤖 ÚLTIMO MENSAJE DEL BOT:")
                print(f"   {ultimo_mensaje.content[:200]}...")
        
        print("="*50)
    
    async def ejecutar_conversacion_paso_a_paso(self, mensajes_usuario: List[str], test_name: str = "test"):
        """Ejecutar conversación paso a paso"""
        print(f"\n🎬 INICIANDO TEST: {test_name}")
        print("="*60)
        
        # Crear estado inicial
        state = await self.crear_estado_inicial(f"{test_name}_{datetime.now().strftime('%H%M%S')}")
        
        # Mensaje inicial del nodo
        print("🤖 BOT: Iniciando conversación...")
        result = await self.node.execute(state)
        state.update(result.update)
        
        # Mostrar mensaje inicial
        if state.get('messages'):
            print(f"🤖 BOT: {state['messages'][-1].content}")
        
        # Procesar cada mensaje del usuario
        for i, mensaje_usuario in enumerate(mensajes_usuario, 1):
            print(f"\n--- TURNO {i} ---")
            print(f"👤 USUARIO: {mensaje_usuario}")
            
            # Añadir mensaje del usuario al estado
            state['messages'].append(HumanMessage(content=mensaje_usuario))
            
            # Ejecutar nodo
            try:
                result = await self.node.execute(state)
                state.update(result.update)
                
                # Mostrar respuesta del bot
                if state.get('messages') and isinstance(state['messages'][-1], AIMessage):
                    print(f"🤖 BOT: {state['messages'][-1].content}")
                
                # Mostrar estado resumido
                print(f"📊 Estado: Nombre={state.get('employee_name', 'N/A')}, "
                      f"Nº={state.get('employee_id', 'N/A')}, "
                      f"Tienda={state.get('incident_store_name', 'N/A')}, "
                      f"Sección={state.get('incident_department', 'N/A')}")
                
                # Verificar si completó
                if state.get('identification_complete'):
                    print("🎉 ¡IDENTIFICACIÓN COMPLETADA!")
                    break
                    
            except Exception as e:
                print(f"❌ ERROR en turno {i}: {e}")
                self.test_results.append({
                    "test": test_name,
                    "turno": i,
                    "error": str(e),
                    "exito": False
                })
                return state
        
        # Resultado final
        exito = state.get('identification_complete', False)
        self.test_results.append({
            "test": test_name,
            "exito": exito,
            "turnos": len(mensajes_usuario),
            "estado_final": {
                "nombre": state.get('employee_name'),
                "numero": state.get('employee_id'),
                "tienda": state.get('incident_store_name'),
                "codigo_tienda": state.get('store_id'),
                "seccion": state.get('incident_department')
            }
        })
        
        print(f"\n🏁 RESULTADO: {'✅ ÉXITO' if exito else '❌ FALLO'}")
        self.mostrar_estado_actual(state)
        
        return state
    
    async def test_interactivo_manual(self):
        """Test interactivo donde el usuario escribe manualmente"""
        print("\n🎮 TEST INTERACTIVO MANUAL")
        print("=" * 40)
        print("💬 Escribe mensajes como si fueras un empleado de Eroski")
        print("💡 Comandos especiales:")
        print("   - 'quit' o 'exit': Salir")
        print("   - 'state': Mostrar estado actual")
        print("   - 'reset': Reiniciar conversación")
        print("   - 'help': Mostrar ayuda")
        print()
        
        state = await self.crear_estado_inicial("interactive_manual")
        
        # Inicializar conversación
        result = await self.node.execute(state)
        state.update(result.update)
        
        if state.get('messages'):
            print(f"🤖 BOT: {state['messages'][-1].content}")
        
        turno = 1
        while True:
            print(f"\n--- TURNO {turno} ---")
            user_input = input("👤 TÚ: ").strip()
            
            # Comandos especiales
            if user_input.lower() in ['quit', 'exit']:
                print("👋 ¡Hasta luego!")
                break
            elif user_input.lower() == 'state':
                self.mostrar_estado_actual(state)
                continue
            elif user_input.lower() == 'reset':
                state = await self.crear_estado_inicial("interactive_manual_reset")
                result = await self.node.execute(state)
                state.update(result.update)
                if state.get('messages'):
                    print(f"🤖 BOT: {state['messages'][-1].content}")
                turno = 1
                continue
            elif user_input.lower() == 'help':
                print("💡 Ejemplo de datos que puedes proporcionar:")
                print("   - 'Mi nombre es Juan Pérez'")
                print("   - 'Mi número de empleado es 1234'")  
                print("   - 'Trabajo en Hipermercado Bilbondo'")
                print("   - 'En la sección de pescadería'")
                print("   - 'Quiero cambiar mi nombre'")
                continue
            elif not user_input:
                print("⚠️ Mensaje vacío, intenta de nuevo")
                continue
            
            # Procesar mensaje
            try:
                state['messages'].append(HumanMessage(content=user_input))
                result = await self.node.execute(state)
                state.update(result.update)
                
                # Mostrar respuesta
                if state.get('messages') and isinstance(state['messages'][-1], AIMessage):
                    print(f"🤖 BOT: {state['messages'][-1].content}")
                
                # Verificar completitud
                if state.get('identification_complete'):
                    print("\n🎉 ¡IDENTIFICACIÓN COMPLETADA!")
                    self.mostrar_estado_actual(state)
                    break
                
                turno += 1
                
            except Exception as e:
                print(f"❌ ERROR: {e}")
                print("🔧 Puedes continuar o escribir 'reset' para reiniciar")
    
    async def test_casos_predefinidos(self):
        """Ejecutar todos los casos de test predefinidos"""
        print("\n🧪 EJECUTANDO CASOS DE TEST PREDEFINIDOS")
        print("=" * 50)
        
        for test_name, mensajes in self.test_cases.items():
            await self.ejecutar_conversacion_paso_a_paso(mensajes, test_name)
            print("\n" + "-" * 30)
            
            # Pausa entre tests
            await asyncio.sleep(1)
    
    def mostrar_resumen_tests(self):
        """Mostrar resumen de todos los tests ejecutados"""
        if not self.test_results:
            print("📊 No hay resultados de tests")
            return
        
        print("\n📊 RESUMEN DE TESTS")
        print("=" * 40)
        
        exitosos = sum(1 for result in self.test_results if result.get('exito'))
        total = len(self.test_results)
        
        print(f"✅ Tests exitosos: {exitosos}/{total}")
        print(f"❌ Tests fallidos: {total - exitosos}/{total}")
        print(f"📈 Tasa de éxito: {(exitosos/total)*100:.1f}%")
        
        print("\n📋 DETALLE POR TEST:")
        for result in self.test_results:
            status = "✅" if result.get('exito') else "❌"
            test_name = result.get('test', 'N/A')
            print(f"   {status} {test_name}")
            
            if 'error' in result:
                print(f"      🐛 Error: {result['error']}")
            elif result.get('exito'):
                estado = result.get('estado_final', {})
                print(f"      📊 Datos: {estado.get('nombre', 'N/A')} | "
                      f"{estado.get('numero', 'N/A')} | "
                      f"{estado.get('tienda', 'N/A')}")
    
    async def test_conexion_bd(self):
        """Test específico de conexión a base de datos"""
        print("\n🔌 TEST DE CONEXIÓN A BASE DE DATOS")
        print("=" * 40)
        
        try:
            # Test de carga de tiendas
            tiendas = await self.node._cargar_tiendas_desde_bd()
            
            if tiendas:
                print(f"✅ Tiendas cargadas desde BD: {len(tiendas)}")
                print("🏬 Primeras 3 tiendas:")
                for i, tienda in enumerate(tiendas[:3], 1):
                    print(f"   {i}. {tienda.get('nombre', 'N/A')} (Código: {tienda.get('codigo', 'N/A')})")
            else:
                print("⚠️ No se cargaron tiendas desde BD - usando fallback")
            
            # Test de búsqueda de tienda
            if tiendas:
                tienda_test = self.node._buscar_tienda_mas_parecida("bilbao")
                if tienda_test:
                    print(f"✅ Test búsqueda 'bilbao': {tienda_test['nombre']}")
                else:
                    print("❌ No se encontró tienda para 'bilbao'")
            
        except Exception as e:
            print(f"❌ Error en test de BD: {e}")
    
    async def menu_principal(self):
        """Menú principal del tester"""
        while True:
            print("\n" + "="*50)
            print("🧪 TEST INTERACTIVO - IDENTIFICACIÓN MANUAL")
            print("="*50)
            print("1. 🎮 Test interactivo manual (escribes tú)")
            print("2. 🧪 Ejecutar casos predefinidos")
            print("3. 🔌 Test conexión base de datos")
            print("4. 🔧 Test confirmation tool")
            print("5. 📊 Mostrar resumen de tests")
            print("6. 🔄 Limpiar resultados")
            print("7. 🚪 Salir")
            print()
            
            try:
                opcion = input("Selecciona una opción (1-7): ").strip()
                
                if opcion == "1":
                    await self.test_interactivo_manual()
                elif opcion == "2":
                    await self.test_casos_predefinidos()
                elif opcion == "3":
                    await self.test_conexion_bd()
                elif opcion == "4":
                    await self.test_confirmation_tool()
                elif opcion == "5":
                    self.mostrar_resumen_tests()
                elif opcion == "6":
                    self.test_results.clear()
                    print("✅ Resultados limpiados")
                elif opcion == "7":
                    print("👋 ¡Hasta luego!")
                    break
                else:
                    print("❌ Opción no válida")
                    
            except KeyboardInterrupt:
                print("\n👋 Saliendo...")
                break
            except Exception as e:
                print(f"❌ Error: {e}")


async def main():
    """Función principal"""
    print("🚀 INICIANDO TESTER INTERACTIVO")
    print("=" * 50)
    
    if not IMPORTS_OK:
        print("❌ No se pueden cargar los módulos necesarios")
        print("💡 Asegúrate de:")
        print("   1. Estar en el directorio raíz del proyecto")
        print("   2. Tener todas las dependencias instaladas")
        print("   3. Configurar correctamente el .env")
        sys.exit(1)
    
    tester = TestIdentificacionManualInteractive()
    
    # Setup inicial
    setup_ok = await tester.setup()
    if not setup_ok:
        print("❌ Error en configuración inicial")
        sys.exit(1)
    
    # Ejecutar menú principal
    await tester.menu_principal()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Test interrumpido por el usuario")
    except Exception as e:
        print(f"\n❌ Error fatal: {e}")
        sys.exit(1)