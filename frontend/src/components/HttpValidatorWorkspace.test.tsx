import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { HttpValidatorWorkspace } from './HttpValidatorWorkspace'
import { useAutomataStore } from '../store/automataStore'
import { useAppStore } from '../store/appStore'

afterEach(() => { cleanup(); vi.unstubAllGlobals(); useAppStore.setState({ activePage: 'builder' }) })

const dfa = { type: 'DFA' as const, states: [{ id: 'q0', label: 'q0', isStart: true, isAccepting: true, x: 0, y: 0 }], alphabet: [], transitions: [] }
const report = {
  overall: 'INVALID' as const,
  checks: [
    { id: 'origin-form', title: 'Request-target', status: 'fail' as const, message: 'Bad percent escape.', rfc: 'RFC 3986 §2.1', position: { offset: 8, line: 1, column: 9 }, automatonId: 'origin-form', input: '/bad%zz' },
    { id: 'host-count', title: 'Host header count', status: 'pass' as const, message: 'Exactly one Host header is present.', rfc: 'RFC 9112 §3.2', position: null, automatonId: null, input: null },
  ],
  parts: { segments: [{ type: 'method', start: 0, end: 3 }, { type: 'target', start: 4, end: 21 }] },
  automata: { 'origin-form': { automaton: dfa } },
}

describe('HTTP Validator workspace', () => {
  it('shows RFC checks and request parts, then hands a rule DFA to Simulator', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => report }))
    render(<HttpValidatorWorkspace />)
    await waitFor(() => expect(screen.getByText('Host header count')).toBeInTheDocument())
    expect(screen.getByText(/RFC 3986 §2.1/)).toBeInTheDocument()
    expect(screen.getByText('/api/users?page=1')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Visualize DFA' }))
    expect(useAutomataStore.getState().automaton).toEqual(dfa)
    expect(useAutomataStore.getState().simulationInput).toBe('/bad%zz')
    expect(useAutomataStore.getState().simulationAutoRun).toBe(true)
    expect(useAppStore.getState().activePage).toBe('simulator')
  })

  it('loads a broken-request sample and jumps to a reported character', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => report }))
    render(<HttpValidatorWorkspace />)
    await waitFor(() => expect(screen.getByText('Request-target')).toBeInTheDocument())
    fireEvent.change(screen.getByRole('combobox', { name: 'Load sample' }), { target: { value: '6' } })
    await waitFor(() => expect(screen.getByDisplayValue(/\/files\/%zz/)).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Jump to character' }))
    const editor = screen.getByRole('textbox', { name: 'Raw HTTP request' }) as HTMLTextAreaElement
    expect(document.activeElement).toBe(editor)
    expect(editor.selectionStart).toBe(8)
  })

  it('shows a friendly backend error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')))
    render(<HttpValidatorWorkspace />)
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('validator service is unavailable'))
  })
})
