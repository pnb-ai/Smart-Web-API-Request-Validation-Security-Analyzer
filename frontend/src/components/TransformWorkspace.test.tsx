import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ToastProvider } from './ToastProvider'
import { TransformWorkspace } from './TransformWorkspace'
import { useAutomataStore } from '../store/automataStore'
import { useAppStore } from '../store/appStore'
import type { Automaton } from '../types/automata'

const source: Automaton = {
  type: 'EPSILON_NFA',
  states: [
    { id: 'q0', label: 'start', isStart: true, isAccepting: false, x: 0, y: 0 },
    { id: 'q1', label: 'accept', isStart: false, isAccepting: true, x: 100, y: 0 },
  ],
  alphabet: ['a'],
  transitions: [{ from: 'q0', to: 'q1', symbols: ['ε', 'a'] }],
}
const nfa: Automaton = { ...source, type: 'NFA', transitions: [{ from: 'q0', to: 'q1', symbols: ['a'] }] }
const dfa: Automaton = { ...nfa, type: 'DFA', states: [{ ...source.states[0], id: '{q0}', label: '{q0}' }, { ...source.states[1], id: '{q1}', label: '{q1}' }], transitions: [{ from: '{q0}', to: '{q1}', symbols: ['a'] }] }
const minimized: Automaton = { ...dfa, states: [{ ...dfa.states[0], id: 'q0', label: 'start' }, { ...dfa.states[1], id: 'q1', label: 'accept' }], transitions: [{ from: 'q0', to: 'q1', symbols: ['a'] }] }

const pipelineResponse = {
  result: minimized,
  trace: [],
  intermediateAutomata: [
    { operation: 'epsilon-elimination', automaton: nfa, trace: [{ title: 'Compute ε-closure', explanation: 'Follow ε edges from q0.', data: { state: 'q0', closure: ['q0', 'q1'] } }] },
    { operation: 'subset-construction', automaton: dfa, trace: [{ title: 'Process subset {q0}', explanation: 'Compute its destination set for each symbol.', data: { sourceState: '{q0}', subsetTable: [{ dfaState: '{q0}', nfaStates: ['q0'] }], transitions: [{ symbols: ['a'], destinationSet: ['q1'], destinationState: '{q1}', newState: true }] } }] },
    { operation: 'minimize-table', automaton: minimized, trace: [{ title: 'Distinguishability pass 1', explanation: 'Mark pairs that can be distinguished.', data: { newlyMarked: [{ states: ['q0', 'q1'], symbol: 'a' }] } }] },
  ],
}

function renderPage() { return render(<ToastProvider><TransformWorkspace /></ToastProvider>) }

beforeEach(() => {
  useAutomataStore.getState().setAutomaton(source)
  useAppStore.getState().setPage('transform')
  vi.stubGlobal('fetch', vi.fn(async (url: string | URL | Request) => ({
    ok: true,
    json: async () => String(url).endsWith('/api/transform') ? pipelineResponse : { accepted: true },
  })))
})
afterEach(() => vi.unstubAllGlobals())

describe('Transform & Optimize workspace', () => {
  it('shows pipeline results and steps through conversion traces', async () => {
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Run full pipeline' }))
    expect(await screen.findByText('ε-NFA → NFA')).toBeInTheDocument()
    expect(screen.getByText('Compute ε-closure')).toBeInTheDocument()
    expect(screen.getByText('2 → 2')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Next transformation' }))
    expect(await screen.findByText('NFA → DFA')).toBeInTheDocument()
    expect(screen.getByText('Process subset {q0}')).toBeInTheDocument()
  })

  it('sends the final automaton to Simulator', async () => {
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Run full pipeline' }))
    await screen.findByText('ε-NFA → NFA')
    fireEvent.click(screen.getByRole('button', { name: 'Send result to Simulator' }))
    expect(useAppStore.getState().activePage).toBe('simulator')
    expect(useAutomataStore.getState().automaton).toEqual(minimized)
  })

  it('requests Hopcroft refinement when selected', async () => {
    renderPage()
    fireEvent.change(screen.getByLabelText('Minimization'), { target: { value: 'hopcroft' } })
    fireEvent.click(screen.getByRole('button', { name: 'Run full pipeline' }))
    await screen.findByText('ε-NFA → NFA')
    const request = vi.mocked(fetch).mock.calls.find(([url]) => String(url).endsWith('/api/transform'))
    expect(JSON.parse(request?.[1]?.body as string).minimizer).toBe('hopcroft')
  })

  it('compares random strings against both automata', async () => {
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Run full pipeline' }))
    await screen.findByText('ε-NFA → NFA')
    fireEvent.click(screen.getByRole('button', { name: 'Compare language preserved' }))
    expect(await screen.findByText('Languages match')).toBeInTheDocument()
    expect(screen.getByText('50 random strings checked')).toBeInTheDocument()
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(101))
  })
})
