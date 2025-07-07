#!/usr/bin/env python3
# =====================================================
# tests/test_identificador_base_de_datos.py - Tests para Nodo Identificador BD
# =====================================================
"""
Suite completa de tests para el nodo IdentificadorBaseDatosNode.

COBERTURA DE TESTS:
- Identificación por email exitosa
- Identificación por número de empleado exitosa
- Manejo de usuarios no encontrados
- Gestión de flags de estado
- Manejo de errores de conexión
- Integración con agente React
- Casos de mensajes ambiguos
- Escalación por fallo de identificación

TIPOS DE TESTS:
- Unit tests: Funcionalidad individual
- Integration tests: Interacción con BD
- Mock tests: Simulación sin BD real
- Error handling tests: Casos de fallo
"""

import pytest
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from datetime import datetime
from typing import Dict, Any, List

# Agregar el directorio raíz del proyecto al path
sys.path.insert(0, str(Path(__file__).parent.parent))

from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.tools import tool

# Importar las tools desde nuestro nodo adaptado
from nodes.identificador_base_de_datos import (
    IdentificadorBaseDatosNode, 
    identificador_base_de_datos_node,
    search_by_email_adapted,
    search_by_employee_id_adapted
)
from models.eroski_state import EroskiState


# =============================================================================
# FIXTURES Y DATOS DE PRUEBA
# =============================================================================

@pytest.fixture
def sample_employee_data():
    """Datos de empleado de prueba válidos"""
    return {
        "numero_empleado": "12345",
        "nombre": "Juan Pérez",
        "apellido": "García",
        "email": "juan.perez@eroski.es",
        "nombre_tienda": "Eroski Bilbao Centro",
        "departamento": "Informática"
    }

@pytest.fixture
def sample_employee_result():
    """Resultado esperado de búsqueda exitosa"""
    return {
        "found": True,
        "numero_empleado": "12345",
        "nombre": "Juan Pérez García",
        "email": "juan.perez@eroski.es",
        "nombre_tienda": "Eroski Bilbao Centro",
        "departamento": "Informática"
    }

@pytest.fixture
def initial_state():
    """Estado inicial básico para tests"""
    return {
        "messages": [],
        "session_id": "test_session_001",
        "email_authen_tried": False,
        "employee_id_authent_tried": False,
        "authenticated": False
    }

@pytest.fixture
def state_with_user_message():
    """Estado con mensaje del usuario"""
    return {
        "messages": [
            HumanMessage(content="Mi email es juan.perez@eroski.es")
        ],
        "session_id": "test_session_002",
        "email_authen_tried": False,
        "employee_id_authent_tried": False,
        "authenticated": False
    }

@pytest.fixture
def authenticated_state():
    """Estado con usuario ya autenticado"""
    return {
        "messages": [
            HumanMessage(content="Hola"),
            AIMessage(content="¡Hola! Te he identificado correctamente...")
        ],
        "session_id": "test_session_003",
        "authenticated": True,
        "employee_name": "Juan Pérez García",
        "employee_email": "juan.perez@eroski.es"
    }

@pytest.fixture
def failed_attempts_state():
    """Estado donde ambos métodos ya fallaron"""
    return {
        "messages": [
            HumanMessage(content="Mi email es inexistente@test.com"),
            AIMessage(content="No pude encontrarte..."),
            HumanMessage(content="Mi número es 99999")
        ],
        "session_id": "test_session_004",
        "email_authen_tried": True,
        "employee_id_authent_tried": True,
        "authenticated": False
    }

@pytest.fixture
def node():
    """Instancia del nodo para tests"""
    return IdentificadorBaseDatosNode()


# =============================================================================
# TESTS UNITARIOS - FUNCIONES HELPER
# =============================================================================

class TestHelperFunctions:
    """Tests para funciones auxiliares del nodo"""
    
    def test_extract_email_from_message(self, node):
        """Test: Extracción de email del mensaje"""
        message = "Mi email es juan.perez@eroski.es y necesito ayuda"
        extracted = node._extract_identification_data(message)
        
        assert extracted["email"] == "juan.perez@eroski.es"
        assert extracted["employee_id"] is None
    
    def test_extract_employee_id_from_message(self, node):
        """Test: Extracción de número de empleado del mensaje"""
        message = "Soy el empleado 12345 y tengo un problema"
        extracted = node._extract_identification_data(message)
        
        assert extracted["employee_id"] == "12345"
        assert extracted["email"] is None
    
    def test_extract_both_identifiers(self, node):
        """Test: Extracción de ambos identificadores"""
        message = "Mi email es juan@eroski.es y mi número de empleado es 54321"
        extracted = node._extract_identification_data(message)
        
        assert extracted["email"] == "juan@eroski.es"
        assert extracted["employee_id"] == "54321"
    
    def test_extract_no_identifiers(self, node):
        """Test: Mensaje sin identificadores"""
        message = "Hola, necesito ayuda con una incidencia"
        extracted = node._extract_identification_data(message)
        
        assert extracted["email"] is None
        assert extracted["employee_id"] is None
    
    def test_get_last_user_message(self, node):
        """Test: Obtener último mensaje del usuario"""
        state = {
            "messages": [
                HumanMessage(content="Primer mensaje"),
                AIMessage(content="Respuesta del bot"),
                HumanMessage(content="Último mensaje del usuario")
            ]
        }
        
        last_message = node._get_last_user_message(state)
        assert last_message == "Último mensaje del usuario"
    
    def test_is_first_interaction(self, node):
        """Test: Detectar primera interacción"""
        # Sin mensajes del usuario
        state1 = {"messages": []}
        assert node._is_first_interaction(state1) is True
        
        # Un mensaje del usuario
        state2 = {"messages": [HumanMessage(content="Hola")]}
        assert node._is_first_interaction(state2) is True
        
        # Dos mensajes del usuario
        state3 = {"messages": [
            HumanMessage(content="Hola"),
            AIMessage(content="Respuesta"),
            HumanMessage(content="Segundo mensaje")
        ]}
        assert node._is_first_interaction(state3) is False


# =============================================================================
# TESTS DE TOOLS - BÚSQUEDA EN BD
# =============================================================================

class TestDatabaseTools:
    """Tests para las tools de búsqueda en base de datos"""
    
    @pytest.mark.asyncio
    @patch('nodes.identificador_base_de_datos.asyncpg.connect')
    async def test_search_by_email_success(self, mock_connect, sample_employee_data):
        """Test: Búsqueda por email exitosa"""
        # Mock de la conexión y resultado
        mock_conn = AsyncMock()
        mock_connect.return_value = mock_conn
        mock_conn.fetchrow.return_value = sample_employee_data
        
        # Ejecutar búsqueda
        result = await search_by_email_adapted.ainvoke({"email": "juan.perez@eroski.es"})
        
        # Verificar resultado
        assert result["found"] is True
        assert result["nombre"] == "Juan Pérez García"
        assert result["email"] == "juan.perez@eroski.es"
        assert result["numero_empleado"] == "12345"
        
        # Verificar que se llamó a la BD correctamente
        mock_conn.fetchrow.assert_called_once()
        mock_conn.close.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('nodes.identificador_base_de_datos.asyncpg.connect')
    async def test_search_by_email_not_found(self, mock_connect):
        """Test: Email no encontrado en BD"""
        # Mock de conexión sin resultado
        mock_conn = AsyncMock()
        mock_connect.return_value = mock_conn
        mock_conn.fetchrow.return_value = None
        
        # Ejecutar búsqueda
        result = await search_by_email("inexistente@test.com")
        
        # Verificar resultado
        assert result["found"] is False
        assert "no encontrado" in result["error"].lower()
    
    @pytest.mark.asyncio
    @patch('nodes.identificador_base_de_datos.asyncpg.connect')
    async def test_search_by_email_connection_error(self, mock_connect):
        """Test: Error de conexión en búsqueda por email"""
        # Mock de error de conexión
        mock_connect.side_effect = Exception("Connection failed")
        
        # Ejecutar búsqueda
        result = await search_by_email("test@eroski.es")
        
        # Verificar manejo de error
        assert result["found"] is False
        assert "error de conexión" in result["error"].lower()
    
    @pytest.mark.asyncio
    @patch('nodes.identificador_base_de_datos.asyncpg.connect')
    async def test_search_by_employee_id_success(self, mock_connect, sample_employee_data):
        """Test: Búsqueda por ID de empleado exitosa"""
        # Mock de la conexión y resultado
        mock_conn = AsyncMock()
        mock_connect.return_value = mock_conn
        mock_conn.fetchrow.return_value = sample_employee_data
        
        # Ejecutar búsqueda
        result = await search_by_employee_id("12345")
        
        # Verificar resultado
        assert result["found"] is True
        assert result["numero_empleado"] == "12345"
        
        # Verificar llamada a BD
        mock_conn.fetchrow.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_search_by_email_invalid_format(self):
        """Test: Email con formato inválido"""
        result = await search_by_email_adapted.ainvoke({"email": "email_invalido"})
        
        assert result["found"] is False
        assert "formato" in result["error"].lower()
    
    @pytest.mark.asyncio
    async def test_search_by_employee_id_invalid_format(self):
        """Test: ID de empleado con formato inválido"""
        result = await search_by_employee_id_adapted.ainvoke({"employee_id": "id_muy_largo_invalido"})
        
        assert result["found"] is False
        assert "caracteres" in result["error"].lower()


# =============================================================================
# TESTS DEL NODO PRINCIPAL
# =============================================================================

class TestIdentificadorBaseDatosNode:
    """Tests para el nodo principal de identificación"""
    
    @pytest.mark.asyncio
    async def test_already_authenticated_user(self, node, authenticated_state):
        """Test: Usuario ya autenticado pasa sin procesar"""
        result = await node.execute(authenticated_state)
        
        # Verificar que no solicita identificación
        assert result.update["current_node"] == "identificador_base_datos"
        assert "messages" not in result.update  # No agrega mensajes nuevos
    
    @pytest.mark.asyncio
    async def test_first_interaction_sends_greeting(self, node, initial_state):
        """Test: Primera interacción envía saludo"""
        result = await node.execute(initial_state)
        
        # Verificar saludo inicial
        assert result.update["awaiting_user_input"] is True
        assert result.update["identification_stage"] == "requesting_credentials"
        
        last_message = result.update["messages"][-1]
        assert isinstance(last_message, AIMessage)
        assert "email corporativo" in last_message.content.lower()
        assert "número de empleado" in last_message.content.lower()
    
    @pytest.mark.asyncio
    @patch('nodes.identificador_base_de_datos.search_by_email')
    async def test_successful_email_identification(self, mock_search, node, state_with_user_message, sample_employee_result):
        """Test: Identificación exitosa por email"""
        # Mock de búsqueda exitosa
        mock_search.return_value = sample_employee_result
        
        # Ejecutar nodo
        result = await node.execute(state_with_user_message)
        
        # Verificar identificación exitosa
        assert result.update["authenticated"] is True
        assert result.update["employee_name"] == "Juan Pérez García"
        assert result.update["employee_email"] == "juan.perez@eroski.es"
        assert result.update["email_authen_tried"] is True
        assert result.update["identification_method"] == "database"
        
        # Verificar mensaje de éxito
        last_message = result.update["messages"][-1]
        assert "identificado correctamente" in last_message.content.lower()
    
    @pytest.mark.asyncio
    @patch('nodes.identificador_base_de_datos.search_by_employee_id')
    async def test_successful_employee_id_identification(self, mock_search, node, sample_employee_result):
        """Test: Identificación exitosa por número de empleado"""
        # Estado con número de empleado
        state = {
            "messages": [HumanMessage(content="Soy el empleado 12345")],
            "session_id": "test",
            "email_authen_tried": False,
            "employee_id_authent_tried": False,
            "authenticated": False
        }
        
        # Mock de búsqueda exitosa
        mock_search.return_value = sample_employee_result
        
        # Ejecutar nodo
        result = await node.execute(state)
        
        # Verificar identificación exitosa
        assert result.update["authenticated"] is True
        assert result.update["employee_id_authent_tried"] is True
        assert result.update["employee_id"] == "12345"
    
    @pytest.mark.asyncio
    @patch('nodes.identificador_base_de_datos.search_by_email')
    async def test_failed_email_search_retry_with_id(self, mock_search, node):
        """Test: Email fallido, ofrecer búsqueda por ID"""
        # Estado con email
        state = {
            "messages": [HumanMessage(content="Mi email es inexistente@test.com")],
            "session_id": "test",
            "email_authen_tried": False,
            "employee_id_authent_tried": False,
            "authenticated": False
        }
        
        # Mock de búsqueda fallida
        mock_search.return_value = {"found": False, "error": "Email no encontrado"}
        
        # Ejecutar nodo
        result = await node.execute(state)
        
        # Verificar que ofrece el otro método
        assert result.update["email_authen_tried"] is True
        assert result.update["authenticated"] is False
        
        last_message = result.update["messages"][-1]
        assert "número de empleado" in last_message.content.lower()
    
    @pytest.mark.asyncio
    async def test_both_methods_failed_escalation(self, node, failed_attempts_state):
        """Test: Ambos métodos fallaron, escalación"""
        result = await node.execute(failed_attempts_state)
        
        # Verificar escalación
        assert result.update["identification_failed"] is True
        assert result.update["escalation_needed"] is True
        assert result.update["authenticated"] is False
        
        last_message = result.update["messages"][-1]
        assert "no pude identificarte" in last_message.content.lower()
    @pytest.mark.asyncio
    async def test_confirmation_tool_integration(self, node):
        """Test: Integración con tool de confirmación"""
        # Verificar que la tool está disponible (si existe)
        if hasattr(node, 'check_confirmation'):
            # Test de confirmación positiva
            confirmation_result = {"is_confirmation": True, "intent": "affirmative"}
            
            state = {
                "messages": [HumanMessage(content="sí")],
                "session_id": "test_confirmation",
                "pending_identification_data": {"email": "test@eroski.es"},
                "email_authen_tried": False,
                "employee_id_authent_tried": False,
                "authenticated": False
            }
            
            with patch.object(node, 'check_confirmation', return_value=confirmation_result):
                with patch('nodes.identificador_base_de_datos.search_by_email_adapted') as mock_search:
                    mock_search.return_value = {"found": False, "error": "Test"}
                    
                    result = await node._process_user_message(state, "sí")
                    
                    # Verificar que se llamó a la búsqueda por email
                    mock_search.assert_called_once_with("test@eroski.es")
        else:
            # Si no está disponible, simplemente verificar que no cause errores
            state = {"messages": [HumanMessage(content="sí")], "session_id": "test"}
            result = await node._process_user_message(state, "sí")
            assert isinstance(result, Command)
    
    @pytest.mark.asyncio
    async def test_message_without_identifiers(self, node):
        """Test: Mensaje sin email ni ID de empleado"""
        state = {
            "messages": [HumanMessage(content="Hola, necesito ayuda")],
            "session_id": "test",
            "email_authen_tried": False,
            "employee_id_authent_tried": False,
            "authenticated": False
        }
        
        result = await node.execute(state)
        
        # Verificar solicitud de información
        assert result.update["awaiting_user_input"] is True
        
        last_message = result.update["messages"][-1]
        assert "email corporativo" in last_message.content.lower()
        assert "número de empleado" in last_message.content.lower()
    
    @pytest.mark.asyncio
    @patch('nodes.identificador_base_de_datos.search_by_email')
    async def test_connection_error_handling(self, mock_search, node, state_with_user_message):
        """Test: Manejo de errores de conexión"""
        # Mock de error de conexión
        mock_search.return_value = {"found": False, "error": "Error de conexión: Connection failed"}
        
        # Ejecutar nodo
        result = await node.execute(state_with_user_message)
        
        # Verificar manejo de error
        assert result.update["error_occurred"] is True
        assert result.update["escalation_needed"] is True
        
        last_message = result.update["messages"][-1]
        assert "error técnico" in last_message.content.lower()


# =============================================================================
# TESTS DE INTEGRACIÓN
# =============================================================================

class TestIntegrationScenarios:
    """Tests de escenarios de integración completos"""
    
    @pytest.mark.asyncio
    @patch('nodes.identificador_base_de_datos.search_by_email')
    async def test_complete_flow_success(self, mock_search, sample_employee_result):
        """Test: Flujo completo exitoso desde saludo hasta identificación"""
        node = IdentificadorBaseDatosNode()
        
        # 1. Primera ejecución - Saludo
        initial_state = {
            "messages": [],
            "session_id": "integration_test",
            "email_authen_tried": False,
            "employee_id_authent_tried": False,
            "authenticated": False
        }
        
        result1 = await node.execute(initial_state)
        
        # Verificar saludo
        assert result1.update["awaiting_user_input"] is True
        assert "email corporativo" in result1.update["messages"][-1].content.lower()
        
        # 2. Segunda ejecución - Usuario proporciona email
        state_with_email = {
            **initial_state,
            "messages": result1.update["messages"] + [
                HumanMessage(content="Mi email es juan.perez@eroski.es")
            ]
        }
        
        # Mock de búsqueda exitosa
        mock_search.return_value = sample_employee_result
        
        result2 = await node.execute(state_with_email)
        
        # Verificar identificación exitosa
        assert result2.update["authenticated"] is True
        assert result2.update["employee_name"] == "Juan Pérez García"
        assert "identificado correctamente" in result2.update["messages"][-1].content.lower()
    
    @pytest.mark.asyncio
    @patch('nodes.identificador_base_de_datos.search_by_email')
    @patch('nodes.identificador_base_de_datos.search_by_employee_id')
    async def test_email_fails_then_id_succeeds(self, mock_search_id, mock_search_email, sample_employee_result):
        """Test: Email falla, luego ID de empleado tiene éxito"""
        node = IdentificadorBaseDatosNode()
        
        # 1. Búsqueda por email falla
        state_email = {
            "messages": [HumanMessage(content="Mi email es inexistente@test.com")],
            "session_id": "test",
            "email_authen_tried": False,
            "employee_id_authent_tried": False,
            "authenticated": False
        }
        
        mock_search_email.return_value = {"found": False, "error": "Email no encontrado"}
        
        result1 = await node.execute(state_email)
        
        # Verificar que solicita ID de empleado
        assert result1.update["email_authen_tried"] is True
        assert result1.update["authenticated"] is False
        assert "número de empleado" in result1.update["messages"][-1].content.lower()
        
        # 2. Búsqueda por ID de empleado tiene éxito
        state_id = {
            **state_email,
            **result1.update,
            "messages": result1.update["messages"] + [
                HumanMessage(content="Mi número de empleado es 12345")
            ]
        }
        
        mock_search_id.return_value = sample_employee_result
        
        result2 = await node.execute(state_id)
        
        # Verificar identificación final exitosa
        assert result2.update["authenticated"] is True
        assert result2.update["employee_id_authent_tried"] is True


# =============================================================================
# TESTS DE RENDIMIENTO Y STRESS
# =============================================================================

class TestPerformanceAndStress:
    """Tests de rendimiento y casos extremos"""
    
    @pytest.mark.asyncio
    async def test_handle_very_long_message(self, node):
        """Test: Manejo de mensajes muy largos"""
        long_message = "A" * 1000 + " mi email es test@eroski.es " + "B" * 1000
        
        state = {
            "messages": [HumanMessage(content=long_message)],
            "session_id": "long_test",
            "email_authen_tried": False,
            "employee_id_authent_tried": False,
            "authenticated": False
        }
        
        extracted = node._extract_identification_data(long_message)
        
        # Debe extraer el email correctamente
        assert extracted["email"] == "test@eroski.es"
    
    @pytest.mark.asyncio
    async def test_multiple_emails_in_message(self, node):
        """Test: Múltiples emails en el mismo mensaje"""
        message = "Mi email anterior era old@eroski.es pero ahora es nuevo@eroski.es"
        
        extracted = node._extract_identification_data(message)
        
        # Debe extraer el primer email encontrado
        assert extracted["email"] in ["old@eroski.es", "nuevo@eroski.es"]
    
    @pytest.mark.asyncio
    async def test_special_characters_in_message(self, node):
        """Test: Caracteres especiales en el mensaje"""
        message = "¡Hola! Mi email es josé.pérez@eroski.es (España)"
        
        extracted = node._extract_identification_data(message)
        
        # Debe manejar caracteres especiales correctamente
        assert extracted["email"] == "josé.pérez@eroski.es"


# =============================================================================
# TESTS DE LA FUNCIÓN WRAPPER
# =============================================================================

class TestWrapperFunction:
    """Tests para la función wrapper de LangGraph"""
    
    @pytest.mark.asyncio
    @patch('nodes.identificador_base_de_datos.IdentificadorBaseDatosNode')
    async def test_wrapper_creates_node_and_executes(self, mock_node_class):
        """Test: Wrapper crea nodo y ejecuta correctamente"""
        # Mock del nodo
        mock_node = Mock()
        mock_node.execute = AsyncMock(return_value="test_result")
        mock_node_class.return_value = mock_node
        
        # Estado de prueba
        test_state = {"test": "data"}
        
        # Ejecutar wrapper
        result = await identificador_base_de_datos_node(test_state)
        
        # Verificar ejecución
        mock_node_class.assert_called_once()
        mock_node.execute.assert_called_once_with(test_state)
        assert result == "test_result"


# =============================================================================
# CONFIGURACIÓN DE PYTEST Y HELPERS
# =============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """Event loop para tests async"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

def setup_test_environment():
    """Configurar entorno de test"""
    # Mock de configuración
    mock_settings = Mock()
    mock_settings.database.connection_string = "postgresql://test:test@localhost:5432/test_db"
    
    return mock_settings

# =============================================================================
# SUITE DE TESTS PRINCIPALES PARA EJECUCIÓN DIRECTA
# =============================================================================

class InteractiveNodeTester:
    """Tester interactivo para probar el nodo manualmente"""
    
    def __init__(self, debug_mode: bool = False):
        self.debug_mode = debug_mode
        self.node = IdentificadorBaseDatosNode()
        self.current_state = {
            "messages": [],
            "session_id": "interactive_test",
            "email_authen_tried": False,
            "employee_id_authent_tried": False,
            "authenticated": False
        }
    
    def print_state(self):
        """Mostrar estado actual"""
        print("\n" + "="*60)
        print("📊 ESTADO ACTUAL:")
        print(f"  • Autenticado: {self.current_state.get('authenticated', False)}")
        print(f"  • Email intentado: {self.current_state.get('email_authen_tried', False)}")
        print(f"  • ID intentado: {self.current_state.get('employee_id_authent_tried', False)}")
        print(f"  • Mensajes: {len(self.current_state.get('messages', []))}")
        
        if self.current_state.get('authenticated'):
            print(f"  • Empleado: {self.current_state.get('employee_name', 'N/A')}")
            print(f"  • Email: {self.current_state.get('employee_email', 'N/A')}")
        
        print("="*60)
    
    async def run_interactive_test(self):
        """Ejecutar test interactivo"""
        print("🧪 TESTER INTERACTIVO - NODO IDENTIFICADOR BD")
        print("="*60)
        print("Comandos disponibles:")
        print("  • 'quit' - Salir")
        print("  • 'state' - Mostrar estado")
        print("  • 'reset' - Reiniciar")
        print("  • Cualquier otro texto se enviará como mensaje del usuario")
        print("="*60)
        
        try:
            while True:
                user_input = input("\n👤 Usuario: ").strip()
                
                if user_input.lower() in ['quit', 'exit']:
                    break
                elif user_input.lower() == 'state':
                    self.print_state()
                    continue
                elif user_input.lower() == 'reset':
                    self.current_state = {
                        "messages": [],
                        "session_id": "interactive_test_reset",
                        "email_authen_tried": False,
                        "employee_id_authent_tried": False,
                        "authenticated": False
                    }
                    print("🔄 Estado reiniciado")
                    continue
                
                # Agregar mensaje del usuario
                if user_input:
                    self.current_state["messages"].append(HumanMessage(content=user_input))
                
                # Ejecutar nodo
                print("🤖 Procesando...")
                print("🌄JGL antes de llamar al node")
                result = await self.node.execute(self.current_state)
                
                # Actualizar estado
                self.current_state.update(result.update)
                
                # Mostrar respuesta del bot
                if "messages" in result.update and result.update["messages"]:
                    last_message = result.update["messages"][-1]
                    if isinstance(last_message, AIMessage):
                        print(f"🤖 Bot: {last_message.content}")
                
                # Mostrar información de debug si está activado
                if self.debug_mode:
                    print(f"\n🐛 DEBUG - Campos actualizados: {list(result.update.keys())}")
                
        except KeyboardInterrupt:
            print("\n👋 Test interrumpido")
        except Exception as e:
            print(f"\n💥 Error: {e}")


# =============================================================================
# FUNCIÓN PRINCIPAL PARA EJECUCIÓN DIRECTA
# =============================================================================

async def main():
    """Función principal para ejecución directa"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Tests para IdentificadorBaseDatosNode")
    parser.add_argument("--interactive", "-i", action="store_true", help="Modo interactivo")
    parser.add_argument("--debug", "-d", action="store_true", help="Modo debug")
    parser.add_argument("--quick", "-q", action="store_true", help="Test rápido")
    
    args = parser.parse_args()
    
    if args.interactive:
        # Modo interactivo
        tester = InteractiveNodeTester(debug_mode=args.debug)
        await tester.run_interactive_test()
    elif args.quick:
        # Test rápido
        print("🚀 EJECUTANDO TEST RÁPIDO...")
        
        # Test básico de importación
        try:
            node = IdentificadorBaseDatosNode()
            print("✅ Nodo creado correctamente")
            
            # Test de extracción de datos
            test_message = "Mi email es test@eroski.es y soy el empleado 12345"
            extracted = node._extract_identification_data(test_message)
            
            assert extracted["email"] == "test@eroski.es"
            assert extracted["employee_id"] == "12345"
            print("✅ Extracción de datos funciona")
            
            print("🎉 Test rápido completado exitosamente")
            
        except Exception as e:
            print(f"❌ Error en test rápido: {e}")
    else:
        # Ejecutar tests con pytest
        print("🧪 Ejecutando suite completa de tests...")
        import pytest
        pytest.main([__file__, "-v"])


if __name__ == "__main__":
    asyncio.run(main())