#!/usr/bin/env python3
# =====================================================
# test_classify_node.py - Script de Prueba para Nodo Classify
# =====================================================
"""
Script interactivo para probar el nodo classify de forma aislada.

FUNCIONALIDAD:
- Simula estado post-autenticación con datos del empleado
- Incluye historial inicial de mensajes
- Permite conversación interactiva
- Muestra estado interno del nodo en cada iteración
- Maneja escalaciones y finalizaciones

EJECUCIÓN:
python test_classify_node.py

COMANDOS ESPECIALES:
- 'quit' o 'exit': Salir del script
- 'state': Mostrar estado completo actual
- 'reset': Reiniciar conversación
- 'debug': Activar/desactivar modo debug
"""

import asyncio
import sys
import json
import logging
from pathlib import Path
from datetime import datetime
# Agregar el directorio raíz del proyecto al path
sys.path.insert(0, str(Path(__file__).parent))
from langchain_core.messages import AIMessage, HumanMessage
from models.eroski_state import EroskiState

# =============================================================================
# CONFIGURACIÓN DE LOGGING
# =============================================================================

def setup_logging(debug_mode: bool = False):
    """Configurar logging para el test"""
    level = logging.DEBUG if debug_mode else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    # Reducir ruido de otros loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)

# =============================================================================
# DATOS DE PRUEBA INICIALES
# =============================================================================

def create_initial_state() -> EroskiState:
    """
    Crear estado inicial simulando que viene del nodo de autenticación.
    
    Incluye:
    - Datos del empleado autenticado
    - Historial de mensajes de la autenticación
    - Estado completo para clasificación
    """
    
    # Historial de mensajes de la fase de autenticación
    messages = [
        HumanMessage(content="hola, tengo un problema con la balanza"),
        AIMessage(content="Hola! Veo que tienes un problema con una balanza. Para ayudarte necesito verificar algunos datos. ¿Podrías decirme tu nombre completo?"),
        HumanMessage(content="Javier Guerra"),
        AIMessage(content="Perfecto, Javier. ¿Cuál es tu email corporativo?"),
        HumanMessage(content="javier.guerra@devol.es, tienda de Eroski en el centro de Bilbao"),
        AIMessage(content="Entiendo que trabajas en Eroski del centro de Bilbao. ¿En qué sección específica trabajas?"),
        HumanMessage(content="esta en la sección de carnicería"),
        AIMessage(content="Perfecto, Javier. Ya tengo todos tus datos:\n- Nombre: Javier Guerra\n- Email: javier.guerra@devol.es\n- Tienda: Eroski Bilbao Centro\n- Sección: Carnicería\n\nAhora vamos a analizar el problema con la balanza. ¿Podrías contarme más detalles sobre qué está ocurriendo?")
    ]
    
    # Estado completo
    state = EroskiState(
        # Identificación de sesión
        session_id="test_session_123",
        employee_name="Javier Guerra",
        employee_email="javier.guerra@devol.es",
        store_name="Eroski Bilbao Centro",
        department="Carnicería",
        authenticated=True,
        current_node="classify",
        user_id="javier.guerra@devol.es",
        
        # Estado de autenticación (COMPLETADO)
        authenticated=True,
        authentication_completed=True,
        
        # Historial de mensajes
        messages=messages,
        
        # Estado actual del workflow
        current_step="classify",
        
        # Datos de clasificación (INICIALES - para que el nodo empiece desde cero)
        classify_data={},
        classify_attempt_number=0,
        classification_completed=False,
        
        # Metadata
        conversation_started_at=datetime.now().isoformat(),
        last_activity=datetime.now().isoformat()
    )
    
    return state
# =============================================================================
# CLASE PRINCIPAL DE TESTING
# =============================================================================
class ClassifyNodeTester:
    """
    Tester interactivo para el nodo classify.
    """
    def __init__(self, debug_mode: bool = False):
        self.debug_mode = debug_mode
        self.state = create_initial_state()
        self.node = None
        setup_logging(debug_mode)
        self.logger = logging.getLogger("ClassifyTester")
        
    async def initialize(self):
        """Inicializar el nodo de clasificación"""
        try:
            # Importar dinámicamente el nodo
            from nodes.old.classify_node import LLMDrivenClassifyNode
            self.node = LLMDrivenClassifyNode()
            self.logger.info("✅ Nodo classify inicializado correctamente")
            # Verificar que se carguen los tipos de incidencia
            incident_count = len(self.node.incident_types)
            self.logger.info(f"📋 Tipos de incidencia cargados: {incident_count}")
            if incident_count == 0:
                self.logger.warning("⚠️ No se cargaron tipos de incidencia. Verificar archivo JSON.")
        except ImportError as e:
            self.logger.error(f"❌ Error importando nodo: {e}")
            self.logger.error("Verifica que el archivo nodes/classify_llm_driven.py exista")
            return False
        except Exception as e:
            self.logger.error(f"❌ Error inicializando nodo: {e}")
            return False
        
        return True
    
    def print_welcome(self):
        """Mostrar mensaje de bienvenida"""
        print("\n" + "="*80)
        print("🧪 TESTER INTERACTIVO PARA NODO CLASSIFY")
        print("="*80)
        print(f"👤 Empleado: {self.state['auth_data_collected']['name']}")
        print(f"📧 Email: {self.state['auth_data_collected']['email']}")
        print(f"🏪 Tienda: {self.state['auth_data_collected']['store_name']}")
        print(f"🔧 Sección: {self.state['auth_data_collected']['section']}")
        print("-"*80)
        print("💬 HISTORIAL INICIAL (que el nodo analizará):")
        self._print_message_history()
        print("-"*80)
        print("🧠 INFORMACIÓN PARA EL ANÁLISIS:")
        print("  • El usuario YA mencionó 'problema con la balanza' en el primer mensaje")
        print("  • El nodo debe DETECTAR esto automáticamente")
        print("  • NO debe pedir que repita información ya proporcionada")
        print("  • Debe ser más específico en sus preguntas")
        print("-"*80)
        print("🎮 COMANDOS ESPECIALES:")
        print("  • 'quit' o 'exit' - Salir")
        print("  • 'state' - Mostrar estado completo")
        print("  • 'reset' - Reiniciar conversación")
        print("  • 'debug' - Alternar modo debug")
        print("  • 'codigo' - Mostrar código de incidencia")
        print("="*80)
        print("\n🚀 El nodo va a analizar automáticamente el historial...")
        print("💡 Observa cómo detecta 'problema con la balanza' del primer mensaje")
        print("🎯 Debería hacer preguntas específicas sobre balanzas, no genéricas")
        # ✅ NUEVO: Mostrar código de incidencia si existe
        incident_code = self.state.get("incident_code")
        if incident_code:
            print(f"\n📋 Código de incidencia activo: {incident_code}")
        print()
    
    def _print_message_history(self, limit: int = None):
        """Imprimir historial de mensajes"""
        messages = self.state.get("messages", [])
        if limit:
            messages = messages[-limit:]
        for i, msg in enumerate(messages):
            if isinstance(msg, HumanMessage):
                print(f"  👤 Usuario: {msg.content}")
            elif isinstance(msg, AIMessage):
                print(f"  🤖 Bot: {msg.content}")
    
    def _print_classify_state(self):
        """Mostrar estado actual de clasificación"""
        classify_data = self.state.get("classify_data", {})
        print("\n📊 ESTADO DE CLASIFICACIÓN:")
        print("-"*50)
        print(f"  Incidencia identificada: {classify_data.get('incident_identified', False)}")
        print(f"  Problema identificado: {classify_data.get('problem_identified', False)}")
        print(f"  Solución lista: {classify_data.get('solution_ready', False)}")
        print(f"  Confianza: {classify_data.get('confidence_level', 0.0):.2f}")
        print(f"  Historial confianza: {classify_data.get('confidence_history', [])}")
        print(f"  Evaluación progreso: {classify_data.get('progress_assessment', 'N/A')}")
        print(f"  Nueva información: {classify_data.get('new_information_provided', False)}")
        print(f"  En bucle: {classify_data.get('stuck_in_loop', False)}")
        print(f"  Tipo: {classify_data.get('incident_type', 'N/A')}")
        print(f"  Problema específico: {classify_data.get('specific_problem', 'N/A')}")
        print(f"  Intentos: {self.state.get('classify_attempt_number', 0)}")
        print(f"  Keywords detectadas: {classify_data.get('keywords_detected', [])}")
        print(f"  Nivel urgencia: {classify_data.get('urgency_level', 'N/A')}")
        print(f"  Info histórica: {classify_data.get('historical_info_found', 'N/A')}")
        print(f"  Fuente solución: {classify_data.get('solution_source', 'N/A')}")
        print(f"  Clasificación automática: {classify_data.get('auto_classify_attempted', False)}")
        print(f"  Esperando confirmación: {classify_data.get('awaiting_confirmation', False)}")
        print(f"  Solución exitosa: {classify_data.get('solution_successful', 'N/A')}")
        print("-"*50)
    
    def _print_full_state(self):
        """Mostrar estado completo (para debugging)"""
        print("\n🔍 ESTADO COMPLETO:")
        print("-"*70)
        
        # Estado de alto nivel
        print(f"Session ID: {self.state.get('session_id')}")
        print(f"Autenticado: {self.state.get('authenticated')}")
        print(f"Paso actual: {self.state.get('current_step')}")
        print(f"Clasificación completa: {self.state.get('classification_completed')}")
        
        # Datos de autenticación
        auth_data = self.state.get("auth_data_collected", {})
        print(f"\nDatos autenticación: {json.dumps(auth_data, indent=2, ensure_ascii=False)}")
        
        # Estado de clasificación
        self._print_classify_state()
        
        # Últimos 3 mensajes
        print("\n💬 ÚLTIMOS MENSAJES:")
        self._print_message_history(limit=3)
        
        print("-"*70)
    
    async def process_user_input(self, user_input: str) -> bool:
        """
        Procesar entrada del usuario y ejecutar el nodo.
        
        Returns:
            True si debe continuar, False si debe salir
        """
        
        # Comandos especiales
        if user_input.lower() in ['quit', 'exit']:
            return False
        
        if user_input.lower() == 'state':
            self._print_full_state()
            return True
        
        if user_input.lower() == 'reset':
            self.state = create_initial_state()
            print("\n🔄 Estado reiniciado")
            return True
        
        if user_input.lower() == 'debug':
            self.debug_mode = not self.debug_mode
            setup_logging(self.debug_mode)
            print(f"\n🐛 Modo debug: {'ON' if self.debug_mode else 'OFF'}")
            return True
        
        if user_input.lower() in ['codigo', 'código']:
            incident_code = self.state.get("incident_code", "No asignado")
            print(f"\n📋 Código de incidencia: {incident_code}")
            return True
        
        # Agregar mensaje del usuario al estado
        self.state["messages"].append(HumanMessage(content=user_input))
        self.state["last_activity"] = datetime.now().isoformat()
        
        try:
            # Ejecutar el nodo
            print("\n🤖 Procesando...")
            
            command = await self.node.execute(self.state)
            
            # Aplicar actualizaciones
            self.state.update(command.update)
            
            # Mostrar respuesta del bot
            messages = self.state.get("messages", [])
            if messages and isinstance(messages[-1], AIMessage):
                bot_response = messages[-1].content
                print(f"\n🤖 Bot: {bot_response}")
                
                # ✅ NUEVO: Mostrar código de incidencia en lateral
                incident_code = self.state.get("incident_code")
                if incident_code:
                    print(f"\n{'':>60}📋 Código: {incident_code}")
            
            # Mostrar estado de clasificación si está en debug
            if self.debug_mode:
                self._print_classify_state()
            
            # Verificar si se completó o escaló
            current_step = self.state.get("current_step")
            if current_step == "escalate":
                print("\n🔝 ESCALACIÓN ACTIVADA - Conversación derivada a supervisor")
                return False
            elif self.state.get("classification_completed"):
                print("\n✅ CLASIFICACIÓN COMPLETADA")
                self._print_classify_state()
                return False
            elif self.state.get("conversation_ended"):
                print("\n🔚 CONVERSACIÓN FINALIZADA - Problema resuelto")
                return False
            elif self.state.get("classify_data", {}).get("awaiting_confirmation"):
                print("\n⏳ ESPERANDO CONFIRMACIÓN DEL USUARIO")
                print("💡 Responde 'sí' si funcionó o 'no' si persiste el problema")
                return True
            
        except Exception as e:
            self.logger.error(f"❌ Error ejecutando nodo: {e}")
            if self.debug_mode:
                import traceback
                traceback.print_exc()
            print(f"\n💥 Error: {e}")
        
        return True
    
    async def run_interactive_session(self):
        """Ejecutar sesión interactiva"""
        
        if not await self.initialize():
            print("❌ No se pudo inicializar el nodo. Abortando.")
            return
        
        self.print_welcome()
        
        try:
            while True:
                # Solicitar input del usuario
                user_input = input("\n👤 Tú: ").strip()
                
                if not user_input:
                    continue
                
                # Procesar input
                should_continue = await self.process_user_input(user_input)
                
                if not should_continue:
                    break
                    
        except KeyboardInterrupt:
            print("\n\n⏹️ Sesión interrumpida por el usuario")
        except Exception as e:
            print(f"\n💥 Error inesperado: {e}")
        
        print("\n👋 ¡Hasta luego!")
# =============================================================================
# FUNCIÓN PRINCIPAL
# =============================================================================
async def main():
    """Función principal del script"""
    
    # Parsear argumentos simples
    debug_mode = '--debug' in sys.argv or '-d' in sys.argv
    
    if '--help' in sys.argv or '-h' in sys.argv:
        print(__doc__)
        return
    
    # Crear y ejecutar tester
    tester = ClassifyNodeTester(debug_mode=debug_mode)
    await tester.run_interactive_session()
# =============================================================================
# SCRIPT PARA TESTING RÁPIDO (NO INTERACTIVO)
# =============================================================================
async def quick_test():
    """Test rápido no interactivo para verificar funcionamiento básico"""
    
    print("🚀 EJECUTANDO TEST RÁPIDO...")
    
    # Crear tester
    tester = ClassifyNodeTester(debug_mode=True)
    
    # Inicializar
    if not await tester.initialize():
        print("❌ Fallo en inicialización")
        return
    
    # Mensajes de prueba
    test_messages = [
        "La balanza no imprime etiquetas",
        "Sí, tiene papel pero aún así no imprime",
        "¿Debería reiniciarla?"
    ]
    
    print(f"\n📝 Probando con {len(test_messages)} mensajes...")
    
    for i, msg in enumerate(test_messages, 1):
        print(f"\n--- TEST {i}/{len(test_messages)} ---")
        print(f"👤 Input: {msg}")
        
        should_continue = await tester.process_user_input(msg)
        
        if not should_continue:
            print("🛑 Test terminado prematuramente")
            break
    
    print("\n✅ Test rápido completado")
# =============================================================================
# PUNTO DE ENTRADA
# =============================================================================
if __name__ == "__main__":
    
    if '--quick' in sys.argv:
        # Test rápido no interactivo
        asyncio.run(quick_test())
    else:
        # Sesión interactiva completa
        asyncio.run(main())