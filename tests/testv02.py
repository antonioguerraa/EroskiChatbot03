#!/usr/bin/env python3
# =====================================================
# test_identificador_interactivo.py - Script de prueba interactivo
# =====================================================
"""
Script para probar interactivamente el nodo identificador_base_de_datos.py
Simula una conversación real con el agente de identificación.
"""

import asyncio
import sys
import os
from datetime import datetime
from typing import Dict, Any

# Agregar el directorio raíz al path para importaciones
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Importaciones del proyecto
from models.eroski_state import EroskiState, create_initial_eroski_state
from nodes.identificador_base_de_datos import identificador_base_de_datos_node
from nodes.identificador_orquestador import identificador_orquestador_node
from nodes.identificador_manual_node import identificacion_manual
from langgraph.graph import StateGraph, END
from langchain_core.messages import AIMessage
# =====================================================
# CONFIGURACIÓN Y HELPERS
# =====================================================

def print_separator():
    """Imprimir separador visual"""
    print("=" * 60)

def print_state_summary(state: EroskiState):
    """Mostrar resumen del estado actual"""
    print("\n📊 ESTADO ACTUAL:")
    print(f"   🔐 Autenticado: {state.get('authenticated', False)}")
    print(f"   👤 Empleado: {state.get('employee_name', 'No identificado')}")
    print(f"   📧 Email: {state.get('employee_email', 'No proporcionado')}")
    print(f"   🆔 ID Empleado: {state.get('employee_id', 'No proporcionado')}")
    print(f"   🏢 Tienda: {state.get('store_name', 'No identificada')}")
    print(f"   🔄 Intentos: {state.get('attempts', 0)}")
    print(f"   📍 Nodo actual: {state.get('current_node', 'unknown')}")
    
    # Mostrar flags de autenticación
    print("\n🚩 FLAGS DE AUTENTICACIÓN:")
    print(f"   📧 Email intentado: {state.get('email_authen_tried', False)}")
    print(f"   🆔 ID intentado: {state.get('employee_id_authent_tried', False)}")

def print_help():
    """Mostrar comandos disponibles"""
    print("\n💡 COMANDOS ESPECIALES:")
    print("   help    - Mostrar esta ayuda")
    print("   state   - Mostrar estado completo")
    print("   reset   - Reiniciar conversación")
    print("   exit    - Salir del programa")
    print("   clear   - Limpiar pantalla")

def clear_screen():
    """Limpiar pantalla"""
    os.system('cls' if os.name == 'nt' else 'clear')




# =====================================================
# CLASE PRINCIPAL DE SIMULACIÓN
# =====================================================

class IdentificadorTester:
    """Tester interactivo para el nodo identificador"""
    
    def __init__(self):
        self.state = None
        
        self.graph = None
        
        
    def create_new_session(self) -> EroskiState:
        """Crear nueva sesión y compilar el grafo solo una vez"""
        self.session_counter += 1
        session_id = f"test_session_{self.session_counter}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Crea el grafo una sola vez
        if not self.graph:
            self.graph = self.build_graph()

        return create_initial_eroski_state(
            session_id=session_id,
            timezone="Europe/Madrid"
        )

    
    def build_graph(self) -> StateGraph:
        """Construir el grafo de nodos"""
        builder = StateGraph(EroskiState)
        print(f"🌄"*100)
        # Envolver nodos async con RunnableLambda
        builder.add_node("orquestador", identificador_orquestador_node)
        builder.add_node("identificador_base_de_datos", identificador_base_de_datos_node)
        builder.add_node("identificacion_manual", identificacion_manual)

        # Ruta condicional
        def route(state: EroskiState):
            #for key, vaule in state.items():
            #    print(f"🌄JGL estado {key}: {vaule}")
            if state.get("authenticated"):
                return END
            if state.get("awaiting_user_input") and state.get("current_node") == "identificacion_manual":
                return END
            if state.get("email_authen_tried", False) and state.get("employee_id_authent_tried", False):
                return "identificacion_manual"
            return "identificador_base_de_datos"

        builder.set_entry_point("orquestador")
        builder.add_conditional_edges("orquestador", route, {
            "identificador_base_de_datos": "identificador_base_de_datos",
            "identificacion_manual": "identificacion_manual",
            END: END
        })
        builder.add_edge("identificacion_manual", END)


        return builder.compile()

    async def handle_user_input(self, user_input: str) -> bool:
        """
        Procesar entrada del usuario y ejecutar el nodo.
        
        Returns:
            bool: True si debe continuar, False si debe salir
        """
        # Comandos especiales
        if user_input.lower() == "exit":
            return False
        elif user_input.lower() == "help":
            print_help()
            return True
        elif user_input.lower() == "clear":
            clear_screen()
            return True
        elif user_input.lower() == "reset":
            self.state = self.create_new_session()
            print("🔄 Nueva sesión iniciada")
            #print_state_summary(self.state)
            return True
        elif user_input.lower() == "state":
            print("\n📋 ESTADO COMPLETO:")
            for key, value in self.state.items():
                if key != "messages":  # No mostrar mensajes para evitar spam
                    print(f"   {key}: {value}")
            return True
        
        # Agregar mensaje del usuario al estado
        from langchain_core.messages import HumanMessage
        if "messages" not in self.state:
            self.state["messages"] = []
        
        self.state["messages"].append(HumanMessage(content=user_input))
        
        # Ejecutar el nodo

        try:
            print("🤖 Procesando...")
            result = await self.graph.ainvoke(self.state)
            self.state.update(result)

            # Mostrar último mensaje del agente
            messages = result.get("messages", [])
            last_ai = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)

            if last_ai:
                print(f"\n🤖 AGENTE: {last_ai.content}")
            else:
                print("\n🤖 AGENTE: (sin respuesta del agente)")

            # Mostrar resumen del estado
            #print_state_summary(self.state)

        except Exception as e:
            print(f"\n❌ ERROR: {str(e)}")
            print("💡 Verifica que la configuración de la base de datos sea correcta")

        return True

    async def run(self):
        """Ejecutar el tester interactivo"""
        print_separator()
        print("🎯 TESTER INTERACTIVO - NODO IDENTIFICADOR BD")
        print_separator()
        print("Este script te permite probar el nodo identificador_base_de_datos.py")
        print("Simula una conversación real con el agente de identificación.")
        
        # Crear sesión inicial
        self.state = self.create_new_session()
        print(f"\n✅ Sesión iniciada: {self.state['session_id']}")
        
        print_help()
        #print_state_summary(self.state)
        
        # Bucle principal de interacción
        while True:
            print_separator()
            try:
                user_input = input("\n👤 TÚ: ").strip()
                
                if not user_input:
                    print("💭 Mensaje vacío, intenta de nuevo...")
                    continue
                
                should_continue = await self.handle_user_input(user_input)
                if not should_continue:
                    break
                    
            except KeyboardInterrupt:
                print("\n\n👋 Interrumpido por el usuario. ¡Hasta luego!")
                break
            except EOFError:
                print("\n\n👋 Fin de entrada. ¡Hasta luego!")
                break
            except Exception as e:
                print(f"\n❌ Error inesperado: {str(e)}")
                continue
        
        print("\n👋 ¡Gracias por usar el tester! Session: " + self.state.get('session_id', 'unknown'))

# =====================================================
# FUNCIÓN PRINCIPAL Y ENTRADA
# =====================================================

async def main():
    """Función principal del script"""
    #logging.disable(logging.CRITICAL)
    # Verificar que el archivo del nodo existe
    node_file = "nodes/identificador_base_de_datos.py"
    if not os.path.exists(node_file):
        print(f"❌ Error: No se encuentra el archivo {node_file}")
        print("💡 Asegúrate de ejecutar el script desde el directorio raíz del proyecto")
        return
    
    # Verificar que el modelo de estado existe
    state_file = "models/eroski_state.py"
    if not os.path.exists(state_file):
        print(f"❌ Error: No se encuentra el archivo {state_file}")
        print("💡 Asegúrate de que el modelo de estado esté disponible")
        return
    
    # Ejecutar el tester
    tester = IdentificadorTester()
    await tester.run()

if __name__ == "__main__":
    # Configurar logging básico
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Ejecutar
    asyncio.run(main())