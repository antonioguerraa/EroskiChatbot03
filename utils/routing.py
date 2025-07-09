# utils/routing.py (nuevo archivo sugerido)

from langchain_core.messages import AIMessage
from langgraph.types import Command
from datetime import datetime
from typing import Dict
from models.eroski_state import EroskiState
from models.classification import ClassificationDecision  # Asegúrate de que esté exportado

class ClassificationRouter:
    """
    Clase de ayuda para enrutar decisiones del LLM de clasificación
    """

    def __init__(self, node):
        self.node = node  # referencia al nodo para usar sus helpers

    def route(self, state: EroskiState, decision: ClassificationDecision, attempt_number: int) -> Command:
        classify_data = self._update_classify_data(state, decision, attempt_number)

        if decision.wants_to_cancel:
            return self.node._handle_cancellation(state)

        if decision.needs_escalation or decision.next_action == "escalate":
            return self.node._escalate_to_supervisor(state)

        if decision.solution_ready and decision.next_action in ["provide_solution", "complete"]:
            return self.node._provide_solution_and_complete(state, decision)

        if decision.incident_identified and decision.incident_type and not decision.problem_identified:
            return self.node._generate_targeted_questions(state, decision, attempt_number)

        return Command(
            update={
                "messages": state["messages"] + [AIMessage(content=decision.message_to_user)],
                "classify_data": classify_data,
                "classify_attempt_number": attempt_number,
                "current_step": "classify"
            }
        )

    def _update_classify_data(self, state: EroskiState, decision: ClassificationDecision, attempt_number: int) -> Dict:
        data = state.get("classify_data", {}).copy()

        data.update({
            "incident_type": decision.incident_type or data.get("incident_type"),
            "specific_problem": decision.specific_problem or data.get("specific_problem"),
            "proposed_solution": decision.proposed_solution or data.get("proposed_solution"),
            "incident_identified": decision.incident_identified,
            "problem_identified": decision.problem_identified,
            "solution_ready": decision.solution_ready,
            "confidence_level": decision.confidence_level,
            "keywords_detected": decision.keywords_detected,
            "urgency_level": decision.urgency_level,
            "progress_assessment": decision.progress_assessment,
            "new_information_provided": decision.new_information_provided,
            "stuck_in_loop": decision.stuck_in_loop,
            "confidence_history": data.get("confidence_history", [])[-4:] + [decision.confidence_level],
            "last_analysis": datetime.now().isoformat()
        })

        return data
