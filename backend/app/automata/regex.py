"""A position-aware regex parser and Thompson ε-NFA compiler.

This intentionally implements a small regular language instead of delegating
to Python's regex engine, so parsing and construction remain inspectable.
"""

from dataclasses import dataclass
from string import ascii_letters, digits

from app.automata.models import Automaton, State, Transition
from app.automata.symbols import SYMBOL_CLASSES
from app.models.trace import TraceStep

UNIVERSE = {chr(code) for code in range(128)}
SHORTHANDS = {
    "d": set(digits),
    "w": set(ascii_letters + digits + "_"),
    "s": {" ", "\t", "\n", "\r", "\f", "\v"},
}


@dataclass(frozen=True)
class RegexNode:
    kind: str
    value: object = None
    children: tuple["RegexNode", ...] = ()
    position: int = 0

    def json(self) -> dict[str, object]:
        result: dict[str, object] = {"type": self.kind, "position": self.position}
        if self.value is not None:
            result["value"] = sorted(self.value) if isinstance(self.value, set) else self.value
        if self.children:
            result["children"] = [child.json() for child in self.children]
        return result


class RegexSyntaxError(ValueError):
    def __init__(self, message: str, position: int) -> None:
        self.position = position
        super().__init__(f"{message} at position {position}.")


class RegexParser:
    def __init__(self, pattern: str) -> None:
        self.pattern = pattern
        self.index = 0

    def parse(self) -> RegexNode:
        if not self.pattern:
            return RegexNode("concat", children=(), position=0)
        node = self.alternation()
        if self.index != len(self.pattern):
            raise RegexSyntaxError(f"Unexpected {self.pattern[self.index]!r}", self.index)
        return node

    def alternation(self) -> RegexNode:
        position = self.index
        choices = [self.concatenation()]
        while self.peek("|"):
            self.index += 1
            if self.index == len(self.pattern) or self.peek(")") or self.peek("|"):
                raise RegexSyntaxError("Expected an expression after '|'", self.index)
            choices.append(self.concatenation())
        return choices[0] if len(choices) == 1 else RegexNode("union", children=tuple(choices), position=position)

    def concatenation(self) -> RegexNode:
        position = self.index
        parts = []
        while self.index < len(self.pattern) and self.pattern[self.index] not in ")|":
            parts.append(self.repetition())
        return parts[0] if len(parts) == 1 else RegexNode("concat", children=tuple(parts), position=position)

    def repetition(self) -> RegexNode:
        node = self.atom()
        if self.index >= len(self.pattern):
            return node
        position = self.index
        char = self.pattern[self.index]
        if char in "*+?":
            self.index += 1
            node = RegexNode({"*": "star", "+": "plus", "?": "optional"}[char], children=(node,), position=position)
        elif char == "{":
            node = self.bounded(node, position)
        if self.index < len(self.pattern) and self.pattern[self.index] in "*+?{":
            raise RegexSyntaxError("Only one repetition operator may follow an atom", self.index)
        return node

    def bounded(self, node: RegexNode, position: int) -> RegexNode:
        self.index += 1
        start = self.index
        while self.index < len(self.pattern) and self.pattern[self.index].isdigit():
            self.index += 1
        if start == self.index:
            raise RegexSyntaxError("Expected a repetition count", self.index)
        minimum = int(self.pattern[start:self.index])
        maximum: int | None = minimum
        if self.peek(","):
            self.index += 1
            upper = self.index
            while self.index < len(self.pattern) and self.pattern[self.index].isdigit():
                self.index += 1
            maximum = int(self.pattern[upper:self.index]) if upper != self.index else None
        if not self.peek("}"):
            raise RegexSyntaxError("Expected '}' to close repetition bounds", self.index)
        self.index += 1
        if maximum is not None and maximum < minimum:
            raise RegexSyntaxError("Repetition upper bound is smaller than its lower bound", position)
        if minimum > 64 or (maximum is not None and maximum > 64):
            raise RegexSyntaxError("Repetition counts are limited to 64", position)
        return RegexNode("repeat", (minimum, maximum), (node,), position)

    def atom(self) -> RegexNode:
        if self.index >= len(self.pattern):
            raise RegexSyntaxError("Expected an expression atom", self.index)
        position = self.index
        char = self.pattern[self.index]
        self.index += 1
        if char == "(":
            if self.peek("?"):
                raise RegexSyntaxError("Lookarounds and special groups are not supported", position)
            child = self.alternation()
            if not self.peek(")"):
                raise RegexSyntaxError("Unclosed group", position)
            self.index += 1
            return child
        if char == ")":
            raise RegexSyntaxError("Unexpected closing parenthesis", position)
        if char == "[":
            return RegexNode("class", self.character_class(position), position=position)
        if char == ".":
            return RegexNode("class", UNIVERSE - {"\n"}, position=position)
        if char == "\\":
            return RegexNode("class", self.escape(position), position=position)
        if char in "^$":
            raise RegexSyntaxError("Anchors are unnecessary because matching uses the complete input", position)
        if char in "*+?{}]":
            raise RegexSyntaxError(f"Unexpected operator {char!r}", position)
        return RegexNode("class", {char}, position=position)

    def character_class(self, position: int) -> set[str]:
        negate = self.peek("^")
        if negate:
            self.index += 1
        values: set[str] = set()
        first_item = True
        while self.index < len(self.pattern) and (self.pattern[self.index] != "]" or first_item):
            first_item = False
            first = self.class_atom()
            if len(first) == 1 and self.peek("-") and self.index + 1 < len(self.pattern) and self.pattern[self.index + 1] != "]":
                dash_position = self.index
                self.index += 1
                last = self.class_atom()
                if len(last) != 1:
                    raise RegexSyntaxError("Range endpoints must be literal characters", dash_position)
                a, b = next(iter(first)), next(iter(last))
                if ord(a) > ord(b):
                    raise RegexSyntaxError("Character class ranges must be ascending", dash_position)
                values.update(chr(code) for code in range(ord(a), ord(b) + 1))
            else:
                values.update(first)
        if not self.peek("]"):
            raise RegexSyntaxError("Unclosed character class", position)
        self.index += 1
        if not values:
            raise RegexSyntaxError("Character class cannot be empty", position)
        return UNIVERSE - values if negate else values

    def class_atom(self) -> set[str]:
        position = self.index
        char = self.pattern[self.index]
        self.index += 1
        if char == "\\":
            return self.escape(position)
        return {char}

    def escape(self, position: int) -> set[str]:
        if self.index >= len(self.pattern):
            raise RegexSyntaxError("Trailing backslash needs an escaped character", position)
        char = self.pattern[self.index]
        self.index += 1
        if char in SHORTHANDS:
            return set(SHORTHANDS[char])
        if char.isalnum():
            raise RegexSyntaxError(f"Unknown escape \\{char}", position)
        return {char}

    def peek(self, value: str) -> bool:
        return self.index < len(self.pattern) and self.pattern[self.index] == value


@dataclass
class _Fragment:
    start: int
    end: int


def compile_regex(pattern: str) -> tuple[Automaton, list[TraceStep]]:
    """Parse a full-string regex and compile the AST with Thompson fragments."""
    if len(pattern) > 256:
        raise RegexSyntaxError("Regular expressions are limited to 256 characters", 256)
    tree = RegexParser(pattern).parse()
    next_id = 0
    transitions: list[Transition] = []
    steps: list[TraceStep] = [TraceStep(title="Parse regular expression", explanation="Build an explicit syntax tree using precedence: repetition, concatenation, then union.", data={"pattern": pattern, "ast": tree.json()})]
    def node_ref(node: RegexNode) -> dict[str, object]:
        """Keep each construction step linked to the one canonical AST copy."""
        return {"type": node.kind, "position": node.position}

    def state_id() -> int:
        nonlocal next_id
        value = next_id
        next_id += 1
        return value

    def edge(source: int, target: int, symbol: str) -> None:
        transitions.append(Transition(from_=f"q{source}", to=f"q{target}", symbols=[symbol]))

    def build(node: RegexNode) -> _Fragment:
        if node.kind == "class":
            start, end = state_id(), state_id()
            characters = set(node.value)  # type: ignore[arg-type]
            # Cover complete named classes first, then keep only residual literals.
            remaining = set(characters)
            symbols: list[str] = []
            exact_class = next((name for name, members in SYMBOL_CLASSES.items() if set(members) == remaining), None)
            if exact_class:
                symbols.append(exact_class)
                remaining.clear()
            else:
                for name, members in sorted(SYMBOL_CLASSES.items(), key=lambda item: (-len(item[1]), item[0])):
                    expanded = set(members)
                    if expanded and expanded <= remaining:
                        symbols.append(name)
                        remaining -= expanded
            symbols.extend(sorted(remaining))
            for symbol in symbols:
                edge(start, end, symbol)
            steps.append(TraceStep(title="Build character fragment", explanation="This character-set AST node becomes a two-state fragment with one edge for each matching character.", data={"node": node.json(), "start": f"q{start}", "end": f"q{end}", "symbols": symbols}))
            return _Fragment(start, end)
        if node.kind == "concat":
            if not node.children:
                start, end = state_id(), state_id()
                edge(start, end, "ε")
                return _Fragment(start, end)
            parts = [build(child) for child in node.children]
            for left, right in zip(parts, parts[1:]):
                edge(left.end, right.start, "ε")
            result = _Fragment(parts[0].start, parts[-1].end)
            steps.append(TraceStep(title="Join concatenation", explanation="Connect the fragments in sequence with ε edges.", data={"node": node_ref(node), "fragments": [[f"q{part.start}", f"q{part.end}"] for part in parts], "result": [f"q{result.start}", f"q{result.end}"]}))
            return result
        if node.kind == "union":
            parts = [build(child) for child in node.children]
            start, end = state_id(), state_id()
            for part in parts:
                edge(start, part.start, "ε")
                edge(part.end, end, "ε")
            result = _Fragment(start, end)
            steps.append(TraceStep(title="Branch for union", explanation="ε branches from the new entry into each alternative and rejoins their exits.", data={"node": node_ref(node), "branches": [[f"q{part.start}", f"q{part.end}"] for part in parts], "result": [f"q{start}", f"q{end}"]}))
            return result
        if node.kind == "repeat":
            minimum, maximum = node.value  # type: ignore[misc]
            fragments = [build(node.children[0]) for _ in range(minimum)]
            optional_count = (maximum - minimum) if maximum is not None else None
            if optional_count is None:
                loop = build(node.children[0])
                start, end = state_id(), state_id()
                edge(start, loop.start, "ε"); edge(start, end, "ε")
                edge(loop.end, loop.start, "ε"); edge(loop.end, end, "ε")
                fragments.append(_Fragment(start, end))
            else:
                for _ in range(optional_count):
                    part = build(node.children[0])
                    start, end = state_id(), state_id()
                    edge(start, part.start, "ε"); edge(start, end, "ε"); edge(part.end, end, "ε")
                    fragments.append(_Fragment(start, end))
            if not fragments:
                start, end = state_id(), state_id(); edge(start, end, "ε")
                result = _Fragment(start, end)
            else:
                for left, right in zip(fragments, fragments[1:]): edge(left.end, right.start, "ε")
                result = _Fragment(fragments[0].start, fragments[-1].end)
            steps.append(TraceStep(title="Expand bounded repetition", explanation="Clone the child fragment for required copies and use ε branches for optional copies or the unbounded tail.", data={"node": node_ref(node), "minimum": minimum, "maximum": maximum, "fragments": [[f"q{part.start}", f"q{part.end}"] for part in fragments], "result": [f"q{result.start}", f"q{result.end}"]}))
            return result
        part = build(node.children[0])
        start, end = state_id(), state_id()
        edge(start, part.start, "ε"); edge(part.end, end, "ε")
        if node.kind in ("star", "optional"): edge(start, end, "ε")
        if node.kind in ("star", "plus"): edge(part.end, part.start, "ε")
        steps.append(TraceStep(title=f"Apply {node.kind}", explanation={"star": "Allow zero or more traversals.", "plus": "Require one traversal and allow more.", "optional": "Allow zero or one traversal."}[node.kind], data={"node": node_ref(node), "fragment": [f"q{part.start}", f"q{part.end}"], "result": [f"q{start}", f"q{end}"]}))
        return _Fragment(start, end)

    fragment = build(tree)
    alphabet = sorted({symbol for transition in transitions for symbol in transition.symbols if symbol != "ε"})
    automaton = Automaton(type="EPSILON_NFA", states=[State(id=f"q{i}", label=f"q{i}", isStart=i == fragment.start, isAccepting=i == fragment.end, x=float((i % 8) * 120), y=float((i // 8) * 100)) for i in range(next_id)], alphabet=alphabet, transitions=transitions)
    steps.append(TraceStep(title="Finish ε-NFA", explanation="The compiled fragment entry is the start and its exit is the sole accepting state.", data={"startState": f"q{fragment.start}", "acceptingStates": [f"q{fragment.end}"], "stateCount": next_id}))
    return automaton, steps


__all__ = ["RegexNode", "RegexParser", "RegexSyntaxError", "compile_regex"]
