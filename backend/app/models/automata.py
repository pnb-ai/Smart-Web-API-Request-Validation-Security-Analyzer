"""Compatibility imports; automata models are owned by app.automata.models."""

from app.automata.models import Automaton, AutomatonState, State, Transition

__all__ = ["Automaton", "AutomatonState", "State", "Transition"]
