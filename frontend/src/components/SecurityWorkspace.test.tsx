import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { SecurityWorkspace } from './SecurityWorkspace'
import { useAutomataStore } from '../store/automataStore'
import { useAppStore } from '../store/appStore'
import { ToastProvider } from './ToastProvider'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  useAppStore.setState({ activePage: 'security' })
})

const sampleDfa = {
  type: 'DFA' as const,
  states: [{ id: 'q0', label: 'q0', isStart: true, isAccepting: true, x: 0, y: 0 }],
  alphabet: ['a'],
  transitions: [{ from: 'q0', to: 'q0', symbols: ['a'] }],
}

const mockReport = {
  status: 'MALICIOUS' as const,
  riskScore: 75,
  findings: [
    {
      id: 'sec-1',
      ruleId: 'sqli-or-tautology',
      ruleName: 'SQL Injection (Boolean Tautology)',
      category: 'sql_injection',
      severity: 'critical' as const,
      matchedText: "' OR 1=1",
      position: { offset: 10, length: 8, line: 1, column: 11, section: 'query' },
      explanation: 'Tautology detected in request.',
      recommendedFix: 'Use parameterized queries.',
      normalizationStep: 'url_decode_1' as const,
      automatonId: 'sqli-or-tautology',
    },
    {
      id: 'sec-2',
      ruleId: 'path-traversal-dotdot',
      ruleName: 'Path Traversal (Directory Climbing)',
      category: 'path_traversal',
      severity: 'high' as const,
      matchedText: '../',
      position: { offset: 25, length: 3, line: 1, column: 26, section: 'path' },
      explanation: 'Directory climbing detected.',
      recommendedFix: 'Validate path allowlist.',
      normalizationStep: 'raw' as const,
      automatonId: 'path-traversal-dotdot',
    },
  ],
  findingsSummary: {
    critical: 1,
    high: 1,
    medium: 0,
    low: 0,
    total: 2,
  },
  categoriesDetected: ['path_traversal', 'sql_injection'],
  normalizationSteps: [
    { step: 'raw', label: 'Raw Request', description: 'Original text' },
    { step: 'url_decode_1', label: 'URL Decode', description: 'Single pass unquote' },
  ],
  normalizationTrace: [
    {
      ruleId: 'sqli-or-tautology',
      section: 'query',
      stage: 'url_decode_1',
      stageLabel: 'URL Decode',
      match: "' OR 1=1",
    },
  ],
  automata: {
    'sqli-or-tautology': sampleDfa,
    'path-traversal-dotdot': sampleDfa,
  },
  trace: [
    {
      title: 'Security Analysis Complete',
      explanation: 'Evaluated request threat level.',
      data: { status: 'MALICIOUS', riskScore: 75 },
    },
  ],
  defenseDisclaimer: 'Automata-based regular expression filters serve as a high-speed first line of defense.',
  requestParts: {
    method: 'GET',
    target: '/items',
    version: 'HTTP/1.1',
    headers: {},
    hasBody: false,
    bodyLength: 0,
  },
}

const mockDiffResult = {
  equivalent: false,
  counterexample: '..\\',
  oldPattern: '(\\.\\./)',
  newPattern: '(\\.\\./|\\.\\.\\\\)',
  oldDfa: sampleDfa,
  newDfa: sampleDfa,
  leftSubsetRight: true,
  payloadEvaluations: [
    { payload: '../', blockedByOld: true, blockedByNew: true, behavior: 'blocked_by_both' as const },
    { payload: '..\\', blockedByOld: false, blockedByNew: true, behavior: 'newly_blocked' as const },
  ],
  trace: [],
}

function renderWorkspace() {
  return render(
    <ToastProvider>
      <SecurityWorkspace />
    </ToastProvider>
  )
}

describe('Security Analyzer workspace', () => {
  it('renders defense-in-depth disclaimer, risk gauge, and displays findings', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => mockReport }))
    renderWorkspace()

    // Assert Defense in Depth disclaimer banner
    expect(screen.getByText(/Defense-in-Depth Principle:/)).toBeInTheDocument()
    expect(document.querySelector('.defense-text')?.textContent).toMatch(
      /not a replacement for parameterized queries/i
    )

    // Wait for findings to render
    await waitFor(() => {
      expect(screen.getByText('SQL Injection (Boolean Tautology)')).toBeInTheDocument()
    })

    expect(screen.getByText('Path Traversal (Directory Climbing)')).toBeInTheDocument()
    expect(screen.getByText('75')).toBeInTheDocument()
    expect(screen.getByText('CRITICAL')).toBeInTheDocument()
    expect(screen.getByText('HIGH')).toBeInTheDocument()
  })

  it('hands a rule DFA to the Simulator when user clicks inspect', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => mockReport }))
    renderWorkspace()

    await waitFor(() => {
      expect(screen.getByText('SQL Injection (Boolean Tautology)')).toBeInTheDocument()
    })

    // Expand details
    const expandButtons = screen.getAllByTitle('Toggle details')
    fireEvent.click(expandButtons[0])

    await waitFor(() => {
      expect(screen.getByText('Inspect Rule DFA in Simulator')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Inspect Rule DFA in Simulator'))
    expect(useAutomataStore.getState().automaton).toEqual(sampleDfa)
    expect(useAutomataStore.getState().simulationInput).toBe("' OR 1=1")
    expect(useAutomataStore.getState().simulationAutoRun).toBe(true)
    expect(useAppStore.getState().activePage).toBe('simulator')
  })

  it('switches to Rule Diff tab and compares regular expressions with Equivalence Checker', async () => {
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/api/security/rule-diff')) {
        return Promise.resolve({ ok: true, json: async () => mockDiffResult })
      }
      return Promise.resolve({ ok: true, json: async () => mockReport })
    })
    vi.stubGlobal('fetch', fetchMock)

    renderWorkspace()

    // Switch to Rule Diff tab
    fireEvent.click(screen.getByRole('button', { name: /Rule Diff & Equivalence/i }))

    await waitFor(() => {
      expect(screen.getByText(/Security Rule Diff & Equivalence Checker/i)).toBeInTheDocument()
    })

    // Click Compare Rules
    fireEvent.click(screen.getByRole('button', { name: /Compare Rules with Equivalence Checker/i }))

    await waitFor(() => {
      expect(screen.getByText(/Rules are Distinguishable: Languages Differ/i)).toBeInTheDocument()
    })

    expect(screen.getAllByText('..\\').length).toBeGreaterThan(0)
    expect(screen.getByText('🛡️ Newly Blocked (Tightened)')).toBeInTheDocument()
  })

  it('renders normalization trace steps in the trace tab', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => mockReport }))
    renderWorkspace()

    await waitFor(() => {
      expect(screen.getByText('SQL Injection (Boolean Tautology)')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /Normalization Trace/i }))

    await waitFor(() => {
      expect(screen.getByText(/Multi-Stage Input Decoding & Execution Steps/i)).toBeInTheDocument()
    })

    expect(screen.getByText('Raw Request')).toBeInTheDocument()
    expect(screen.getByText('URL Decode')).toBeInTheDocument()
  })

  it('displays a friendly error when backend is unreachable', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    renderWorkspace()

    await waitFor(() => {
      expect(screen.getByText(/Security analyzer backend service is offline/i)).toBeInTheDocument()
    })
  })
})
