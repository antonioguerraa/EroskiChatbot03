from pydantic import BaseModel, Field
from typing import Optional

class IdentificarIncidencia(BaseModel):
    incident_found: bool = Field(description="Detecta si encontró el incidente")
    incident_type: Optional[str] = Field(description="Typo de incidente encontrado")
    incident_confidence: Optional[float] = Field(description="float_entre_0_y_1")
    incident_evidence: Optional[str] = Field(description="texto_que_llevó_a_la_conclusión")
    incident_reasoning: Optional[str] = Field(description="explicación_del_análisis")
    incident_needs_more_info: bool = Field(description="Indica si necesita más información")
    respuesta_al_usuario: Optional[str] = Field(description="Respuesta al usuario")
    escalation_needed: Optional[bool] = Field(
        default=False,
        description="True si el usuario ha expresado intención de hablar con un supervisor o no se ha podido avanzar."
    )