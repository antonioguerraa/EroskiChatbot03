from pydantic import BaseModel, Field
from typing import List, Optional

class IdentificacionSolucion(BaseModel):
    problem_identified: bool = Field(..., description="True si el usuario describe claramente un problema técnico o consulta")
    confidence: float = Field(..., description="Nivel de confianza entre 0.0 y 1.0")
    problem_description: str = Field(..., description="Resumen del problema o consulta técnica identificada")
    requires_confirmation: bool = Field(..., description="True si se requiere confirmar con el usuario")
    message_to_user: str = Field(..., description="Respuesta generada al usuario")
    escalation_needed: Optional[bool] = Field(default=False, description="True si el usuario requiere escalar la conversación")
    user_intent: Optional[str] = Field(default=None, description="Etiqueta de intención detectada (opcional, para trazabilidad)")
    solution_found: bool = Field(default=False, description="True si el usuario indica que se ha resuelta la consulta")
