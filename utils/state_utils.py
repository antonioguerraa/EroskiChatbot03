# utils/state_utils.py

from models.eroski_state import EroskiState

def ensure_incident_description(state: EroskiState) -> EroskiState:
    """
    Asegura que el campo incident_description esté presente y con valor válido.
    Si no existe, se asigna un valor por defecto.
    """
    if not state.get("incident_description"):
        state["incident_description"] = "Problema no especificado claramente"
    return state
