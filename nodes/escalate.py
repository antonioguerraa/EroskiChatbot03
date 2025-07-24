# =====================================================
# nodes/escalate.py - MODIFICADO CON INCIDENT MANAGER
# =====================================================
"""
Nodo de escalación con integración de IncidentManager.

CAMBIOS IMPLEMENTADOS:
- Importación de get_incident_manager
- Implementación de _get_incident_manager() 
- Implementación de _track_incident_state()
- Uso de manage_incident en execute()
- Guardado de datos de escalación en incident_database.json
"""

from typing import Dict, Any, Optional, List
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command
from datetime import datetime
import logging

from models.eroski_state import EroskiState
from nodes.base_node import BaseNode
from utils.incident_manager import get_incident_manager  # 🆕 NUEVO IMPORT


# =============================================================================
# CONFIGURACIÓN DE ESCALACIÓN
# =============================================================================

class EscalationType:
    """Tipos de escalación disponibles"""
    TECHNICAL = "technical"
    SUPERVISOR = "supervisor"
    IT_SUPPORT = "it_support"
    EMERGENCY = "emergency"
    TRAINING = "training"
    ADMINISTRATIVE = "administrative"


# =============================================================================
# NODO DE ESCALACIÓN CON INCIDENT MANAGER
# =============================================================================

class EscalateToSupervisorNode(BaseNode):
    """
    Nodo para escalación a supervisor o soporte técnico con IncidentManager.
    """
    
    def __init__(self):
        super().__init__("EscalateToSupervisor")
        self._incident_manager = None  # 🆕 NUEVO: Instancia del incident manager
        
        # Contactos de escalación por tipo
        self.escalation_contacts = {
            EscalationType.TECHNICAL: {
                "name": "Soporte Técnico",
                "phone": "+34 946 211 000",
                "email": "soporte.tecnico@eroski.es",
                "hours": "24/7",
                "priority": "alta",
                "department": "Soporte Técnico"
            },
            EscalationType.SUPERVISOR: {
                "name": "Supervisor de Tienda",
                "phone": "Ext. 100",
                "email": "supervisor@tienda.eroski.es",
                "hours": "Horario de tienda",
                "priority": "media",
                "department": "Supervisión"
            },
            EscalationType.IT_SUPPORT: {
                "name": "Soporte IT",
                "phone": "+34 946 211 200",
                "email": "it.support@eroski.es",
                "hours": "L-V 8:00-20:00",
                "priority": "alta",
                "department": "IT Support"
            },
            EscalationType.EMERGENCY: {
                "name": "Emergencias",
                "phone": "112",
                "email": "emergency@eroski.es",
                "hours": "24/7",
                "priority": "crítica",
                "department": "Emergencias"
            }
        }
    
    def get_required_fields(self) -> List[str]:
        """Campos requeridos en el estado"""
        return ["messages"]
    
    def get_actor_description(self) -> str:
        """Descripción del rol del nodo"""
        return ("Escalo problemas que no pueden resolverse automáticamente. "
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
        Ejecutar lógica principal de escalación CON INCIDENT MANAGER.
        
        Args:
            state: Estado actual del workflow
            
        Returns:
            Command con la escalación procesada
        """
        try:
            self.logger.info("🔥 === ESCALATE NODE EJECUTÁNDOSE ===")
            
            # 🆕 NUEVO: Obtener o crear incident_id
            incident_id = state.get("incident_id", None)
            if not incident_id:
                incident_id = self._get_incident_manager().manage_incident(state)
            
            # Determinar tipo de escalación
            escalation_type = self._determine_escalation_type(state)
            
            # Obtener contacto apropiado
            contact_info = self._get_contact_info(escalation_type)
            
            # Crear ticket de escalación
            ticket_info = self._create_escalation_ticket(state, escalation_type)
            
            # 🆕 NUEVO: Preparar updates para incident tracking
            escalation_updates = {
                "escalation_processed": True,
                "escalation_type": escalation_type,
                "escalation_contact": contact_info,
                "escalation_ticket": ticket_info,
                "escalacion_necesaria": True,
                "razon_escalacion": state.get("escalation_reason", f"Escalado a {escalation_type}"),
                "estado": "escalada",  # Estado para incident_database.json
                "contenido_solucion": f"Escalado a {contact_info['department']}",
                "timestamp_escalacion": datetime.now().isoformat()
            }
            
            # 🆕 NUEVO: Trackear y guardar en incident_database.json
            incident_id = self._track_incident_state(state, escalation_updates)
            
            # Notificar escalación (futuro: integración con sistema externo)
            # await self._notify_escalation(ticket_info, contact_info)
            
            # Proporcionar información al usuario
            escalation_message = self._provide_escalation_info(contact_info, ticket_info)
            
            self.logger.info(f"✅ Escalación procesada: {escalation_type} → {contact_info['department']}")
            self.logger.info(f"💾 Incidencia guardada: {incident_id}")
            
            return Command(update={
                "incident_id": incident_id,  # 🆕 NUEVO: Incluir incident_id
                "messages": [AIMessage(content=escalation_message)],
                "escalation_processed": True,
                "escalation_type": escalation_type,
                "escalation_contact": contact_info,
                "escalation_ticket": ticket_info,
                "flow_completed": True,
                "awaiting_user_input": False,
                "current_node": "escalate",
                "last_activity": datetime.now()
            })
            
        except Exception as e:
            self.logger.error(f"❌ Error en escalación: {e}")
            return self._provide_emergency_contacts(state)
    
    # =========================================================================
    # MÉTODOS DE PROCESAMIENTO (LÓGICA ORIGINAL MEJORADA)
    # =========================================================================
    
    def _determine_escalation_type(self, state: EroskiState) -> str:
        """Determinar tipo de escalación basado en el contexto"""
        
        # Verificar si hay nivel de escalación específico
        escalation_level = state.get("escalation_level")
        if escalation_level and escalation_level in self.escalation_contacts:
            return escalation_level
        
        # Determinar basado en equipos mencionados
        affected_equipment = state.get("affected_equipment", "").lower()
        incident_description = state.get("incident_description", "").lower()
        incident_type = state.get("incident_type", "").lower()
        
        # Palabras clave para escalación técnica
        technical_keywords = ["tpv", "pos", "balanza", "impresora", "scanner", "red", "wifi", "internet"]
        if any(keyword in affected_equipment or keyword in incident_description or keyword in incident_type 
               for keyword in technical_keywords):
            return EscalationType.TECHNICAL
        
        # Palabras clave para IT
        it_keywords = ["ordenador", "computadora", "sistema", "software", "aplicación", "programa"]
        if any(keyword in affected_equipment or keyword in incident_description 
               for keyword in it_keywords):
            return EscalationType.IT_SUPPORT
        
        # Emergencias
        emergency_keywords = ["emergencia", "urgente", "peligro", "accidente", "fuego", "robo"]
        if any(keyword in incident_description for keyword in emergency_keywords):
            return EscalationType.EMERGENCY
        
        # Por defecto: supervisor
        return EscalationType.SUPERVISOR
    
    def _get_contact_info(self, escalation_type: str) -> Dict[str, Any]:
        """Obtener información de contacto para el tipo de escalación"""
        return self.escalation_contacts.get(escalation_type, self.escalation_contacts[EscalationType.SUPERVISOR])
    
    def _create_escalation_ticket(self, state: EroskiState, escalation_type: str) -> Dict[str, Any]:
        """Crear ticket de escalación"""
        ticket_id = f"ESC-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        return {
            "ticket_id": ticket_id,
            "created_at": datetime.now().isoformat(),
            "escalation_type": escalation_type,
            "priority": self.escalation_contacts[escalation_type]["priority"],
            "employee_info": {
                "name": state.get("incident_user_name", "No identificado"),
                "email": state.get("employee_email", ""),
                "store": state.get("incident_store_name", ""),
                "department": state.get("incident_department", "")
            },
            "incident_info": {
                "type": state.get("incident_type", ""),
                "description": state.get("incident_description", ""),
                "affected_equipment": state.get("affected_equipment", "")
            },
            "escalation_reason": state.get("escalation_reason", "Escalación automática"),
            "session_id": state.get("session_id", "")
        }
    
    def _provide_escalation_info(self, contact_info: Dict[str, Any], ticket_info: Dict[str, Any]) -> str:
        """Proporcionar información de escalación al usuario"""
        
        ticket_id = ticket_info["ticket_id"]
        department = contact_info["department"]
        contact_name = contact_info["name"]
        phone = contact_info["phone"]
        email = contact_info["email"]
        hours = contact_info["hours"]
        priority = contact_info["priority"]
        
        escalation_message = f"""🎯 **Tu consulta ha sido escalada**

📋 **Información del ticket:**
• **Número de ticket:** {ticket_id}
• **Asignado a:** {department}
• **Prioridad:** {priority.upper()}

📞 **Información de contacto:**
• **Contacto:** {contact_name}
• **Teléfono:** {phone}
• **Email:** {email}
• **Horario:** {hours}

⏱️ **Próximos pasos:**
1. Tu consulta ha sido registrada con prioridad {priority}
2. El equipo de {department} revisará tu caso
3. Te contactarán en breve para dar seguimiento

📋 **Información importante:**
• Guarda este número de ticket: **{ticket_id}**
• Tenlo a mano cuando te contacten
• Si necesitas hacer seguimiento, menciona este número

🔧 **¿Necesitas contactar directamente?**
• Teléfono: {phone}
• Email: {email}
• Horario de atención: {hours}

¡Gracias por tu paciencia! El equipo especializado se pondrá en contacto contigo pronto. 🤝"""
        
        return escalation_message
    
    def _provide_emergency_contacts(self, state: EroskiState) -> Command:
        """Proporcionar contactos de emergencia cuando falla la escalación"""
        
        # 🆕 NUEVO: Intentar guardar estado de error
        try:
            incident_id = self._track_incident_state(state, {
                "escalation_failed": True,
                "escalation_type": "emergency",
                "estado": "error_escalacion",
                "razon_escalacion": "Error técnico en escalación"
            })
        except:
            incident_id = state.get("incident_id", "ERROR-UNKNOWN")
        
        emergency_message = """🚨 **CONTACTOS DE EMERGENCIA**

Ha ocurrido un problema técnico con el sistema de escalación, pero puedes contactar directamente:

📞 **Contactos Inmediatos:**

🔧 **Soporte Técnico (24/7):**
• Teléfono: +34 946 211 000
• Email: soporte.tecnico@eroski.es
• Para: Problemas con TPV, impresoras, scanners

👨‍💼 **Supervisor de Tienda:**
• Teléfono: Ext. 100 (desde teléfono de tienda)
• Para: Consultas generales, procedimientos

💻 **Soporte IT:**
• Teléfono: +34 946 211 200
• Email: it.support@eroski.es
• Horario: L-V 8:00-20:00
• Para: Problemas de red, ordenadores, sistemas

🏥 **Emergencias:**
• Teléfono: 112
• Para: Emergencias médicas o de seguridad

📋 **Información a proporcionar:**
• Tu nombre y número de empleado
• Código de tienda
• Descripción del problema
• Ubicación exacta

¡Disculpa las molestias técnicas! 🙏"""
        
        return Command(update={
            "incident_id": incident_id,  # 🆕 NUEVO
            "escalation_processed": True,
            "escalation_type": "emergency",
            "escalation_failed": True,
            "messages": [AIMessage(content=emergency_message)],
            "current_node": "escalate",
            "last_activity": datetime.now(),
            "awaiting_user_input": False,
            "flow_completed": True
        })
    
    async def _notify_escalation(self, ticket_info: Dict[str, Any], 
                               contact_info: Dict[str, Any]) -> bool:
        """
        Notificar escalación al equipo correspondiente.
        
        TODO: Implementar integración con sistema externo
        - Email automático
        - Notificación SMS
        - Integración con sistema de tickets
        """
        try:
            # Placeholder para integración futura
            self.logger.info(f"📧 Notificación de escalación enviada para ticket {ticket_info['ticket_id']}")
            return True
        except Exception as e:
            self.logger.error(f"❌ Error enviando notificación: {e}")
            return False


# =============================================================================
# FUNCIÓN WRAPPER PARA LANGGRAPH (SIN CAMBIOS)
# =============================================================================

async def escalate_supervisor_node(state: EroskiState) -> Command:
    """
    Wrapper function para el nodo de escalación.
    
    Args:
        state: Estado actual del workflow
        
    Returns:
        Command con la actualización de estado
    """
    node = EscalateToSupervisorNode()
    return await node.execute(state)


# =============================================================================
# EXPORT PARA INTEGRACIÓN (SIN CAMBIOS)
# =============================================================================

__all__ = [
    "EscalateToSupervisorNode",
    "escalate_supervisor_node",
    "EscalationType"
]