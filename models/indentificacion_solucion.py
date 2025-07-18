from pydantic import BaseModel, Field

class IdentificacionSolucion(BaseModel):
    problem_identified: bool = Field(..., description="True si se ha descrito claramente un problema técnico")
    confidence: float = Field(..., description="Nivel de confianza entre 0.0 y 1.0")
    problema: str = Field(..., description="Descripción breve del problema detectado o vacío")
    requires_confirmation: bool = Field(..., description="True si se requiere confirmación del usuario sobre la solución")
    message_to_user: str = Field(..., description="Mensaje a mostrar al usuario")
    solution_content: str = Field(..., description="Solución (vacía si aún no se ha buscado)")
