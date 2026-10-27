"""A small Thompson compiler for the regular-expression syntax used by the lab."""

from dataclasses import dataclass

from app.automata.models import Automaton, State, Transition
from app.models.trace import TraceStep


@dataclass
class _Fragment:
    start: int
    end: int


class _Parser:
    def __init__(self, pattern: str) -> None:
        self.pattern = pattern
        self.index = 0

    def parse(self):
        node = self.alternation()
        if self.index != len(self.pattern):
            raise ValueError(f"Unexpected {self.pattern[self.index]!r} at position {self.index}.")
        return node

    def alternation(self):
        choices = [self.concatenation()]
        while self.peek("|"):
            self.index += 1
            choices.append(self.concatenation())
        return choices[0] if len(choices) == 1 else ("alt", choices)

    def concatenation(self):
        parts = []
        while self.index < len(self.pattern) and self.pattern[self.index] not in ")|":
            parts.append(self.repetition())
        return ("concat", parts)

    def repetition(self):
        node = self.atom()
        if self.index < len(self.pattern) and self.pattern[self.index] in "*+?":
            operator = self.pattern[self.index]
            self.index += 1
            node = (operator, node)
            if self.index < len(self.pattern) and self.pattern[self.index] in "*+?":
                raise ValueError("Use one repetition operator per expression atom.")
        return node

    def atom(self):
        if self.index >= len(self.pattern):
            raise ValueError("Expected an expression atom.")
        char = self.pattern[self.index]
        self.index += 1
        if char == "(":
            node = self.alternation()
            if not self.peek(")"):
                raise ValueError("Unclosed group in regular expression.")
            self.index += 1
            return node
        if char == ")":
            raise ValueError("Unexpected closing parenthesis.")
        if char == "[":
            return ("set", self.character_class())
        if char == ".":
            return ("set", ["VCHAR"])
        if char == "\\":
            if self.index >= len(self.pattern):
                raise ValueError("A trailing backslash needs an escaped character.")
            escaped = self.pattern[self.index]
            self.index += 1
            classes = {"d": ["DIGIT"], "s": ["SP"], "w": ["ALPHA", "DIGIT", "_"]}
            return ("set", classes[escaped]) if escaped in classes else ("set", [escaped])
        if char in "^$":
            raise ValueError("Anchors are unnecessary; the automaton matches the complete input string.")
        return ("set", [char])

    def character_class(self) -> list[str]:
        values: list[str] = []
        while self.index < len(self.pattern) and self.pattern[self.index] != "]":
            first = self.class_character()
            if self.index + 1 < len(self.pattern) and self.pattern[self.index] == "-" and self.pattern[self.index + 1] != "]":
                self.index += 1
                last = self.class_character()
                if len(first) != 1 or len(last) != 1 or ord(first) > ord(last):
                    raise ValueError("Character class ranges must be ascending single characters.")
                values.extend(chr(code) for code in range(ord(first), ord(last) + 1))
            else:
                values.append(first)
        if self.index >= len(self.pattern) or self.pattern[self.index] != "]":
            raise ValueError("Unclosed character class.")
        self.index += 1
        if not values:
            raise ValueError("Character classes cannot be empty.")
        return list(dict.fromkeys(values))

    def class_character(self) -> str:
        char = self.pattern[self.index]
        self.index += 1
        if char == "\\":
            if self.index >= len(self.pattern):
                raise ValueError("A trailing backslash needs an escaped character.")
            char = self.pattern[self.index]
            self.index += 1
        return char

    def peek(self, value: str) -> bool:
        return self.index < len(self.pattern) and self.pattern[self.index] == value


def compile_regex(pattern: str) -> tuple[Automaton, list[TraceStep]]:
    """Compile a full-string regex to an ε-NFA and explain Thompson fragments."""
    if len(pattern) > 256:
        raise ValueError("Regular expressions are limited to 256 characters.")
    tree = _Parser(pattern).parse()
    next_id = 0
    transitions: list[Transition] = []
    steps: list[TraceStep] = []

    def state_id() -> int:
        nonlocal next_id
        value = next_id
        next_id += 1
        return value

    def edge(source: int, target: int, symbol: str) -> None:
        transitions.append(Transition(from_=f"q{source}", to=f"q{target}", symbols=[symbol]))

    def build(node) -> _Fragment:
        kind = node[0]
        if kind == "set":
            start, end = state_id(), state_id()
            for symbol in node[1]:
                edge(start, end, symbol)
            steps.append(TraceStep(title="Build symbol fragment", explanation="Create a two-state fragment for a literal, character class, or shorthand class.", data={"operator": "symbol", "symbols": node[1], "start": f"q{start}", "end": f"q{end}"}))
            return _Fragment(start, end)
        if kind == "concat":
            parts = node[1]
            if not parts:
                start, end = state_id(), state_id()
                edge(start, end, "ε")
                return _Fragment(start, end)
            fragments = [build(part) for part in parts]
            for previous, following in zip(fragments, fragments[1:]):
                edge(previous.end, following.start, "ε")
            steps.append(TraceStep(title="Join concatenated fragments", explanation="Connect each fragment's exit to the next fragment's entry with ε.", data={"operator": "concatenation", "fragments": [[f"q{part.start}", f"q{part.end}"] for part in fragments]}))
            return _Fragment(fragments[0].start, fragments[-1].end)
        if kind == "alt":
            start, end = state_id(), state_id()
            branches = [build(part) for part in node[1]]
            for part in branches:
                edge(start, part.start, "ε")
                edge(part.end, end, "ε")
            steps.append(TraceStep(title="Branch for alternation", explanation="Split with ε into each alternative and rejoin their exits.", data={"operator": "alternation", "branches": [[f"q{part.start}", f"q{part.end}"] for part in branches], "start": f"q{start}", "end": f"q{end}"}))
            return _Fragment(start, end)
        part = build(node[1])
        start, end = state_id(), state_id()
        edge(start, part.start, "ε")
        edge(part.end, end, "ε")
        if kind in ("*", "?"):
            edge(start, end, "ε")
        if kind in ("*", "+"):
            edge(part.end, part.start, "ε")
        steps.append(TraceStep(title=f"Apply {kind} repetition", explanation={"*": "Allow zero or more traversals of the fragment.", "+": "Require one traversal, then allow further traversals.", "?": "Allow either zero or one traversal."}[kind], data={"operator": kind, "fragment": [f"q{part.start}", f"q{part.end}"], "start": f"q{start}", "end": f"q{end}"}))
        return _Fragment(start, end)

    fragment = build(tree)
    alphabet = sorted({symbol for transition in transitions for symbol in transition.symbols if symbol != "ε"})
    automaton = Automaton(
        type="EPSILON_NFA",
        states=[State(id=f"q{index}", label=f"q{index}", isStart=index == fragment.start, isAccepting=index == fragment.end, x=float((index % 8) * 120), y=float((index // 8) * 100)) for index in range(next_id)],
        alphabet=alphabet,
        transitions=transitions,
    )
    steps.insert(0, TraceStep(title="Parse regular expression", explanation="The expression is parsed using grouping, alternation, concatenation, and one postfix repetition operator.", data={"pattern": pattern, "syntax": ["|", "()", "*", "+", "?", "[ranges]", "\\d", "\\s", "\\w", "."]}))
    steps.append(TraceStep(title="Finish ε-NFA", explanation="The start fragment entry is the start state and its exit is the only accepting state.", data={"startState": f"q{fragment.start}", "acceptingStates": [f"q{fragment.end}"], "stateCount": next_id}))
    return automaton, steps


__all__ = ["compile_regex"]
