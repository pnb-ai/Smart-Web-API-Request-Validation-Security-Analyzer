"""Combined-DFA lexer for HTTP request text.

Each token rule is compiled by Regex Lab's Thompson compiler. The rule NFAs
are joined under one ε start and determinized over the finite ASCII alphabet.
"""

from collections import deque
from dataclasses import dataclass
from functools import lru_cache
from string import ascii_letters, digits
from typing import Any

from app.automata.models import Automaton, State, Transition
from app.automata.regex import compile_regex
from app.automata.symbols import EPSILON, SYMBOL_CLASSES
from app.models.trace import TraceStep


@dataclass(frozen=True)
class TokenRule:
    kind: str
    pattern: str
    priority: int


_WORD = "[A-Za-z0-9._~-]+"
TOKEN_RULES = (
    TokenRule("CRLF", "\r\n", 0),
    TokenRule("WHITESPACE", "[ \t]+", 1),
    TokenRule("HTTP_VERSION", "HTTP/1\\.[01]", 2),
    TokenRule("METHOD", "(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS|TRACE|CONNECT)", 3),
    TokenRule("UUID", "[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", 4),
    TokenRule("PATH", f"/{_WORD}(/ {_WORD})*".replace(" ", ""), 5),
    TokenRule("QUERY_KEY", "[A-Za-z_][A-Za-z0-9._~-]*", 6),
    TokenRule("QUERY_VALUE", "[A-Za-z0-9._~-]+", 7),
    TokenRule("HEADER_NAME", "[A-Za-z][A-Za-z0-9-]*", 8),
    TokenRule("NUMBER", "[0-9]+", 9),
    TokenRule("IDENTIFIER", "[A-Za-z_][A-Za-z0-9._~-]*", 10),
    TokenRule("OPERATORS", "[=?&:]", 11),
    TokenRule("DELIMITERS", "[/;,]", 12),
)
_PUNCTUATION = {"=": "OPERATORS", "?": "OPERATORS", "&": "OPERATORS", ":": "OPERATORS", "/": "DELIMITERS", ";": "DELIMITERS", ",": "DELIMITERS"}


def _epsilon_closure(states: set[str], edges: dict[str, list[tuple[str, str]]]) -> frozenset[str]:
    result = set(states)
    stack = list(states)
    while stack:
        state = stack.pop()
        for symbol, target in edges.get(state, []):
            if symbol == EPSILON and target not in result:
                result.add(target)
                stack.append(target)
    return frozenset(result)


@lru_cache(maxsize=1)
def build_combined_dfa() -> tuple[Automaton, dict[str, str], list[TraceStep]]:
    """Compile every token regex and determinize the combined ε-NFA."""
    edges: dict[str, list[tuple[str, str]]] = {}
    accepts: dict[str, tuple[str, int]] = {}
    next_id = 0
    start = "q0"
    next_id = 1
    construction: list[TraceStep] = []
    for rule in TOKEN_RULES:
        nfa, trace = compile_regex(rule.pattern)
        prefix = f"r{rule.priority}_"
        remap = {state.id: f"{prefix}{state.id}" for state in nfa.states}
        nfa_start = next(state.id for state in nfa.states if state.isStart)
        edges.setdefault(start, []).append((EPSILON, remap[nfa_start]))
        for edge in nfa.transitions:
            edges.setdefault(remap[edge.from_], []).extend((symbol, remap[edge.to]) for symbol in edge.symbols)
        final = next(state.id for state in nfa.states if state.isAccepting)
        accepts[remap[final]] = (rule.kind, rule.priority)
        construction.append(TraceStep(title=f"Compile {rule.kind}", explanation=f"Regex Lab compiled {rule.kind} as an individual token automaton.", data={"pattern": rule.pattern, "stateCount": len(nfa.states), "regexTrace": [step.model_dump(mode="json") for step in trace]}))

    alphabet = sorted({character for code in range(128) for character in [chr(code)]})
    initial = _epsilon_closure({start}, edges)
    sets = [initial]
    index = {initial: 0}
    transitions: list[Transition] = []
    token_accept: dict[str, str] = {}
    queue = deque([initial])
    while queue:
        subset = queue.popleft()
        source = index[subset]
        winners = sorted((accepts[state] for state in subset if state in accepts), key=lambda item: item[1])
        if winners:
            token_accept[f"d{source}"] = winners[0][0]
        destinations: dict[int, list[str]] = {}
        for char in alphabet:
            reached = {target for state in subset for symbol, target in edges.get(state, []) if symbol != EPSILON and char in (SYMBOL_CLASSES.get(symbol, {symbol}))}
            if not reached:
                continue
            target_set = _epsilon_closure(reached, edges)
            if target_set not in index:
                index[target_set] = len(sets); sets.append(target_set); queue.append(target_set)
            destinations.setdefault(index[target_set], []).append(char)
        for target, chars in destinations.items():
            labels = _compress_symbols(set(chars))
            transitions.append(Transition(from_=f"d{source}", to=f"d{target}", symbols=labels))

    states = [State(id=f"d{i}", label=f"d{i}", isStart=i == 0, isAccepting=f"d{i}" in token_accept, x=float((i % 12) * 100), y=float((i // 12) * 85)) for i in range(len(sets))]
    dfa = Automaton(type="DFA", states=states, alphabet=sorted({symbol for edge in transitions for symbol in edge.symbols}), transitions=transitions)
    construction.append(TraceStep(title="Determinize combined rules", explanation="Subset construction merges every token automaton into one DFA; accepting ties use the declared rule priority.", data={"stateCount": len(states), "tokenPriorities": [{"type": rule.kind, "priority": rule.priority} for rule in TOKEN_RULES]}))
    return dfa, token_accept, construction


def _compress_symbols(characters: set[str]) -> list[str]:
    remaining = set(characters)
    labels: list[str] = []
    for name, members in sorted(SYMBOL_CLASSES.items(), key=lambda entry: (-len(entry[1]), entry[0])):
        if members and set(members) <= remaining:
            labels.append(name)
            remaining -= set(members)
    labels.extend(sorted(remaining))
    return labels


def tokenize_request(text: str) -> dict[str, Any]:
    """Scan with maximal munch and recover from invalid input one character at a time."""
    if len(text) > 20_000:
        raise ValueError("Request text is limited to 20,000 characters.")
    dfa, accepting, build_trace = build_combined_dfa()
    edge_map: dict[tuple[str, str], str] = {}
    for edge in dfa.transitions:
        for symbol in edge.symbols:
            members = SYMBOL_CLASSES.get(symbol, {symbol})
            for char in members:
                edge_map[(edge.from_, char)] = edge.to
    transitions_by_state: dict[str, list[str]] = {}
    for edge in dfa.transitions:
        transitions_by_state.setdefault(edge.from_, []).append(edge.to)
    tokens: list[dict[str, Any]] = []
    steps: list[TraceStep] = [*build_trace]
    offset = 0
    line, column = 1, 1
    query_mode: str | None = None
    while offset < len(text):
        start_offset, start_line, start_column = offset, line, column
        state = "d0"
        path = [state]
        cursor = offset
        best: tuple[int, str] | None = None
        while cursor < len(text):
            target = edge_map.get((state, text[cursor]))
            if target is None:
                break
            state = target; cursor += 1; path.append(state)
            if state in accepting:
                best = (cursor, accepting[state])
        if best is None:
            raw = text[offset]
            end = offset + 1
            kind = "ERROR"
            explanation = "Unterminated CRLF; expected LF after CR." if raw == "\r" else "Illegal character; skipped it and resumed scanning."
            token_path = path
            value = raw
        else:
            end, kind = best
            value = text[offset:end]
            explanation = ""
            token_path = path[:end - offset + 1]
            if kind == "WHITESPACE" and any(token["type"] == "PATH" and token["line"] == start_line for token in tokens):
                remainder = text[end:]
                if remainder and not remainder.startswith("HTTP/") and not remainder.startswith("\r\n"):
                    kind = "ERROR"
                    explanation = "Space in path; paths cannot contain unescaped spaces."
            # Classify ambiguous generic words by their request-line/query/header context.
            if kind == "QUERY_KEY" and query_mode != "key": kind = "IDENTIFIER"
            if kind in {"QUERY_KEY", "IDENTIFIER", "NUMBER"} and query_mode == "value": kind = "QUERY_VALUE"
            if kind in {"QUERY_KEY", "IDENTIFIER"} and start_column == 1 and " " not in text[offset:end] and "\r" not in value:
                following = text[end:end + 1]
                if following == ":": kind = "HEADER_NAME"
            if value == "?": query_mode = "key"
            elif value == "=": query_mode = "value"
            elif value == "&": query_mode = "key"
            elif value in {"\r\n", "\n", " ", "\t"}: query_mode = None
        end_line, end_column = start_line, start_column
        for char in text[start_offset:end]:
            if char == "\n": end_line += 1; end_column = 1
            else: end_column += 1
        token = {"type": kind, "value": value, "line": start_line, "column": start_column, "endLine": end_line, "endColumn": end_column, "start": start_offset, "end": end, "dfaPath": token_path, "error": explanation or None}
        tokens.append(token)
        steps.append(TraceStep(title=f"Scan {kind}", explanation=explanation or f"Maximal munch consumed {len(value)} character(s) as {kind}.", data={"token": token, "states": token_path, "startOffset": start_offset, "endOffset": end}))
        offset = end
        line, column = end_line, end_column
    return {"tokens": tokens, "automaton": dfa.model_dump(by_alias=True, mode="json"), "trace": [step.model_dump(mode="json") for step in steps]}


__all__ = ["TOKEN_RULES", "build_combined_dfa", "tokenize_request"]
