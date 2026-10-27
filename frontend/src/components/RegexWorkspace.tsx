import { useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { ArrowRight, LoaderCircle, Play, Send, Sparkles } from 'lucide-react'
import { useAutomataStore } from '../store/automataStore'
import { useAppStore } from '../store/appStore'
import type { Automaton, TraceStep } from '../types/automata'

const API = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'
type Ast = { type: string; position: number; value?: unknown; children?: Ast[] }
type Converted = { ast: Ast; epsilonNfa: Automaton; dfa: Automaton; minimalDfa: Automaton; trace: TraceStep[] }
type Preset = { name: string; pattern: string }
const presets: Preset[] = [
  { name: 'Email-like', pattern: '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}' },
  { name: 'IPv4', pattern: '(25[0-5]|2[0-4]\\d|1?\\d?\\d)(\\.(25[0-5]|2[0-4]\\d|1?\\d?\\d)){3}' },
  { name: 'UUID', pattern: '[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}' },
  { name: 'API key', pattern: 'sk_[A-Za-z0-9]{24,40}' },
  { name: '/users/{id}', pattern: '/users/[0-9]+' },
]

export function RegexWorkspace() {
  const regexDraft = useAppStore((state) => state.regexDraft)
  const setRegexDraft = useAppStore((state) => state.setRegexDraft)
  const setPage = useAppStore((state) => state.setPage)
  const setAutomaton = useAutomataStore((state) => state.setAutomaton)
  const [pattern, setPattern] = useState(regexDraft || presets[0].pattern)
  const [converted, setConverted] = useState<Converted | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [stage, setStage] = useState<'epsilonNfa' | 'dfa' | 'minimalDfa'>('epsilonNfa')
  const [traceIndex, setTraceIndex] = useState(0)
  const [testString, setTestString] = useState('')
  const [match, setMatch] = useState<{ accepted: boolean; reason: string; trace: TraceStep[] } | null>(null)
  const [matchBusy, setMatchBusy] = useState(false)
  const machine = converted?.[stage]
  const currentStep = converted?.trace[traceIndex]
  const stageNames = useMemo(() => ({ epsilonNfa: 'ε-NFA', dfa: 'DFA', minimalDfa: 'Minimal DFA' }), [])

  useEffect(() => {
    let cancelled = false
    const timer = window.setTimeout(() => {
      setBusy(true); setError(''); setMatch(null)
      fetch(`${API}/api/regex/convert`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ pattern }) })
        .then(async (response) => { const payload = await response.json(); if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : 'Check the expression and try again.'); return payload as Converted })
        .then((payload) => { if (!cancelled) { setConverted(payload); setTraceIndex(0) } })
        .catch((cause: unknown) => { if (!cancelled) { setConverted(null); setError(cause instanceof TypeError ? 'The regex service is unavailable. Start the backend and try again.' : cause instanceof Error ? cause.message : 'Could not parse this expression.') } })
        .finally(() => { if (!cancelled) setBusy(false) })
    }, 250)
    return () => { cancelled = true; window.clearTimeout(timer) }
  }, [pattern])

  // Keep the shared draft current so Equivalence Checker can open with this expression.
  useEffect(() => setRegexDraft(pattern), [pattern, setRegexDraft])

  useEffect(() => {
    if (!converted) return
    let cancelled = false
    const timer = window.setTimeout(() => {
      setMatchBusy(true)
      fetch(`${API}/api/automata/simulate`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ automaton: converted.epsilonNfa, input: testString }) })
        .then(async (response) => { const payload = await response.json(); if (!response.ok) throw new Error('Could not simulate this test string.'); if (!cancelled) setMatch({ accepted: Boolean(payload.accepted), reason: String(payload.reason), trace: payload.trace as TraceStep[] }) })
        .catch(() => { if (!cancelled) setMatch(null) }).finally(() => { if (!cancelled) setMatchBusy(false) })
    }, 180)
    return () => { cancelled = true; window.clearTimeout(timer) }
  }, [converted, testString])

  const openSimulator = () => { if (!converted) return; setAutomaton(converted.epsilonNfa); setPage('simulator') }
  const openEquivalence = () => { setRegexDraft(pattern); setPage('equivalence') }
  const playTrace = () => { if (!converted) return; const last = converted.trace.length - 1; let index = traceIndex; const timer = window.setInterval(() => { index += 1; setTraceIndex(Math.min(index, last)); if (index >= last) window.clearInterval(timer) }, 650) }

  return <motion.section className="regex-workspace" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
    <div className="regex-toolbar"><div><span className="inspector-kicker">REGULAR LANGUAGE PLAYGROUND</span><h2>Regex Lab</h2><p>Parse a pattern, watch Thompson’s construction, then explore its deterministic forms.</p></div><label className="regex-preset"><span>Start with a preset</span><select className="text-input" defaultValue="" onChange={(event) => { const preset = presets[Number(event.target.value)]; if (preset) setPattern(preset.pattern); event.target.value = '' }}><option value="" disabled>Choose a format…</option>{presets.map((item, i) => <option key={item.name} value={i}>{item.name}</option>)}</select></label></div>
    <div className="regex-editor-card"><div className="regex-card-heading"><div><span className="inspector-kicker">FULL-STRING MATCH</span><strong>Regular expression</strong></div><span className="regex-language">| · () · * + ? · {'{m,n}'} · [] · escapes · .</span></div><div className="regex-code-wrap"><div className="regex-code-highlight" aria-hidden="true">{highlightPattern(pattern, errorPosition(error))}{!pattern && <span className="regex-placeholder">(GET|POST) /users/\d+</span>}</div><input className={`text-input regex-main-input ${error ? 'regex-invalid' : ''}`} aria-label="Regular expression" aria-invalid={Boolean(error)} value={pattern} onChange={(event) => setPattern(event.target.value)} spellCheck={false} placeholder="" /></div><div className="regex-editor-footer"><small>{busy ? 'Parsing and converting…' : error ? 'Syntax issue' : 'Live parse'}{error && <span className="regex-error"> · {error}</span>}</small><small>Positions are zero-based · match entire input</small></div></div>
    <div className="regex-presets">{presets.map((item) => <button key={item.name} className="regex-preset-chip" onClick={() => setPattern(item.pattern)}>{item.name}</button>)}</div>
    {converted && <>
      <div className="regex-overview">
        <section className="regex-ast-card"><div className="regex-card-heading"><div><span className="inspector-kicker">PARSED STRUCTURE</span><strong>AST</strong></div><span className="regex-language">position · node</span></div><AstTree node={converted.ast} /></section>
        <section className="regex-machine-card"><div className="regex-card-heading"><div><span className="inspector-kicker">AUTOMATA PIPELINE</span><strong>From expression to minimal machine</strong></div><Sparkles size={17}/></div><div className="regex-tabs">{(['epsilonNfa', 'dfa', 'minimalDfa'] as const).map((key) => <button key={key} className={stage === key ? 'selected' : ''} onClick={() => setStage(key)}>{stageNames[key]} <small>{converted[key].states.length}</small></button>)}</div><AutomatonPreview automaton={machine!} activeStates={(currentStep?.data.states as string[] | undefined) || []}/></section>
      </div>
      <div className="regex-actions"><button className="button button-primary" onClick={openSimulator}><Send size={14}/> Open ε-NFA in Simulator</button><button className="button button-secondary" onClick={openEquivalence}><ArrowRight size={14}/> Open in Equivalence Checker</button></div>
      <section className="regex-trace-card"><div className="regex-card-heading"><div><span className="inspector-kicker">THOMPSON CONSTRUCTION</span><strong>{currentStep?.title || 'Construction trace'}</strong></div><div className="regex-trace-controls"><button className="button button-secondary" onClick={() => setTraceIndex((i) => Math.max(0, i - 1))} disabled={traceIndex === 0}>Back</button><span>{traceIndex + 1} / {converted.trace.length}</span><button className="button button-secondary" onClick={playTrace} title="Animate the remaining construction"><Play size={13}/> Play</button><button className="button button-secondary" onClick={() => setTraceIndex((i) => Math.min(converted.trace.length - 1, i + 1))} disabled={traceIndex >= converted.trace.length - 1}>Next</button></div></div><p className="regex-explanation">{currentStep?.explanation}</p><pre className="regex-trace-data">{JSON.stringify(currentStep?.data || {}, null, 2)}</pre></section>
      <section className="regex-test-card"><div className="regex-card-heading"><div><span className="inspector-kicker">TRY A STRING</span><strong>Live full-match test</strong></div>{matchBusy && <LoaderCircle className="spin" size={15}/>}</div><input className="text-input" aria-label="Test string" value={testString} onChange={(event) => setTestString(event.target.value)} placeholder="Type a test string…" />{match && <div className={`regex-match ${match.accepted ? 'yes' : 'no'}`}><strong>{match.accepted ? 'MATCH ✓' : 'NO MATCH'}</strong><span>{match.reason}</span></div>}<ol className="regex-simulation-trace">{match?.trace.filter((step) => step.data.symbolRead !== undefined).map((step, index) => <li key={index}><code>{String(step.data.symbolRead)}</code><span>{Array.isArray(step.data.currentStates) ? step.data.currentStates.join(', ') : '—'} → {Array.isArray(step.data.nextStates) ? step.data.nextStates.join(', ') : '∅'}</span></li>)}</ol></section>
    </>}
    {!converted && !busy && <section className="regex-empty"><Sparkles size={22}/><strong>Waiting for a valid expression</strong><span>{error || 'Enter a pattern or choose a preset to build its automata.'}</span></section>}
  </motion.section>
}

function AstTree({ node, depth = 0 }: { node: Ast; depth?: number }) { return <div className="ast-node" style={{ marginLeft: depth * 12 }}><span className="ast-kind">{node.type}</span><small>@{node.position}</small>{node.value !== undefined && <code>{Array.isArray(node.value) ? `[${node.value.join('')}]` : JSON.stringify(node.value)}</code>}{node.children?.map((child, i) => <AstTree key={`${child.position}-${i}`} node={child} depth={depth + 1}/>)}</div> }

function highlightPattern(value: string, errorAt: number | null) { return [...value].map((char, index) => { const kind = '\\[]'.includes(char) ? 'escape' : '()|*+?{}'.includes(char) ? 'operator' : char === '.' ? 'wildcard' : char === '-' ? 'range' : ''; return <span className={`${kind} ${index === errorAt ? 'syntax-error' : ''}`} key={index}>{char}</span> }) }
function errorPosition(message: string) { const found = message.match(/position (\d+)/i); return found ? Number(found[1]) : null }

function AutomatonPreview({ automaton, activeStates }: { automaton: Automaton; activeStates: string[] }) {
  const width = Math.max(420, automaton.states.length * 92)
  return <div className="regex-automaton-scroll"><svg className="regex-automaton" viewBox={`0 0 ${width} 160`} role="img" aria-label={`${automaton.type} with ${automaton.states.length} states`}><defs><marker id="regex-arrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0,0 L7,3.5 L0,7 z" fill="currentColor"/></marker></defs>{automaton.transitions.map((edge, i) => { const from = automaton.states.findIndex((s) => s.id === edge.from); const to = automaton.states.findIndex((s) => s.id === edge.to); const x1 = 48 + from * 92; const x2 = 48 + to * 92; const self = from === to; const cy = self ? 42 : i % 2 ? 115 : 53; return <g key={i} className="regex-edge"><path d={self ? `M${x1 - 13},66 C${x1 - 40},${cy} ${x1 + 40},${cy} ${x1 + 13},66` : `M${x1 + 22},80 Q${(x1 + x2) / 2},${cy} ${x2 - 22},80`} markerEnd="url(#regex-arrow)"/><text x={self ? x1 : (x1 + x2) / 2} y={cy - 3}>{edge.symbols.slice(0, 3).join(', ')}{edge.symbols.length > 3 ? '…' : ''}</text></g> })}{automaton.states.map((state, i) => { const x = 48 + i * 92; return <g key={state.id} className={`regex-state ${state.isAccepting ? 'accept' : ''} ${state.isStart ? 'start' : ''} ${activeStates.includes(state.id) ? 'active' : ''}`}><circle cx={x} cy="80" r="22"/><circle className="regex-inner" cx={x} cy="80" r="17" visibility={state.isAccepting ? 'visible' : 'hidden'}/>{state.isStart && <path d={`M${x - 42},80 L${x - 24},80`} markerEnd="url(#regex-arrow)"/>}<text x={x} y="83">{state.label}</text></g>})}</svg></div>
}
