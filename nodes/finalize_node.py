# =====================================================
# nodes/finalize_node.py - Nodo de Finalización y Cierre
# =====================================================
"""
Nodo mock para finalización exitosa de incidencias resueltas.

RESPONSABILIDADES FUTURAS:
- Confirmar resolución exitosa con el usuario
- Recopilar feedback y satisfacción del usuario
- Actualizar sistemas de tickets/incidencias
- Generar métricas de resolución
- Cerrar sesión de forma ordenada
- Ofrecer servicios adicionales

ESTADO ACTUAL:
- Implementación dummy/mock siguiendo estructura del proyecto
- Análisis de resolución basado en el estado
- Respuestas contextuales según tipo de solución
- Registro de métricas básicas para análisis
- Preparado para integración de sistemas externos
"""

from typing import Dict, Any, Optional, List
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command
from datetime import datetime
import logging

from models.eroski_state import EroskiState
from nodes.base_node import BaseNode


# =============================================================================
# CONFIGURACIÓN DE TIPOS DE RESOLUCIÓN
# =============================================================================

class ResolutionType:
    """Tipos de resolución disponibles"""
    AUTOMATED = "automated"                     # Solución automática aplicada
    MANUAL_GUIDED = "manual_guided"            # Usuario siguió pasos manuales
    KNOWLEDGE_PROVIDED = "knowledge_provided"   # Se proporcionó información
    PARTIAL_RESOLUTION = "partial_resolution"  # Resolución parcial
    USER_SELF_RESOLVED = "user_self_resolved"  # Usuario resolvió por sí mismo
    ESCALATED_RESOLVED = "escalated_resolved"  # Resuelto tras escalación


class SatisfactionLevel:
    """Niveles de satisfacción del usuario"""
    VERY_SATISFIED = 5
    SATISFIED = 4
    NEUTRAL = 3
    DISSATISFIED = 2
    VERY_DISSATISFIED = 1


# =============================================================================
# NODO DE FINALIZACIÓN PRINCIPAL
# =============================================================================

class FinalizeNode(BaseNode):
    """
    Nodo de finalización mock para cerrar incidencias resueltas exitosamente.
    
    DISEÑO:
    - Analiza el contexto de resolución del estado
    - Genera mensaje de cierre contextual y personalizado
    - Recopila métricas de la sesión
    - Proporciona información de contacto futuro
    - Cierra la sesión de forma ordenada
    
    PREPARADO PARA:
    - Integración con sistemas de tickets
    - Recopilación de feedback del usuario
    - Análisis de satisfacción automático
    - Métricas de tiempo de resolución
    - Notificaciones de cierre a supervisores
    """
    
    def __init__(self):
        super().__init__("finalize")
        self.resolutions_count = 0
        self.resolution_history = []
        
    def get_required_fields(self) -> List[str]:
        """Campos requeridos en el estado"""
        return ["messages", "resolved"]
    
    def get_actor_description(self) -> str:
        """Descripción del rol del nodo"""
        return ("Finalizo incidencias resueltas exitosamente. "
                "Confirmo la resolución con el usuario, recopilo feedback "
                "y cierro la sesión de forma ordenada.")
    
    async def execute(self, state: EroskiState) -> Command:
        """
        Ejecutar lógica principal de finalización.
        
        Args:
            state: Estado actual del workflow
            
        Returns:
            Command con mensaje de finalización
        """
        try:
            self.logger.info("🎯 === FINALIZE NODE EJECUTÁNDOSE ===")
            
            # Analizar contexto de resolución
            resolution_context = self._analyze_resolution_context(state)
            
            # Determinar tipo de resolución
            resolution_type = self._determine_resolution_type(resolution_context)
            
            # Calcular métricas de la sesión
            session_metrics = self._calculate_session_metrics(state)
            
            # Crear registro de finalización
            finalization_record = self._create_finalization_record(state, resolution_type, session_metrics)
            
            # Generar mensaje de cierre contextual
            finalization_message = self._generate_finalization_message(
                resolution_context, resolution_type, session_metrics, finalization_record
            )
            
            # Actualizar contador y historial
            self.resolutions_count += 1
            self.resolution_history.append(finalization_record)
            
            self.logger.info(f"✅ Finalización procesada: {resolution_type} | Tiempo: {session_metrics['resolution_time_minutes']:.1f}min")
            
            return Command(update={
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
    
    def _analyze_resolution_context(self, state: EroskiState) -> Dict[str, Any]:
        """
        Analizar contexto completo de la resolución.
        
        Args:
            state: Estado actual
            
        Returns:
            Diccionario con contexto analizado
        """
        context = {
            "resolution_confirmed": state.get("resolved", False),
            "solution_found": state.get("solution_found", False),
            "solution_type": state.get("solution_type", "unknown"),
            "solution_content": state.get("solution_content", ""),
            "satisfaction_score": state.get("satisfaction_score"),
            "automated_resolution": state.get("automated_resolution", False),
            "user_info": {
                "name": state.get("employee_name", "Usuario"),
                "email": state.get("employee_email", "No proporcionado"),
                "store": state.get("store_name", "No identificada"),
                "department": state.get("incident_department", "No especificado")
            },
            "incident_info": {
                "type": state.get("incident_type", "No identificado"),
                "description": state.get("incident_description", "No proporcionada"),
                "code": state.get("incident_code", "No asignado"),
                "equipment": state.get("affected_equipment", "No especificado")
            },
            "process_info": {
                "session_id": state.get("session_id", "unknown"),
                "execution_path": state.get("execution_path", []),
                "total_attempts": state.get("attempts", 0),
                "identification_attempts": state.get("identification_attempts", 0),
                "error_count": state.get("error_count", 0),
                "start_time": state.get("start_time"),
                "messages_count": len(state.get("messages", []))
            }
        }
        
        self.logger.info(f"🎯 Resolución confirmada: {context['resolution_confirmed']}")
        self.logger.info(f"🔧 Tipo solución: {context['solution_type']}")
        self.logger.info(f"🤖 Automatizada: {context['automated_resolution']}")
        
        return context
    
    def _determine_resolution_type(self, context: Dict[str, Any]) -> str:
        """
        Determinar tipo específico de resolución basado en contexto.
        
        Args:
            context: Contexto analizado
            
        Returns:
            Tipo de resolución
        """
        if context["automated_resolution"]:
            return ResolutionType.AUTOMATED
        
        elif context["solution_type"] in ["manual", "step_by_step"]:
            return ResolutionType.MANUAL_GUIDED
        
        elif context["solution_type"] in ["information", "knowledge"]:
            return ResolutionType.KNOWLEDGE_PROVIDED
        
        elif context["satisfaction_score"] and context["satisfaction_score"] < 4:
            return ResolutionType.PARTIAL_RESOLUTION
        
        elif "usuario resolvió" in str(context["solution_content"]).lower():
            return ResolutionType.USER_SELF_RESOLVED
        
        elif context["process_info"]["error_count"] > 0:
            return ResolutionType.ESCALATED_RESOLVED
        
        else:
            return ResolutionType.MANUAL_GUIDED  # Default
    
    def _calculate_session_metrics(self, state: EroskiState) -> Dict[str, Any]:
        """
        Calcular métricas completas de la sesión.
        
        Args:
            state: Estado actual
            
        Returns:
            Diccionario con métricas
        """
        start_time = state.get("start_time")
        end_time = datetime.now()
        
        resolution_time_minutes = 0.0
        if start_time:
            resolution_time_minutes = (end_time - start_time).total_seconds() / 60.0
        
        execution_path = state.get("execution_path", [])
        
        return {
            "session_id": state.get("session_id", "unknown"),
            "resolution_time_minutes": round(resolution_time_minutes, 2),
            "nodes_visited": len(execution_path),
            "execution_path": execution_path,
            "messages_exchanged": len(state.get("messages", [])),
            "total_attempts": state.get("attempts", 0),
            "identification_attempts": state.get("identification_attempts", 0),
            "errors_encountered": state.get("error_count", 0),
            "automated_resolution": state.get("automated_resolution", False),
            "satisfaction_score": state.get("satisfaction_score"),
            "start_time": start_time.isoformat() if start_time else None,
            "end_time": end_time.isoformat(),
            "efficiency_rating": self._calculate_efficiency_rating(resolution_time_minutes, len(execution_path))
        }
    
    def _calculate_efficiency_rating(self, resolution_time: float, nodes_visited: int) -> str:
        """
        Calcular rating de eficiencia del proceso.
        
        Args:
            resolution_time: Tiempo de resolución en minutos
            nodes_visited: Número de nodos visitados
            
        Returns:
            Rating de eficiencia
        """
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
        """
        Crear registro de finalización para tracking.
        
        Args:
            state: Estado actual
            resolution_type: Tipo de resolución
            session_metrics: Métricas de la sesión
            
        Returns:
            Registro de finalización
        """
        return {
            "finalization_id": f"FIN-{datetime.now().strftime('%Y%m%d%H%M%S')}-{self.resolutions_count + 1}",
            "timestamp": datetime.now().isoformat(),
            "resolution_type": resolution_type,
            "session_metrics": session_metrics,
            "employee_info": {
                "email": state.get("employee_email", ""),
                "name": state.get("employee_name", ""),
                "store": state.get("store_name", ""),
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
        """
        Generar mensaje de finalización contextual.
        
        Args:
            context: Contexto de resolución
            resolution_type: Tipo de resolución
            session_metrics: Métricas de la sesión
            finalization_record: Registro de finalización
            
        Returns:
            Mensaje de finalización
        """
        user_name = context["user_info"]["name"]
        incident_code = context["incident_info"]["code"]
        incident_type = context["incident_info"]["type"]
        resolution_time = session_metrics["resolution_time_minutes"]
        efficiency_rating = session_metrics["efficiency_rating"]
        finalization_id = finalization_record["finalization_id"]
        
        # Mensaje personalizado según tipo de resolución
        if resolution_type == ResolutionType.AUTOMATED:
            resolution_desc = "se ha resuelto automáticamente"
            emoji = "🤖"
        elif resolution_type == ResolutionType.MANUAL_GUIDED:
            resolution_desc = "se ha resuelto siguiendo los pasos proporcionados"
            emoji = "🔧"
        elif resolution_type == ResolutionType.KNOWLEDGE_PROVIDED:
            resolution_desc = "se ha proporcionado la información solicitada"
            emoji = "📚"
        elif resolution_type == ResolutionType.USER_SELF_RESOLVED:
            resolution_desc = "has logrado resolverlo por ti mismo"
            emoji = "💪"
        else:
            resolution_desc = "se ha resuelto exitosamente"
            emoji = "✅"
        
        # Mensaje de eficiencia
        if efficiency_rating == "excellent":
            efficiency_msg = "¡Ha sido muy rápido y eficiente!"
        elif efficiency_rating == "good":
            efficiency_msg = "El proceso ha sido eficiente."
        elif efficiency_rating == "acceptable":
            efficiency_msg = "Hemos logrado resolverlo sin complicaciones."
        else:
            efficiency_msg = "Aunque ha tomado tiempo, lo hemos resuelto."
        
        # Construcción del mensaje completo
        message = f"""{emoji} **¡INCIDENCIA RESUELTA EXITOSAMENTE!**

Hola **{user_name}**, me complace confirmar que tu problema con **{incident_type}** {resolution_desc}.

📋 **Resumen de la sesión:**
• **Código incidencia**: `{incident_code}`
• **Tiempo de resolución**: {resolution_time:.1f} minutos
• **Tipo de solución**: {resolution_type.replace('_', ' ').title()}
• **Eficiencia**: {efficiency_msg}

---

💡 **Para futuras consultas:**
• Menciona el código `{incident_code}` si necesitas referencias
• Contacta al soporte técnico: **+34 946 211 000**
• Email soporte: **soporte.tecnico@eroski.es**

📊 **Tu feedback es importante:**
Si tienes unos segundos, nos ayudaría mucho conocer tu experiencia para mejorar nuestro servicio.

---

🙏 **¡Gracias por usar el chatbot de soporte de Eroski!**

*ID de finalización: `{finalization_id}` | {datetime.now().strftime('%d/%m/%Y %H:%M')}*

¿Hay algo más en lo que pueda ayudarte hoy?"""

        return message
    
    def _handle_finalization_error(self, state: EroskiState, error_message: str) -> Command:
        """
        Manejar errores durante la finalización.
        
        Args:
            state: Estado actual
            error_message: Mensaje de error
            
        Returns:
            Command con respuesta de error
        """
        self.logger.error(f"💥 Error en finalización: {error_message}")
        
        user_name = state.get("employee_name", "Usuario")
        incident_code = state.get("incident_code", "No disponible")
        
        error_response = f"""⚠️ **FINALIZACIÓN CON INCIDENCIAS**

Hola **{user_name}**, aunque tu problema se ha resuelto, ha ocurrido un error menor en el sistema de finalización.

📋 **Tu incidencia ha sido resuelta correctamente:**
• **Código**: `{incident_code}`
• **Estado**: Resuelto exitosamente

📞 **Si necesitas un comprobante o tienes dudas:**
• Soporte técnico: +34 946 211 000
• Email: soporte.tecnico@eroski.es

🆔 **Código de error**: `FIN-ERROR-{datetime.now().strftime('%Y%m%d%H%M%S')}`

¡Gracias por tu paciencia!"""

        return Command(update={
            "messages": [AIMessage(content=error_response)],
            "finalization_error": True,
            "error_message": error_message,
            "flow_completed": True,
            "session_closed": True,
            "awaiting_user_input": False,
            "current_node": "finalize",
            "last_activity": datetime.now()
        })
    
    def get_finalization_stats(self) -> Dict[str, Any]:
        """
        Obtener estadísticas de finalizaciones (para debugging/monitoreo).
        
        Returns:
            Estadísticas de finalizaciones
        """
        if not self.resolution_history:
            return {"total_resolutions": 0, "node_name": self.name}
        
        # Calcular estadísticas básicas
        total_time = sum(r["session_metrics"]["resolution_time_minutes"] for r in self.resolution_history)
        avg_time = total_time / len(self.resolution_history)
        
        resolution_types = {}
        for record in self.resolution_history:
            res_type = record["resolution_type"]
            resolution_types[res_type] = resolution_types.get(res_type, 0) + 1
        
        return {
            "total_resolutions": self.resolutions_count,
            "average_resolution_time": round(avg_time, 2),
            "resolution_types": resolution_types,
            "resolution_history": self.resolution_history,
            "node_name": self.name,
            "last_resolution": self.resolution_history[-1] if self.resolution_history else None
        }


# =============================================================================
# FUNCIÓN WRAPPER PARA LANGGRAPH
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
# EXPORT PARA INTEGRACIÓN
# =============================================================================

__all__ = [
    "FinalizeNode",
    "finalize_node", 
    "ResolutionType",
    "SatisfactionLevel"
]


# =============================================================================
# TESTING Y DEBUGGING
# =============================================================================

if __name__ == "__main__":
    """
    Test básico del nodo de finalización.
    """
    import asyncio
    from models.eroski_state import create_initial_eroski_state
    
    async def test_finalize():
        print("🧪 Testing Finalize Node...")
        
        # Estado de prueba con resolución exitosa
        test_state = create_initial_eroski_state("test-session")
        test_state.update({
            "resolved": True,
            "solution_found": True,
            "solution_type": "manual_guided",
            "incident_type": "balanza",
            "incident_code": "ER-2024",
            "incident_description": "Problema con etiquetado de precios",
            "employee_name": "María García",
            "employee_email": "maria.garcia@eroski.es",
            "store_name": "Eroski Bilbao Centro",
            "incident_department": "Pescadería",
            "automated_resolution": False,
            "satisfaction_score": 4,
            "attempts": 2,
            "identification_attempts": 1,
            "execution_path": ["authenticate", "identificar_incidencia", "buscar_solucion", "finalize"]
        })
        
        # Ejecutar nodo
        node = FinalizeNode()
        result = await node.execute(test_state)
        
        print("✅ Test completado:")
        print(f"🎯 Finalizado: {result.update.get('finalization_processed', False)}")
        print(f"📊 Tipo resolución: {result.update.get('resolution_type', 'N/A')}")
        print(f"⏱️ Tiempo: {result.update.get('session_metrics', {}).get('resolution_time_minutes', 0):.1f}min")
        print(f"🔄 Sesión cerrada: {result.update.get('session_closed', False)}")
        
        # Mostrar mensaje completo
        if result.update.get('messages'):
            print("\n💬 Mensaje de finalización:")
            print(result.update['messages'][-1].content[:300] + "...")
    
    # Ejecutar test
    asyncio.run(test_finalize())