"""Language-preserving conversions and DFA minimizers with visual traces."""

from collections import deque
from dataclasses import dataclass
from itertools import combinations
from typing import Literal

from app.automata.models import Automaton, State, Transition
from app.automata.symbols import EPSILON, expand_symbol, expand_symbols
from app.automata.utilities import AlgorithmResult, epsilon_closure, reachable_states
from app.models.trace import TraceStep


def _state_order(automaton: Automaton, values: set[str] | frozenset[str]) -> list[str]:
    return [state.id for state in automaton.states if state.id in values]


def _labels_for_tokens(tokens: set[str], alphabet: list[str]) -> list[str]:
    """Cover a concrete token set with non-overlapping original class labels."""
    remaining = set(tokens)
    labels: list[str] = []
    for label in sorted(alphabet, key=lambda item: (-len(expand_symbol(item)), item)):
        members = set(expand_symbol(label))
        if members and members <= remaining:
            labels.append(label)
            remaining -= members
    labels.extend(sorted(remaining))
    return labels


def _transitions_from_token_map(
    sources: list[str],
    token_destinations: dict[tuple[str, str], set[str]],
    source_alphabet: list[str],
) -> list[Transition]:
    result: list[Transition] = []
    tokens = sorted(expand_symbols(source_alphabet))
    for source in sources:
        by_target: dict[frozenset[str], set[str]] = {}
        for token in tokens:
            targets = frozenset(token_destinations.get((source, token), set()))
            if targets:
                by_target.setdefault(targets, set()).add(token)
        for targets, matched_tokens in by_target.items():
            symbols = _labels_for_tokens(matched_tokens, source_alphabet)
            if symbols:
                for target in _state_order_from_values(sources, targets):
                    result.append(Transition(from_=source, to=target, symbols=symbols))
    return result


def _state_order_from_values(order: list[str], values: frozenset[str]) -> list[str]:
    return [state for state in order if state in values]


def eliminate_epsilon(automaton: Automaton) -> AlgorithmResult[Automaton]:
    """Remove ε edges using E(q) and E(move(E(q), a)) for each input token."""
    if automaton.type != "EPSILON_NFA":
        raise ValueError("epsilon elimination requires an EPSILON_NFA")

    closures = {state.id: set(epsilon_closure(automaton, {state.id}).result) for state in automaton.states}
    trace: list[TraceStep] = [TraceStep(
        title=f"Compute ε-closure of {state.id}",
        explanation=f"Start at {state.id} and follow every ε transition, including chains, until no new states are reached.",
        data={"state": state.id, "closure": _state_order(automaton, closures[state.id])},
    ) for state in automaton.states]

    tokens = sorted(expand_symbols(automaton.alphabet))
    token_destinations: dict[tuple[str, str], set[str]] = {}
    for state in automaton.states:
        for token in tokens:
            moved = {
                transition.to
                for transition in automaton.transitions
                if transition.from_ in closures[state.id]
                and EPSILON not in transition.symbols
                and any(token in expand_symbol(symbol) for symbol in transition.symbols)
            }
            targets = set().union(*(closures[target] for target in moved)) if moved else set()
            if targets:
                token_destinations[(state.id, token)] = targets
            trace.append(TraceStep(
                title=f"Compute transitions from {state.id} on {token!r}",
                explanation="Take the ε-closure, consume the symbol, then take ε-closure again from every destination.",
                data={"source": state.id, "symbol": token, "sourceClosure": _state_order(automaton, closures[state.id]), "movedStates": _state_order(automaton, moved), "destinationClosure": _state_order(automaton, targets)},
            ))

    old_accepting = {state.id for state in automaton.states if state.isAccepting}
    accepting = {state.id for state in automaton.states if closures[state.id] & old_accepting}
    transitions = _transitions_from_token_map([state.id for state in automaton.states], token_destinations, automaton.alphabet)
    result = Automaton(
        type="NFA",
        states=[state.model_copy(update={"isAccepting": state.id in accepting}) for state in automaton.states],
        alphabet=list(automaton.alphabet),
        transitions=transitions,
    )
    trace.extend([
        TraceStep(
            title="Build ε-free transition relation",
            explanation="Combine symbols that lead to the same destination set and remove all ε edges.",
            data={"transitions": [transition.model_dump(by_alias=True) for transition in transitions]},
        ),
        TraceStep(
            title="Update accepting states",
            explanation="A state accepts when its ε-closure contains an accepting state from the original machine.",
            data={"originalAcceptingStates": _state_order(automaton, old_accepting), "newAcceptingStates": _state_order(automaton, accepting)},
        ),
    ])
    return AlgorithmResult(result, trace)


def subset_construction(automaton: Automaton) -> AlgorithmResult[Automaton]:
    """Build only reachable DFA subsets, treating named classes as token sets."""
    if automaton.type != "NFA":
        raise ValueError("subset construction requires an NFA without ε transitions")

    state_ids = [state.id for state in automaton.states]
    state_by_id = {state.id: state for state in automaton.states}
    accepting = {state.id for state in automaton.states if state.isAccepting}
    start = frozenset({automaton.start_state().id})
    tokens = sorted(expand_symbols(automaton.alphabet))
    destination_map: dict[tuple[str, str], set[str]] = {}
    for transition in automaton.transitions:
        for symbol in transition.symbols:
            if symbol == EPSILON:
                raise ValueError("subset construction requires an NFA without ε transitions")
            for token in expand_symbol(symbol):
                destination_map.setdefault((transition.from_, token), set()).add(transition.to)

    subsets: list[frozenset[str]] = [start]
    # Keep diagram labels short; the trace records each generated state's source subset.
    subset_names: dict[frozenset[str], str] = {start: "q0"}

    def subset_name(subset: frozenset[str]) -> str:
        if subset not in subset_names:
            subset_names[subset] = f"q{len(subset_names)}"
        return subset_names[subset]
    queue: deque[frozenset[str]] = deque([start])
    seen = {start}
    subset_transitions: list[Transition] = []
    trace = [TraceStep(
        title="Initialize subset queue",
        explanation="Begin from the NFA start state. Only subsets reached by processing this queue become DFA states.",
        data={"dfaState": subset_name(start), "nfaStates": _state_order(automaton, set(start)), "queue": [subset_name(start)], "processed": []},
    )]

    while queue:
        current = queue.popleft()
        grouped_tokens: dict[frozenset[str], set[str]] = {}
        for token in tokens:
            destinations = frozenset(
                target
                for source in current
                for target in destination_map.get((source, token), set())
            )
            grouped_tokens.setdefault(destinations, set()).add(token)
        rows: list[dict[str, object]] = []
        for targets, matched_tokens in grouped_tokens.items():
            name = subset_name(targets)
            labels = _labels_for_tokens(matched_tokens, automaton.alphabet)
            is_new = targets not in seen
            if is_new:
                seen.add(targets)
                subsets.append(targets)
                queue.append(targets)
            if labels:
                subset_transitions.append(Transition(from_=subset_name(current), to=name, symbols=labels))
            rows.append({"symbols": labels, "expandedSymbols": sorted(matched_tokens), "destinationSet": _state_order(automaton, set(targets)), "destinationState": name, "newState": is_new})

        trace.append(TraceStep(
            title=f"Process subset {subset_name(current)}",
            explanation="For each input symbol, union all NFA destinations from states in this subset; enqueue each newly reached subset once.",
            data={"sourceState": subset_name(current), "sourceSet": _state_order(automaton, set(current)), "transitions": rows, "queue": [subset_name(item) for item in queue], "processed": [subset_name(item) for item in subsets if item not in queue], "subsetTable": [{"dfaState": subset_name(item), "nfaStates": _state_order(automaton, set(item))} for item in subsets]},
        ))

    # subset_transitions use compact ids; the trace maps each id back to its full subset.
    alphabet = list(dict.fromkeys(symbol for transition in subset_transitions for symbol in transition.symbols))
    dfa_states = [State(
        id=subset_name(subset),
        label=subset_name(subset),
        isStart=subset == start,
        isAccepting=bool(set(subset) & accepting),
        x=sum(state_by_id[item].x for item in subset) / len(subset) if subset else 0,
        y=sum(state_by_id[item].y for item in subset) / len(subset) if subset else 0,
    ) for subset in subsets]
    result = Automaton(type="DFA", states=dfa_states, alphabet=alphabet, transitions=subset_transitions)
    trace.append(TraceStep(
        title="Name reachable DFA states",
        explanation="Each compactly named DFA state represents one reachable subset of NFA states. The mapping below keeps the full subset visible in the trace.",
        data={"states": [{"id": state.id, "nfaStates": _state_order(automaton, set(subset)), "isAccepting": state.isAccepting} for state, subset in zip(dfa_states, subsets)], "stateCount": len(dfa_states), "transitionCount": len(subset_transitions)},
    ))
    return AlgorithmResult(result, trace)


@dataclass
class _MinimizationInput:
    automaton: Automaton
    state_ids: list[str]
    tokens: list[str]
    delta: dict[tuple[str, str], str]
    accepting: set[str]
    sink: str | None
    trace: list[TraceStep]


def _prepare_dfa(automaton: Automaton) -> _MinimizationInput:
    if automaton.type != "DFA":
        raise ValueError("DFA minimization requires a DFA")
    reachable = reachable_states(automaton).result
    reachable_set = set(reachable)
    unreachable = [state.id for state in automaton.states if state.id not in reachable_set]
    states = [state for state in automaton.states if state.id in reachable_set]
    transitions = [transition for transition in automaton.transitions if transition.from_ in reachable_set and transition.to in reachable_set]
    trimmed = Automaton(type="DFA", states=states, alphabet=list(automaton.alphabet), transitions=transitions)
    trace: list[TraceStep] = [TraceStep(
        title="Remove unreachable states",
        explanation="Start from the DFA start state and discard states that no input path can reach.",
        data={"reachableStates": reachable, "removedStates": unreachable, "beforeCount": len(automaton.states), "afterCount": len(states)},
    )]
    tokens = sorted(expand_symbols(trimmed.alphabet))
    ids = [state.id for state in states]
    ids_set = set(ids)
    delta: dict[tuple[str, str], str] = {}
    for transition in trimmed.transitions:
        for symbol in transition.symbols:
            for token in expand_symbol(symbol):
                delta[(transition.from_, token)] = transition.to
    missing = [(state_id, token) for state_id in ids for token in tokens if (state_id, token) not in delta]
    sink: str | None = None
    if missing:
        sink = "__implicit_sink__"
        suffix = 1
        while sink in ids_set:
            sink = f"__implicit_sink_{suffix}__"
            suffix += 1
        ids.append(sink)
        for state_id, token in missing:
            delta[(state_id, token)] = sink
        for token in tokens:
            delta[(sink, token)] = sink
        trace.append(TraceStep(
            title="Model missing edges with an implicit sink",
            explanation="For the distinguishability calculation, every missing DFA edge leads to a non-accepting sink that loops on every symbol. A sink-only result can be omitted from the final partial DFA.",
            data={"sinkState": sink, "missingTransitions": [{"from": state_id, "symbol": token, "to": sink} for state_id, token in missing], "completedStateCount": len(ids)},
        ))
    return _MinimizationInput(trimmed, ids, tokens, delta, {state.id for state in states if state.isAccepting}, sink, trace)


def _pair_key(left: str, right: str, order: list[str]) -> tuple[str, str]:
    return (left, right) if order.index(left) < order.index(right) else (right, left)


def minimize_table(automaton: Automaton) -> AlgorithmResult[Automaton]:
    """Minimize a DFA using the Myhill–Nerode table-filling algorithm."""
    prepared = _prepare_dfa(automaton)
    ids = prepared.state_ids
    accepting = prepared.accepting
    pairs = list(combinations(ids, 2))
    marked: dict[tuple[str, str], dict[str, object]] = {}
    initial: list[dict[str, object]] = []
    for left, right in pairs:
        if (left in accepting) != (right in accepting):
            marked[(left, right)] = {"reason": "finality", "witness": None}
            initial.append({"states": [left, right], "reason": "one accepting and one non-accepting"})
    prepared.trace.append(TraceStep(
        title="Initialize distinguishability table",
        explanation="Mark every pair where exactly one state is accepting. These pairs already differ on the empty suffix.",
        data={"states": ids, "acceptingStates": sorted(accepting), "initiallyMarked": initial, "unmarkedPairs": [[a, b] for a, b in pairs if (a, b) not in marked]},
    ))

    round_number = 0
    while True:
        round_number += 1
        additions: list[dict[str, object]] = []
        for left, right in pairs:
            if (left, right) in marked:
                continue
            for token in prepared.tokens:
                left_target = prepared.delta[(left, token)]
                right_target = prepared.delta[(right, token)]
                successor_pair = _pair_key(left_target, right_target, ids) if left_target != right_target else None
                if successor_pair and successor_pair in marked:
                    marked[(left, right)] = {"reason": "successors", "witness": token, "successorPair": list(successor_pair)}
                    additions.append({"states": [left, right], "symbol": token, "successors": [left_target, right_target], "distinguishedBy": list(successor_pair)})
                    break
        prepared.trace.append(TraceStep(
            title=f"Distinguishability pass {round_number}",
            explanation="Mark a pair when some symbol sends its two states to a pair already known to be distinguishable.",
            data={"round": round_number, "newlyMarked": additions, "markedPairs": [{"states": [left, right], **marked[(left, right)]} for left, right in pairs if (left, right) in marked], "unmarkedPairs": [[left, right] for left, right in pairs if (left, right) not in marked]},
        ))
        if not additions:
            break

    blocks = _equivalence_blocks(ids, marked)
    result, quotient_data = _quotient(prepared, blocks, automaton.alphabet)
    prepared.trace.append(TraceStep(
        title="Merge indistinguishable states",
        explanation="Unmarked pairs are language-equivalent. Merge their equivalence classes to form the minimal DFA.",
        data={**quotient_data, "algorithm": "table-filling", "minimalStateCount": len(result.states)},
    ))
    return AlgorithmResult(result, prepared.trace)


def _equivalence_blocks(ids: list[str], marked: dict[tuple[str, str], dict[str, object]]) -> list[set[str]]:
    remaining = set(ids)
    blocks: list[set[str]] = []
    while remaining:
        seed = next(state for state in ids if state in remaining)
        block = {state for state in remaining if state == seed or _pair_key(seed, state, ids) not in marked}
        blocks.append(block)
        remaining -= block
    return blocks


def minimize_hopcroft(automaton: Automaton) -> AlgorithmResult[Automaton]:
    """Minimize a DFA with Hopcroft partition refinement."""
    prepared = _prepare_dfa(automaton)
    ids = prepared.state_ids
    accepting = set(prepared.accepting)
    nonaccepting = set(ids) - accepting
    partitions = [block for block in (accepting, nonaccepting) if block]
    work = deque([min(partitions, key=lambda block: (len(block), min(ids.index(s) for s in block)))]) if partitions else deque()
    prepared.trace.append(TraceStep(
        title="Initialize Hopcroft partitions",
        explanation="Separate accepting and non-accepting states; repeatedly split blocks whose states react differently to a symbol.",
        data={"partitions": [_ordered_by_ids(ids, block) for block in partitions], "workQueue": [_ordered_by_ids(ids, block) for block in work]},
    ))

    round_number = 0
    while work:
        splitter = work.popleft()
        round_number += 1
        splits: list[dict[str, object]] = []
        for token in prepared.tokens:
            predecessors = {state for state in ids if prepared.delta[(state, token)] in splitter}
            for block in list(partitions):
                intersection = block & predecessors
                difference = block - predecessors
                if not intersection or not difference:
                    continue
                partitions.remove(block)
                partitions.extend((intersection, difference))
                split_info = {"symbol": token, "originalBlock": _ordered_by_ids(ids, block), "into": [_ordered_by_ids(ids, intersection), _ordered_by_ids(ids, difference)]}
                splits.append(split_info)
                queued = next((item for item in work if item == block), None)
                if queued is not None:
                    work.remove(queued)
                    work.extend((intersection, difference))
                else:
                    work.append(min((intersection, difference), key=lambda item: (len(item), min(ids.index(s) for s in item))))
        prepared.trace.append(TraceStep(
            title=f"Hopcroft refinement round {round_number}",
            explanation="Use the splitter block to find states that transition into it; split any partition containing both such states and non-predecessors.",
            data={"splitter": _ordered_by_ids(ids, splitter), "splits": splits, "partitions": [_ordered_by_ids(ids, block) for block in partitions], "workQueue": [_ordered_by_ids(ids, block) for block in work]},
        ))

    blocks = sorted(partitions, key=lambda block: min(ids.index(state) for state in block))
    result, quotient_data = _quotient(prepared, blocks, automaton.alphabet)
    prepared.trace.append(TraceStep(
        title="Merge equivalent states",
        explanation="The stable partitions are the DFA's equivalence classes. Merge each class to produce the minimal DFA.",
        data={**quotient_data, "algorithm": "hopcroft", "minimalStateCount": len(result.states)},
    ))
    return AlgorithmResult(result, prepared.trace)


def _ordered_by_ids(ids: list[str], states: set[str]) -> list[str]:
    return [state for state in ids if state in states]


def _quotient(prepared: _MinimizationInput, blocks: list[set[str]], original_alphabet: list[str]) -> tuple[Automaton, dict[str, object]]:
    original_states = {state.id: state for state in prepared.automaton.states}
    sink = prepared.sink
    retained = [block for block in blocks if not (sink is not None and block == {sink})]
    block_name: dict[str, str] = {}
    states: list[State] = []
    merged: list[dict[str, object]] = []
    for block in retained:
        members = _ordered_by_ids(prepared.state_ids, block - ({sink} if sink else set()))
        if not members:
            continue
        identifier = members[0]
        label = identifier
        for member in block:
            block_name[member] = identifier
        members_states = [original_states[item] for item in members]
        states.append(State(
            id=identifier,
            label=label,
            isStart=any(state.isStart for state in members_states),
            isAccepting=any(state.isAccepting for state in members_states),
            x=sum(state.x for state in members_states) / len(members_states),
            y=sum(state.y for state in members_states) / len(members_states),
        ))
        merged.append({"newState": identifier, "mergedStates": members})

    token_destinations: dict[tuple[str, str], set[str]] = {}
    for block in retained:
        members = _ordered_by_ids(prepared.state_ids, block)
        if not members:
            continue
        representative = members[0]
        source_name = block_name[representative]
        for token in prepared.tokens:
            target = prepared.delta[(representative, token)]
            target_name = block_name.get(target)
            if target_name is not None:
                token_destinations[(source_name, token)] = {target_name}
    output_ids = [state.id for state in states]
    transitions = _transitions_from_token_map(output_ids, token_destinations, original_alphabet)
    alphabet = list(dict.fromkeys(symbol for transition in transitions for symbol in transition.symbols))
    result = Automaton(type="DFA", states=states, alphabet=alphabet, transitions=transitions)
    return result, {"equivalenceClasses": merged, "transitions": [transition.model_dump(by_alias=True) for transition in transitions]}


def run_pipeline(automaton: Automaton, minimizer: Literal["table", "hopcroft"] = "table") -> dict[str, object]:
    """Run the applicable ε-elimination, subset and minimization stages."""
    current = automaton
    intermediates: list[dict[str, object]] = []
    all_trace: list[TraceStep] = []
    if current.type == "EPSILON_NFA":
        converted = eliminate_epsilon(current)
        current = converted.result
        intermediates.append(_intermediate("epsilon-elimination", current, converted.trace))
        all_trace.extend(_pipeline_trace("epsilon-elimination", converted.trace))
    if current.type == "NFA":
        converted = subset_construction(current)
        current = converted.result
        intermediates.append(_intermediate("subset-construction", current, converted.trace))
        all_trace.extend(_pipeline_trace("subset-construction", converted.trace))
    minimized = minimize_hopcroft(current) if minimizer == "hopcroft" else minimize_table(current)
    current = minimized.result
    intermediates.append(_intermediate(f"minimize-{minimizer}", current, minimized.trace))
    all_trace.extend(_pipeline_trace(f"minimize-{minimizer}", minimized.trace))
    return {"result": current, "trace": all_trace, "intermediateAutomata": intermediates}


def _pipeline_trace(stage: str, trace: list[TraceStep]) -> list[TraceStep]:
    return [TraceStep(title=step.title, explanation=step.explanation, data={"stage": stage, **step.data}) for step in trace]


def _intermediate(operation: str, automaton: Automaton, trace: list[TraceStep]) -> dict[str, object]:
    return {"operation": operation, "automaton": automaton, "trace": trace}
