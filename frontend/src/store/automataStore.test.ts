import { beforeEach, describe, expect, it } from 'vitest'
import { emptyAutomaton, useAutomataStore } from './automataStore'

const reset = () => useAutomataStore.setState({ ...useAutomataStore.getState(), automaton: emptyAutomaton(), past: [], future: [] })

describe('automata store', () => {
  beforeEach(reset)

  it('adds a unique state and assigns the first state as start', () => {
    const store = useAutomataStore.getState()
    store.addState(20, 30)
    useAutomataStore.getState().addState(50, 60)
    expect(useAutomataStore.getState().automaton.states.map((s) => s.id)).toEqual(['q1', 'q2'])
    expect(useAutomataStore.getState().automaton.states[0].isStart).toBe(true)
    expect(useAutomataStore.getState().automaton.states[1].isStart).toBe(false)
  })

  it('maintains one start state when selecting a new one', () => {
    const store = useAutomataStore.getState()
    store.addState(0, 0)
    useAutomataStore.getState().addState(1, 1)
    useAutomataStore.getState().updateState('q2', { isStart: true })
    expect(useAutomataStore.getState().automaton.states.filter((s) => s.isStart).map((s) => s.id)).toEqual(['q2'])
  })

  it('adds and edits transition symbols while excluding epsilon from alphabet', () => {
    useAutomataStore.getState().addState(0, 0)
    useAutomataStore.getState().addState(1, 1)
    useAutomataStore.getState().addTransition('q1', 'q2', ['ε', 'DIGIT'])
    expect(useAutomataStore.getState().automaton.alphabet).toEqual(['DIGIT'])
    useAutomataStore.getState().updateTransition(0, { symbols: ['a', 'b'] })
    expect(useAutomataStore.getState().automaton.alphabet).toEqual(['a', 'b'])
  })

  it('removes a state and its incident edges', () => {
    useAutomataStore.getState().addState(0, 0)
    useAutomataStore.getState().addState(1, 1)
    useAutomataStore.getState().addTransition('q1', 'q2')
    useAutomataStore.getState().removeState('q1')
    expect(useAutomataStore.getState().automaton.states).toHaveLength(1)
    expect(useAutomataStore.getState().automaton.transitions).toHaveLength(0)
  })

  it('undoes and redoes edits', () => {
    useAutomataStore.getState().addState(10, 12)
    useAutomataStore.getState().undo()
    expect(useAutomataStore.getState().automaton.states).toHaveLength(0)
    useAutomataStore.getState().redo()
    expect(useAutomataStore.getState().automaton.states[0]).toMatchObject({ id: 'q1', x: 10, y: 12 })
  })

  it('clears redo history after a new edit', () => {
    useAutomataStore.getState().addState(0, 0)
    useAutomataStore.getState().undo()
    useAutomataStore.getState().addState(1, 2)
    useAutomataStore.getState().redo()
    expect(useAutomataStore.getState().automaton.states.map((s) => s.id)).toEqual(['q1'])
  })

  it('loads a complete automaton snapshot', () => {
    const value = { type: 'NFA' as const, states: [{ id: 's', label: 'S', isStart: true, isAccepting: true, x: 3, y: 4 }], alphabet: ['ALPHA'], transitions: [] }
    useAutomataStore.getState().setAutomaton(value)
    expect(useAutomataStore.getState().automaton).toEqual(value)
  })
})
