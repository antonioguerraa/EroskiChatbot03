from pydantic import BaseModel, Field

class UnifiedSolutionResponse(BaseModel):
    message_to_user: str = Field(..., description="Mensaje en lenguaje natural dirigido al usuario")
    solution_content: str = Field(..., description="Texto con la solución combinada, solo si está relacionada")
    requires_confirmation: bool = Field(..., description="True si el usuario debe confirmar la solución")
    escalation_needed: bool = Field(..., description="True si no se puede avanzar y se debe escalar a un humano")

