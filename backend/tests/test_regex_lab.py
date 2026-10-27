import random
import re

import pytest
from fastapi.testclient import TestClient

from app.automata.engine import simulate
from app.automata.regex import RegexParser, RegexSyntaxError, compile_regex
from app.main import app

client = TestClient(app)


@pytest.mark.parametrize("pattern,accepted,rejected", [
    ("a|bc", ["a", "bc"], ["", "b", "ac"]),
    ("ab*c", ["ac", "abc", "abbbc"], ["ab", "cab"]),
    ("[a-c][0-2]", ["a0", "c2"], ["d0", "a3"]),
    ("[^a-c]+", ["z", "9", "___"], ["a", "xb"]),
    (r"\w+\.\d?", ["id.2", "abc.", "_x.9"], ["!a.2", "abc.22"]),
    ("a{2,4}", ["aa", "aaa", "aaaa"], ["a", "aaaaa"]),
    ("x{2,}", ["xx", "xxxxx"], ["x", "xy"]),
    ("a{0,2}b", ["b", "ab", "aab"], ["aa", "aaab"]),
    (r"\s+", [" ", "\t", " \n"], ["", "a"]),
    (".", ["a", " ", "~"], ["", "ab", "\n"]),
])
def test_supported_regex_syntax(pattern, accepted, rejected):
    automaton, trace = compile_regex(pattern)
    assert trace[0].data["ast"]["type"]
    assert all(simulate(automaton, value).accepted for value in accepted)
    assert all(not simulate(automaton, value).accepted for value in rejected)


@pytest.mark.parametrize("pattern,position", [("(", 0), ("a|", 2), ("[z-a]", 2), ("a{3,2}", 1), (r"\q", 0), ("a{2", 3)])
def test_parser_errors_include_character_position(pattern, position):
    with pytest.raises(RegexSyntaxError, match=f"position {position}"):
        RegexParser(pattern).parse()


def test_convert_endpoint_returns_ast_all_pipeline_machines_and_trace():
    response = client.post("/api/regex/convert", json={"pattern": "(ab|c)+"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["ast"]["type"] == "plus"
    assert payload["epsilonNfa"]["type"] == "EPSILON_NFA"
    assert payload["dfa"]["type"] == "DFA"
    assert payload["minimalDfa"]["type"] == "DFA"
    assert any("fragment" in step["data"] or "result" in step["data"] for step in payload["trace"])
    assert payload["pipelineSummary"]


def test_character_ranges_and_negation_agree_with_python_fullmatch_for_ascii_samples():
    patterns = [r"[a-z0-9_]{1,3}", r"[^A-Z]{0,2}", r"\d+([.-]\w+)?", r"a{1,3}|b?c"]
    alphabet = "aZ09_- .bc"
    rng = random.Random(4102)
    samples = [""] + ["".join(rng.choice(alphabet) for _ in range(size)) for size in range(1, 5) for _ in range(50)]
    for pattern in patterns:
        automaton, _ = compile_regex(pattern)
        for value in samples:
            assert simulate(automaton, value).accepted == (re.fullmatch(pattern, value) is not None), (pattern, value)


def test_regex_presets_patterns_parse():
    for pattern in ("[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}", "(25[0-5]|2[0-4]\\d|1?\\d?\\d)(\\.(25[0-5]|2[0-4]\\d|1?\\d?\\d)){3}", "[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", "sk_[A-Za-z0-9]{24,40}", "/users/[0-9]+"):
        compile_regex(pattern)
