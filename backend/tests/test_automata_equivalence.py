"""Equivalence, inclusion, and shortest-witness behavior."""

from fastapi.testclient import TestClient

from app.automata.equivalence import check_equivalence, check_equivalence_hopcroft_karp
from app.automata.models import Automaton
from app.automata.regex import compile_regex
from app.main import app


client = TestClient(app)


def state(identifier: str, start: bool = False, accept: bool = False) -> dict[str, object]:
    return {"id": identifier, "label": identifier, "isStart": start, "isAccepting": accept, "x": 0, "y": 0}


def machine(kind: str, states: list[dict[str, object]], alphabet: list[str], transitions: list[dict[str, object]]) -> Automaton:
    return Automaton.model_validate({"type": kind, "states": states, "alphabet": alphabet, "transitions": transitions})


def accepts_a() -> Automaton:
    return machine("DFA", [state("q0", True), state("q1", accept=True)], ["a"], [
        {"from": "q0", "to": "q1", "symbols": ["a"]}, {"from": "q1", "to": "q1", "symbols": ["a"]},
    ])


def accepts_a_alternate() -> Automaton:
    return machine("DFA", [state("s", True), state("f", accept=True), state("dead")], ["a", "b"], [
        {"from": "s", "to": "f", "symbols": ["a"]}, {"from": "s", "to": "dead", "symbols": ["b"]},
        {"from": "f", "to": "f", "symbols": ["a"]}, {"from": "f", "to": "dead", "symbols": ["b"]},
        {"from": "dead", "to": "dead", "symbols": ["a", "b"]},
    ])


def accepts_b() -> Automaton:
    return machine("DFA", [state("r0", True), state("r1", accept=True)], ["a", "b"], [
        {"from": "r0", "to": "r0", "symbols": ["a"]}, {"from": "r0", "to": "r1", "symbols": ["b"]},
        {"from": "r1", "to": "r1", "symbols": ["a", "b"]},
    ])


def assert_methods_agree(left: Automaton, right: Automaton) -> None:
    bfs = check_equivalence(left, right)
    hk = check_equivalence_hopcroft_karp(left, right)
    assert bfs.result["equivalent"] == hk.result["equivalent"]
    assert hk.result["method"] == "hopcroft-karp"
    assert any("Hopcroft-Karp" in step.title for step in hk.trace)


def test_same_language_with_different_state_names_and_alphabet_labels():
    result = check_equivalence(accepts_a(), accepts_a_alternate()).result
    assert result["equivalent"] is True
    assert result["counterexample"] is None
    assert_methods_agree(accepts_a(), accepts_a_alternate())


def test_returns_shortest_counterexample_and_state_pair_path():
    result = check_equivalence(accepts_a(), accepts_b()).result
    assert result["equivalent"] is False
    assert result["counterexample"] == ["a"]
    assert result["counterexampleString"] == "a"
    assert result["acceptedBy"] == "left"
    assert result["path"] == [["q0", "r0"], ["q1", "r0"]]
    assert_methods_agree(accepts_a(), accepts_b())


def test_reports_the_right_side_when_it_alone_accepts_the_shortest_witness():
    result = check_equivalence(accepts_b(), accepts_a()).result
    assert result["counterexample"] == ["a"]
    assert result["acceptedBy"] == "right"
    assert_methods_agree(accepts_b(), accepts_a())


def test_empty_string_can_be_the_shortest_counterexample():
    left = machine("DFA", [state("yes", True, True)], [], [])
    right = machine("DFA", [state("no", True)], [], [])
    result = check_equivalence(left, right).result
    assert result["counterexample"] == []
    assert result["counterexampleString"] == ""
    assert result["acceptedBy"] == "left"


def test_different_alphabets_are_completed_over_their_union():
    left = machine("DFA", [state("q0", True), state("qa", accept=True)], ["a"], [
        {"from": "q0", "to": "qa", "symbols": ["a"]}, {"from": "qa", "to": "qa", "symbols": ["a"]},
    ])
    right = machine("DFA", [state("r0", True), state("ra", accept=True)], ["a", "b"], [
        {"from": "r0", "to": "ra", "symbols": ["a"]}, {"from": "ra", "to": "ra", "symbols": ["a"]},
    ])
    result = check_equivalence(left, right).result
    assert result["equivalent"] is True
    assert any("Complete both" in step.title for step in check_equivalence(left, right).trace)
    assert_methods_agree(left, right)


def test_nfa_is_converted_and_inclusion_is_reported():
    left = machine("NFA", [state("n0", True), state("nf", accept=True)], ["a"], [
        {"from": "n0", "to": "nf", "symbols": ["a"]},
    ])
    right = accepts_a()
    result = check_equivalence(left, right)
    assert result.result["equivalent"] is False
    assert result.result["leftSubsetRight"] is True
    assert any(step.title == "Convert left input to a DFA" for step in result.trace)
    assert_methods_agree(left, right)


def test_epsilon_nfa_conversion_and_empty_language_reporting():
    empty = machine("EPSILON_NFA", [state("e0", True), state("e1")], ["a"], [
        {"from": "e0", "to": "e1", "symbols": ["ε"]},
    ])
    result = check_equivalence(empty, empty)
    assert result.result["equivalent"] is True
    assert result.result["leftEmpty"] is True
    assert result.result["rightEmpty"] is True
    assert any(step.title == "Convert left input to a DFA" for step in result.trace)
    assert_methods_agree(empty, empty)


def test_symbol_classes_compare_concrete_tokens_without_spurious_difference():
    digits = machine("DFA", [state("d0", True), state("df", accept=True)], ["DIGIT"], [
        {"from": "d0", "to": "df", "symbols": ["DIGIT"]}, {"from": "df", "to": "df", "symbols": ["DIGIT"]},
    ])
    zero_to_nine = machine("DFA", [state("x0", True), state("xf", accept=True)], list("0123456789"), [
        {"from": "x0", "to": "xf", "symbols": list("0123456789")}, {"from": "xf", "to": "xf", "symbols": list("0123456789")},
    ])
    assert check_equivalence(digits, zero_to_nine).result["equivalent"] is True


def test_largeish_equivalent_automata_and_trace_explores_product():
    count = 35
    states_left = [state(f"q{i}", start=i == 0, accept=i == count - 1) for i in range(count)]
    states_right = [state(f"r{i}", start=i == 0, accept=i == count - 1) for i in range(count)]
    edges_left = [{"from": f"q{i}", "to": f"q{i + 1}", "symbols": ["a"]} for i in range(count - 1)]
    edges_right = [{"from": f"r{i}", "to": f"r{i + 1}", "symbols": ["a"]} for i in range(count - 1)]
    left = machine("DFA", states_left, ["a"], edges_left)
    right = machine("DFA", states_right, ["a"], edges_right)
    result = check_equivalence(left, right)
    assert result.result["equivalent"] is True
    assert result.result["productStatesExplored"] == count + 1  # the completed shared trap pair is reachable
    assert_methods_agree(left, right)


def test_endpoint_returns_result_and_visualization_trace():
    response = client.post("/api/equivalence", json={"left": accepts_a().model_dump(by_alias=True), "right": accepts_b().model_dump(by_alias=True)})
    assert response.status_code == 200
    payload = response.json()
    assert payload["equivalent"] is False
    assert payload["counterexampleString"] == "a"
    assert payload["method"] == "product-bfs"
    assert payload["trace"]


def test_endpoint_supports_hopcroft_karp_option():
    response = client.post("/api/equivalence", json={"left": accepts_a().model_dump(by_alias=True), "right": accepts_a_alternate().model_dump(by_alias=True), "method": "hopcroft-karp"})
    assert response.status_code == 200
    assert response.json()["equivalent"] is True
    assert response.json()["method"] == "hopcroft-karp"


def test_regex_compiler_thompson_builds_traceable_epsilon_nfa():
    automaton, trace = compile_regex("(GET|POST) /\\d+")
    assert automaton.type == "EPSILON_NFA"
    assert automaton.start_state().isStart
    assert any(state.isAccepting for state in automaton.states)
    assert "DIGIT" in automaton.alphabet
    assert trace[0].title == "Parse regular expression"


def test_regex_compile_endpoint_reports_friendly_parse_errors():
    response = client.post("/api/regex/compile", json={"pattern": "("})
    assert response.status_code == 400
    assert "Unclosed group" in response.json()["detail"]

