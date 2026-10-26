"""Automata models, simulation, and pure analysis algorithms."""

from app.automata.engine import SimulationResult, simulate
from app.automata.models import Automaton, State, Transition
from app.automata.utilities import (
    AlgorithmResult,
    classify_automaton,
    complete_dfa,
    dead_states,
    epsilon_closure,
    reachable_states,
    trap_states,
)

__all__ = [
    "AlgorithmResult",
    "Automaton",
    "SimulationResult",
    "State",
    "Transition",
    "classify_automaton",
    "complete_dfa",
    "dead_states",
    "epsilon_closure",
    "reachable_states",
    "simulate",
    "trap_states",
]
