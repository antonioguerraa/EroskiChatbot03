from pydantic import BaseModel, Field
from typing import List, Optional, Dict

class InfoAdicionalResponse(BaseModel):
    info_recogida: Dict[str, str] = Field(..., description="Campos adicionales proporcionados por el usuario")
    fields_pending: List[str] = Field(..., description="Campos aún pendientes de obtener")
    escalation_needed: bool = Field(..., description="Si el usuario ha pedido hablar con un supervisor")
    message_to_user: str = Field(..., description="Mensaje que se debe enviar al usuario")
