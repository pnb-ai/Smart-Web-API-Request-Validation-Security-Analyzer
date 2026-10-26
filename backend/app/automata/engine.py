"""Pure simulation routines for deterministic and nondeterministic automata."""

from dataclasses import dataclass
from typing import Literal

from app.automata.models import Automaton, Transition
from app.automata.symbols import EPSILON, display_symbol, expand_symbol, tokenize_input
from app.models.trace import TraceStep


@dataclass(frozen=True)
class SimulationResult:
    status: Literal["ACCEPTED", "REJECTED"]
    accepted: bool
    reason: str
    final_states: list[str]
    trace: list[TraceStep]


def _epsilon_closure(
    automaton: Automaton, seeds: set[str]
) -> tuple[set[str], list[dict[str, str]]]:
    """Traverse epsilon edges once per reachable state, including ε-loops safely."""
    closure = set(seeds)
    queue = list(state.id for state in automaton.states if state.id in seeds)
    fired: list[dict[str, str]] = []
    transitions_by_source: dict[str, list[Transition]] = {}
    for transition in automaton.transitions:
        if EPSILON in transition.symbols:
            transitions_by_source.setdefault(transition.from_, []).append(transition)
    index = 0
    while index < len(queue):
        current = queue[index]
        index += 1
        for transition in transitions_by_source.get(current, []):
            fired.append({"from": current, "to": transition.to, "symbol": EPSILON})
            if transition.to not in closure:
                closure.add(transition.to)
                queue.append(transition.to)
    return closure, fired


def _ordered(automaton: Automaton, states: set[str]) -> list[str]:
    return [state.id for state in automaton.states if state.id in states]


def simulate(automaton: Automaton, input_value: str) -> SimulationResult:
    """Run an input and return its decision plus an animation-ready trace."""
    start = automaton.start_state().id
    active = {start}
    trace: list[TraceStep] = []
    if automaton.type in {"NFA", "EPSILON_NFA"}:
        active, fired = _epsilon_closure(automaton, active)
        if automaton.type == "EPSILON_NFA":
            trace.append(TraceStep(
                title="Take the initial ε-closure",
                explanation="Before reading input, follow every ε transition from the start state.",
                data={"currentStates": [start], "nextStates": _ordered(automaton, active), "transitionsFired": fired},
            ))

    tokens = tokenize_input(input_value, automaton.alphabet)
    for index, token in enumerate(tokens):
        before = set(active)
        next_states: set[str] = set()
        fired: list[dict[str, str]] = []
        for transition in automaton.transitions:
            if transition.from_ not in active or EPSILON in transition.symbols:
                continue
            matched_symbols = [
                symbol for symbol in transition.symbols
                if token in expand_symbol(symbol)
            ]
            if matched_symbols:
                next_states.add(transition.to)
                fired.append({
                    "from": transition.from_,
                    "to": transition.to,
                    "symbols": matched_symbols,
                    "input": display_symbol(token),
                    "phase": "consume",
                })

        if automaton.type in {"NFA", "EPSILON_NFA"}:
            raw_next = set(next_states)
            next_states, epsilon_fired = _epsilon_closure(automaton, next_states)
            if automaton.type == "EPSILON_NFA":
                fired.extend({**edge, "phase": "epsilon-closure"} for edge in epsilon_fired)
        else:
            raw_next = set(next_states)

        trace.append(TraceStep(
            title=f"Read {display_symbol(token)!r}",
            explanation=(
                f"Follow matching transitions for {display_symbol(token)!r}, then take the ε-closure."
                if automaton.type == "EPSILON_NFA"
                else f"Follow every transition matching {display_symbol(token)!r} from the active state set."
            ),
            data={
                "index": index,
                "currentStates": _ordered(automaton, before),
                "symbolRead": display_symbol(token),
                "nextStates": _ordered(automaton, next_states),
                "consumingStates": _ordered(automaton, raw_next),
                "transitionsFired": fired,
            },
        ))
        active = next_states
        if not active:
            previous = _ordered(automaton, before)
            source = previous[0] if len(previous) == 1 else "{" + ", ".join(previous) + "}"
            reason = f"stuck at {source} on symbol {display_symbol(token)!r}"
            trace.append(TraceStep(
                title="No transition available",
                explanation=f"No active path can consume {display_symbol(token)!r}; the input is rejected.",
                data={"symbolRead": display_symbol(token), "currentStates": previous, "nextStates": []},
            ))
            trace.append(TraceStep(
                title="Rejected",
                explanation="The automaton has no active state after trying to consume the input symbol.",
                data={"status": "REJECTED", "reason": reason, "finalStates": []},
            ))
            return SimulationResult("REJECTED", False, reason, [], trace)

    accepting = {state.id for state in automaton.states if state.isAccepting}
    final_states = _ordered(automaton, active)
    accepting_active = active & accepting
    if accepting_active:
        result = SimulationResult("ACCEPTED", True, "ended in an accepting state", final_states, trace)
        explanation = "At least one active state is accepting, so the input is accepted."
    else:
        result = SimulationResult("REJECTED", False, "ended in a non-accepting state", final_states, trace)
        explanation = "No active state is accepting after the input is consumed."
    trace.append(TraceStep(
        title=result.status.title(),
        explanation=explanation,
        data={"finalStates": final_states, "acceptingStates": _ordered(automaton, accepting_active)},
    ))
    return result
