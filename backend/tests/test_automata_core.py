"""Behavioral coverage for automata validation, algorithms, and API routes."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.automata.engine import simulate
from app.automata.models import Automaton
from app.automata.utilities import (
    classify_automaton,
    complete_dfa,
    dead_states,
    epsilon_closure,
    reachable_states,
    trap_states,
)
from app.main import app

client = TestClient(app)


def make_automaton(
    kind="DFA", states=None, alphabet=None, transitions=None
) -> Automaton:
    return Automaton.model_validate({
        "type": kind,
        "states": states if states is not None else [
            {"id": "q0", "label": "Start", "isStart": True, "isAccepting": False, "x": 0, "y": 0},
            {"id": "q1", "label": "Accept", "isStart": False, "isAccepting": True, "x": 100, "y": 0},
        ],
        "alphabet": alphabet if alphabet is not None else ["a"],
        "transitions": transitions if transitions is not None else [
            {"from": "q0", "to": "q1", "symbols": ["a"]},
            {"from": "q1", "to": "q1", "symbols": ["a"]},
        ],
    })


def state(identifier, *, start=False, accepting=False, x=0, y=0):
    return {"id": identifier, "label": identifier, "isStart": start, "isAccepting": accepting, "x": x, "y": y}


def test_dfa_accepts_matching_path():
    result = simulate(make_automaton(), "a")
    assert result.status == "ACCEPTED"
    assert result.final_states == ["q1"]
    assert result.trace[0].data["transitionsFired"][0]["to"] == "q1"


def test_dfa_rejects_when_input_has_no_transition():
    result = simulate(make_automaton(), "x")
    assert result.status == "REJECTED"
    assert result.reason == "stuck at q0 on symbol 'x'"


def test_dfa_rejects_nonaccepting_final_state():
    automaton = make_automaton(transitions=[])
    result = simulate(automaton, "")
    assert result.status == "REJECTED"
    assert result.reason == "ended in a non-accepting state"


def test_empty_string_accepts_when_start_is_accepting():
    automaton = make_automaton(states=[state("q0", start=True, accepting=True)], transitions=[])
    result = simulate(automaton, "")
    assert result.accepted is True
    assert result.final_states == ["q0"]


def test_empty_string_trace_has_final_decision():
    automaton = make_automaton(states=[state("q0", start=True, accepting=True)], transitions=[])
    result = simulate(automaton, "")
    assert result.trace[-1].title == "Accepted"


def test_nfa_accepts_if_one_branch_reaches_accepting_state():
    automaton = make_automaton(
        "NFA",
        states=[state("q0", start=True), state("q1"), state("q2", accepting=True)],
        transitions=[{"from": "q0", "to": "q1", "symbols": ["a"]}, {"from": "q0", "to": "q2", "symbols": ["a"]}],
    )
    result = simulate(automaton, "a")
    assert result.accepted
    assert result.final_states == ["q1", "q2"]


def test_nfa_keeps_all_active_states_after_each_symbol():
    automaton = make_automaton(
        "NFA",
        states=[state("q0", start=True), state("q1"), state("q2")],
        transitions=[{"from": "q0", "to": "q1", "symbols": ["a"]}, {"from": "q0", "to": "q2", "symbols": ["a"]}],
    )
    assert simulate(automaton, "a").trace[0].data["nextStates"] == ["q1", "q2"]


def test_nfa_rejects_if_no_active_state_is_accepting():
    automaton = make_automaton("NFA", transitions=[])
    assert simulate(automaton, "a").reason == "stuck at q0 on symbol 'a'"


def test_nfa_rejects_when_all_branches_end_nonaccepting():
    automaton = make_automaton("NFA", states=[state("q0", start=True), state("q1")], transitions=[{"from": "q0", "to": "q1", "symbols": ["a"]}])
    result = simulate(automaton, "a")
    assert result.reason == "ended in a non-accepting state"


def test_epsilon_nfa_accepts_empty_string_through_epsilon_edge():
    automaton = make_automaton(
        "EPSILON_NFA",
        states=[state("q0", start=True), state("q1", accepting=True)],
        transitions=[{"from": "q0", "to": "q1", "symbols": ["ε"]}],
    )
    result = simulate(automaton, "")
    assert result.accepted
    assert result.final_states == ["q0", "q1"]


def test_epsilon_loop_closure_terminates_and_includes_seed():
    automaton = make_automaton("EPSILON_NFA", states=[state("q0", start=True), state("q1")], transitions=[{"from": "q0", "to": "q1", "symbols": ["ε"]}, {"from": "q1", "to": "q0", "symbols": ["ε"]}, {"from": "q1", "to": "q1", "symbols": ["ε"]}])
    assert epsilon_closure(automaton, {"q0"}).result == ["q0", "q1"]


def test_epsilon_closure_trace_lists_fired_edges():
    automaton = make_automaton("EPSILON_NFA", transitions=[{"from": "q0", "to": "q1", "symbols": ["ε"]}])
    step = epsilon_closure(automaton, ["q0"]).trace[0]
    assert step.title == "Compute ε-closure"
    assert step.data["transitionsFired"] == [{"from": "q0", "to": "q1", "symbol": "ε"}]


def test_epsilon_nfa_takes_closure_after_consuming_symbol():
    automaton = make_automaton("EPSILON_NFA", transitions=[{"from": "q0", "to": "q1", "symbols": ["a"]}, {"from": "q1", "to": "q2", "symbols": ["ε"]}], states=[state("q0", start=True), state("q1"), state("q2", accepting=True)])
    result = simulate(automaton, "a")
    assert result.accepted
    assert result.trace[-2].data["nextStates"] == ["q1", "q2"]


def test_epsilon_nfa_initial_closure_is_in_trace():
    automaton = make_automaton("EPSILON_NFA", transitions=[{"from": "q0", "to": "q1", "symbols": ["ε"]}])
    result = simulate(automaton, "")
    assert result.trace[0].title == "Take the initial ε-closure"


def test_reachable_states_excludes_unreachable_state():
    automaton = make_automaton(states=[state("q0", start=True), state("q1", accepting=True), state("q9")])
    result = reachable_states(automaton)
    assert result.result == ["q0", "q1"]
    assert result.trace


def test_reachable_states_follows_epsilon_edges():
    automaton = make_automaton("EPSILON_NFA", states=[state("q0", start=True), state("q1")], transitions=[{"from": "q0", "to": "q1", "symbols": ["ε"]}])
    assert reachable_states(automaton).result == ["q0", "q1"]


def test_dead_states_includes_unreachable_nonaccepting_state():
    automaton = make_automaton(states=[state("q0", start=True), state("q1", accepting=True), state("qdead")])
    assert dead_states(automaton).result == ["qdead"]


def test_dead_states_includes_reachable_state_with_no_accepting_path():
    automaton = make_automaton(states=[state("q0", start=True), state("q1", accepting=True), state("q2")], transitions=[{"from": "q0", "to": "q1", "symbols": ["a"]}, {"from": "q2", "to": "q2", "symbols": ["a"]}])
    assert dead_states(automaton).result == ["q2"]


def test_trap_state_requires_all_symbols_to_loop_to_itself():
    automaton = make_automaton(states=[state("q0", start=True), state("qtrap")], alphabet=["a", "b"], transitions=[{"from": "qtrap", "to": "qtrap", "symbols": ["a", "b"]}])
    assert trap_states(automaton).result == ["qtrap"]


def test_state_with_exit_is_not_a_trap_even_if_it_has_all_self_loops():
    automaton = make_automaton("NFA", states=[state("q0", start=True), state("qtrap"), state("qf", accepting=True)], alphabet=["a", "b"], transitions=[{"from": "qtrap", "to": "qtrap", "symbols": ["a", "b"]}, {"from": "qtrap", "to": "qf", "symbols": ["a"]}])
    assert trap_states(automaton).result == []


def test_classifier_recognizes_dfa():
    assert classify_automaton(make_automaton()).result["type"] == "DFA"


def test_classifier_recognizes_nondeterminism():
    automaton = make_automaton("NFA", states=[state("q0", start=True), state("q1"), state("q2")], transitions=[{"from": "q0", "to": "q1", "symbols": ["a"]}, {"from": "q0", "to": "q2", "symbols": ["a"]}])
    assert classify_automaton(automaton).result["type"] == "NFA"


def test_classifier_prioritizes_epsilon_nfa():
    automaton = make_automaton("EPSILON_NFA", transitions=[{"from": "q0", "to": "q1", "symbols": ["ε"]}])
    assert classify_automaton(automaton).result["type"] == "EPSILON_NFA"


def test_deterministic_nfa_classifies_as_dfa():
    automaton = make_automaton("NFA")
    assert classify_automaton(automaton).result["isDFA"] is True


def test_dfa_completion_adds_trap_and_missing_edge():
    automaton = make_automaton(alphabet=["a", "b"], transitions=[{"from": "q0", "to": "q1", "symbols": ["a"]}])
    completed = complete_dfa(automaton).result
    assert completed.states[-1].id == "__trap__"
    assert any(t.from_ == "q0" and t.to == "__trap__" and "b" in t.symbols for t in completed.transitions)
    assert any(t.from_ == "__trap__" and t.to == "__trap__" for t in completed.transitions)


def test_dfa_completion_does_not_mutate_original():
    automaton = make_automaton(alphabet=["a", "b"], transitions=[])
    completed = complete_dfa(automaton).result
    assert len(automaton.states) == 2
    assert len(completed.states) == 3


def test_completion_preserves_whole_symbol_class_edges():
    automaton = make_automaton(alphabet=["DIGIT"], transitions=[])
    completed = complete_dfa(automaton).result
    assert any(t.from_ == "q0" and t.symbols == ["DIGIT"] for t in completed.transitions)


def test_completion_can_finish_partial_class_with_literal_atoms():
    automaton = make_automaton(
        alphabet=["DIGIT", "0"],
        transitions=[{"from": "q0", "to": "q1", "symbols": ["0"]}],
    )
    completed = complete_dfa(automaton).result
    q0_fallback = next(t for t in completed.transitions if t.from_ == "q0" and t.to == "__trap__")
    assert "0" not in q0_fallback.symbols
    assert set("123456789").issubset(q0_fallback.symbols)
    assert set("123456789").issubset(completed.alphabet)


def test_digit_class_matches_ascii_digits():
    automaton = make_automaton(alphabet=["DIGIT"], transitions=[{"from": "q0", "to": "q1", "symbols": ["DIGIT"]}])
    assert simulate(automaton, "7").accepted


def test_digit_class_does_not_match_letters():
    automaton = make_automaton(alphabet=["DIGIT"], transitions=[{"from": "q0", "to": "q1", "symbols": ["DIGIT"]}])
    assert simulate(automaton, "g").reason == "stuck at q0 on symbol 'g'"


def test_alpha_class_matches_ascii_letters():
    automaton = make_automaton(alphabet=["ALPHA"], transitions=[{"from": "q0", "to": "q1", "symbols": ["ALPHA"]}])
    assert simulate(automaton, "Z").accepted


def test_crlf_class_is_one_input_step():
    automaton = make_automaton(alphabet=["CRLF"], transitions=[{"from": "q0", "to": "q1", "symbols": ["CRLF"]}])
    result = simulate(automaton, "\r\n")
    assert result.accepted
    assert result.trace[0].data["symbolRead"] == "CRLF"


def test_sp_class_matches_space():
    automaton = make_automaton(alphabet=["SP"], transitions=[{"from": "q0", "to": "q1", "symbols": ["SP"]}])
    assert simulate(automaton, " ").accepted


def test_tchar_class_excludes_space():
    automaton = make_automaton(alphabet=["TCHAR"], transitions=[{"from": "q0", "to": "q1", "symbols": ["TCHAR"]}])
    assert simulate(automaton, " ").reason == "stuck at q0 on symbol ' '"


def test_dfa_rejects_overlapping_classes_with_different_targets():
    with pytest.raises(ValidationError, match="nondeterministic"):
        make_automaton(alphabet=["DIGIT", "TCHAR"], transitions=[{"from": "q0", "to": "q1", "symbols": ["DIGIT"]}, {"from": "q0", "to": "q0", "symbols": ["TCHAR"]}])


def test_dfa_allows_overlapping_classes_to_same_target():
    automaton = make_automaton(alphabet=["DIGIT", "TCHAR"], transitions=[{"from": "q0", "to": "q1", "symbols": ["DIGIT", "TCHAR"]}])
    assert automaton.type == "DFA"


def test_partial_dfa_is_valid():
    automaton = make_automaton(transitions=[])
    assert automaton.type == "DFA"


def test_model_rejects_multiple_start_states():
    with pytest.raises(ValidationError, match="exactly one start"):
        make_automaton(states=[state("q0", start=True), state("q1", start=True)])


def test_model_rejects_no_start_state():
    with pytest.raises(ValidationError, match="exactly one start"):
        make_automaton(states=[state("q0")])


def test_model_rejects_transition_to_unknown_state():
    with pytest.raises(ValidationError, match="existing states"):
        make_automaton(transitions=[{"from": "q0", "to": "missing", "symbols": ["a"]}])


def test_model_rejects_transition_from_unknown_state():
    with pytest.raises(ValidationError, match="existing states"):
        make_automaton(transitions=[{"from": "missing", "to": "q0", "symbols": ["a"]}])


def test_model_rejects_epsilon_in_plain_nfa():
    with pytest.raises(ValidationError, match="only in EPSILON_NFA"):
        make_automaton("NFA", transitions=[{"from": "q0", "to": "q1", "symbols": ["ε"]}])


def test_model_rejects_transition_symbol_outside_alphabet():
    with pytest.raises(ValidationError, match="not in the alphabet"):
        make_automaton(transitions=[{"from": "q0", "to": "q1", "symbols": ["b"]}])


def test_model_rejects_duplicate_state_ids():
    with pytest.raises(ValidationError, match="state ids must be unique"):
        make_automaton(states=[state("q0", start=True), state("q0")])


def test_model_rejects_epsilon_in_alphabet():
    with pytest.raises(ValidationError, match="cannot include ε"):
        make_automaton(alphabet=["ε"], transitions=[])


def test_model_rejects_dfa_with_overlapping_destinations():
    with pytest.raises(ValidationError, match="nondeterministic"):
        make_automaton(alphabet=["a", "ALPHA"], transitions=[{"from": "q0", "to": "q1", "symbols": ["a"]}, {"from": "q0", "to": "q0", "symbols": ["ALPHA"]}])


def test_validate_endpoint_reports_type_and_trace():
    response = client.post("/api/automata/validate", json=make_automaton().model_dump(by_alias=True))
    assert response.status_code == 200
    assert response.json()["valid"] is True
    assert response.json()["classification"]["type"] == "DFA"
    assert response.json()["trace"]


def test_validate_endpoint_returns_422_for_invalid_automaton():
    payload = make_automaton().model_dump(by_alias=True)
    payload["states"][0]["isStart"] = False
    response = client.post("/api/automata/validate", json=payload)
    assert response.status_code == 422


def test_simulate_endpoint_returns_decision_and_trace():
    payload = {"automaton": make_automaton().model_dump(by_alias=True), "input": "a"}
    response = client.post("/api/automata/simulate", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert response.json()["finalStates"] == ["q1"]
    assert response.json()["trace"]


def test_simulate_endpoint_explains_stuck_input():
    payload = {"automaton": make_automaton().model_dump(by_alias=True), "input": "x"}
    response = client.post("/api/automata/simulate", json=payload)
    assert response.json()["reason"] == "stuck at q0 on symbol 'x'"
