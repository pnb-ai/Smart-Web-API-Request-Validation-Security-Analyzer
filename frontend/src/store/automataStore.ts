import { create } from 'zustand'
import type { Automaton, AutomatonState, Transition, AutomatonType } from '../types/automata'

type Snapshot = { automaton: Automaton; past: Automaton[]; future: Automaton[] }
type AutomataState = Snapshot & {
  setAutomaton: (automaton: Automaton) => void
  addState: (x: number, y: number) => void
  updateState: (id: string, patch: Partial<AutomatonState>) => void
  removeState: (id: string) => void
  addTransition: (from: string, to: string, symbols?: string[]) => void
  updateTransition: (index: number, patch: Partial<Transition>) => void
  removeTransition: (index: number) => void
  setType: (type: AutomatonType) => void
  undo: () => void
  redo: () => void
}
export const emptyAutomaton = (): Automaton => ({ type: 'DFA', states: [], alphabet: [], transitions: [] })
const snapshot = (state: Snapshot, automaton: Automaton): Snapshot => ({ automaton, past: [...state.past, state.automaton].slice(-80), future: [] })
const initial: Snapshot = { automaton: emptyAutomaton(), past: [], future: [] }

export const useAutomataStore = create<AutomataState>((set) => ({
  ...initial,
  setAutomaton: (automaton) => set((state) => snapshot(state, automaton)),
  addState: (x, y) => set((state) => {
    let index = 1
    while (state.automaton.states.some((item) => item.id === `q${index}`)) index += 1
    const id = `q${index}`
    const next: Automaton = { ...state.automaton, states: [...state.automaton.states, { id, label: id, isStart: index === 1, isAccepting: false, x, y }] }
    return snapshot(state, next)
  }),
  updateState: (id, patch) => set((state) => snapshot(state, { ...state.automaton, states: state.automaton.states.map((item) => ({ ...item, ...(item.id === id ? patch : {}), ...(patch.isStart && item.id !== id ? { isStart: false } : {}) })) })),
  removeState: (id) => set((state) => snapshot(state, { ...state.automaton, states: state.automaton.states.filter((item) => item.id !== id), transitions: state.automaton.transitions.filter((edge) => edge.from !== id && edge.to !== id) })),
  addTransition: (from, to, symbols = ['a']) => set((state) => snapshot(state, { ...state.automaton, alphabet: [...new Set([...state.automaton.alphabet, ...symbols.filter((s) => s !== 'ε')])], transitions: [...state.automaton.transitions, { from, to, symbols }] })),
  updateTransition: (index, patch) => set((state) => {
    const transitions = state.automaton.transitions.map((edge, i) => i === index ? { ...edge, ...patch } : edge)
    const alphabet = [...new Set(transitions.flatMap((edge) => edge.symbols).filter((symbol) => symbol !== 'ε'))]
    return snapshot(state, { ...state.automaton, transitions, alphabet })
  }),
  removeTransition: (index) => set((state) => {
    const transitions = state.automaton.transitions.filter((_, i) => i !== index)
    return snapshot(state, { ...state.automaton, transitions, alphabet: [...new Set(transitions.flatMap((edge) => edge.symbols).filter((s) => s !== 'ε'))] })
  }),
  setType: (type) => set((state) => snapshot(state, { ...state.automaton, type })),
  undo: () => set((state) => {
    if (!state.past.length) return state
    const previous = state.past.at(-1)!
    return { automaton: previous, past: state.past.slice(0, -1), future: [state.automaton, ...state.future] }
  }),
  redo: () => set((state) => {
    if (!state.future.length) return state
    return { automaton: state.future[0], past: [...state.past, state.automaton], future: state.future.slice(1) }
  }),
}))
