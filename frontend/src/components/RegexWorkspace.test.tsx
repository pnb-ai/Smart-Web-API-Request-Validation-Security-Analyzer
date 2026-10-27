import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { RegexWorkspace } from './RegexWorkspace'
import { useAppStore } from '../store/appStore'

const automaton = { type: 'EPSILON_NFA' as const, states: [{ id: 'q0', label: 'q0', isStart: true, isAccepting: false, x: 0, y: 0 }, { id: 'q1', label: 'q1', isStart: false, isAccepting: true, x: 100, y: 0 }], alphabet: ['a'], transitions: [{ from: 'q0', to: 'q1', symbols: ['a'] }] }

describe('Regex Lab', () => {
  beforeEach(() => {
    useAppStore.setState({ regexDraft: '', activePage: 'regex' })
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => ({
      ok: true,
      json: async () => String(input).includes('/simulate') ? { accepted: true, reason: 'ended in an accepting state', trace: [] } : {
        ast: { type: 'class', position: 0, value: ['a'] }, epsilonNfa: automaton, dfa: { ...automaton, type: 'DFA' }, minimalDfa: { ...automaton, type: 'DFA' }, trace: [{ title: 'Build character fragment', explanation: 'Create a symbol fragment.', data: { start: 'q0', end: 'q1' } }], intermediateAutomata: [], pipelineTrace: [],
      },
    })))
  })

  it('parses an expression, displays its AST/pipeline, and offers example presets', async () => {
    render(<RegexWorkspace />)
    expect(screen.getByRole('textbox', { name: 'Regular expression' })).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('Build character fragment')).toBeInTheDocument())
    expect(screen.getByText('PARSED STRUCTURE')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'UUID' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Open ε-NFA in Simulator' }))
    expect(useAppStore.getState().activePage).toBe('simulator')
  })
})
