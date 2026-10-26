// Keep this interface aligned with backend/app/models/automata.py, the schema source of truth.
export type AutomatonType = 'DFA' | 'NFA' | 'EPSILON_NFA'

export interface AutomatonState {
  id: string
  label: string
  isStart: boolean
  isAccepting: boolean
  x: number
  y: number
}

export interface Transition {
  from: string
  to: string
  symbols: string[]
}

export interface Automaton {
  type: AutomatonType
  states: AutomatonState[]
  alphabet: string[]
  transitions: Transition[]
}

export interface TraceStep {
  title: string
  explanation: string
  data: Record<string, unknown>
}
