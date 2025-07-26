from pydantic import BaseModel, Field
from typing import List, Optional

class IncidentResponse(BaseModel):
    response_to_user: str = Field(..., description="Respuesta para el usuario final")
    incident_type: str = Field(..., description="Tipo de incidencia identificada")
    incident_type_confirmed: bool = Field(..., description="True si el usuario lo ha confirmado")
    confidence: float = Field(..., description="Confianza entre 0.0 y 1.0")
    keywords: List[str] = Field(..., description="Palabras clave detectadas")
    reasoning: str = Field(..., description="Explicación del análisis")
    action_required: Optional[str] = Field(None, description="confirmacion_usuario, escalar, etc.")
    escalation_needed: Optional[bool] = Field(
        default=False,
        description="True si el usuario ha expresado intención de hablar con un supervisor o no se ha podido avanzar."
    )
