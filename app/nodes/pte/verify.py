# =====================================================
# nodes/verify.py - Nodo de Verificación de Resolución
# =====================================================
"""
Nodo para verificar si la solución proporcionada ha resuelto el problema.

RESPONSABILIDADES:
- Confirmar con el usuario si el problema se ha resuelto
- Recopilar feedback sobre la solución
- Actualizar estado de resolución
- Determinar si necesita escalación adicional
"""

from typing import Dict, Any, Optional, List
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command
from datetime import datetime
import logging
import re

from app.models.eroski_state import EroskiState
from app.nodes.base_node import BaseNode

class VerifyResolutionNode(BaseNode):
    """
    Nodo para verificar resolución de problemas.
    
    CARACTERÍSTICAS:
    - Confirmación interactiva con el usuario
    - Recopilación de feedback
    - Actualización de métricas
    - Escalación si no se resuelve
    """
    
    def __init__(self):
        super().__init__("VerifyResolution")
        
        # Palabras clave para respuestas positivas
        self.positive_keywords = [
            "sí", "si", "yes", "resuelto", "solucionado", "funcionando",
            "funciona", "perfecto", "bien", "correcto", "gracias"
        ]
        
        # Palabras clave para respuestas negativas
        self.negative_keywords = [
            "no", "not", "sigue", "todavía", "aún", "problema",
            "error", "fallo", "mal", "incorrecto"
        ]
        
        # Palabras clave para respuestas parciales
        self.partial_keywords = [
            "parcialmente", "algo", "un poco", "mejora", "mejor",
            "pero", "aunque", "sin embargo"
        ]
    
    def get_required_fields(self) -> List[str]:
        return ["messages", "solution_found", "solution_content"]
    
    def get_actor_description(self) -> str:
        return "Verifico si las soluciones proporcionadas han resuelto el problema del usuario"
    
    async def execute(self, state: EroskiState) -> Command:
        """
        Ejecutar verificación de resolución.
        
        Args:
            state: Estado actual del workflow
            
        Returns:
            Command con el resultado de la verificación
        """
        try:
            # Verificar si ya tenemos una respuesta del usuario
            user_response = self.get_last_user_message(state)
            
            if not user_response:
                return self._request_confirmation(state)
            
            # Analizar respuesta del usuario
            resolution_status = self._analyze_user_response(user_response)
            
            # Procesar basado en el estado de resolución
            if resolution_status == "resolved":
                return self._handle_resolution_success(state, user_response)
            elif resolution_status == "not_resolved":
                return self._handle_resolution_failure(state, user_response)
            elif resolution_status == "partial":
                return self._handle_partial_resolution(state, user_response)
            else:
                return self._request_clarification(state)
                
        except Exception as e:
            self.logger.error(f"❌ Error en verificación: {e}")
            return self._escalate_error(state, str(e))
    
    def _analyze_user_response(self, response: str) -> str:
        """Analizar respuesta del usuario para determinar estado de resolución"""
        response_lower = response.lower()
        
        # Contar palabras clave de cada tipo
        positive_count = sum(1 for keyword in self.positive_keywords if keyword in response_lower)
        negative_count = sum(1 for keyword in self.negative_keywords if keyword in response_lower)
        partial_count = sum(1 for keyword in self.partial_keywords if keyword in response_lower)
        
        # Lógica de decisión
        if positive_count > negative_count and partial_count == 0:
            return "resolved"
        elif negative_count > positive_count:
            return "not_resolved"
        elif partial_count > 0:
            return "partial"
        else:
            return "unclear"
    
    def _request_confirmation(self, state: EroskiState) -> Command:
        """Solicitar confirmación de resolución al usuario"""
        
        solution_content = state.get("solution_content", {})
        solution_title = solution_content.get("title", "solución proporcionada") if isinstance(solution_content, dict) else "solución proporcionada"
        
        confirmation_message = f"""✅ **VERIFICACIÓN DE RESOLUCIÓN**

Has seguido los pasos de la **{solution_title}**.

**¿Se ha resuelto tu problema?**

Por favor, responde con una de estas opciones:
• **"Sí, está resuelto"** - Si el problema se solucionó completamente
• **"No, sigue sin funcionar"** - Si el problema persiste
• **"Funciona parcialmente"** - Si mejoró pero aún hay problemas

**Tu respuesta me ayudará a:**
• Cerrar el ticket si está resuelto
• Buscar soluciones alternativas si es necesario  
• Escalarlo a un especialista si es complejo

**¿Cómo está funcionando ahora?** 🤔"""
        
        return Command(update={
            "messages": [AIMessage(content=confirmation_message)],
            "awaiting_user_input": True,
            "current_node": "verify",
            "last_activity": datetime.now(),
            "verification_stage": "awaiting_confirmation"
        })
    
    def _handle_resolution_success(self, state: EroskiState, user_response: str) -> Command:
        """Manejar resolución exitosa"""
        
        # Calcular tiempo de resolución
        resolution_time = self._calculate_resolution_time(state)
        
        # Recopilar feedback
        feedback = self._extract_feedback(user_response)
        
        success_message = f"""🎉 **¡PROBLEMA RESUELTO CON ÉXITO!**

¡Excelente! Me alegra saber que el problema se ha solucionado.

**📊 Resumen de la resolución:**
• **Tiempo total:** {resolution_time}
• **Solución aplicada:** {self._get_solution_summary(state)}
• **Tu feedback:** {feedback}

**📋 Ticket cerrado:** {state.get('ticket_number', 'N/A')}

**🌟 ¡Gracias por tu colaboración!** 
Tu problema ha sido resuelto satisfactoriamente y el ticket ha sido cerrado.

**📞 ¿Necesitas más ayuda?**
Si tienes otros problemas o consultas, no dudes en contactarme de nuevo.

¡Que tengas un buen día! 😊"""
        
        return Command(update={
            "resolved": True,
            "automated_resolution": True,
            "resolution_time": resolution_time,
            "user_feedback": feedback,
            "solution_effective": True,
            "ticket_status": "Cerrada",
            "messages": [AIMessage(content=success_message)],
            "current_node": "verify",
            "last_activity": datetime.now(),
            "awaiting_user_input": False,
            "flow_completed": True
        })
    
    def _handle_resolution_failure(self, state: EroskiState, user_response: str) -> Command:
        """Manejar fallo en la resolución"""
        
        attempts = state.get("verification_attempts", 0)
        
        if attempts >= 1:  # Después de 1 intento fallido, escalar
            return self._escalate_unresolved_issue(state, user_response)
        
        failure_message = """😔 **El problema aún persiste**

Entiendo que la solución no ha funcionado completamente.

**Opciones disponibles:**
• **Intentar una solución alternativa** - Tengo otras opciones que pueden funcionar
• **Escalarlo a soporte técnico** - Un especialista puede ayudarte mejor
• **Revisión presencial** - Solicitar que alguien revise el equipo físicamente

**Para ayudarte mejor, cuéntame:**
• ¿Qué pasó exactamente cuando seguiste los pasos?
• ¿Hay algún mensaje de error específico?
• ¿El problema es exactamente igual que antes?

**¿Qué prefieres que haga?** 🤔"""
        
        return Command(update={
            "resolved": False,
            "solution_effective": False,
            "verification_attempts": attempts + 1,
            "messages": [AIMessage(content=failure_message)],
            "awaiting_user_input": True,
            "current_node": "verify",
            "last_activity": datetime.now(),
            "verification_stage": "solution_failed"
        })
    
    def _handle_partial_resolution(self, state: EroskiState, user_response: str) -> Command:
        """Manejar resolución parcial"""
        
        partial_message = """🔄 **Resolución parcial detectada**

Entiendo que la solución ha mejorado el problema pero no lo ha resuelto completamente.

**Esto es normal** - a veces los problemas técnicos requieren varios pasos.

**Opciones para completar la solución:**
• **Pasos adicionales** - Puedo sugerir acciones complementarias
• **Solución alternativa** - Intentar un enfoque diferente
• **Soporte especializado** - Escalarlo para una revisión más detallada

**Para ayudarte mejor:**
• ¿Qué parte funciona bien ahora?
• ¿Qué aspecto aún no está funcionando?
• ¿Prefieres intentar más pasos o que lo derive a un especialista?

**¿Cómo quieres proceder?** 🤔"""
        
        return Command(update={
            "resolved": False,
            "solution_effective": "partial",
            "partial_resolution": True,
            "messages": [AIMessage(content=partial_message)],
            "awaiting_user_input": True,
            "current_node": "verify",
            "last_activity": datetime.now(),
            "verification_stage": "partial_resolution"
        })
    
    def _request_clarification(self, state: EroskiState) -> Command:
        """Solicitar clarificación cuando la respuesta no es clara"""
        
        clarification_message = """❔ **Necesito aclaración**

No he podido entender claramente si el problema se ha resuelto.

**Por favor, responde de forma clara:**
• **"Sí, funciona perfectamente"** ✅
• **"No, sigue igual"** ❌  
• **"Funciona mejor pero aún hay problemas"** 🔄

**¿Podrías confirmar el estado actual del problema?** 🤔"""
        
        attempts = state.get("verification_attempts", 0)
        
        if attempts >= 2:
            return self._escalate_unclear_status(state)
        
        return Command(update={
            "messages": [AIMessage(content=clarification_message)],
            "verification_attempts": attempts + 1,
            "awaiting_user_input": True,
            "current_node": "verify",
            "last_activity": datetime.now(),
            "verification_stage": "awaiting_clarification"
        })
    
    def _escalate_unresolved_issue(self, state: EroskiState, user_response: str) -> Command:
        """Escalar problema no resuelto"""
        
        escalation_message = """🔼 **ESCALANDO A SOPORTE ESPECIALIZADO**

El problema no se ha resuelto con las soluciones automáticas disponibles.

**Te he derivado a soporte técnico especializado** que podrá:
• Revisar el problema en detalle
• Aplicar soluciones avanzadas
• Realizar diagnósticos específicos
• Hacer revisión presencial si es necesario

**📋 Información transferida:**
• Ticket original: {ticket_number}
• Soluciones intentadas: {solution_summary}
• Feedback del usuario: {user_feedback}

**📞 Contacto directo:**
• Soporte técnico: +34 946 211 000
• Menciona el ticket: {ticket_number}

**⏰ Tiempo de respuesta:** 15-30 minutos

¡Gracias por tu paciencia! El equipo especializado se pondrá en contacto contigo pronto. 🤝""".format(
            ticket_number=state.get("ticket_number", "N/A"),
            solution_summary=self._get_solution_summary(state),
            user_feedback=user_response[:100]
        )
        
        return Command(update={
            "escalation_needed": True,
            "escalation_reason": "Solución automática no efectiva",
            "escalation_level": "technical",
            "resolved": False,
            "solution_effective": False,
            "messages": [AIMessage(content=escalation_message)],
            "current_node": "verify",
            "last_activity": datetime.now(),
            "awaiting_user_input": False,
            "flow_completed": True
        })
    
    def _escalate_unclear_status(self, state: EroskiState) -> Command:
        """Escalar por estado no claro"""
        
        return Command(update={
            "escalation_needed": True,
            "escalation_reason": "No se pudo verificar el estado de resolución",
            "escalation_level": "supervisor",
            "messages": [
                AIMessage(content="No he podido verificar el estado de resolución. Te derivo a un supervisor para asistencia personalizada.")
            ],
            "current_node": "verify",
            "last_activity": datetime.now(),
            "awaiting_user_input": False
        })
    
    def _calculate_resolution_time(self, state: EroskiState) -> str:
        """Calcular tiempo de resolución"""
        start_time = state.get("start_time")
        if not start_time:
            return "N/A"
        
        resolution_time = datetime.now() - start_time
        minutes = int(resolution_time.total_seconds() / 60)
        
        if minutes < 1:
            return "menos de 1 minuto"
        elif minutes < 60:
            return f"{minutes} minutos"
        else:
            hours = minutes // 60
            remaining_minutes = minutes % 60
            return f"{hours}h {remaining_minutes}m"
    
    def _extract_feedback(self, user_response: str) -> str:
        """Extraer feedback útil de la respuesta del usuario"""
        # Buscar frases positivas específicas
        positive_phrases = [
            "funciona perfectamente", "muy bien", "excelente", 
            "rápido", "fácil", "claro", "útil"
        ]
        
        response_lower = user_response.lower()
        feedback_elements = []
        
        for phrase in positive_phrases:
            if phrase in response_lower:
                feedback_elements.append(phrase)
        
        if feedback_elements:
            return f"Positivo: {', '.join(feedback_elements)}"
        else:
            return "Resolución confirmada"
    
    def _get_solution_summary(self, state: EroskiState) -> str:
        """Obtener resumen de la solución aplicada"""
        solution_content = state.get("solution_content", {})
        
        if isinstance(solution_content, dict):
            return solution_content.get("title", "Solución automática")
        else:
            return "Solución automática"
    
    def _escalate_error(self, state: EroskiState, error_message: str) -> Command:
        """Escalar por error técnico"""
        return Command(update={
            "escalation_needed": True,
            "escalation_reason": f"Error técnico en verificación: {error_message}",
            "escalation_level": "technical",
            "messages": [
                AIMessage(content="Ha ocurrido un error técnico. Te derivo a soporte técnico.")
            ],
            "current_node": "verify",
            "last_activity": datetime.now(),
            "error_count": state.get("error_count", 0) + 1
        })

# ========== WRAPPER PARA LANGGRAPH ==========

async def verify_resolution_node(state: EroskiState) -> Command:
    """
    Wrapper function para el nodo de verificación de resolución.
    
    Args:
        state: Estado actual del workflow
        
    Returns:
        Command con la actualización de estado
    """
    node = VerifyResolutionNode()
    return await node.execute(state)