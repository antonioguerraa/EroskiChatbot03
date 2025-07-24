from pydantic import BaseModel, Field

class FAQ_ProblemMatch(BaseModel):
    problem_identified: str = Field(..., description="Nombre o descripción del problema más similar encontrado en el JSON")
    solution_content: str = Field(..., description="Solución correspondiente al problema detectado")
    confianza: float = Field(..., ge=0.0, le=1.0, description="Nivel de confianza en el match entre el problema del usuario y el JSON")
    problem_name: str = Field(..., description="Problema identificado en el archivo")
                