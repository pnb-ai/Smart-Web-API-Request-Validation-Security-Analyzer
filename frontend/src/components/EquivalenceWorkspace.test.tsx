import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { EquivalenceWorkspace } from './EquivalenceWorkspace'
import { useAutomataStore } from '../store/automataStore'

const machine = {
  type: 'EPSILON_NFA', states: [
    { id: 'q0', label: 'q0', isStart: true, isAccepting: false, x: 0, y: 0 },
    { id: 'q1', label: 'q1', isStart: false, isAccepting: true, x: 100, y: 0 },
  ], alphabet: ['a'], transitions: [{ from: 'q0', to: 'q1', symbols: ['a'] }],
}

const result = {
  equivalent: false, counterexample: ['a'], counterexampleString: 'a', acceptedBy: 'left',
  path: [['q0', 'r0'], ['q1', 'r0']], leftEmpty: false, rightEmpty: true, leftSubsetRight: false,
  productStatesExplored: 1, method: 'product-bfs', trace: [
    { title: 'Explore pair (q0, r0)', explanation: 'BFS explores this pair.', data: { purpose: 'equivalence', pair: ['q0', 'r0'], transitions: [{ symbol: 'a', to: ['q1', 'r0'] }] } },
  ],
}

describe('EquivalenceWorkspace', () => {
  beforeEach(() => {
    useAutomataStore.setState({ automaton: { type: 'DFA', states: [], alphabet: [], transitions: [] }, past: [], future: [] })
    vi.restoreAllMocks()
  })

  it('lets each side select a regex and displays the shortest-witness playback', async () => {
    let simulationCount = 0
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/api/regex/compile')) return { ok: true, json: async () => ({ automaton: machine, trace: [] }) } as Response
      if (url.endsWith('/api/equivalence')) return { ok: true, json: async () => result } as Response
      simulationCount += 1
      return { ok: true, json: async () => ({ accepted: simulationCount === 1, reason: simulationCount === 1 ? 'ended in accepting state' : 'ended in non-accepting state', trace: [{ title: 'Read a', explanation: '', data: { symbolRead: 'a', currentStates: ['q0'], nextStates: ['q1'] } }] }) } as Response
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<EquivalenceWorkspace />)
    fireEvent.change(screen.getAllByLabelText('Source')[0], { target: { value: 'regex' } })
    fireEvent.change(screen.getByLabelText('Rule v1 regular expression'), { target: { value: 'a' } })
    fireEvent.click(screen.getByRole('button', { name: 'Check equivalence' }))
    expect(await screen.findByText('DIFFERENT ✗')).toBeInTheDocument()
    expect(screen.getByText('request-line: "a"')).toBeInTheDocument()
    expect(await screen.findByText('Run the same request through both rules')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Animated reachable product state graph' })).toBeInTheDocument()
    await waitFor(() => expect(fetchMock.mock.calls.filter(([url]) => String(url).endsWith('/api/automata/simulate'))).toHaveLength(2))
  })

  it('offers an HTTP rule source and reports a friendly backend error', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).endsWith('/api/regex/compile')) return { ok: false, json: async () => ({ detail: 'Unclosed group in regular expression.' }) } as Response
      return { ok: true, json: async () => result } as Response
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<EquivalenceWorkspace />)
    fireEvent.change(screen.getAllByLabelText('Source')[0], { target: { value: 'http-rule' } })
    expect(screen.getByLabelText('Rule v1 HTTP rule')).toBeInTheDocument()
    fireEvent.change(screen.getAllByLabelText('Source')[1], { target: { value: 'regex' } })
    fireEvent.change(screen.getByLabelText('Rule v2 regular expression'), { target: { value: '(' } })
    fireEvent.click(screen.getByRole('button', { name: 'Check equivalence' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Unclosed group in regular expression.')
  })
})
