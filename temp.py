# =====================================================
# nodes/buscar_solucion_node.py - INTEGRACIÓN DENTRO DE LA CLASE
# =====================================================

# 🆕 AGREGAR AL INICIO DEL ARCHIVO (fuera de la clase):
from utils.incident_manager import get_incident_manager

class BuscarSolucionNode:
    """Clase para buscar soluciones a incidencias"""
    
    def __init__(self):
        # ... tu código existente de __init__ ...
        
        # 🆕 AGREGAR: Inicializar incident manager
        self._incident_manager = None
    
    # =========================================================================
    # 🆕 MÉTODOS HELPER PARA INCIDENT TRACKING (dentro de la clase)
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
            from models.eroski_state import EroskiState
            if not isinstance(state, EroskiState):
                eroski_state = EroskiState(state)
            else:
                eroski_state = state
            
            # Trackear con incident manager
            incident_id = self._get_incident_manager().manage_incident(eroski_state)
            
            return incident_id
            
        except Exception as e:
            # No fallar si hay error en tracking
            print(f"⚠️ Error en incident tracking: {e}")
            return state.get("incident_id", "ERROR-TRACKING")
    
    # =========================================================================
    # TUS MÉTODOS EXISTENTES - MODIFICACIONES MÍNIMAS
    # =========================================================================
    
    async def execute(self, state):
        """Método principal - MODIFICACIÓN MÍNIMA"""
        
        # 🆕 AGREGAR: Inicializar tracking (1 línea)
        incident_id = self._track_incident_state(state)
        
        try:
            # ... TU CÓDIGO EXISTENTE SIN CAMBIOS ...
            
            # Obtener último mensaje del usuario
            last_message = None
            for msg in reversed(state.get("messages", [])):
                if isinstance(msg, HumanMessage):
                    last_message = msg.content
                    break
            
            if not last_message:
                return {
                    "messages": state.get("messages", []) + [
                        AIMessage(content="No pude obtener tu respuesta...")
                    ],
                    "awaiting_user_input": True,
                    "incident_id": incident_id  # 🆕 AGREGAR
                }
            
            # Usar ConfirmationTool para procesar la respuesta
            confirmacion = self.confirmation_tool.process_confirmation(last_message)
            
            if confirmacion["confirmed"]:
                # Usuario confirmó - proceder a buscar soluciones
                problema = state.get("problem_description", "")
                incident_type = state.get("incident_type", "")
                
                # ... tu código existente para buscar soluciones ...
                
                if combined_solutions:
                    solucion_completa = "\n\n".join(combined_solutions) + "\n\n¿Esta solución resuelve tu problema?"
                    
                    # 🆕 AGREGAR: Trackear solución encontrada (1 línea)
                    incident_id = self._track_incident_state(state, {
                        "solution_found": True,
                        "solution_content": solucion_completa,
                        "solution_type": "combined_json_manual"
                    })
                    
                    return {
                        "messages": state.get("messages", []) + [AIMessage(content=solucion_completa)],
                        "solution_found": True,
                        "solution_content": solucion_completa,
                        "awaiting_solution_confirmation": True,
                        "current_node": "buscar_solucion",
                        "incident_id": incident_id  # 🆕 AGREGAR
                    }
                else:
                    # 🆕 AGREGAR: Trackear falta de solución (1 línea)
                    incident_id = self._track_incident_state(state, {
                        "solution_found": False,
                        "escalation_needed": True,
                        "escalation_reason": "No se encontraron soluciones específicas"
                    })
                    
                    return {
                        "messages": state.get("messages", []) + [
                            AIMessage(content="No se encontraron soluciones específicas...")
                        ],
                        "solution_found": False,
                        "escalation_needed": True,
                        "incident_id": incident_id  # 🆕 AGREGAR
                    }
            
            else:
                # Usuario no confirmó
                return {
                    "messages": state.get("messages", []) + [
                        AIMessage(content="Entiendo. ¿Podrías describir mejor el problema?")
                    ],
                    "awaiting_user_input": True,
                    "problem_identified": False,
                    "current_node": "buscar_solucion",
                    "incident_id": incident_id  # 🆕 AGREGAR
                }
                
        except Exception as e:
            # 🆕 AGREGAR: Trackear errores (1 línea)
            incident_id = self._track_incident_state(state, {
                "escalation_needed": True,
                "escalation_reason": f"Error técnico: {str(e)}",
                "escalation_level": "technical"
            })
            
            return {
                "messages": state.get("messages", []) + [
                    AIMessage(content="Ha ocurrido un error técnico. Te derivo a soporte.")
                ],
                "escalation_needed": True,
                "escalation_level": "technical",
                "error_details": str(e),
                "incident_id": incident_id  # 🆕 AGREGAR
            }
    
    # =========================================================================
    # TUS OTROS MÉTODOS EXISTENTES - EJEMPLOS DE INTEGRACIÓN
    # =========================================================================
    
    def handle_solution_confirmation(self, state, user_response):
        """Manejar confirmación de solución del usuario"""
        
        if "sí" in user_response.lower() or "si" in user_response.lower():
            # 🆕 Solución exitosa
            incident_id = self._track_incident_state(state, {
                "solution_found": True,
                "solution_confirmed": True,
                "incident_resolved": True
            })
            
            return {
                "messages": state.get("messages", []) + [
                    AIMessage(content="¡Perfecto! Incidencia resuelta exitosamente.")
                ],
                "resolved": True,
                "incident_id": incident_id
            }
        
        elif "no" in user_response.lower():
            # 🆕 Solución falló - escalar
            incident_id = self._track_incident_state(state, {
                "solution_found": False,
                "solution_confirmed": False,
                "escalation_needed": True,
                "escalation_reason": "Solución propuesta no funcionó"
            })
            
            return {
                "messages": state.get("messages", []) + [
                    AIMessage(content="Entiendo que la solución no funcionó. Te conectaré con un especialista.")
                ],
                "escalation_needed": True,
                "escalation_level": "specialist",
                "incident_id": incident_id
            }

# =====================================================
# FUNCIÓN WRAPPER (fuera de la clase)
# =====================================================

async def buscar_solucion_node(state):
    """Función wrapper para LangGraph"""
    node = BuscarSolucionNode()
    return await node.execute(state)