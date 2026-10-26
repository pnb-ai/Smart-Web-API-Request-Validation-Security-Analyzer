"""Validated automaton models used by the API and pure algorithms."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.automata.symbols import EPSILON, expand_symbol
from app.models.trace import TraceStep


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class State(StrictModel):
    id: str = Field(min_length=1)
    label: str
    isStart: bool = False
    isAccepting: bool = False
    x: float
    y: float


class Transition(StrictModel):
    from_: str = Field(alias="from", min_length=1)
    to: str = Field(min_length=1)
    symbols: list[str] = Field(min_length=1)


class Automaton(StrictModel):
    """Serialized DFA, NFA, or epsilon-NFA using symbol-class labels."""

    type: Literal["DFA", "NFA", "EPSILON_NFA"]
    states: list[State] = Field(min_length=1)
    alphabet: list[str]
    transitions: list[Transition]

    @model_validator(mode="after")
    def validate_structure(self) -> "Automaton":
        state_ids = [state.id for state in self.states]
        if len(state_ids) != len(set(state_ids)):
            raise ValueError("state ids must be unique")
        if sum(state.isStart for state in self.states) != 1:
            raise ValueError("automaton must have exactly one start state")
        if len(self.alphabet) != len(set(self.alphabet)):
            raise ValueError("alphabet symbols must be unique")
        if any(not symbol or symbol == EPSILON for symbol in self.alphabet):
            raise ValueError("alphabet symbols must be non-empty and cannot include ε")

        known_states = set(state_ids)
        alphabet = set(self.alphabet)
        by_state_token: dict[str, dict[str, set[str]]] = {state_id: {} for state_id in state_ids}
        for transition in self.transitions:
            if transition.from_ not in known_states or transition.to not in known_states:
                raise ValueError("every transition must reference existing states")
            for symbol in transition.symbols:
                if not symbol:
                    raise ValueError("transition symbols must be non-empty")
                if symbol == EPSILON:
                    if self.type != "EPSILON_NFA":
                        raise ValueError("ε transitions are allowed only in EPSILON_NFA")
                    continue
                if symbol not in alphabet:
                    raise ValueError(f"transition symbol {symbol!r} is not in the alphabet")
                for token in expand_symbol(symbol):
                    by_state_token[transition.from_].setdefault(token, set()).add(transition.to)

        if self.type == "DFA":
            for state_id, tokens in by_state_token.items():
                ambiguous = [token for token, destinations in tokens.items() if len(destinations) > 1]
                if ambiguous:
                    shown = ", ".join(repr(token) for token in sorted(ambiguous))
                    raise ValueError(f"DFA is nondeterministic at {state_id} for input {shown}")
        return self

    def start_state(self) -> State:
        """Return the unique start state, guaranteed by model validation."""
        return next(state for state in self.states if state.isStart)


# A descriptive alias is retained for existing code and the JSON schema docs.
AutomatonState = State


__all__ = ["Automaton", "AutomatonState", "State", "TraceStep", "Transition"]
