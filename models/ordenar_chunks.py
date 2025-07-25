from pydantic import BaseModel, Field
from typing import List, Optional

class OrdenarChunks(BaseModel):
    problem_identified: bool = Field(..., description="True si se ha descrito claramente un problema técnico")
    confidence: float = Field(..., description="Nivel de confianza entre 0.0 y 1.0")
    solution_content: str = Field(..., description="Solución (vacía si aún no se ha encontrado)")
    chunk_id_list: list = Field(..., description="Lista de IDs de los chunks utilizados para formar la solución")
    