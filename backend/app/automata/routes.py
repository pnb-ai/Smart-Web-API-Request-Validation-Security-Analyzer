"""HTTP endpoints for automaton validation and simulation."""

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.automata.engine import simulate
from app.automata.equivalence import check_equivalence, check_equivalence_hopcroft_karp
from app.automata.models import Automaton
from app.automata.regex import RegexParser, compile_regex
from app.automata.transformations import eliminate_epsilon, minimize_hopcroft, minimize_table, run_pipeline, subset_construction
from app.automata.utilities import classify_automaton

router = APIRouter(prefix="/api/automata", tags=["automata"])
transform_router = APIRouter(prefix="/api", tags=["transformations"])
equivalence_router = APIRouter(prefix="/api", tags=["equivalence"])


class SimulationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    automaton: Automaton
    input_value: str = Field(alias="input")


class TransformRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    automaton: Automaton
    operation: Literal["epsilon-elimination", "subset-construction", "minimize-table", "minimize-hopcroft", "pipeline"]
    minimizer: Literal["table", "hopcroft"] = "table"


class EquivalenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    left: Automaton
    right: Automaton
    method: Literal["product-bfs", "hopcroft-karp"] = "product-bfs"


class RegexRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pattern: str = Field(max_length=256)


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


@equivalence_router.post("/equivalence")
def compare_automata(request: EquivalenceRequest) -> dict[str, object]:
    """Compare two regular languages and return witnesses plus exploration trace."""
    try:
        check = check_equivalence_hopcroft_karp if request.method == "hopcroft-karp" else check_equivalence
        result = check(request.left, request.right)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {**result.result, "trace": [step.model_dump(mode="json") for step in result.trace]}


@equivalence_router.post("/regex/convert")
@equivalence_router.post("/regex/compile", include_in_schema=False)
def compile_regular_expression(request: RegexRequest) -> dict[str, object]:
    """Compile a regex and return its complete automata conversion pipeline."""
    try:
        automaton, trace = compile_regex(request.pattern)
        ast = RegexParser(request.pattern).parse()
        pipeline = run_pipeline(automaton)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    intermediate = pipeline["intermediateAutomata"]
    nfa = intermediate[0]["automaton"]
    dfa = intermediate[1]["automaton"] if len(intermediate) > 1 else intermediate[0]["automaton"]
    minimal = pipeline["result"]
    return {
        "automaton": automaton.model_dump(by_alias=True, mode="json"),
        "ast": ast.json(),
        "epsilonNfa": automaton.model_dump(by_alias=True, mode="json"),
        "nfa": nfa.model_dump(by_alias=True, mode="json"),
        "dfa": dfa.model_dump(by_alias=True, mode="json"),
        "minimalDfa": minimal.model_dump(by_alias=True, mode="json"),
        "trace": [step.model_dump(mode="json") for step in trace],
        "pipelineSummary": [
            {
                "title": item["operation"],
                "explanation": f"Built {item['automaton'].type} with {len(item['automaton'].states)} reachable states.",
                "data": {"operation": item["operation"], "stateCount": len(item["automaton"].states), "traceStepCount": len(item["trace"])},
            }
            for item in intermediate
        ],
    }
