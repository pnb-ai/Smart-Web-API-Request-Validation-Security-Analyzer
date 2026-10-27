"""HTTP endpoints for automaton validation and simulation."""

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.automata.engine import simulate
from app.automata.models import Automaton
from app.automata.transformations import eliminate_epsilon, minimize_hopcroft, minimize_table, run_pipeline, subset_construction
from app.automata.utilities import classify_automaton

router = APIRouter(prefix="/api/automata", tags=["automata"])
transform_router = APIRouter(prefix="/api", tags=["transformations"])


class SimulationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    automaton: Automaton
    input_value: str = Field(alias="input")


class TransformRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    automaton: Automaton
    operation: Literal["epsilon-elimination", "subset-construction", "minimize-table", "minimize-hopcroft", "pipeline"]
    minimizer: Literal["table", "hopcroft"] = "table"


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


@transform_router.post("/transform")
def transform_automaton(request: TransformRequest) -> dict[str, object]:
    """Run one conversion or the full applicable pipeline with every trace."""
    try:
        if request.operation == "epsilon-elimination":
            transformed = eliminate_epsilon(request.automaton)
        elif request.operation == "subset-construction":
            transformed = subset_construction(request.automaton)
        elif request.operation == "minimize-table":
            transformed = minimize_table(request.automaton)
        elif request.operation == "minimize-hopcroft":
            transformed = minimize_hopcroft(request.automaton)
        else:
            pipeline = run_pipeline(request.automaton, request.minimizer)
            return {
                "operation": request.operation,
                "result": pipeline["result"].model_dump(by_alias=True, mode="json"),
                "trace": [step.model_dump(mode="json") for step in pipeline["trace"]],
                "intermediateAutomata": [
                    {
                        "operation": item["operation"],
                        "automaton": item["automaton"].model_dump(by_alias=True, mode="json"),
                        "trace": [step.model_dump(mode="json") for step in item["trace"]],
                    }
                    for item in pipeline["intermediateAutomata"]
                ],
            }
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return {
        "operation": request.operation,
        "result": transformed.result.model_dump(by_alias=True, mode="json"),
        "trace": [step.model_dump(mode="json") for step in transformed.trace],
        "intermediateAutomata": [],
    }
