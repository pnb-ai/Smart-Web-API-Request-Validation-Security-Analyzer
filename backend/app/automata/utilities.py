"""Pure analysis and completion helpers for finite automata."""

from dataclasses import dataclass
from typing import Generic, TypeVar

from app.automata.engine import _epsilon_closure, _ordered
from app.automata.models import Automaton, State, Transition
from app.automata.symbols import EPSILON, expand_symbol, expand_symbols
from app.models.trace import TraceStep

T = TypeVar("T")


@dataclass(frozen=True)
class AlgorithmResult(Generic[T]):
    result: T
    trace: list[TraceStep]


def epsilon_closure(automaton: Automaton, state_ids: set[str] | list[str]) -> AlgorithmResult[list[str]]:
    """Return the states reachable from seeds using only ε transitions."""
    unknown = set(state_ids) - {state.id for state in automaton.states}
    if unknown:
        raise ValueError(f"unknown state id(s): {', '.join(sorted(unknown))}")
    closure, fired = _epsilon_closure(automaton, set(state_ids))
    ordered = _ordered(automaton, closure)
    return AlgorithmResult(ordered, [TraceStep(
        title="Compute ε-closure",
        explanation="Collect each seed state and every state reachable by following only ε transitions.",
        data={"seedStates": _ordered(automaton, set(state_ids)), "states": ordered, "transitionsFired": fired},
    )])


def reachable_states(automaton: Automaton) -> AlgorithmResult[list[str]]:
    """Return states reachable from the start by any transition."""
    start = automaton.start_state().id
    reached = {start}
    queue = [start]
    trace = [TraceStep(
        title="Start reachability search",
        explanation="Begin a graph traversal at the unique start state.",
        data={"startState": start, "reachableStates": [start]},
    )]
    while queue:
        source = queue.pop(0)
        for transition in automaton.transitions:
            if transition.from_ == source and transition.to not in reached:
                reached.add(transition.to)
                queue.append(transition.to)
                trace.append(TraceStep(
                    title="Discover a reachable state",
                    explanation=f"A transition from {source} reaches {transition.to}.",
                    data={"from": source, "to": transition.to, "symbolLabels": transition.symbols, "reachableStates": _ordered(automaton, reached)},
                ))
    return AlgorithmResult(_ordered(automaton, reached), trace)


def dead_states(automaton: Automaton) -> AlgorithmResult[list[str]]:
    """Return states from which no accepting state can be reached."""
    predecessors: dict[str, set[str]] = {state.id: set() for state in automaton.states}
    for transition in automaton.transitions:
        predecessors[transition.to].add(transition.from_)
    can_accept = {state.id for state in automaton.states if state.isAccepting}
    queue = list(state.id for state in automaton.states if state.isAccepting)
    while queue:
        current = queue.pop(0)
        for previous in predecessors[current] - can_accept:
            can_accept.add(previous)
            queue.append(previous)
    dead = [state.id for state in automaton.states if state.id not in can_accept]
    return AlgorithmResult(dead, [TraceStep(
        title="Find states that can reach acceptance",
        explanation="Walk backward from accepting states; every remaining state is dead because no accepting state is reachable from it.",
        data={"canReachAccepting": _ordered(automaton, can_accept), "deadStates": dead},
    )])


def trap_states(automaton: Automaton) -> AlgorithmResult[list[str]]:
    """Return non-accepting states that loop on every concrete alphabet token."""
    alphabet_tokens = expand_symbols(automaton.alphabet)
    traps: list[str] = []
    for state in automaton.states:
        if state.isAccepting:
            continue
        destinations: dict[str, set[str]] = {}
        for transition in automaton.transitions:
            if transition.from_ == state.id and EPSILON not in transition.symbols:
                for token in expand_symbols(transition.symbols):
                    destinations.setdefault(token, set()).add(transition.to)
        if alphabet_tokens and all(destinations.get(token) == {state.id} for token in alphabet_tokens):
            traps.append(state.id)
    return AlgorithmResult(traps, [TraceStep(
        title="Identify trap states",
        explanation="A trap state is non-accepting and has a self-loop for every concrete alphabet token.",
        data={"alphabetTokens": sorted(alphabet_tokens), "trapStates": traps},
    )])


def classify_automaton(automaton: Automaton) -> AlgorithmResult[dict[str, object]]:
    """Classify the transition structure, independent of its declared label."""
    has_epsilon = any(EPSILON in transition.symbols for transition in automaton.transitions)
    deterministic = True
    ambiguous: list[dict[str, str]] = []
    destinations: dict[tuple[str, str], set[str]] = {}
    for transition in automaton.transitions:
        for symbol in transition.symbols:
            if symbol == EPSILON:
                continue
            for token in expand_symbol(symbol):
                destinations.setdefault((transition.from_, token), set()).add(transition.to)
    for (state_id, token), targets in destinations.items():
        if len(targets) > 1:
            deterministic = False
            ambiguous.append({"state": state_id, "symbol": token})
    classified_type = "EPSILON_NFA" if has_epsilon else "DFA" if deterministic else "NFA"
    result: dict[str, object] = {
        "type": classified_type,
        "isDFA": classified_type == "DFA",
        "isNFA": classified_type in {"DFA", "NFA"},
        "isEpsilonNFA": classified_type == "EPSILON_NFA",
        "hasEpsilonTransitions": has_epsilon,
        "isDeterministic": deterministic and not has_epsilon,
        "ambiguousStateSymbols": ambiguous,
    }
    return AlgorithmResult(result, [TraceStep(
        title="Classify transition structure",
        explanation=(
            "An ε edge makes this an ε-NFA. Otherwise, overlapping destinations make it an NFA; no ambiguity means it is a DFA."
        ),
        data=result,
    )])


def complete_dfa(automaton: Automaton, trap_id: str = "__trap__") -> AlgorithmResult[Automaton]:
    """Return a complete DFA, adding one trap state if any transitions are missing."""
    classification = classify_automaton(automaton).result
    if classification["type"] != "DFA":
        raise ValueError("only deterministic automata without ε transitions can be completed as a DFA")
    occupied_ids = {state.id for state in automaton.states}
    if trap_id in occupied_ids:
        suffix = 1
        while f"{trap_id}_{suffix}" in occupied_ids:
            suffix += 1
        trap_id = f"{trap_id}_{suffix}"

    token_to_labels: dict[str, list[str]] = {}
    for label in automaton.alphabet:
        for token in expand_symbol(label):
            token_to_labels.setdefault(token, []).append(label)

    additions: list[Transition] = []
    missing_by_state: dict[str, list[str]] = {}
    expanded_alphabet: set[str] = set()
    for state in automaton.states:
        covered: set[str] = set()
        for transition in automaton.transitions:
            if transition.from_ == state.id:
                covered.update(expand_symbols(transition.symbols))
        missing = set(token_to_labels) - covered
        if not missing:
            continue
        labels: list[str] = []
        remaining = set(missing)
        # Preserve a class edge when the whole class is missing; only split a
        # class into concrete labels when existing edges cover part of it.
        for label in sorted(automaton.alphabet, key=lambda item: (-len(expand_symbol(item)), item)):
            members = set(expand_symbol(label))
            if members and members <= remaining:
                labels.append(label)
                remaining -= members
        labels.extend(sorted(remaining))
        expanded_alphabet.update(remaining)
        additions.append(Transition.model_validate({"from": state.id, "to": trap_id, "symbols": labels}))
        missing_by_state[state.id] = labels

    states = list(automaton.states)
    if additions:
        states.append(State(
            id=trap_id,
            label="Trap",
            isStart=False,
            isAccepting=False,
            x=max((state.x for state in states), default=0) + 140,
            y=max((state.y for state in states), default=0) + 40,
        ))
        additions.append(Transition(from_=trap_id, to=trap_id, symbols=list(automaton.alphabet)))

    completed = Automaton(
        type="DFA",
        states=states,
        alphabet=[*automaton.alphabet, *sorted(expanded_alphabet - set(automaton.alphabet))],
        transitions=[*automaton.transitions, *additions],
    )
    trace = [TraceStep(
        title="Complete DFA",
        explanation="Add a non-accepting trap state for missing input tokens; any missing edge points to it and it loops on the full alphabet.",
        data={"trapState": trap_id if additions else None, "missingTransitions": missing_by_state, "addedTransitions": [t.model_dump(by_alias=True) for t in additions]},
    )]
    return AlgorithmResult(completed, trace)
