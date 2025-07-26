# =====================================================
# nodes/identificador_base_de_datos.py - Nodo de Identificación con PostgreSQL
# =====================================================
"""
Nodo de identificación de usuario mediante búsqueda en base de datos PostgreSQL.

RESPONSABILIDADES:
- Identificar usuario por email o número de empleado
- Consultar base de datos PostgreSQL con dos tools específicas
- Manejar flags de estado para evitar búsquedas repetidas
- Usar agente React para interactuar naturalmente con el usuario
- Integrar herramientas de confirmación inteligente

CARACTERÍSTICAS:
- Agente React con dos tools especializadas
- Gestión de flags para optimización de consultas
- Manejo robusto de errores de conexión
- Interacción conversacional natural
- Mapeo automático al estado de EroskiState
- Tools adaptadas a la estructura real de la BD
"""

from typing import Dict, Any, Optional, List
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langchain.agents import create_react_agent, AgentExecutor
from langchain_core.prompts import PromptTemplate
from langgraph.types import Command
from datetime import datetime
import logging
import asyncpg
import json
import re

from app.models.eroski_state import EroskiState
from app.nodes.base_node import BaseNode
from app.utils.llm.providers import get_llm
from config.settings import get_settings

# Importar el decorador de confirmación
try:
    from app.nodes.tools.confirmation_tool import add_confirmation_tool_to_node
    CONFIRMATION_AVAILABLE = True
    print("👹 esta disponible el confirmation tool  ")
except ImportError:
    CONFIRMATION_AVAILABLE = False
    add_confirmation_tool_to_node = lambda cls: cls  # Decorador vacío si no está disponible


# =============================================================================
# TOOLS ADAPTADAS A LA ESTRUCTURA REAL DE LA BD
# =============================================================================

@tool
async def search_by_email_adapted(email: str) -> Dict[str, Any]:
    """
    Buscar empleado por email en la base de datos PostgreSQL.
    Adaptado a la estructura real: nombre, apellido, email, numero_empleado, rol, departamento, activo
    
    Args:
        email: Email del empleado a buscar
        
    Returns:
        Dict con los datos del empleado o información de error
    """
    logger = logging.getLogger("SearchByEmailAdapted")
    
    try:
        # Validar formato de email
        if not email or not isinstance(email, str):
            return {"found": False, "error": "Email no válido"}
        
        email = email.strip().lower()
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            return {"found": False, "error": "Formato de email inválido"}
        
        # Obtener configuración de BD
        settings = get_settings()
        connection_string = settings.database.connection_string
        
        # Conectar y buscar usando la estructura real
        conn = await asyncpg.connect(connection_string)
        
        try:
            result = await conn.fetchrow("""
                SELECT numero_empleado, nombre, apellido, email, 
                       rol, departamento, tienda, activo
                FROM usuarios 
                WHERE LOWER(email) = $1 AND activo = true
            """, email)
            
            if result:
                logger.info(f"✅ Empleado encontrado por email: {result['nombre']} {result['apellido']}")

                nombre = result['nombre'] or ''
                apellido = result['apellido'] or ''
                departamento = result['departamento'] or 'Sin asignar'
                nombre_tienda = result['tienda'] or 'Sin asignar'
                # Construir nombre completo de forma segura
                nombre_completo = f"{nombre} {apellido}".strip()
                if not nombre_completo:
                    nombre_completo = 'Usuario sin nombre'
                
                return {
                    "found": True,
                    "numero_empleado": result['numero_empleado'],
                    "nombre": nombre_completo,
                    "email": result['email'],
                    "nombre_tienda": nombre_tienda,  # Usar departamento como tienda
                    "departamento": departamento
                }
            else:
                logger.info(f"❌ No se encontró empleado con email: {email}")
                return {"found": False, "error": "Email no encontrado en la base de datos"}
                
        finally:
            await conn.close()
            
    except Exception as e:
        logger.error(f"❌ Error buscando por email {email}: {e}")
        return {"found": False, "error": f"Error de conexión: {str(e)}"}

@tool
async def search_by_employee_id_adapted(employee_id: str) -> Dict[str, Any]:
    """
    Buscar empleado por número de empleado en la base de datos PostgreSQL.
    Adaptado a la estructura real: numero_empleado (VARCHAR(4))
    
    Args:
        employee_id: Número de empleado a buscar
        
    Returns:
        Dict con los datos del empleado o información de error
    """
    logger = logging.getLogger("SearchByEmployeeIdAdapted")
    
    try:
        # Validar número de empleado
        if not employee_id or not isinstance(employee_id, str):
            return {"found": False, "error": "Número de empleado no válido"}
        
        employee_id = employee_id.strip()
        # Acepta tanto números como códigos alfanuméricos de hasta 4 caracteres
        if len(employee_id) > 4:
            return {"found": False, "error": "Número de empleado debe tener máximo 4 caracteres"}
        
        # Obtener configuración de BD
        settings = get_settings()
        connection_string = settings.database.connection_string
        
        # Conectar y buscar
        conn = await asyncpg.connect(connection_string)
        
        try:
            result = await conn.fetchrow("""
                SELECT numero_empleado, nombre, apellido, email, 
                       rol, departamento, tienda, activo
                FROM usuarios 
                WHERE numero_empleado = $1 AND activo = true
            """, employee_id)
            
            if result:
                nombre = result['nombre'] or ''
                apellido = result['apellido'] or ''
                departamento = result['departamento'] or 'Sin asignar'
                nombre_tienda = result['tienda'] or 'Sin asignar'

                # Construir nombre completo de forma segura
                nombre_completo = f"{nombre} {apellido}".strip()
                if not nombre_completo:
                    nombre_completo = 'Usuario sin nombre'
                logger.info(f"✅ Empleado encontrado por ID: {result['nombre']} {result['apellido']}")
                return {
                    "found": True,
                    "numero_empleado": result['numero_empleado'],
                    "nombre": nombre_completo,
                    "email": result['email'],
                    "nombre_tienda": nombre_tienda,  # Usar departamento como tienda
                    "departamento": departamento
                }
            else:
                logger.info(f"❌ No se encontró empleado con ID: {employee_id}")
                return {"found": False, "error": "Número de empleado no encontrado"}
                
        finally:
            await conn.close()
            
    except Exception as e:
        logger.error(f"❌ Error buscando por ID {employee_id}: {e}")
        return {"found": False, "error": f"Error de conexión: {str(e)}"}

next_node_after_authentication = "classify_node"

# =============================================================================
# NODO PRINCIPAL DE IDENTIFICACIÓN
# =============================================================================

@add_confirmation_tool_to_node
class IdentificadorBaseDatosNode(BaseNode):
    """
    Nodo de identificación de usuarios mediante base de datos PostgreSQL.
    
    Utiliza un agente React con dos tools especializadas para buscar empleados
    por email o número de empleado, manejando flags de estado para optimización.
    """
    
    def __init__(self):
        super().__init__("IdentificadorBaseDatos")
        self.llm = get_llm()
        self.max_attempts = 10
        
        # Crear agente React con las tools adaptadas
        self.tools = [search_by_email_adapted, search_by_employee_id_adapted]
        self.agent = self._create_react_agent()
        
        # Log sobre la tool de confirmación
        if hasattr(self, 'confirmation_tool'):
            self.logger.info("✅ Tool de confirmación integrada correctamente")
        else:
            self.logger.warning("⚠️ Tool de confirmación no disponible")
    
    def _create_react_agent(self) -> AgentExecutor:
        """Crear agente React con las tools de búsqueda"""
        
        prompt = PromptTemplate(
            input_variables=["input", "agent_scratchpad", "tools", "tool_names"],
            template=
            """
Eres un asistente especializado en identificar empleados de Eroski mediante búsqueda en base de datos.

HERRAMIENTAS DISPONIBLES:
{tools}

NOMBRES DE LAS HERRAMIENTAS:
{tool_names}


🎯 MISIÓN:
Identificar al usuario utilizando su email o número de empleado a partir de su mensaje.

📋 INSTRUCCIONES:
1. Si encuentras un email, usa `search_by_email_adapted`
2. Si encuentras un número de empleado, usa `search_by_employee_id_adapted`
3. Si encuentras ambos, prioriza el email
4. Si no encuentras ninguno, pide que el usuario proporcione sus datos

⚠️ IMPORTANTE:
Usa SIEMPRE este formato para ejecutar una herramienta:

Thought: Necesito buscar al usuario por email
Action: search_by_email_adapted
Action Input: {{"email": "nombre@eroski.es"}}

Otro ejemplo:

Thought: El usuario ha dado su número de empleado
Action: search_by_employee_id_adapted
Action Input: {{"employee_id": "G123"}}

❌ NO digas "usaré la herramienta..." en lenguaje natural.
✅ Usa el formato exacto con Action y Action Input.

MENSAJE DEL USUARIO:
{input}

{agent_scratchpad}

""")
        
        agent = create_react_agent(self.llm, self.tools, prompt)
        return AgentExecutor(agent=agent, 
                             tools=self.tools, 
                             verbose=True, 
                             max_iterations=3,
                             handle_parsing_errors=True)
    
    def get_required_fields(self) -> List[str]:
        return ["messages"]
    
    def get_actor_description(self) -> str:
        return "Identifico empleados mediante búsqueda en base de datos PostgreSQL usando email o número de empleado"
    
    async def execute(self, state: EroskiState) -> Command:
        """
        Ejecutar identificación del usuario.
        
        Args:
            state: Estado actual del workflow
            
        Returns:
            Command con las actualizaciones de estado
        """
        self.logger.info(f'🌄JGL entra en {self.__class__.__name__}')

        self.logger.info("🔍 === INICIANDO IDENTIFICACIÓN POR BASE DE DATOS ===")
        # Verificar si la autenticación ya está completada
        if state.get("authenticated", False):
            self.logger.info("✅ Usuario ya autenticado, pasando al siguiente paso")
            
            return Command(update={
                "current_node": "identificador_base_datos",
                "last_activity": datetime.now()
            })
        
        # Verificar flags para evitar búsquedas repetidas
        email_tried = state.get("email_authen_tried", False)
        employee_id_tried = state.get("employee_id_authent_tried", False)
        
        logging.info(f"👹 JGL email_tried:{email_tried}, employee_id_tried:{employee_id_tried}")
        # Si ambos métodos ya fueron intentados sin éxito
        if email_tried and employee_id_tried and not state.get("authenticated", False):
            return self._handle_identification_failed(state)
        
        # Obtener último mensaje del usuario
        user_message = self._get_last_user_message(state)
        self.logger.info(f"🌄JGL user_message:{user_message}" )
        # Si es el primer mensaje, enviar saludo inicial
        #if not user_message or self._is_first_interaction(state):
        #    self.logger.info("🌄JGL es la primera interacción o no hay mensaje del usuario")
        #    return self._send_initial_greeting(state)
        
        # Procesar mensaje del usuario con el agente React
        resultado = await self._process_user_message(state, user_message)
        # Actualizar estado con 
        return resultado
    
    def _get_last_user_message(self, state: EroskiState) -> Optional[str]:
        """Obtener el último mensaje del usuario"""
        messages = state.get("messages", [])
        
        for message in reversed(messages):
            if isinstance(message, HumanMessage) and message.content.strip():
                return message.content.strip()
        
        return None
    
    def _is_first_interaction(self, state: EroskiState) -> bool:
        """Verificar si es la primera interacción"""
        messages = state.get("messages", [])
        human_messages = [m for m in messages if isinstance(m, HumanMessage)]
        return len(human_messages) <= 1
    
    def _send_initial_greeting(self, state: EroskiState) -> Command:
        """Enviar saludo inicial solicitando identificación"""
        
        greeting_message = """¡Hola! 👋 Soy tu asistente de incidencias de Eroski.

Para ayudarte de la mejor manera, necesito identificarte. Por favor, proporciona:

📧 **Tu email corporativo** (ejemplo: nombre.apellido@eroski.es)
**O**
🆔 **Tu número de empleado** (ejemplo: 12345)

Puedes escribir algo como:
• "Mi email es juan.perez@eroski.es"
• "Soy el empleado 12345"
• "juan.perez@eroski.es, necesito ayuda con una incidencia"

¿Cómo te identifico? 😊"""
        
        return Command(update={
            "messages": state.get("messages", []) + [AIMessage(content=greeting_message)],
            "current_node": "identificador_base_datos",
            "awaiting_user_input": True,
            "last_activity": datetime.now(),
            "identification_stage": "requesting_credentials"
        })
    
    async def _process_user_message(self, state: EroskiState, user_message: str) -> Command:
        """Procesar mensaje del usuario con el agente React"""
        
        self.logger.info(f"🔍 Procesando mensaje: {user_message[:100]}...")
        
        try:
            # Para este nodo, vamos directo a extraer datos sin tool de confirmación
            # ya que está causando problemas de validación
            
            # Extraer email y número de empleado del mensaje
            self.logger.info("🌄JGL antes de extraer datos de identificación")
            extracted_data = await self._extract_identification_data(user_message)
            self.logger.info("🌄JGL datos extraídos 358:", extracted_data)
            
            # Verificar qué tipo de búsqueda realizar basado en flags
            email_tried = state.get("email_authen_tried", False)
            employee_id_tried = state.get("employee_id_authent_tried", False)
            
            # Determinar método de búsqueda
            self.logger.info("🌄JGL punto 1", extracted_data)
            if extracted_data["email"] and not email_tried:
                self.logger.info("🌄JGL punto 2", extracted_data)
                self.logger.info(f"🔄 Intentando búsqueda por email: {extracted_data['email']}")
                return await self._search_by_email(state, extracted_data["email"])
            elif extracted_data["employee_id"] and not employee_id_tried:
                self.logger.info("🌄JGL punto 3", extracted_data)
                self.logger.info(f"🔄 Intentando búsqueda por ID: {extracted_data['employee_id']}")
                return await self._search_by_employee_id(state, extracted_data["employee_id"])
            elif extracted_data["email"] or extracted_data["employee_id"]:
                self.logger.info("🌄JGL punto 4", extracted_data)
                # Ya se intentó este método, usar el agente para responder
                self.logger.info("🔄 Método ya intentado, usando agente React")
                response = await self.agent.ainvoke({"input": user_message})
                output = None
                self.logger.info("🌄JGL punto 5:\n", response)
                if isinstance(response, dict) and "output" in response:
                    output = response["output"]
                elif hasattr(response, "return_values") and "output" in response.return_values:
                    output = response.return_values["output"]
                else:
                    self.logger.warning("⚠️ No se pudo extraer 'output' del agente. Respuesta cruda: %s", response)
                    output = "⚠️ No entendí tu mensaje. ¿Podrías repetirlo con más claridad?"

                return self._handle_agent_response(state, output)
               
                
                
                
            else:
                # No se encontró información de identificación
                self.logger.info("❌ No se encontró email ni ID en el mensaje")
                return self._request_identification_info(state)
                
        except Exception as e:
            self.logger.info("🌄JGL 1")
            self.logger.error(f"❌ Error procesando mensaje: {e}")
            return self._handle_error(state, str(e))
    
    async def _handle_confirmation_response(self, state: EroskiState, confirmation_result: Dict) -> Command:
        """Manejar respuesta de confirmación del usuario"""
        
        self.logger.info(f"🎯 Procesando confirmación: {confirmation_result}")
        
        if confirmation_result.get('intent') == 'affirmative':
            # Usuario confirma - continuar con el flujo
            pending_data = state.get('pending_identification_data')
            if pending_data:
                # Continuar con identificación pendiente
                if pending_data.get('email'):
                    return await self._search_by_email(state, pending_data['email'])
                elif pending_data.get('employee_id'):
                    return await self._search_by_employee_id(state, pending_data['employee_id'])
            
            # Si no hay datos pendientes, solicitar información
            return self._request_identification_info(state)
            
        elif confirmation_result.get('intent') == 'negative':
            # Usuario no confirma - solicitar información nuevamente
            return self._request_identification_info(state)
            
        else:
            # Respuesta ambigua - solicitar clarificación
            clarification_message = """🤔 **No estoy seguro de entender tu respuesta**

Por favor, proporciona:
📧 **Tu email corporativo** (ejemplo: nombre.apellido@eroski.es)
**O**
🆔 **Tu número de empleado** (ejemplo: 12345)

¿Podrías ayudarme con esta información? 😊"""
            
            return Command(update={
                "messages": state.get("messages", []) + [AIMessage(content=clarification_message)],
                "current_node": "identificador_base_datos",
                "awaiting_user_input": True,
                "last_activity": datetime.now()
            })

    async def _extract_identification_data(self, message: str) -> Dict[str, Optional[str]]:
        self.logger.info(f"🔍 Iniciando extracción híbrida del mensaje: '{message}'")

        # PASO 1: REGEX
        self.logger.info("🌄JGL antes de extraer con REGEX")
        regex_result = self._extract_with_regex(message)
        self.logger.info("🌄JGL REGEX result:", regex_result)

        extracted_id = regex_result.get("employee_id")
        self.logger.info(f"🌄JGL REGEX result: {extracted_id}")
        if extracted_id and not self.is_valid_employee_id(extracted_id):
            self.logger.info(f"🌄JGL ID inválido, aplicando regex\nEmployee ID rechazado por patrón inválido: {extracted_id}")
            self.logger.info(f"⚠️ Employee ID rechazado por patrón inválido: {extracted_id}")
            regex_result["employee_id"] = None

        self.logger.info("🌄Ha pasado")
        # PASO 2: Confianza
        confidence = self._evaluate_regex_confidence(regex_result, message)
        self.logger.info(f"🌄JGL 📊 REGEX: email='{regex_result['email']}', id='{regex_result['employee_id']}', confianza={confidence:.2f}")
        self.logger.info(f"📊 REGEX: email='{regex_result['email']}', id='{regex_result['employee_id']}', confianza={confidence:.2f}")

        # PASO 3: Usar o no usar LLM
        if confidence >= 0.7:
            self.logger.info("🌄JGL REGEX confiable, usando resultado directo")
            self.logger.info("✅ REGEX confiable, usando resultado directo")
            return {
                "email": regex_result["email"],
                "employee_id": regex_result["employee_id"],
                "method": "regex",
                "confidence": confidence
            }
        else:
            self.logger.info("🤖 REGEX no confiable, ejecutando fallback con LLM")
            return await self._extract_with_llm_fallback(message, regex_result)

    def _extract_with_regex(self, message: str) -> Dict[str, Optional[str]]:
        """Extracción rápida con REGEX - versión mejorada"""
        
        # Buscar email con patrón robusto
        email_pattern = r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b'
        email_match = re.search(email_pattern, message)
        email = email_match.group() if email_match else None
        
        # Buscar employee_id con múltiples estrategias
        employee_id = None
        
        # Estrategia 1: Patrones explícitos con palabras clave
        explicit_patterns = [
            r'empleado\s+([A-Za-z0-9]{1,4})',
            r'mi\s+(?:número|codigo|id)\s+(?:es\s+)?([A-Za-z0-9]{1,4})',
            r'soy\s+(?:el\s+)?([A-Za-z0-9]{1,4})',
        ]
        
        for pattern in explicit_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                employee_id = match.group(1)
                break
        
        # Estrategia 2: Códigos alfanuméricos típicos de empleados
        if not employee_id:
            alpha_num_pattern = r'\b(?:[A-Za-z]\d{1,3}|[A-Za-z]{1,2}\d{1,2})\b'
            alpha_matches = re.findall(alpha_num_pattern, message)
            if alpha_matches:
                employee_id = alpha_matches[0]
        
        # Estrategia 3: Números simples (solo si son únicos y cortos)
        if not employee_id:
            number_pattern = r'\b\d{1,4}\b'
            number_matches = re.findall(number_pattern, message)
            
            # Filtrar números que probablemente no sean IDs
            valid_numbers = []
            for num in number_matches:
                # Evitar números muy largos que podrían ser teléfonos
                if len(num) <= 4 and not self._is_likely_phone_or_date(num, message):
                    valid_numbers.append(num)
            
            if len(valid_numbers) == 1:  # Solo si hay un único candidato
                employee_id = valid_numbers[0]
        
        return {
            "email": email,
            "employee_id": employee_id
        }
    
    def _is_likely_phone_or_date(self, number: str, message: str) -> bool:
        """Determinar si un número es probablemente teléfono o fecha"""
        
        # Buscar contexto que sugiera teléfono
        phone_keywords = ['teléfono', 'telefono', 'móvil', 'movil', 'llama', 'contacto']
        if any(keyword in message.lower() for keyword in phone_keywords):
            return True
        
        # Buscar contexto que sugiera fecha
        date_keywords = ['fecha', 'año', 'mes', 'día', 'nacimiento']
        if any(keyword in message.lower() for keyword in date_keywords):
            return True
        
        return False
    
    def _evaluate_regex_confidence(self, regex_result: Dict, message: str) -> float:
        """Evaluar confianza del resultado REGEX"""
        
        confidence = 0.0
        # Email válido encontrado
        if regex_result["email"]:
            confidence += 0.4
            
            # Bonus si es email corporativo de Eroski
            if "@eroski.es" in regex_result["email"].lower():
                confidence += 0.2
        
        # Employee ID encontrado
        if regex_result["employee_id"]:
            confidence += 0.3
            
            # Bonus por formato típico de código de empleado
            if re.match(r'^[A-Za-z]{1,2}\d{1,3}$', regex_result["employee_id"]):
                confidence += 0.2
        return confidence

    def is_valid_employee_id(self, value: Optional[str]) -> bool:
        """
        Verifica si el valor sigue el patrón típico de un código de empleado.
        Ejemplo: E123, G301, X9, etc.
        """
        self.logger.info("🌄JGL is_valid_employee_id:", value)
        if not value:
            return False
        return bool(re.match(r'^[A-Za-z]{1,2}\d{1,3}$', value.strip()))
   
    async def _search_by_email(self, state: EroskiState, email: str) -> Command:
        """Buscar por email y actualizar estado"""
        
        self.logger.info(f"📧 Buscando por email: {email}")
        
        # Realizar búsqueda usando invoke en lugar de llamada directa
        try:
            result = await search_by_email_adapted.ainvoke({"email": email})
        except Exception as e:
            self.logger.error(f"❌ Error en tool search_by_email_adapted: {e}")
            result = {"found": False, "error": f"Error técnico: {str(e)}"}
        
        # Actualizar flag
        base_update = {
            "email_authen_tried": True,
            "current_node": "identificador_base_datos",
            "last_activity": datetime.now()
        }
        
        if result["found"]:
            return self._handle_successful_identification(state, result, base_update)
        else:
            return self._handle_failed_search(state, "email", result.get("error"), base_update)
    
    async def _search_by_employee_id(self, state: EroskiState, employee_id: str) -> Command:
        """Buscar por número de empleado y actualizar estado"""
        
        self.logger.info(f"🆔 Buscando por número de empleado: {employee_id}")
        
        # Realizar búsqueda usando invoke en lugar de llamada directa
        try:
            result = await search_by_employee_id_adapted.ainvoke({"employee_id": employee_id})
        except Exception as e:
            self.logger.error(f"❌ Error en tool search_by_employee_id_adapted: {e}")
            result = {"found": False, "error": f"Error técnico: {str(e)}"}
        
        # Actualizar flag
        base_update = {
            "employee_id_authent_tried": True,
            "current_node": "identificador_base_datos",
            "last_activity": datetime.now()
        }
        
        if result["found"]:
            return self._handle_successful_identification(state, result, base_update)
        else:
            return self._handle_failed_search(state, "número de empleado", result.get("error"), base_update)
    
    def _handle_successful_identification(self, state: EroskiState, result: Dict, base_update: Dict) -> Command:
        """Manejar identificación exitosa"""
        
        self.logger.info(f"✅ Empleado identificado: {result['nombre']}")
        empleado_nombre = result.get('nombre') or 'No disponible'
        empleado_email = result.get('email') or 'No disponible'
        nombre_tienda = result.get('nombre_tienda') or 'No especificada'
        departamento = result.get('departamento') or 'No especificado'

        success_message = f"""✅ **¡Te he identificado correctamente!**
    
👤 **Empleado:** {empleado_nombre}
📧 **Email:** {empleado_email}
🏪 **Tienda:** {nombre_tienda}
🏢 **Departamento:** {departamento}

¡Perfecto! Ahora puedo ayudarte con tu incidencia. ¿Qué problema necesitas reportar? 🔧"""
        
        # Mapear datos al estado
        complete_update = {
            **base_update,
            "authenticated": True,
            "employee_id": result.get('numero_empleado'),
            "employee_name": empleado_nombre,
            "employee_email": empleado_email,
            "store_name": nombre_tienda,
            "department": departamento,
            "identification_method": "database",
            "messages": state.get("messages", []) + [AIMessage(content=success_message)]
        }
        
        return Command(update=complete_update)
    
    def _handle_failed_search(self, state: EroskiState, search_type: str, error: str, base_update: Dict) -> Command:
        """Manejar búsqueda fallida"""
        
        self.logger.info(f"❌ Búsqueda fallida por {search_type}: {error}")
        
        # Verificar si se puede intentar el otro método
        email_tried = base_update.get("email_authen_tried", state.get("email_authen_tried", False))
        employee_id_tried = base_update.get("employee_id_authent_tried", state.get("employee_id_authent_tried", False))
        
        if not email_tried or not employee_id_tried:
            # Aún se puede intentar el otro método
            other_method = "email" if not email_tried else "número de empleado"
            search_type_safe = search_type or "método de búsqueda"
            other_method_safe = other_method or "otro método"
            retry_message = f"""❌ No pude encontrarte con ese {search_type_safe}.

¿Podrías intentar proporcionando tu **{other_method_safe}**?

• Si tienes tu email corporativo: **nombre.apellido@eroski.es**
• Si tienes tu número de empleado: **12345**

También puedes contactar con tu supervisor si no tienes estos datos. 📞"""
            
            complete_update = {
                **base_update,
                "messages": state.get("messages", []) + [AIMessage(content=retry_message)]
            }
            
        else:
            # Ambos métodos fallaron
            return self._handle_identification_failed(state, base_update)
            
        return Command(update=complete_update)
    
    def _handle_identification_failed(self, state: EroskiState, base_update: Dict = None) -> Command:
        """Manejar fallo completo de identificación"""
        
        if base_update is None:
            base_update = {
                "current_node": "identificador_base_datos",
                "last_activity": datetime.now()
            }
        
        failure_message = """❌ **No pude identificarte en la base de datos**

Proporcioname tus datos para que pueda ayudarte con la incidencia."""
        
        complete_update = {
            **base_update,
            "authenticated": False,
            "identification_failed": True,
            "escalation_needed": True,
            "escalation_reason": "Usuario no encontrado en base de datos",
            "messages": state.get("messages", []) + [AIMessage(content=failure_message)]
        }
        
        return Command(update=complete_update)
    
    def _request_identification_info(self, state: EroskiState) -> Command:
        """Solicitar información de identificación"""
        
        request_message = """📋 **Necesito información para identificarte**

Para poder ayudarte necesito que me proporciones tu email o número de empleado en tu mensaje.

Por favor, proporciona:
📧 **Tu email corporativo** (ejemplo: nombre.apellido@eroski.es)
**O**
🆔 **Tu número de empleado** (ejemplo: 12345)

Ejemplos:
• "Mi email es maria.garcia@eroski.es"
• "Soy el empleado T999"

¿Podrías ayudarme con esta información? 😊"""
        
        return Command(update={
            "messages": state.get("messages", []) + [AIMessage(content=request_message)],
            "current_node": "identificador_base_datos",
            "awaiting_user_input": True,
            "last_activity": datetime.now()
        })
    
    def _handle_agent_response(self, state: EroskiState, agent_output: str) -> Command:
        """Manejar respuesta del agente React"""
        
        return Command(update={
            "messages": state.get("messages", []) + [AIMessage(content=agent_output)],
            "current_node": "identificador_base_datos",
            "awaiting_user_input": True,
            "last_activity": datetime.now()
        })
    
    def _handle_error(self, state: EroskiState, error_message: str) -> Command:
        """Manejar errores técnicos"""
        
        self.logger.error(f"💥 Error en identificación: {error_message}")
        
        error_response = """❌ **Error técnico temporal**

Ha ocurrido un problema técnico durante la identificación.

**¿Qué hacer?**
1. 🔄 **Intenta nuevamente** en unos minutos
2. 📞 **Si persiste**: Contacta soporte técnico

📞 **Soporte:** +34 946 211 000
📧 **Email:** soporte.tecnico@eroski.es

¡Disculpa las molestias! 🔧"""
        
        return Command(update={
            "messages": state.get("messages", []) + [AIMessage(content=error_response)],
            "current_node": "identificador_base_datos",
            "error_occurred": True,
            "error_details": error_message,
            "escalation_needed": True,
            "escalation_reason": f"Error técnico en identificación: {error_message}",
            "last_activity": datetime.now()
        })

    async def _extract_with_llm_fallback(self, message: str, regex_result: Dict) -> Dict[str, Optional[str]]:
        """Usar LLM como fallback para casos complejos"""
        
        try:
            llm_result = await self._extract_with_llm(message)
            
            # Combinar resultados: LLM tiene prioridad, REGEX como respaldo
            final_result = {
                "email": llm_result.get("email") or regex_result.get("email"),
                "employee_id": llm_result.get("employee_id") or regex_result.get("employee_id"),
                "method": "llm_hybrid",
                "confidence": llm_result.get("confidence", 0.8)
            }
            
            self.logger.info(f"🤖 LLM resultado: email='{final_result['email']}', id='{final_result['employee_id']}'")
            return final_result
            
        except Exception as e:
            self.logger.warning(f"⚠️ Error en LLM, usando REGEX como fallback: {e}")
            return {
                "email": regex_result["email"],
                "employee_id": regex_result["employee_id"],
                "method": "regex_fallback",
                "confidence": 0.5
            }
    
    async def _extract_with_llm(self, message: str) -> Dict[str, Any]:
        """Usar LLM para extracción inteligente y contextual"""
        
        prompt = f"""Analiza este mensaje de un empleado de Eroski y extrae la información de identificación.

MENSAJE: "{message}"

INSTRUCCIONES:
- EMAIL: Busca direcciones de correo electrónico válidas
- EMPLOYEE_ID: Busca códigos/números de empleado (1-4 caracteres)
- IGNORA: teléfonos, fechas, direcciones, otros números no relacionados

CONTEXTO:
- Los IDs de empleado suelen ser códigos cortos (ej: G301, E001, 1234)
- Los emails corporativos suelen terminar en @eroski.es
- Si hay múltiples números, determina cuál es más probable que sea un ID

Responde con JSON válido sin markdown:
{{"email": "email@domain.com", "employee_id": "ID123", "confidence": 0.9}}

Si no encuentras email o employee_id, usa null."""

        try:
            response = await self.llm.ainvoke(prompt)
            content = response.content.strip()
            
            # Limpiar la respuesta de posible markdown
            if content.startswith("```"):
                lines = content.split('\n')
                content = '\n'.join(lines[1:-1])  # Remover primera y última línea
            
            result = json.loads(content)
            
            # Validar y normalizar
            if not isinstance(result, dict):
                raise ValueError("Respuesta no es un dict válido")
            
            # Convertir "null" strings a None
            for key in ["email", "employee_id"]:
                if result.get(key) == "null" or result.get(key) == "":
                    result[key] = None
            
            # Asegurar que tenemos confidence
            if "confidence" not in result:
                result["confidence"] = 0.8
                
            return result
            
        except Exception as e:
            self.logger.error(f"❌ Error procesando respuesta LLM: {e}")
            self.logger.error(f"❌ Contenido recibido: {response.content if 'response' in locals() else 'No response'}")
            return {"email": None, "employee_id": None, "confidence": 0.0}
    


# =============================================================================
# FUNCIÓN WRAPPER PARA LANGGRAPH
# =============================================================================

async def identificador_base_de_datos_node(state: EroskiState) -> Command:
    """
    Función wrapper para LangGraph - Nodo Identificador Base de Datos
    
    Args:
        state: Estado actual como EroskiState
        
    Returns:
        Command con las actualizaciones de estado
    """
    
    # Crear instancia del nodo
    node = IdentificadorBaseDatosNode()
    
    # Ejecutar el nodo
    return await node.execute(state)


# Exports
__all__ = ["identificador_base_de_datos_node", "IdentificadorBaseDatosNode", "search_by_email_adapted", "search_by_employee_id_adapted"]