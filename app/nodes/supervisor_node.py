# =====================================================
# nodes/supervisor_node.py - MODIFICADO CON INCIDENT MANAGER
# =====================================================
"""
Nodo supervisor con integración de IncidentManager.

CAMBIOS IMPLEMENTADOS:
- Importación de get_incident_manager
- Implementación de _get_incident_manager() 
- Implementación de _track_incident_state()
- Uso de manage_incident en execute()
- Guardado de datos de supervisión en incident_database.json
"""

from typing import Dict, Any, Optional, List, Literal
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command
from datetime import datetime
import logging

from app.models.eroski_state import EroskiState
from app.nodes.base_node import BaseNode
from app.utils.incident_manager import get_incident_manager  # 🆕 NUEVO IMPORT


# =============================================================================
# CONFIGURACIÓN DE TIPOS DE ESCALACIÓN
# =============================================================================

class EscalationType:
    """Tipos de escalación para supervisor"""
    AUTHENTICATION = "authentication"      # Problemas de autenticación
    IDENTIFICATION = "identification"      # No se pudo identificar incidencia
    TECHNICAL = "technical"                # Problemas técnicos complejos
    TIMEOUT = "timeout"                    # Timeout o máximo intentos
    SYSTEM_ERROR = "system_error"          # Errores del sistema
    USER_REQUEST = "user_request"          # Usuario solicita supervisor


class SupervisorContactInfo:
    """Información de contactos para diferentes tipos de escalación"""
    
    CONTACTS = {
        EscalationType.TECHNICAL: {
            "department": "Soporte Técnico",
            "phone": "+34 946 211 000",
            "email": "soporte.tecnico@eroski.es",
            "hours": "24/7",
            "priority": "alta",
            "description": "Problemas técnicos complejos con equipos"
        },
        EscalationType.IDENTIFICATION: {
            "department": "Supervisor Técnico",
            "phone": "+34 946 211 150",
            "email": "supervisor.tecnico@eroski.es",
            "hours": "L-V 8:00-20:00",
            "priority": "media",
            "description": "Identificación de incidencias complejas"
        },
        EscalationType.TIMEOUT: {
            "department": "Supervisor de Tienda",
            "phone": "Extensión 100",
            "email": "supervisor@tienda.eroski.es",
            "hours": "Horario de tienda",
            "priority": "media",
            "description": "Seguimiento de casos con múltiples intentos"
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
        EscalationType.USER_REQUEST: {
            "department": "Supervisor de Tienda",
            "phone": "Extensión 100",
            "email": "supervisor@tienda.eroski.es",
            "hours": "Horario de tienda",
            "priority": "media",
            "description": "Solicitud directa del usuario"
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
# NODO SUPERVISOR CON INCIDENT MANAGER
# =============================================================================

class SupervisorNode(BaseNode):
    """
    Nodo supervisor con integración de IncidentManager.
    """
    
    def __init__(self):
        super().__init__("supervisor")
        self.escalation_count = 0
        self.escalations_history = []
        self._incident_manager = None  # 🆕 NUEVO: Instancia del incident manager
        
    def get_required_fields(self) -> List[str]:
        """Campos requeridos en el estado"""
        return ["messages", "escalation_needed"]
    
    def get_actor_description(self) -> str:
        """Descripción del rol del nodo"""
        return ("Gestiono escalaciones a supervisores y personal especializado. "
                "Analizo el contexto para derivar al contacto más apropiado y "
                "proporciono información clara sobre los próximos pasos.")
    
    # =========================================================================
    # 🆕 NUEVOS MÉTODOS PARA INCIDENT MANAGER
    # =========================================================================
    
    def _get_incident_manager(self):
        """Obtener instancia singleton del incident manager"""
        if self._incident_manager is None:
            self._incident_manager = get_incident_manager()
        return self._incident_manager
    
    def _track_incident_state(self, state: dict, updates: dict = None) -> str:
        """
        🎯 HELPER METHOD: Actualizar y trackear estado de incidencia
        
        Args:
            state: Estado actual del nodo
            updates: Actualizaciones opcionales al estado
            
        Returns:
            incident_id: ID de la incidencia
        """
        try:
            # Aplicar updates si se proporcionan
            if updates:
                state = {**state, **updates}
            
            # Convertir a EroskiState si no lo es
            eroski_state = dict(state)
            
            # Trackear con incident manager
            incident_id = self._get_incident_manager().manage_incident(eroski_state)
            
            return incident_id
            
        except Exception as e:
            # No fallar si hay error en tracking
            self.logger.warning(f"⚠️ Error en incident tracking: {e}")
            return state.get("incident_id", "ERROR-TRACKING")
    
    # =========================================================================
    # MÉTODO EXECUTE MODIFICADO
    # =========================================================================
    
    async def execute(self, state: EroskiState) -> Command:
        """
        Ejecutar lógica principal del supervisor CON INCIDENT MANAGER.
        
        Args:
            state: Estado actual del workflow
            
        Returns:
            Command con respuesta del supervisor
        """
        try:
            self.logger.info("🔥 === SUPERVISOR NODE EJECUTÁNDOSE ===")
            
            # 🆕 NUEVO: Obtener o crear incident_id
            incident_id = state.get("incident_id", None)
            if not incident_id:
                incident_id = self._get_incident_manager().manage_incident(state)
            
            # Analizar contexto de escalación
            escalation_context = self._analyze_escalation_context(state)
            
            # Determinar tipo de escalación
            escalation_type = self._determine_escalation_type(escalation_context)
            
            # Obtener información de contacto apropiada
            contact_info = self._get_contact_info(escalation_type)
            
            # Registrar escalación
            escalation_record = self._create_escalation_record(state, escalation_type, contact_info)
            
            # 🆕 NUEVO: Preparar updates para incident tracking
            supervisor_updates = {
                "escalation_processed": True,
                "escalation_type": escalation_type,
                "escalation_contact": contact_info,
                "escalation_record": escalation_record,
                "supervisor_response_generated": True,
                "supervisor_assigned": True,
                "assigned_department": contact_info["department"],
                "escalacion_necesaria": True,
                "razon_escalacion": state.get("escalation_reason", f"Supervisión: {escalation_type}"),
                "estado": "supervisor_asignado",  # Estado específico para supervisión
                "contenido_solucion": f"Asignado a {contact_info['department']}",
                "timestamp_supervision": datetime.now().isoformat()
            }
            
            # 🆕 NUEVO: Trackear y guardar en incident_database.json
            incident_id = self._track_incident_state(state, supervisor_updates)
            
            # Generar respuesta contextual
            supervisor_response = self._generate_supervisor_response(
                escalation_context, escalation_type, contact_info, escalation_record
            )
            
            # Actualizar contador y historial
            self.escalation_count += 1
            self.escalations_history.append(escalation_record)
            
            self.logger.info(f"✅ Supervisión procesada: {escalation_type} → {contact_info['department']}")
            self.logger.info(f"💾 Incidencia guardada: {incident_id}")
            
            return Command(update={
                "incident_id": incident_id,  # 🆕 NUEVO: Incluir incident_id
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
    
    # =========================================================================
    # MÉTODOS DE ANÁLISIS Y PROCESAMIENTO (LÓGICA ORIGINAL MEJORADA)
    # =========================================================================
    
    def _analyze_escalation_context(self, state: EroskiState) -> Dict[str, Any]:
        """Analizar contexto completo de la escalación."""
        context = {
            "escalation_reason": state.get("escalation_reason", "No especificado"),
            "escalation_level": state.get("escalation_level", "unknown"),
            "source_node": state.get("current_node", "unknown"),
            "user_attempts": state.get("attempts", 0),
            "max_attempts": state.get("max_attempts", 3),
            "identification_attempts": state.get("identification_attempts", 0),
            "solution_attempts": state.get("solution_attempts", 0),
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
            },
            "user_requested_escalation": state.get("user_requested_escalation", False)
        }
        
        self.logger.info(f"📊 Contexto supervisión: {context['escalation_reason']}")
        self.logger.info(f"🔄 Origen: {context['source_node']} | Intentos: {context['user_attempts']}/{context['max_attempts']}")
        
        return context
    
    def _determine_escalation_type(self, context: Dict[str, Any]) -> str:
        """Determinar tipo específico de escalación basado en contexto."""
        
        # Usuario solicitó escalación directamente
        if context.get("user_requested_escalation"):
            return EscalationType.USER_REQUEST
        
        # Basado en el nodo de origen
        source_node = context["source_node"]
        
        if source_node in ["authenticate", "identificador_manual"]:
            return EscalationType.AUTHENTICATION
        elif source_node in ["identificar_incidencia", "classify"]:
            return EscalationType.IDENTIFICATION
        elif source_node == "buscar_solucion":
            # Determinar si es técnico o timeout
            solution_attempts = context.get("solution_attempts", 0)
            if solution_attempts >= 3:
                return EscalationType.TECHNICAL
            else:
                return EscalationType.TIMEOUT
        
        # Basado en el motivo de escalación
        escalation_reason = context["escalation_reason"].lower()
        
        if "error" in escalation_reason or "técnico" in escalation_reason:
            return EscalationType.SYSTEM_ERROR
        elif "intento" in escalation_reason or "máximo" in escalation_reason:
            return EscalationType.TIMEOUT
        elif "identificación" in escalation_reason or "clasificación" in escalation_reason:
            return EscalationType.IDENTIFICATION
        elif "autenticación" in escalation_reason or "empleado" in escalation_reason:
            return EscalationType.AUTHENTICATION
        
        # Por defecto
        return EscalationType.TECHNICAL
    
    def _get_contact_info(self, escalation_type: str) -> Dict[str, Any]:
        """Obtener información de contacto para el tipo de escalación"""
        return SupervisorContactInfo.CONTACTS.get(escalation_type, SupervisorContactInfo.CONTACTS["default"])
    
    def _create_escalation_record(self, state: EroskiState, escalation_type: str, contact_info: Dict[str, Any]) -> Dict[str, Any]:
        """Crear registro de escalación para tracking."""
        return {
            "escalation_id": f"SUP-{datetime.now().strftime('%Y%m%d%H%M%S')}-{self.escalation_count + 1}",
            "timestamp": datetime.now().isoformat(),
            "escalation_type": escalation_type,
            "source_node": state.get("current_node", "unknown"),
            "employee_email": state.get("employee_email", ""),
            "incident_store_name": state.get("incident_store_name", ""),
            "escalation_reason": state.get("escalation_reason", ""),
            "assigned_department": contact_info["department"],
            "priority": contact_info["priority"],
            "session_id": state.get("session_id", ""),
            "execution_path": state.get("execution_path", []),
            "incident_type": state.get("incident_type", ""),
            "solution_attempts": state.get("solution_attempts", 0),
            "identification_attempts": state.get("identification_attempts", 0)
        }
    
    def _generate_supervisor_response(self, context: Dict[str, Any], escalation_type: str, 
                                    contact_info: Dict[str, Any], escalation_record: Dict[str, Any]) -> str:
        """Generar respuesta contextual del supervisor."""
        
        incident_user_name = context["employee_info"]["name"]
        escalation_id = escalation_record["escalation_id"]
        department = contact_info["department"]
        phone = contact_info["phone"]
        email = contact_info["email"]
        hours = contact_info["hours"]
        priority = contact_info["priority"]
        
        # Mensaje base personalizado por tipo
        if escalation_type == EscalationType.AUTHENTICATION:
            intro = f"Hola {incident_user_name}, veo que hay dificultades verificando tu identidad."
            problem_context = "problemas de acceso"
            
        elif escalation_type == EscalationType.IDENTIFICATION:
            intro = f"Hola {incident_user_name}, entiendo que no hemos logrado identificar tu problema técnico claramente."
            problem_context = "identificación del problema"
            
        elif escalation_type == EscalationType.TECHNICAL:
            equipment = context["incident_info"]["equipment"]
            intro = f"Hola {incident_user_name}, veo que tienes problemas técnicos complejos."
            problem_context = f"problemas técnicos con {equipment}" if equipment != "No especificado" else "problemas técnicos"
            
        elif escalation_type == EscalationType.TIMEOUT:
            intro = f"Hola {incident_user_name}, hemos intentado ayudarte varias veces sin éxito."
            problem_context = "múltiples intentos de resolución"
            
        elif escalation_type == EscalationType.USER_REQUEST:
            intro = f"Hola {incident_user_name}, entiendo que solicitas hablar con un supervisor."
            problem_context = "solicitud de supervisión"
            
        elif escalation_type == EscalationType.SYSTEM_ERROR:
            intro = f"Hola {incident_user_name}, ha ocurrido un error técnico en el sistema."
            problem_context = "error del sistema"
            
        else:
            intro = f"Hola {incident_user_name}, te derivamos a supervisión."
            problem_context = "consulta general"
        
        # Construir mensaje completo
        supervisor_message = f"""{intro}

🎯 **Tu caso ha sido asignado:**
• **Número de caso:** {escalation_id}
• **Departamento:** {department}
• **Motivo:** {problem_context}
• **Prioridad:** {priority.upper()}

📞 **Información de contacto:**
• **Teléfono:** {phone}
• **Email:** {email}
• **Horario:** {hours}

⏱️ **Próximos pasos:**
1. Tu caso está registrado con prioridad {priority}
2. El equipo de {department} revisará tu situación
3. Te contactarán siguiendo el orden de prioridad

📋 **Información importante:**
• **Guarda este número de caso:** {escalation_id}
• Tenlo a mano cuando te contacten
• Si necesitas seguimiento urgente, menciona este número

🔧 **¿Necesitas contactar directamente?**
• Teléfono: {phone}
• Email: {email}
• Horario de atención: {hours}

¡Gracias por tu paciencia! El equipo de {department} se pondrá en contacto contigo según la prioridad asignada. 🤝"""

        return supervisor_message
    
    def _calculate_elapsed_time(self, state: EroskiState) -> float:
        """Calcular tiempo transcurrido en la sesión."""
        start_time = state.get("start_time")
        if not start_time:
            return 0.0
        
        try:
            if isinstance(start_time, str):
                start_time = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            
            elapsed = (datetime.now() - start_time).total_seconds() / 60
            return round(elapsed, 2)
        except Exception:
            return 0.0
    
    def _handle_supervisor_error(self, state: EroskiState, error_message: str) -> Command:
        """Manejar errores durante la supervisión."""
        self.logger.error(f"❌ Error en supervisión: {error_message}")
        
        # 🆕 NUEVO: Intentar guardar estado de error
        try:
            incident_id = self._track_incident_state(state, {
                "supervisor_error": True,
                "error_message": error_message,
                "estado": "error_supervision"
            })
        except:
            incident_id = state.get("incident_id", "ERROR-UNKNOWN")
        
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        
        emergency_response = f"""🚨 **ERROR DEL SISTEMA DE SUPERVISIÓN**

Ha ocurrido un problema técnico con el sistema de supervisión, pero puedes contactar directamente:

📞 **CONTACTOS DE EMERGENCIA**:
• **Soporte técnico**: +34 946 211 000
• **Supervisor tienda**: Extensión 100  
• **Email urgencias**: urgencias@eroski.es

🆔 **Código de error**: `SUP-ERROR-{timestamp}`

Por favor, contacta directamente usando estos números y menciona que el chatbot presentó un fallo técnico.

¡Disculpa las molestias!"""
        
        return Command(update={
            "incident_id": incident_id,  # 🆕 NUEVO
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
        """Obtener estadísticas de escalaciones (para debugging/monitoreo)."""
        return {
            "total_escalations": self.escalation_count,
            "escalations_history": self.escalations_history,
            "node_name": self.name,
            "last_escalation": self.escalations_history[-1] if self.escalations_history else None
        }


# =============================================================================
# FUNCIÓN WRAPPER PARA LANGGRAPH (SIN CAMBIOS)
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
# EXPORT PARA INTEGRACIÓN (SIN CAMBIOS)
# =============================================================================

__all__ = [
    "SupervisorNode", 
    "supervisor_node", 
    "EscalationType", 
    "SupervisorContactInfo"
]


# =============================================================================
# TESTING Y DEBUGGING (SIN CAMBIOS)
# =============================================================================

if __name__ == "__main__":
    """Test básico del nodo supervisor."""
    import asyncio
    from app.models.eroski_state import create_initial_eroski_state
    
    async def test_supervisor():
        print("🧪 Testing Supervisor Node con IncidentManager...")
        
        # Estado de prueba con escalación
        test_state = create_initial_eroski_state("test-session")
        test_state.update({
            "escalation_needed": True,
            "escalation_reason": "Máximo intentos alcanzado en búsqueda de solución",
            "escalation_level": "supervisor",
            "current_node": "buscar_solucion",
            "incident_user_name": "Juan Pérez",
            "employee_email": "juan.perez@eroski.es",
            "incident_store_name": "Eroski Bilbao Centro",
            "incident_type": "balanza",
            "solution_attempts": 3,
            "user_requested_escalation": False
        })
        
        # Ejecutar nodo
        node = SupervisorNode()
        result = await node.execute(test_state)
        
        print("✅ Test completado:")
        print(f"💾 Incident ID: {result.update.get('incident_id')}")
        print(f"📧 Mensaje generado: {len(result.update.get('messages', []))} mensajes")
        print(f"📋 ID Escalación: {result.update.get('escalation_record', {}).get('escalation_id', 'N/A')}")
        print(f"👥 Departamento: {result.update.get('escalation_contact', {}).get('department', 'N/A')}")
        print(f"🎯 Tipo escalación: {result.update.get('escalation_type', 'N/A')}")
        
        # Mostrar respuesta completa (primeros 200 caracteres)
        if result.update.get('messages'):
            print(f"\n💬 Respuesta del supervisor (preview):")
            print(result.update['messages'][-1].content[:200] + "...")
    
    # Ejecutar test
    asyncio.run(test_supervisor())