"""Automata models, simulation, and pure analysis algorithms."""

from app.automata.engine import SimulationResult, simulate
from app.automata.models import Automaton, State, Transition
from app.automata.transformations import eliminate_epsilon, minimize_hopcroft, minimize_table, run_pipeline, subset_construction
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
    "eliminate_epsilon",
    "epsilon_closure",
    "minimize_hopcroft",
    "minimize_table",
    "reachable_states",
    "simulate",
    "run_pipeline",
    "subset_construction",
    "trap_states",
]
