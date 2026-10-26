from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AutomatonState(StrictModel):
    id: str = Field(min_length=1)
    label: str
    isStart: bool = False
    isAccepting: bool = False
    x: float
    y: float


class Transition(StrictModel):
    from_: str = Field(alias="from", min_length=1)
    to: str = Field(min_length=1)
    symbols: list[str]


class Automaton(StrictModel):
    """Shared serialized automaton shape; ε is the epsilon-transition symbol."""

    type: Literal["DFA", "NFA", "EPSILON_NFA"]
    states: list[AutomatonState]
    alphabet: list[str]
    transitions: list[Transition]

