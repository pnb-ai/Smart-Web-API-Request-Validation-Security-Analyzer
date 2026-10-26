"""HTTP endpoints for automaton validation and simulation."""

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.automata.engine import simulate
from app.automata.models import Automaton
from app.automata.utilities import classify_automaton

router = APIRouter(prefix="/api/automata", tags=["automata"])


class SimulationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    automaton: Automaton
    input_value: str = Field(alias="input")


@router.post("/validate")
def validate_automaton(automaton: Automaton) -> dict[str, object]:
    """Validate the schema and return its automatically inferred class."""
    classification = classify_automaton(automaton)
    return {
        "valid": True,
        "declaredType": automaton.type,
        "classification": classification.result,
        "trace": [step.model_dump(mode="json") for step in classification.trace],
    }


@router.post("/simulate")
def simulate_automaton(request: SimulationRequest) -> dict[str, object]:
    """Simulate an input and return its decision and visualization trace."""
    result = simulate(request.automaton, request.input_value)
    return {
        "status": result.status,
        "accepted": result.accepted,
        "reason": result.reason,
        "finalStates": result.final_states,
        "trace": [step.model_dump(mode="json") for step in result.trace],
    }
