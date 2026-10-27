"""Language preservation and trace coverage for automata transformations."""

import random

import pytest
from fastapi.testclient import TestClient

from app.automata.engine import simulate
from app.automata.models import Automaton
from app.automata.transformations import (
    eliminate_epsilon,
    minimize_hopcroft,
    minimize_table,
    run_pipeline,
    subset_construction,
)
from app.main import app

client = TestClient(app)


def state(identifier: str, *, start: bool = False, accepting: bool = False, x: int = 0):
    return {"id": identifier, "label": identifier, "isStart": start, "isAccepting": accepting, "x": x, "y": 0}


def build(kind: str, states: list[dict], alphabet: list[str], transitions: list[dict]) -> Automaton:
    return Automaton.model_validate({"type": kind, "states": states, "alphabet": alphabet, "transitions": transitions})


def epsilon_example() -> Automaton:
    return build("EPSILON_NFA", [state("q0", start=True), state("q1"), state("q2", accepting=True)], ["a", "b"], [
        {"from": "q0", "to": "q1", "symbols": ["ε"]},
        {"from": "q0", "to": "q0", "symbols": ["b"]},
        {"from": "q1", "to": "q2", "symbols": ["a"]},
        {"from": "q2", "to": "q2", "symbols": ["b"]},
    ])


def contains_ab_nfa() -> Automaton:
    return build("NFA", [state("q0", start=True), state("q1"), state("q2", accepting=True)], ["a", "b"], [
        {"from": "q0", "to": "q0", "symbols": ["a", "b"]},
        {"from": "q0", "to": "q1", "symbols": ["a"]},
        {"from": "q1", "to": "q2", "symbols": ["b"]},
        {"from": "q2", "to": "q2", "symbols": ["a", "b"]},
    ])


def mergeable_dfa() -> Automaton:
    return build("DFA", [state("q0", start=True), state("q1", accepting=True), state("q2"), state("q3"), state("unreachable")], ["a", "b"], [
        {"from": "q0", "to": "q1", "symbols": ["a"]}, {"from": "q0", "to": "q2", "symbols": ["b"]},
        {"from": "q1", "to": "q1", "symbols": ["a"]}, {"from": "q1", "to": "q2", "symbols": ["b"]},
        {"from": "q2", "to": "q2", "symbols": ["a"]}, {"from": "q2", "to": "q3", "symbols": ["b"]},
        {"from": "q3", "to": "q2", "symbols": ["a"]}, {"from": "q3", "to": "q3", "symbols": ["b"]},
        {"from": "unreachable", "to": "unreachable", "symbols": ["a", "b"]},
    ])


def random_strings(seed: int = 31, count: int = 200) -> list[str]:
    rng = random.Random(seed)
    return ["".join(rng.choice("ab") for _ in range(rng.randrange(8))) for _ in range(count)]


def assert_same_language(left: Automaton, right: Automaton) -> None:
    for value in random_strings():
        assert simulate(left, value).accepted == simulate(right, value).accepted, f"language mismatch for {value!r}"


def test_epsilon_elimination_shows_closures_transitions_and_final_states():
    source = epsilon_example()
    converted = eliminate_epsilon(source)
    assert converted.result.type == "NFA"
    assert all("ε" not in edge.symbols for edge in converted.result.transitions)
    assert converted.result.states[0].isAccepting is False
    assert converted.trace[0].data["closure"] == ["q0", "q1"]
    assert converted.trace[-1].data["newAcceptingStates"] == ["q2"]
    assert any("destinationClosure" in step.data for step in converted.trace)
    assert_same_language(source, converted.result)


def test_epsilon_elimination_property_preserves_200_random_strings():
    source = epsilon_example()
    assert_same_language(source, eliminate_epsilon(source).result)


def test_subset_construction_creates_only_reachable_subsets_and_expected_count():
    converted = subset_construction(contains_ab_nfa())
    assert converted.result.type == "DFA"
    assert len(converted.result.states) == 4
    assert {state.id for state in converted.result.states} == {"q0", "q1", "q2", "q3"}
    mapping = converted.trace[-1].data["states"]
    assert {tuple(item["nfaStates"]) for item in mapping} == {("q0",), ("q0", "q1"), ("q0", "q2"), ("q0", "q1", "q2")}
    assert all("queue" in step.data and "transitions" in step.data for step in converted.trace if step.title.startswith("Process subset"))
    assert_same_language(contains_ab_nfa(), converted.result)


def test_subset_construction_property_preserves_200_random_strings():
    source = contains_ab_nfa()
    assert_same_language(source, subset_construction(source).result)


def test_subset_construction_partitions_overlapping_symbol_classes_correctly():
    source = build("NFA", [state("q0", start=True), state("digits", accepting=True), state("letters")], ["DIGIT", "ALPHA"], [
        {"from": "q0", "to": "digits", "symbols": ["DIGIT"]},
        {"from": "q0", "to": "letters", "symbols": ["ALPHA"]},
    ])
    converted = subset_construction(source).result
    assert converted.type == "DFA"
    assert_same_language(source, converted)
    for transition in converted.transitions:
        assert transition.symbols


def test_subset_construction_rejects_epsilon_nfa_until_epsilon_removal():
    with pytest.raises(ValueError, match="requires an NFA"):
        subset_construction(epsilon_example())


@pytest.mark.parametrize("minimizer", [minimize_table, minimize_hopcroft])
def test_minimizers_remove_unreachable_states_and_merge_equivalent_states(minimizer):
    source = mergeable_dfa()
    converted = minimizer(source)
    assert len(converted.result.states) == 3
    assert "unreachable" not in {state.id for state in converted.result.states}
    assert any(set(item["mergedStates"]) == {"q2", "q3"} for item in converted.trace[-1].data["equivalenceClasses"])
    assert "{q2,q3}" not in {state.id for state in converted.result.states}
    assert converted.trace[0].data["removedStates"] == ["unreachable"]
    assert_same_language(source, converted.result)


def test_table_filling_property_preserves_200_random_strings():
    source = mergeable_dfa()
    assert_same_language(source, minimize_table(source).result)


def test_hopcroft_property_preserves_200_random_strings():
    source = mergeable_dfa()
    result = minimize_hopcroft(source)
    assert_same_language(source, result.result)
    assert any("splits" in step.data for step in result.trace if "Hopcroft refinement" in step.title)


def test_partial_dfa_implicit_sink_can_be_omitted_after_minimization():
    source = build("DFA", [state("q0", start=True)], ["a"], [])
    for minimizer in (minimize_table, minimize_hopcroft):
        result = minimizer(source).result
        assert len(result.states) == 1
        assert_same_language(source, result)


def test_pipeline_returns_each_intermediate_and_all_stage_traces():
    result = run_pipeline(epsilon_example())
    assert [item["operation"] for item in result["intermediateAutomata"]] == ["epsilon-elimination", "subset-construction", "minimize-table"]
    assert result["result"].type == "DFA"
    assert {step.data.get("stage") for step in result["trace"]} == {"epsilon-elimination", "subset-construction", "minimize-table"}
    assert_same_language(epsilon_example(), result["result"])


def test_transform_endpoint_returns_pipeline_and_each_intermediate_automaton():
    response = client.post("/api/transform", json={"automaton": epsilon_example().model_dump(by_alias=True), "operation": "pipeline"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["type"] == "DFA"
    assert len(payload["intermediateAutomata"]) == 3
    assert payload["trace"]
    hopcroft = client.post("/api/transform", json={"automaton": epsilon_example().model_dump(by_alias=True), "operation": "pipeline", "minimizer": "hopcroft"})
    assert hopcroft.status_code == 200
    assert hopcroft.json()["intermediateAutomata"][-1]["operation"] == "minimize-hopcroft"


def test_transform_endpoint_supports_hopcroft_and_reports_wrong_operation_type():
    response = client.post("/api/transform", json={"automaton": mergeable_dfa().model_dump(by_alias=True), "operation": "minimize-hopcroft"})
    assert response.status_code == 200
    assert len(response.json()["result"]["states"]) == 3
    invalid = client.post("/api/transform", json={"automaton": epsilon_example().model_dump(by_alias=True), "operation": "minimize-table"})
    assert invalid.status_code == 400

