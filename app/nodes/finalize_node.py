# =====================================================
# nodes/finalize_node.py - MODIFICADO CON INCIDENT MANAGER
# =====================================================
"""
Nodo de finalización con integración de IncidentManager.

CAMBIOS IMPLEMENTADOS:
- Importación de get_incident_manager
- Implementación de _get_incident_manager() 
- Implementación de _track_incident_state()
- Uso de manage_incident en execute()
- Guardado de datos de finalización en incident_database.json
"""

from typing import Dict, Any, Optional, List
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command
from datetime import datetime
import logging

from app.models.eroski_state import EroskiState
from app.nodes.base_node import BaseNode
from app.utils.incident_manager import get_incident_manager  # 🆕 NUEVO IMPORT


# =============================================================================
# CONFIGURACIÓN DE TIPOS DE RESOLUCIÓN
# =============================================================================

class ResolutionType:
    """Tipos de resolución disponibles"""
    AUTOMATED = "automated"
    MANUAL_GUIDED = "manual_guided"
    KNOWLEDGE_PROVIDED = "knowledge_provided"
    PARTIAL_RESOLUTION = "partial_resolution"
    USER_SELF_RESOLVED = "user_self_resolved"
    ESCALATED_RESOLVED = "escalated_resolved"


class SatisfactionLevel:
    """Niveles de satisfacción del usuario"""
    VERY_SATISFIED = 5
    SATISFIED = 4
    NEUTRAL = 3
    DISSATISFIED = 2
    VERY_DISSATISFIED = 1


# =============================================================================
# NODO DE FINALIZACIÓN CON INCIDENT MANAGER
# =============================================================================

class FinalizeNode(BaseNode):
    """
    Nodo de finalización con integración de IncidentManager.
    """
    
    def __init__(self):
        super().__init__("finalize")
        self.resolutions_count = 0
        self.resolution_history = []
        self._incident_manager = None  # 🆕 NUEVO: Instancia del incident manager
        
    def get_required_fields(self) -> List[str]:
        """Campos requeridos en el estado"""
        return ["messages", "resolved"]
    
    def get_actor_description(self) -> str:
        """Descripción del rol del nodo"""
        return ("Finalizo incidencias resueltas exitosamente. "
                "Confirmo la resolución con el usuario, recopilo feedback "
                "y cierro la sesión de forma ordenada.")
    
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
        Ejecutar lógica principal de finalización CON INCIDENT MANAGER.
        
        Args:
            state: Estado actual del workflow
            
        Returns:
            Command con mensaje de finalización
        """
        try:
            self.logger.info("🎯 === FINALIZE NODE EJECUTÁNDOSE ===")
            
            # 🆕 NUEVO: Obtener o crear incident_id
            incident_id = state.get("incident_id", None)
            if not incident_id:
                incident_id = self._get_incident_manager().manage_incident(state)
            
            # Analizar contexto de resolución
            resolution_context = self._analyze_resolution_context(state)
            
            # Determinar tipo de resolución
            resolution_type = self._determine_resolution_type(resolution_context)
            
            # Calcular métricas de la sesión
            session_metrics = self._calculate_session_metrics(state)
            
            # Crear registro de finalización
            finalization_record = self._create_finalization_record(state, resolution_type, session_metrics)
            
            # 🆕 NUEVO: Preparar updates para incident tracking
            incident_updates = {
                "resolved": True,
                "resolution_type": resolution_type,
                "session_metrics": session_metrics,
                "finalization_record": finalization_record,
                "finalization_processed": True,
                "flow_completed": True,
                "session_closed": True,
                "end_time": datetime.now(),
                "estado": "resuelta",  # Estado para incident_database.json
                "contenido_solucion": f"Finalización {resolution_type}",
                "timestamp_cierre": datetime.now().isoformat()
            }
            
            # 🆕 NUEVO: Trackear y guardar en incident_database.json
            incident_id = self._track_incident_state(state, incident_updates)
            
            # Generar mensaje de cierre contextual
            finalization_message = self._generate_finalization_message(
                resolution_context, resolution_type, session_metrics, finalization_record
            )
            
            # Actualizar contador y historial
            self.resolutions_count += 1
            self.resolution_history.append(finalization_record)
            
            self.logger.info(f"✅ Finalización procesada: {resolution_type} | Tiempo: {session_metrics['resolution_time_minutes']:.1f}min")
            self.logger.info(f"💾 Incidencia guardada: {incident_id}")
            
            return Command(update={
                "incident_id": incident_id,  # 🆕 NUEVO: Incluir incident_id
                "messages": [AIMessage(content=finalization_message)],
                "finalization_processed": True,
                "resolution_type": resolution_type,
                "session_metrics": session_metrics,
                "finalization_record": finalization_record,
                "finalization_message_generated": True,
                "flow_completed": True,
                "session_closed": True,
                "awaiting_user_input": False,
                "current_node": "finalize",
                "end_time": datetime.now(),
                "last_activity": datetime.now()
            })
            
        except Exception as e:
            self.logger.error(f"❌ Error en finalize node: {e}")
            return self._handle_finalization_error(state, str(e))
    
    # =========================================================================
    # MÉTODOS DE ANÁLISIS Y PROCESAMIENTO (MANTIENEN LÓGICA ORIGINAL)
    # =========================================================================
    
    def _analyze_resolution_context(self, state: EroskiState) -> Dict[str, Any]:
        """Analizar contexto completo de la resolución."""
        return {
            "resolved": state.get("resolved", False),
            "solution_found": state.get("solution_found", False),
            "solution_type": state.get("solution_type", "unknown"),
            "incident_type": state.get("incident_type", "unknown"),
            "automated_resolution": state.get("automated_resolution", False),
            "escalation_used": state.get("escalation_processed", False),
            "user_satisfaction": state.get("satisfaction_score"),
            "attempts_made": state.get("attempts", 0),
            "identification_attempts": state.get("identification_attempts", 0)
        }
    
    def _determine_resolution_type(self, context: Dict[str, Any]) -> str:
        """Determinar tipo de resolución basado en el contexto."""
        if context["automated_resolution"]:
            return ResolutionType.AUTOMATED
        elif context["escalation_used"]:
            return ResolutionType.ESCALATED_RESOLVED
        elif context["solution_found"]:
            return ResolutionType.MANUAL_GUIDED
        elif context["attempts_made"] > 1:
            return ResolutionType.PARTIAL_RESOLUTION
        else:
            return ResolutionType.USER_SELF_RESOLVED
    
    def _calculate_session_metrics(self, state: EroskiState) -> Dict[str, Any]:
        """Calcular métricas de la sesión."""
        start_time = state.get("start_time")
        end_time = datetime.now()
        
        resolution_time = 0
        if start_time:
            if isinstance(start_time, str):
                start_time = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            elif isinstance(start_time, datetime):
                pass
            else:
                start_time = datetime.now()
            
            resolution_time = (end_time - start_time).total_seconds() / 60
        
        execution_path = state.get("execution_path", [])
        nodes_visited = len(execution_path)
        
        return {
            "resolution_time_minutes": round(resolution_time, 2),
            "nodes_visited": nodes_visited,
            "attempts_total": state.get("attempts", 0),
            "identification_attempts": state.get("identification_attempts", 0),
            "efficiency_rating": self._calculate_efficiency_rating(resolution_time, nodes_visited),
            "start_time": start_time.isoformat() if start_time else None,
            "end_time": end_time.isoformat(),
            "execution_path": execution_path
        }
    
    def _calculate_efficiency_rating(self, resolution_time: float, nodes_visited: int) -> str:
        """Calcular rating de eficiencia."""
        if resolution_time <= 3 and nodes_visited <= 4:
            return "excellent"
        elif resolution_time <= 10 and nodes_visited <= 6:
            return "good"
        elif resolution_time <= 20 and nodes_visited <= 8:
            return "acceptable"
        else:
            return "needs_improvement"
    
    def _create_finalization_record(self, state: EroskiState, resolution_type: str, 
                                  session_metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Crear registro de finalización para tracking."""
        return {
            "finalization_id": f"FIN-{datetime.now().strftime('%Y%m%d%H%M%S')}-{self.resolutions_count + 1}",
            "timestamp": datetime.now().isoformat(),
            "resolution_type": resolution_type,
            "session_metrics": session_metrics,
            "employee_info": {
                "email": state.get("employee_email", ""),
                "name": state.get("incident_user_name", ""),
                "store": state.get("incident_store_name", ""),
                "department": state.get("incident_department", "")
            },
            "incident_info": {
                "code": state.get("incident_code", ""),
                "type": state.get("incident_type", ""),
                "description": state.get("incident_description", "")[:100] + "..." if len(state.get("incident_description", "")) > 100 else state.get("incident_description", "")
            },
            "resolution_details": {
                "solution_type": state.get("solution_type", ""),
                "automated": state.get("automated_resolution", False),
                "satisfaction": state.get("satisfaction_score"),
                "success_confirmed": state.get("resolved", False)
            }
        }
    
    def _generate_finalization_message(self, context: Dict[str, Any], resolution_type: str,
                                     session_metrics: Dict[str, Any], finalization_record: Dict[str, Any]) -> str:
        """Generar mensaje de finalización contextual."""
        
        # Datos básicos
        user_name = context.get("employee_info", {}).get("name", "")
        resolution_time = session_metrics["resolution_time_minutes"]
        
        # Mensaje base según tipo de resolución
        if resolution_type == ResolutionType.AUTOMATED:
            base_message = f"🎉 ¡Perfecto{', ' + user_name if user_name else ''}! Tu problema se resolvió automáticamente."
        elif resolution_type == ResolutionType.MANUAL_GUIDED:
            base_message = f"✅ ¡Genial{', ' + user_name if user_name else ''}! Hemos encontrado una solución para tu problema."
        elif resolution_type == ResolutionType.ESCALATED_RESOLVED:
            base_message = f"🤝 Perfecto{', ' + user_name if user_name else ''}! Tu problema fue resuelto con ayuda especializada."
        else:
            base_message = f"👍 ¡Excelente{', ' + user_name if user_name else ''}! Tu consulta ha sido atendida."
        
        # Información de seguimiento
        follow_up = """

📋 **Resumen de tu sesión:**
• Problema resuelto exitosamente
• Tiempo de resolución: {:.1f} minutos
• Todo está registrado en nuestro sistema

🔧 **¿Necesitas algo más?**
• Puedes contactarnos nuevamente cuando quieras
• Tu información de empleado está guardada para futuras consultas

¡Que tengas un excelente día de trabajo! 😊""".format(resolution_time)
        
        return base_message + follow_up
    
    def _handle_finalization_error(self, state: EroskiState, error_message: str) -> Command:
        """Manejar errores durante la finalización."""
        self.logger.error(f"❌ Error en finalización: {error_message}")
        
        error_response = """❌ **Error de Sistema**

Ha ocurrido un problema técnico durante la finalización de tu consulta.

**No te preocupes:**
• Tu problema ha sido registrado en nuestro sistema
• Un supervisor revisará tu caso
• Te contactaremos si necesitamos información adicional

**Si necesitas ayuda inmediata:**
📞 Contacta con tu supervisor de tienda
📧 Email: soporte.tecnico@eroski.es

¡Disculpa las molestias técnicas! 🙏"""
        
        # 🆕 NUEVO: Intentar guardar estado de error
        try:
            incident_id = self._track_incident_state(state, {
                "finalization_error": True,
                "error_message": error_message,
                "estado": "error_finalizacion"
            })
        except:
            incident_id = state.get("incident_id", "ERROR-UNKNOWN")
        
        return Command(update={
            "incident_id": incident_id,  # 🆕 NUEVO
            "messages": [AIMessage(content=error_response)],
            "finalization_error": True,
            "error_message": error_message,
            "flow_completed": True,
            "session_closed": True,
            "awaiting_user_input": False,
            "current_node": "finalize",
            "last_activity": datetime.now()
        })


# =============================================================================
# FUNCIÓN WRAPPER PARA LANGGRAPH (SIN CAMBIOS)
# =============================================================================

async def finalize_node(state: EroskiState) -> Command:
    """
    Función wrapper para LangGraph - Nodo de Finalización
    
    Args:
        state: Estado actual como EroskiState
        
    Returns:
        Command con la respuesta de finalización
    """
    node = FinalizeNode()
    return await node.execute(state)


# =============================================================================
# EXPORT PARA INTEGRACIÓN (SIN CAMBIOS)
# =============================================================================

__all__ = [
    "FinalizeNode",
    "finalize_node", 
    "ResolutionType",
    "SatisfactionLevel"
]