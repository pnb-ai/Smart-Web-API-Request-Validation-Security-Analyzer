import { useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { ChevronLeft, ChevronRight, Network, Play, ScanText } from 'lucide-react'
import type { Automaton } from '../types/automata'

const API = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'
type Token = { type: string; value: string; line: number; column: number; endLine: number; endColumn: number; start: number; end: number; dfaPath: string[]; error: string | null }
type Machine = Automaton
type Result = { tokens: Token[]; automaton: Machine; trace: { title: string; explanation: string; data: Record<string, unknown> }[] }
const sample = 'GET /api/users?id=42 HTTP/1.1\r\nHost: example.com\r\n'
const color = (kind: string) => kind === 'ERROR' ? 'error' : kind.toLowerCase().replaceAll('_', '-')

export function LexerWorkspace() {
  const [source, setSource] = useState(sample)
  const [result, setResult] = useState<Result | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [showDfa, setShowDfa] = useState(false)
  const [step, setStep] = useState(0)
  const [stepping, setStepping] = useState(false)
  useEffect(() => {
    let cancelled = false
    const timer = window.setTimeout(() => {
      setBusy(true); setError('')
      fetch(`${API}/api/lexer/tokenize`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: source }) })
        .then(async response => { const payload = await response.json(); if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : 'Could not tokenize this request.'); return payload as Result })
        .then(payload => { if (!cancelled) { setResult(payload); setStep(0) } })
        .catch(cause => { if (!cancelled) { setResult(null); setError(cause instanceof TypeError ? 'Lexer service is unavailable. Start the backend and try again.' : cause instanceof Error ? cause.message : 'Could not tokenize this request.') } })
        .finally(() => { if (!cancelled) setBusy(false) })
    }, 180)
    return () => { cancelled = true; window.clearTimeout(timer) }
  }, [source])
  useEffect(() => {
    if (!stepping || !result) return
    const timer = window.setInterval(() => setStep(value => { if (value >= source.length) { setStepping(false); return value }; return value + 1 }), 320)
    return () => window.clearInterval(timer)
  }, [stepping, result, source.length])
  const highlighted = useMemo(() => result?.tokens.map(token => <span key={`${token.start}-${token.end}`} className={`lexer-highlight ${color(token.type)}`}>{source.slice(token.start, token.end)}</span>) || null, [result, source])
  const currentToken = result?.tokens.find(token => step >= token.start && step < token.end)
  const machine = result?.automaton
  return <motion.section className="lexer-workspace" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
    <div className="lexer-intro"><div><span className="inspector-kicker">HTTP REQUEST SCANNER</span><h2>Lexer</h2><p>Scan request text with a combined DFA using maximal munch and priority rules.</p></div><span className="lexer-status">{busy ? 'Scanning…' : result ? `${result.tokens.length} tokens` : 'Ready'}</span></div>
    <section className="lexer-card"><div className="regex-card-heading"><div><span className="inspector-kicker">REQUEST TEXT</span><strong>Input</strong></div><small>Tokenizes as you type</small></div><textarea aria-label="HTTP request text" className="text-input lexer-input" value={source} onChange={event => setSource(event.target.value)} spellCheck={false} /><div className="lexer-input-footer"><span>Lines and columns are one-based</span><button className="button button-secondary" onClick={() => setSource(sample)}>Load example</button></div></section>
    {error && <div className="lexer-error-banner" role="alert">{error}</div>}
    {result && <>
      <section className="lexer-card"><div className="regex-card-heading"><div><span className="inspector-kicker">TOKEN STREAM</span><strong>Colored tokens</strong></div><span className="lexer-legend">Hover a token for its DFA path</span></div><div className="lexer-chips">{result.tokens.length ? result.tokens.map(token => <span key={`chip-${token.start}`} className={`lexer-chip ${color(token.type)}`} title={`${token.type} · line ${token.line}, column ${token.column}\nDFA: ${token.dfaPath.join(' → ')}${token.error ? `\n${token.error}` : ''}`}>{token.value === '\r\n' ? '↵ CRLF' : token.value === ' ' ? '␠' : token.value === '\t' ? '⇥' : token.value}<small>{token.type}</small></span>) : <div className="lexer-empty">No tokens yet. Enter an HTTP request above.</div>}</div></section>
      <section className="lexer-card"><div className="regex-card-heading"><div><span className="inspector-kicker">TOKEN DETAILS</span><strong>Token table</strong></div><button className="button button-secondary" onClick={() => setShowDfa(value => !value)}><Network size={14}/>{showDfa ? 'Hide combined DFA' : 'Show combined DFA'}</button></div><div className="lexer-table-wrap"><table className="lexer-table"><thead><tr><th>Type</th><th>Value</th><th>Position</th><th>DFA path</th></tr></thead><tbody>{result.tokens.map(token => <tr key={`row-${token.start}`} className={token.type === 'ERROR' ? 'lexer-error-row' : ''}><td><span className={`lexer-kind ${color(token.type)}`}>{token.type}</span>{token.error && <small className="lexer-error-copy">{token.error}</small>}</td><td><code>{token.value === '\r\n' ? 'CRLF' : token.value === ' ' ? '␠' : token.value}</code></td><td><code>{token.line}:{token.column}</code></td><td><code className="lexer-path">{token.dfaPath.join(' → ')}</code></td></tr>)}</tbody></table>{!result.tokens.length && <div className="lexer-empty">No input to tokenize.</div>}</div></section>
      {showDfa && machine && <section className="lexer-card"><div className="regex-card-heading"><div><span className="inspector-kicker">TOKEN RULE AUTOMATA</span><strong>Combined DFA</strong></div><span className="lexer-legend">{machine.states.length} states · {machine.transitions.length} transitions</span></div><div className="lexer-dfa-summary"><span>Regex Lab compiles each token pattern into an ε-NFA, then subset construction joins the rules.</span><span>Longest match wins; ties use token priority.</span></div><div className="lexer-dfa-list">{machine.states.map(state => <span key={state.id} className={`${state.isStart ? 'start' : ''} ${state.isAccepting ? 'accept' : ''}`}>{state.id}{state.isStart ? ' · start' : ''}{state.isAccepting ? ' · token accept' : ''}</span>)}</div><details className="lexer-transitions"><summary>View transition table</summary><div className="lexer-table-wrap"><table className="lexer-table"><thead><tr><th>From</th><th>Symbols</th><th>To</th></tr></thead><tbody>{machine.transitions.map((edge, i) => <tr key={i}><td><code>{edge.from}</code></td><td><code>{edge.symbols.join(', ')}</code></td><td><code>{edge.to}</code></td></tr>)}</tbody></table></div></details></section>}
      <section className="lexer-card lexer-step-card"><div className="regex-card-heading"><div><span className="inspector-kicker">ANIMATED SCAN</span><strong>Step through characters</strong></div><ScanText size={17}/></div><div className="lexer-step-text" aria-label="Character scan visualization">{highlighted?.map((fragment, index) => <span key={index}>{fragment}</span>)}{!source && <span className="lexer-empty-inline">Type request text to begin.</span>}</div><div className="lexer-step-controls"><button className="button button-secondary" title="Previous character" onClick={() => { setStepping(false); setStep(value => Math.max(0, value - 1)) }}><ChevronLeft size={14}/>Back</button><input aria-label="Character scan position" type="range" min={0} max={source.length} value={Math.min(step, source.length)} onChange={event => { setStepping(false); setStep(Number(event.target.value)) }}/><code>{Math.min(step, source.length)} / {source.length}</code><button className="button button-secondary" title="Next character" onClick={() => { setStepping(false); setStep(value => Math.min(source.length, value + 1)) }}>Next<ChevronRight size={14}/></button><button className="button button-primary" onClick={() => { if (step >= source.length) setStep(0); setStepping(value => !value) }}><Play size={13}/>{stepping ? 'Pause' : 'Play'}</button></div><p className="lexer-step-explanation">{currentToken ? `Reading ${JSON.stringify(source[step])} in ${currentToken.type}; current DFA path: ${currentToken.dfaPath.slice(0, Math.max(1, step - currentToken.start + 2)).join(' → ')}.` : step >= source.length ? 'End of input.' : 'Advance to inspect each character and the token it belongs to.'}</p></section>
    </>}
  </motion.section>
}
