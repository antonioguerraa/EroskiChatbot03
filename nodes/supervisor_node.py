# =====================================================
# nodes/supervisor_node.py - Nodo Supervisor Mock/Dummy
# =====================================================
"""
Nodo supervisor mock para integración posterior de lógica específica.

RESPONSABILIDADES FUTURAS:
- Manejar escalaciones de todos los nodos del sistema
- Clasificar tipos de escalación (técnica, operativa, recursos humanos)
- Gestionar derivaciones a personal especializado
- Crear tickets en sistemas externos
- Notificar a supervisores correspondientes
- Proporcionar información de contacto emergencia

ESTADO ACTUAL: 
- Implementación dummy/mock siguiendo estructura del proyecto
- Logging detallado para debugging
- Respuestas básicas según tipo de escalación
- Preparado para integración de lógica real
"""

from typing import Dict, Any, Optional, List
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command
from datetime import datetime
import logging

from models.eroski_state import EroskiState
from nodes.base_node import BaseNode


# =============================================================================
# CONFIGURACIÓN DE ESCALACIONES
# =============================================================================

class EscalationType:
    """Tipos de escalación disponibles"""
    AUTHENTICATION = "authentication"           # Fallos de autenticación
    IDENTIFICATION = "identification"          # Problemas identificando incidencias
    CLASSIFICATION = "classification"          # Problemas clasificando consultas
    TECHNICAL = "technical"                    # Problemas técnicos de equipos
    SYSTEM_ERROR = "system_error"              # Errores del sistema chatbot
    TIMEOUT = "timeout"                        # Timeouts por exceso intentos
    USER_REQUEST = "user_request"              # Usuario solicita hablar con supervisor
    UNKNOWN = "unknown"                        # Escalación sin categoría clara


class SupervisorContactInfo:
    """Información de contacto por tipo de escalación"""
    
    CONTACTS = {
        EscalationType.TECHNICAL: {
            "department": "Soporte Técnico",
            "phone": "+34 946 211 000",
            "email": "soporte.tecnico@eroski.es",
            "hours": "24/7",
            "priority": "alta",
            "description": "Problemas con equipos técnicos (TPV, impresoras, balanzas, etc.)"
        },
        EscalationType.AUTHENTICATION: {
            "department": "Recursos Humanos",
            "phone": "+34 946 211 100", 
            "email": "rrhh@eroski.es",
            "hours": "L-V 9:00-17:00",
            "priority": "media",
            "description": "Problemas de acceso y verificación de empleados"
        },
        EscalationType.SYSTEM_ERROR: {
            "department": "Soporte IT",
            "phone": "+34 946 211 200",
            "email": "it.support@eroski.es", 
            "hours": "L-V 8:00-20:00",
            "priority": "alta",
            "description": "Errores del sistema chatbot y aplicaciones"
        },
        "default": {
            "department": "Supervisor de Tienda",
            "phone": "Extensión 100",
            "email": "supervisor@tienda.eroski.es",
            "hours": "Horario de tienda", 
            "priority": "media",
            "description": "Supervisión general y consultas diversas"
        }
    }


# =============================================================================
# NODO SUPERVISOR PRINCIPAL
# =============================================================================

class SupervisorNode(BaseNode):
    """
    Nodo supervisor mock para manejar todas las escalaciones del sistema.
    
    DISEÑO:
    - Analiza motivo de escalación desde el estado
    - Determina contacto apropiado según tipo
    - Genera respuesta contextual al usuario
    - Registra escalación para seguimiento
    - Proporciona información de contacto relevante
    
    PREPARADO PARA:
    - Integración con sistemas de tickets
    - Notificaciones automáticas a supervisores
    - Escalación inteligente por tipo de problema
    - Métricas de escalaciones
    """
    
    def __init__(self):
        super().__init__("supervisor")
        self.escalation_count = 0
        self.escalations_history = []
        
    def get_required_fields(self) -> List[str]:
        """Campos requeridos en el estado"""
        return ["messages", "escalation_needed"]
    
    def get_actor_description(self) -> str:
        """Descripción del rol del nodo"""
        return ("Gestiono escalaciones a supervisores y personal especializado. "
                "Analizo el contexto para derivar al contacto más apropiado y "
                "proporciono información clara sobre los próximos pasos.")
    
    async def execute(self, state: EroskiState) -> Command:
        """
        Ejecutar lógica principal del supervisor.
        
        Args:
            state: Estado actual del workflow
            
        Returns:
            Command con respuesta del supervisor
        """
        try:
            self.logger.info("🔥 === SUPERVISOR NODE EJECUTÁNDOSE ===")
            
            # Analizar contexto de escalación
            escalation_context = self._analyze_escalation_context(state)
            
            # Determinar tipo de escalación
            escalation_type = self._determine_escalation_type(escalation_context)
            
            # Obtener información de contacto apropiada
            contact_info = self._get_contact_info(escalation_type)
            
            # Registrar escalación
            escalation_record = self._create_escalation_record(state, escalation_type, contact_info)
            
            # Generar respuesta contextual
            supervisor_response = self._generate_supervisor_response(
                escalation_context, escalation_type, contact_info, escalation_record
            )
            
            # Actualizar contador y historial
            self.escalation_count += 1
            self.escalations_history.append(escalation_record)
            
            self.logger.info(f"✅ Escalación procesada: {escalation_type} → {contact_info['department']}")
            
            return Command(update={
                "messages": [AIMessage(content=supervisor_response)],
                "escalation_processed": True,
                "escalation_type": escalation_type,
                "escalation_contact": contact_info,
                "escalation_record": escalation_record,
                "supervisor_response_generated": True,
                "flow_completed": True,
                "awaiting_user_input": False,
                "current_node": "supervisor",
                "last_activity": datetime.now()
            })
            
        except Exception as e:
            self.logger.error(f"❌ Error en supervisor node: {e}")
            return self._handle_supervisor_error(state, str(e))
    
    def _analyze_escalation_context(self, state: EroskiState) -> Dict[str, Any]:
        """
        Analizar contexto completo de la escalación.
        
        Args:
            state: Estado actual
            
        Returns:
            Diccionario con contexto analizado
        """
        context = {
            "escalation_reason": state.get("escalation_reason", "No especificado"),
            "escalation_level": state.get("escalation_level", "unknown"),
            "source_node": state.get("current_node", "unknown"),
            "user_attempts": state.get("attempts", 0),
            "max_attempts": state.get("max_attempts", 3),
            "identification_attempts": state.get("identification_attempts", 0),
            "max_identification_attempts": state.get("max_intent_tipo_incidencia", 4),
            "employee_info": {
                "name": state.get("incident_user_name", "No identificado"),
                "email": state.get("employee_email", "No proporcionado"),
                "store": state.get("incident_store_name", "No identificada"),
                "department": state.get("incident_department", "No especificado")
            },
            "incident_info": {
                "type": state.get("incident_type", "No identificado"),
                "description": state.get("incident_description", "No proporcionada"),
                "equipment": state.get("affected_equipment", "No especificado")
            },
            "system_info": {
                "session_id": state.get("session_id", "unknown"),
                "execution_path": state.get("execution_path", []),
                "error_count": state.get("error_count", 0),
                "start_time": state.get("start_time"),
                "elapsed_time": self._calculate_elapsed_time(state)
            }
        }
        
        self.logger.info(f"📊 Contexto escalación: {context['escalation_reason']}")
        self.logger.info(f"🔄 Origen: {context['source_node']} | Intentos: {context['user_attempts']}/{context['max_attempts']}")
        
        return context
    
    def _determine_escalation_type(self, context: Dict[str, Any]) -> str:
        """
        Determinar tipo específico de escalación basado en contexto.
        
        Args:
            context: Contexto analizado
            
        Returns:
            Tipo de escalación
        """
        escalation_reason = context["escalation_reason"].lower()
        source_node = context["source_node"]
        
        # Mapeo de patrones a tipos
        if "autenticación" in escalation_reason or "authentication" in escalation_reason:
            return EscalationType.AUTHENTICATION
        
        elif "identificación" in escalation_reason or "identification" in escalation_reason:
            return EscalationType.IDENTIFICATION
        
        elif "clasificación" in escalation_reason or "classification" in escalation_reason:
            return EscalationType.CLASSIFICATION
        
        elif any(word in escalation_reason for word in ["tpv", "impresora", "balanza", "technical"]):
            return EscalationType.TECHNICAL
        
        elif "error" in escalation_reason or "exception" in escalation_reason:
            return EscalationType.SYSTEM_ERROR
        
        elif "límite" in escalation_reason or "timeout" in escalation_reason:
            return EscalationType.TIMEOUT
        
        elif "usuario solicita" in escalation_reason or "user_request" in escalation_reason:
            return EscalationType.USER_REQUEST
        
        else:
            self.logger.warning(f"⚠️ Tipo de escalación no reconocido: {escalation_reason}")
            return EscalationType.UNKNOWN
    
    def _get_contact_info(self, escalation_type: str) -> Dict[str, Any]:
        """
        Obtener información de contacto para el tipo de escalación.
        
        Args:
            escalation_type: Tipo de escalación
            
        Returns:
            Información de contacto
        """
        return SupervisorContactInfo.CONTACTS.get(escalation_type, SupervisorContactInfo.CONTACTS["default"])
    
    def _create_escalation_record(self, state: EroskiState, escalation_type: str, contact_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Crear registro de escalación para tracking.
        
        Args:
            state: Estado actual
            escalation_type: Tipo de escalación
            contact_info: Información de contacto
            
        Returns:
            Registro de escalación
        """
        return {
            "escalation_id": f"ESC-{datetime.now().strftime('%Y%m%d%H%M%S')}-{self.escalation_count + 1}",
            "timestamp": datetime.now().isoformat(),
            "escalation_type": escalation_type,
            "source_node": state.get("current_node", "unknown"),
            "employee_email": state.get("employee_email", ""),
            "incident_store_name": state.get("incident_store_name", ""),
            "escalation_reason": state.get("escalation_reason", ""),
            "assigned_department": contact_info["department"],
            "priority": contact_info["priority"],
            "session_id": state.get("session_id", ""),
            "execution_path": state.get("execution_path", [])
        }
    
    def _generate_supervisor_response(self, context: Dict[str, Any], escalation_type: str, 
                                    contact_info: Dict[str, Any], escalation_record: Dict[str, Any]) -> str:
        """
        Generar respuesta contextual del supervisor.
        
        Args:
            context: Contexto de escalación
            escalation_type: Tipo de escalación
            contact_info: Información de contacto
            escalation_record: Registro de escalación
            
        Returns:
            Mensaje del supervisor
        """
        incident_user_name = context["employee_info"]["name"]
        escalation_id = escalation_record["escalation_id"]
        department = contact_info["department"]
        
        # Mensaje base personalizado por tipo
        if escalation_type == EscalationType.AUTHENTICATION:
            intro = f"Hola {incident_user_name}, veo que hay dificultades verificando tu identidad."
            
        elif escalation_type == EscalationType.IDENTIFICATION:
            intro = f"Hola {incident_user_name}, entiendo que no hemos logrado identificar tu problema técnico claramente."
            
        elif escalation_type == EscalationType.TECHNICAL:
            equipment = context["incident_info"]["equipment"]
            intro = f"Hola {incident_user_name}, veo que tienes problemas técnicos con {equipment}."
            
        elif escalation_type == EscalationType.TIMEOUT:
            intro = f"Hola {incident_user_name}, hemos intentado ayudarte varias veces sin éxito."
            
        else:
            intro = f"Hola {incident_user_name}, he revisado tu consulta."
        
        # Construcción del mensaje completo
        response = f"""🔥 **SUPERVISOR CONECTADO**

{intro}

📋 **Escalación registrada**: `{escalation_id}`
👥 **Derivado a**: {department}
⚡ **Prioridad**: {contact_info['priority'].upper()}

📞 **Información de contacto**:
• **Teléfono**: {contact_info['phone']}
• **Email**: {contact_info['email']}
• **Horario**: {contact_info['hours']}

🎯 **Descripción**: {contact_info['description']}

---

💡 **Próximos pasos**:
1. Recibirás contacto de {department} en breve
2. Menciona el código `{escalation_id}` para referencia
3. Para urgencias inmediatas, usa el teléfono directo

🙏 **Gracias por tu paciencia**. El equipo de {department} resolverá tu consulta lo antes posible.

---
*¿Hay algo más en lo que pueda ayudarte mientras esperas?*"""

        return response
    
    def _calculate_elapsed_time(self, state: EroskiState) -> Optional[float]:
        """Calcular tiempo transcurrido desde inicio"""
        start_time = state.get("start_time")
        if start_time:
            elapsed = datetime.now() - start_time
            return elapsed.total_seconds() / 60.0  # en minutos
        return None
    
    def _handle_supervisor_error(self, state: EroskiState, error_message: str) -> Command:
        """
        Manejar errores del supervisor con respuesta de emergencia.
        
        Args:
            state: Estado actual
            error_message: Mensaje de error
            
        Returns:
            Command con respuesta de emergencia
        """
        self.logger.error(f"💥 Error crítico en supervisor: {error_message}")
        
        emergency_response = """🚨 **ERROR DEL SISTEMA**

Lo siento, ha ocurrido un error inesperado en el sistema de escalación.

📞 **CONTACTOS DE EMERGENCIA**:
• **Soporte técnico**: +34 946 211 000
• **Supervisor tienda**: Extensión 100  
• **Email urgencias**: urgencias@eroski.es

🆔 **Código de error**: `SUP-ERROR-{timestamp}`

Por favor, contacta directamente usando estos números y menciona que el chatbot presentó un fallo técnico.

¡Disculpa las molestias!""".format(timestamp=datetime.now().strftime('%Y%m%d%H%M%S'))
        
        return Command(update={
            "messages": [AIMessage(content=emergency_response)],
            "escalation_error": True,
            "error_message": error_message,
            "emergency_contacts_provided": True,
            "flow_completed": True,
            "awaiting_user_input": False,
            "current_node": "supervisor",
            "last_activity": datetime.now()
        })
    
    def get_escalation_stats(self) -> Dict[str, Any]:
        """
        Obtener estadísticas de escalaciones (para debugging/monitoreo).
        
        Returns:
            Estadísticas de escalaciones
        """
        return {
            "total_escalations": self.escalation_count,
            "escalations_history": self.escalations_history,
            "node_name": self.name,
            "last_escalation": self.escalations_history[-1] if self.escalations_history else None
        }


# =============================================================================
# FUNCIÓN WRAPPER PARA LANGGRAPH
# =============================================================================

async def supervisor_node(state: EroskiState) -> Command:
    """
    Función wrapper para LangGraph - Nodo Supervisor
    
    Args:
        state: Estado actual como EroskiState
        
    Returns:
        Command con la respuesta del supervisor
    """
    node = SupervisorNode()
    return await node.execute(state)


# =============================================================================
# EXPORT PARA INTEGRACIÓN
# =============================================================================

__all__ = [
    "SupervisorNode", 
    "supervisor_node", 
    "EscalationType", 
    "SupervisorContactInfo"
]


# =============================================================================
# TESTING Y DEBUGGING
# =============================================================================

if __name__ == "__main__":
    """
    Test básico del nodo supervisor.
    """
    import asyncio
    from models.eroski_state import create_initial_eroski_state
    
    async def test_supervisor():
        print("🧪 Testing Supervisor Node...")
        
        # Estado de prueba con escalación
        test_state = create_initial_eroski_state("test-session")
        test_state.update({
            "escalation_needed": True,
            "escalation_reason": "Límite de intentos de identificación alcanzado (4/4)",
            "escalation_level": "supervisor",
            "current_node": "identificar_incidencia",
            "incident_user_name": "Juan Pérez",
            "employee_email": "juan.perez@eroski.es",
            "incident_store_name": "Eroski Bilbao Centro",
            "attempts": 4,
            "identification_attempts": 4
        })
        
        # Ejecutar nodo
        node = SupervisorNode()
        result = await node.execute(test_state)
        
        print("✅ Test completado:")
        print(f"📧 Mensaje generado: {len(result.update.get('messages', []))} mensajes")
        print(f"📋 ID Escalación: {result.update.get('escalation_record', {}).get('escalation_id', 'N/A')}")
        print(f"👥 Departamento: {result.update.get('escalation_contact', {}).get('department', 'N/A')}")
        
        # Mostrar respuesta completa
        if result.update.get('messages'):
            print("\n💬 Respuesta del supervisor:")
            print(result.update['messages'][-1].content)
    
    # Ejecutar test
    asyncio.run(test_supervisor())