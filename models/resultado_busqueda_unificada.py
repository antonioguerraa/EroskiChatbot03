from pydantic import BaseModel
from typing import Optional

class ResultadoBusquedaUnificada(BaseModel):
    solution_found: bool
    solution_content: str
    confidence_rag: Optional[float] = 0.0
    confidence_faq: Optional[float] = 0.0
    source_rag: Optional[str] = None
    source_faq: Optional[str] = None