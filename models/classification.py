from pydantic import BaseModel, Field
from typing import Optional, List

class ClassificationDecision(BaseModel):
    incident_identified: bool
    problem_identified: bool
    solution_ready: bool
    escalation_needed: bool
    wants_to_cancel: bool
    incident_type: Optional[str] = None
    specific_problem: Optional[str] = None
    proposed_solution: Optional[str] = None
    confidence_level: float = 0.0
    next_action: str
    message_to_user: str
    questions_to_ask: List[str] = []
    keywords_detected: List[str] = []
    urgency_level: int = 2
    historical_info_found: Optional[str] = None
    progress_assessment: str = "unknown"
    new_information_provided: bool = False
    questions_already_asked: List[str] = []
    stuck_in_loop: bool = False
