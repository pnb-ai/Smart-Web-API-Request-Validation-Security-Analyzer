import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { LexerWorkspace } from './LexerWorkspace'

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe('LexerWorkspace', () => {
  it('renders scanned token chips and opens the combined DFA', async () => {
    const payload = {
      tokens: [{ type: 'METHOD', value: 'GET', line: 1, column: 1, endLine: 1, endColumn: 4, start: 0, end: 3, dfaPath: ['d0', 'd4'], error: null }],
      automaton: { type: 'DFA', states: [{ id: 'd0', label: 'd0', isStart: true, isAccepting: false }], transitions: [] }, trace: [],
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => payload }))
    render(<LexerWorkspace />)
    await waitFor(() => expect(screen.getByText('METHOD', { selector: 'small' })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Show combined DFA' }))
    expect(screen.getByText('Combined DFA')).toBeInTheDocument()
    expect(screen.getByText('d0 · start')).toBeInTheDocument()
  })

  it('shows a friendly service error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('fetch failed')))
    render(<LexerWorkspace />)
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Lexer service is unavailable'))
  })
})
