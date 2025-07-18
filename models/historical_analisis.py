from pydantic import BaseModel, Field
from typing import List, Optional

class HistoricalAnalysis(BaseModel):
    incident_found: bool = Field(description="Detecta si encontró el incidente")
    incident_type: Optional[str] = Field(description="Typo de incidente encontrado")
    confidence: Optional[float] = Field(description="float_entre_0_y_1")
    evidence: Optional[str] = Field(description="texto_que_llevó_a_la_conclusión")
    keywords_detected: Optional[List[str]] = Field(description="lista de keywords")
    reasoning: Optional[str] = Field(description="explicación_del_análisis")
    needs_more_info: bool = Field(description="Indica si necesita más información")
    respuesta_al_usuario: Optional[str] = Field(description="Respuesta al usuario")
    escalation_needed: Optional[bool] = Field(
        default=False,
        description="True si el usuario ha expresado intención de hablar con un supervisor o no se ha podido avanzar."
    )