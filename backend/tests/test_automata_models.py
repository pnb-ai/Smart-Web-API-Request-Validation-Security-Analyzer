import pytest
from pydantic import ValidationError

from app.models.automata import Automaton
from app.models.trace import TraceStep


def test_automaton_schema_accepts_epsilon_and_symbol_classes() -> None:
    automaton = Automaton.model_validate(
        {
            "type": "EPSILON_NFA",
            "states": [{"id": "q0", "label": "Start", "isStart": True, "isAccepting": False, "x": 0, "y": 0}],
            "alphabet": ["DIGIT"],
            "transitions": [{"from": "q0", "to": "q0", "symbols": ["DIGIT", "ε"]}],
        }
    )

    assert automaton.transitions[0].from_ == "q0"
    assert automaton.model_dump(by_alias=True)["transitions"][0]["from"] == "q0"


def test_automaton_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        Automaton.model_validate({"type": "DFA", "states": [], "alphabet": [], "transitions": [], "extra": True})


def test_trace_step_has_visualization_data() -> None:
    step = TraceStep(title="Read symbol", explanation="Follow the matching edge.", data={"state": "q0"})

    assert step.data["state"] == "q0"
