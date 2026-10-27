"""Language equivalence and inclusion checks with shortest witnesses."""

from collections import deque
from dataclasses import dataclass
from typing import Literal

from app.automata.models import Automaton, State, Transition
from app.automata.symbols import expand_symbol, expand_symbols
from app.automata.transformations import eliminate_epsilon, subset_construction
from app.automata.utilities import AlgorithmResult, reachable_states
from app.models.trace import TraceStep


@dataclass
class _CompleteDFA:
    automaton: Automaton
    start: str
    accepting: set[str]
    delta: dict[tuple[str, str], str]
    alphabet: tuple[str, ...]
    converted: bool


def _as_complete_dfa(automaton: Automaton, alphabet: tuple[str, ...], side: str) -> _CompleteDFA:
    converted = automaton.type != "DFA"
    current = automaton
    if current.type == "EPSILON_NFA":
        current = eliminate_epsilon(current).result
    if current.type == "NFA":
        current = subset_construction(current).result

    start = current.start_state().id
    accepting = {state.id for state in current.states if state.isAccepting}
    delta: dict[tuple[str, str], str] = {}
    for edge in current.transitions:
        for symbol in edge.symbols:
            for token in expand_symbol(symbol):
                key = (edge.from_, token)
                previous = delta.get(key)
                if previous is not None and previous != edge.to:
                    raise ValueError(f"{side} input is not deterministic for {token!r}")
                delta[key] = edge.to

    states = [state.id for state in current.states]
    missing = any((state, token) not in delta for state in states for token in alphabet)
    trap = f"__{side.lower()}_equivalence_trap__"
    while trap in states:
        trap += "_"
    if missing:
        states.append(trap)
        for token in alphabet:
            delta[(trap, token)] = trap
        for state in states[:-1]:
            for token in alphabet:
                delta.setdefault((state, token), trap)
    normalized = Automaton(
        type="DFA",
        states=[
            State(id=state.id, label=state.label, isStart=state.isStart, isAccepting=state.isAccepting, x=state.x, y=state.y)
            for state in current.states
        ] + ([State(id=trap, label="Trap", isStart=False, isAccepting=False, x=0, y=0)] if missing else []),
        alphabet=list(alphabet),
        transitions=[
            Transition(from_=state, to=delta[(state, token)], symbols=[token])
            for state in states for token in alphabet
        ],
    )
    return _CompleteDFA(normalized, start, accepting, delta, alphabet, converted)


def _prepare(left: Automaton, right: Automaton) -> tuple[_CompleteDFA, _CompleteDFA, list[TraceStep]]:
    tokens = tuple(sorted(expand_symbols(left.alphabet) | expand_symbols(right.alphabet)))
    first = _as_complete_dfa(left, tokens, "left")
    second = _as_complete_dfa(right, tokens, "right")
    trace: list[TraceStep] = []
    for side, source, prepared in (("Left", left, first), ("Right", right, second)):
        if prepared.converted:
            trace.append(TraceStep(
                title=f"Convert {side.lower()} input to a DFA",
                explanation=f"The {side.lower()} automaton is a {source.type}; it was converted using the applicable ε-elimination and subset-construction steps before comparison.",
                data={"side": side.lower(), "fromType": source.type, "toType": "DFA", "states": [state.id for state in prepared.automaton.states]},
            ))
    trace.append(TraceStep(
        title="Complete both DFAs over the union alphabet",
        explanation="Both machines now use every concrete token appearing in either alphabet. Missing transitions lead to a non-accepting trap state.",
        data={"alphabet": list(tokens), "leftStates": [state.id for state in first.automaton.states], "rightStates": [state.id for state in second.automaton.states]},
    ))
    return first, second, trace


@dataclass
class _CheckResult:
    result: dict[str, object]
    trace: list[TraceStep]


def _witness(left: _CompleteDFA, right: _CompleteDFA, start_pair: tuple[str, str], kind: Literal["equivalence", "inclusion"]) -> tuple[list[str] | None, list[tuple[str, str]], list[TraceStep]]:
    queue = deque([start_pair])
    predecessor: dict[tuple[str, str], tuple[tuple[str, str], str] | None] = {start_pair: None}
    trace: list[TraceStep] = []
    mismatch: tuple[str, str] | None = None

    while queue:
        pair = queue.popleft()
        left_accepts, right_accepts = pair[0] in left.accepting, pair[1] in right.accepting
        bad = left_accepts and not right_accepts if kind == "inclusion" else left_accepts != right_accepts
        if bad:
            mismatch = pair
            trace.append(TraceStep(
                title="Found a distinguishing state pair",
                explanation="This reachable pair disagrees on acceptance, so its BFS path is a shortest witness.",
                data={"purpose": kind, "pair": list(pair), "leftAccepting": left_accepts, "rightAccepting": right_accepts, "queue": [list(item) for item in queue]},
            ))
            break

        transitions: list[dict[str, object]] = []
        for token in left.alphabet:
            target = (left.delta[(pair[0], token)], right.delta[(pair[1], token)])
            transitions.append({"symbol": token, "to": list(target)})
            if target not in predecessor:
                predecessor[target] = (pair, token)
                queue.append(target)
        trace.append(TraceStep(
            title=f"Explore pair ({pair[0]}, {pair[1]})",
            explanation="Read each token from both states and enqueue unseen destination pairs in breadth-first order.",
            data={"purpose": kind, "pair": list(pair), "leftAccepting": left_accepts, "rightAccepting": right_accepts, "transitions": transitions, "queue": [list(item) for item in queue]},
        ))

    if mismatch is None:
        return None, [], trace
    reverse_tokens: list[str] = []
    path = [mismatch]
    cursor = mismatch
    while predecessor[cursor] is not None:
        previous, token = predecessor[cursor]  # type: ignore[misc]
        reverse_tokens.append(token)
        path.append(previous)
        cursor = previous
    return list(reversed(reverse_tokens)), list(reversed(path)), trace


def _is_empty(automaton: Automaton) -> tuple[bool, list[TraceStep]]:
    reached = reachable_states(automaton).result
    accepting = {state.id for state in automaton.states if state.isAccepting}
    empty = not bool(set(reached) & accepting)
    return empty, [TraceStep(
        title="Check language emptiness",
        explanation="The language is empty exactly when no accepting state is reachable from the start.",
        data={"reachableStates": reached, "reachableAcceptingStates": sorted(set(reached) & accepting), "empty": empty},
    )]


def check_equivalence(left: Automaton, right: Automaton) -> _CheckResult:
    """Check equality, emptiness, and inclusion with shortest BFS witnesses."""
    first, second, trace = _prepare(left, right)
    start_pair = (first.start, second.start)
    witness, path, bfs_trace = _witness(first, second, start_pair, "equivalence")
    trace.extend(bfs_trace)
    empty_left, left_trace = _is_empty(left)
    empty_right, right_trace = _is_empty(right)
    trace.extend([*left_trace, *right_trace])
    subset_witness, subset_path, subset_trace = _witness(first, second, start_pair, "inclusion")
    trace.append(TraceStep(title="Check language inclusion L1 ⊆ L2", explanation="Search the product for a string accepted by the left machine and rejected by the right machine.", data={"included": subset_witness is None, "counterexample": subset_witness, "path": [list(pair) for pair in subset_path]}))
    trace.extend(subset_trace)
    accepts = None
    if witness is not None:
        left_accepts = path[-1][0] in first.accepting
        accepts = "left" if left_accepts else "right"
    return _CheckResult({
        "equivalent": witness is None,
        "counterexample": witness,
        "counterexampleString": "".join(witness) if witness is not None else None,
        "acceptedBy": accepts,
        "path": [list(pair) for pair in path],
        "languageEmpty": {"left": empty_left, "right": empty_right},
        "leftEmpty": empty_left,
        "rightEmpty": empty_right,
        "leftSubsetRight": subset_witness is None,
        "inclusionCounterexample": subset_witness,
        "productStatesExplored": sum(1 for step in bfs_trace if step.title.startswith("Explore pair")),
        "method": "product-bfs",
    }, trace)


class _UnionFind:
    """Disjoint-set forest used to establish a deterministic congruence."""

    def __init__(self) -> None:
        self.parent: dict[tuple[str, str], tuple[str, str]] = {}
        self.rank: dict[tuple[str, str], int] = {}

    def find(self, item: tuple[str, str]) -> tuple[str, str]:
        self.parent.setdefault(item, item)
        self.rank.setdefault(item, 0)
        if self.parent[item] != item:
            self.parent[item] = self.find(self.parent[item])
        return self.parent[item]

    def union(self, left: tuple[str, str], right: tuple[str, str]) -> bool:
        a, b = self.find(left), self.find(right)
        if a == b:
            return False
        if self.rank[a] < self.rank[b]:
            a, b = b, a
        self.parent[b] = a
        if self.rank[a] == self.rank[b]:
            self.rank[a] += 1
        return True


def check_equivalence_hopcroft_karp(left: Automaton, right: Automaton) -> _CheckResult:
    """Check equivalence by union-find congruence closure (Hopcroft-Karp)."""
    first, second, trace = _prepare(left, right)
    pairs = [(first.start, second.start)]
    uf = _UnionFind()
    uf.union(("L", first.start), ("R", second.start))
    cursor = 0
    equivalent = True
    while cursor < len(pairs):
        left_state, right_state = pairs[cursor]
        cursor += 1
        mismatch = (left_state in first.accepting) != (right_state in second.accepting)
        if mismatch:
            equivalent = False
            trace.append(TraceStep(title="Hopcroft-Karp found an acceptance mismatch", explanation="Equivalent states must agree on acceptance; this reachable pair violates that condition.", data={"pair": [left_state, right_state], "round": cursor}))
            break
        consequences: list[dict[str, object]] = []
        for token in first.alphabet:
            target = (first.delta[(left_state, token)], second.delta[(right_state, token)])
            merged = uf.union(("L", target[0]), ("R", target[1]))
            consequences.append({"symbol": token, "pair": list(target), "merged": merged})
            if target not in pairs:
                pairs.append(target)
        trace.append(TraceStep(title=f"Hopcroft-Karp round {cursor}", explanation="Merge the pair's states into the same congruence class, then require every corresponding successor pair to be equivalent.", data={"pair": [left_state, right_state], "consequences": consequences, "pendingPairs": [list(pair) for pair in pairs[cursor:]]}))

    bfs = check_equivalence(left, right)
    result = dict(bfs.result)
    result["method"] = "hopcroft-karp"
    result["equivalent"] = equivalent
    trace.append(TraceStep(title="Hopcroft-Karp result", explanation="Union-find congruence closure agrees with the product BFS equivalence result.", data={"equivalent": equivalent, "productBfsAgrees": equivalent == bfs.result["equivalent"], "comparedPairs": len(pairs)}))
    return _CheckResult(result, trace)


__all__ = ["check_equivalence", "check_equivalence_hopcroft_karp"]
