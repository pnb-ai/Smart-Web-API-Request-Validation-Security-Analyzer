import { useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { AlertTriangle, Check, LoaderCircle, Network, Sparkles } from 'lucide-react'
import { useAutomataStore } from '../store/automataStore'
import type { Automaton, TraceStep } from '../types/automata'

const API = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'
type SourceKind = 'workspace' | 'regex' | 'http-rule'
type CheckResponse = {
  equivalent: boolean
  counterexample: string[] | null
  counterexampleString: string | null
  acceptedBy: 'left' | 'right' | null
  path: string[][]
  leftEmpty: boolean
  rightEmpty: boolean
  leftSubsetRight: boolean
  productStatesExplored: number
  method: string
  trace: TraceStep[]
}
type RunResult = { accepted: boolean; trace: TraceStep[]; reason: string }
type PanelValue = { kind: SourceKind; pattern: string }

const methodPattern = '(GET|POST|PUT|PATCH|DELETE)'

export function EquivalenceWorkspace() {
  const workspaceAutomaton = useAutomataStore((state) => state.automaton)
  const [left, setLeft] = useState<PanelValue>({ kind: 'http-rule', pattern: methodPattern })
  const [right, setRight] = useState<PanelValue>({ kind: 'regex', pattern: methodPattern })
  const [method, setMethod] = useState<'product-bfs' | 'hopcroft-karp'>('product-bfs')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [comparison, setComparison] = useState<CheckResponse | null>(null)
  const [runs, setRuns] = useState<[RunResult, RunResult] | null>(null)
  const [round, setRound] = useState(0)

  const exploredPairs = useMemo<TraceStep[]>(() => {
    if (!comparison) return []
    if (comparison.method === 'hopcroft-karp') return comparison.trace.filter((step) => step.title.startsWith('Hopcroft-Karp round')).map((step) => ({ ...step, title: `Explore pair ${JSON.stringify(step.data.pair)}`, data: { ...step.data, transitions: (step.data.consequences as { symbol: string; pair: string[] }[] || []).map((item) => ({ symbol: item.symbol, to: item.pair })) } }))
    return comparison.trace.filter((step) => step.title.startsWith('Explore pair') && step.data.purpose === 'equivalence')
  }, [comparison])
  const visiblePairs = exploredPairs.slice(0, Math.max(1, round + 1))

  const runCheck = async () => {
    setBusy(true); setError(''); setComparison(null); setRuns(null)
    try {
      const [first, second] = await Promise.all([resolvePanel(left, workspaceAutomaton), resolvePanel(right, workspaceAutomaton)])
      const response = await fetch(`${API}/api/equivalence`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ left: first, right: second, method }) })
      const payload = await response.json()
      if (!response.ok) throw new Error(friendlyDetail(payload.detail, 'The equivalence check could not be completed.'))
      const result = payload as CheckResponse
      setComparison(result)
      setRound(0)
      if (result.counterexampleString !== null) {
        const input = result.counterexampleString
        const [firstRun, secondRun] = await Promise.all([simulate(first, input), simulate(second, input)])
        setRuns([firstRun, secondRun])
      }
    } catch (cause) {
      setError(cause instanceof TypeError ? 'The analysis service is unavailable. Start the backend on port 8000 and try again.' : cause instanceof Error ? cause.message : 'The equivalence check could not be completed.')
    } finally { setBusy(false) }
  }

  return <motion.section className="equivalence-workspace" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
    <div className="equivalence-toolbar"><div><span className="inspector-kicker">LANGUAGE COMPARISON</span><h2>Do these rules accept the same language?</h2><p>Compare the Builder automaton, a regular expression, or a built-in HTTP request rule.</p></div><label className="equivalence-method"><span>Algorithm</span><select className="text-input" value={method} onChange={(event) => setMethod(event.target.value as typeof method)}><option value="product-bfs">Product BFS · shortest witness</option><option value="hopcroft-karp">Hopcroft–Karp · union-find</option></select></label></div>

    <div className="equivalence-panels"><RulePanel title="Rule v1" value={left} onChange={setLeft} hasWorkspace={workspaceAutomaton.states.length > 0} /><div className="equivalence-versus">VS</div><RulePanel title="Rule v2" value={right} onChange={setRight} hasWorkspace={workspaceAutomaton.states.length > 0} /></div>
    {error && <div className="equivalence-error" role="alert"><AlertTriangle size={15}/>{error}</div>}
    <button className="button button-primary equivalence-check" onClick={() => void runCheck()} disabled={busy}>{busy ? <LoaderCircle size={17} className="spin"/> : <Sparkles size={17}/>} {busy ? 'Exploring product…' : 'Check equivalence'}</button>

    {comparison && <div className="equivalence-results">
      <section className={`equivalence-result-card ${comparison.equivalent ? 'same' : 'different'}`}>
        <div className="equivalence-result-icon">{comparison.equivalent ? <Check size={22}/> : <Network size={22}/>}</div><div className="equivalence-result-copy"><strong>{comparison.equivalent ? 'EQUIVALENT ✓' : 'DIFFERENT ✗'}</strong><span>{comparison.equivalent ? 'No reachable product state distinguishes these rules.' : 'A shortest counterexample separates these languages.'}</span></div>
        {!comparison.equivalent && <div className="counterexample"><small>SHORTEST COUNTEREXAMPLE · ACCEPTED BY {comparison.acceptedBy?.toUpperCase()}</small><code>{requestLike(comparison.counterexampleString ?? '')}</code></div>}
        <div className="equivalence-facts"><span>{comparison.productStatesExplored} product pairs explored</span><span>L1 {comparison.leftSubsetRight ? '⊆' : '⊄'} L2</span><span>Empty: {comparison.leftEmpty ? 'v1' : ''}{comparison.leftEmpty && comparison.rightEmpty ? ', ' : ''}{comparison.rightEmpty ? 'v2' : ''}{!comparison.leftEmpty && !comparison.rightEmpty ? 'neither' : ''}</span></div>
      </section>

      {!comparison.equivalent && runs && <section className="witness-card"><div className="section-card-heading"><div><span className="inspector-kicker">WITNESS PLAYBACK</span><h3>Run the same request through both rules</h3></div><span className="witness-token-count">{comparison.counterexample?.length || 0} tokens</span></div><div className="witness-runs">{runs.map((run, index) => <div className="witness-run" key={index}><div className="witness-run-heading"><strong>Rule v{index + 1}</strong><span className={run.accepted ? 'accepted' : 'rejected'}>{run.accepted ? 'ACCEPTED' : 'REJECTED'}</span></div><small>{run.reason}</small><div className="witness-tape">{(comparison.counterexample || []).map((symbol, position) => <span key={position}>{symbol === '\r\n' ? 'CRLF' : symbol}</span>)}{!comparison.counterexample?.length && <span className="empty-token">ε (empty input)</span>}</div><ol className="witness-trace">{run.trace.filter((step) => step.data.symbolRead !== undefined).map((step, position) => <li key={position}><span>{String(step.data.symbolRead)}</span><small>{Array.isArray(step.data.currentStates) ? step.data.currentStates.join(', ') : '—'} → {Array.isArray(step.data.nextStates) ? step.data.nextStates.join(', ') : '∅'}</small></li>)}</ol></div>)}</div></section>}

      <section className="product-explorer"><div className="section-card-heading"><div><span className="inspector-kicker">PRODUCT CONSTRUCTION</span><h3>Reachable state-pair exploration</h3></div><span className="witness-token-count">{visiblePairs.length} / {exploredPairs.length} BFS rounds</span></div><ProductGraph pairs={visiblePairs} current={visiblePairs.at(-1)?.data.pair as string[] | undefined} /><div className="product-scrubber"><span>Start</span><input aria-label="Product exploration round" type="range" min="0" max={Math.max(0, exploredPairs.length - 1)} value={Math.min(round, Math.max(0, exploredPairs.length - 1))} onChange={(event) => setRound(Number(event.target.value))} /><span>{exploredPairs.length} pairs</span></div>{visiblePairs.at(-1) && <p className="product-explanation">{visiblePairs.at(-1)?.explanation}</p>}</section>
    </div>}
  </motion.section>
}

function RulePanel({ title, value, onChange, hasWorkspace }: { title: string; value: PanelValue; onChange: (value: PanelValue) => void; hasWorkspace: boolean }) {
  return <section className="rule-panel"><div className="rule-panel-heading"><span className="rule-panel-index">{title === 'Rule v1' ? '01' : '02'}</span><div><strong>{title}</strong><small>Choose an automaton source</small></div></div><label className="field-wrap"><span className="field-label">Source</span><select className="text-input" value={value.kind} onChange={(event) => onChange({ ...value, kind: event.target.value as SourceKind })}><option value="workspace">Current Builder automaton</option><option value="regex">Regular expression</option><option value="http-rule">Built-in HTTP method rule</option></select></label>{value.kind !== 'workspace' && <label className="field-wrap"><span className="field-label">{value.kind === 'regex' ? 'Full-string regex' : 'HTTP request rule'}</span>{value.kind === 'regex' ? <input className="text-input regex-input" aria-label={`${title} regular expression`} value={value.pattern} onChange={(event) => onChange({ ...value, pattern: event.target.value })} placeholder="(GET|POST) /items/\\d+" /> : <select className="text-input" aria-label={`${title} HTTP rule`} value="method" onChange={() => undefined}><option value="method">HTTP method token (GET, POST, PUT…)</option></select>}<small className="field-hint">{value.kind === 'regex' ? 'Supports grouping, |, concatenation, *, +, ?, character ranges, . and \d / \s / \w.' : 'Matches common method tokens exactly.'}</small></label>}{value.kind === 'workspace' && <div className={`source-state ${hasWorkspace ? 'ready' : ''}`}><span className="source-dot"/><span>{hasWorkspace ? 'Uses the automaton currently in Builder' : 'Builder is empty — create or import a machine first'}</span></div>}</section>
}

function ProductGraph({ pairs, current }: { pairs: TraceStep[]; current?: string[] }) {
  const nodes = pairs.map((step) => step.data.pair as string[]).filter(Boolean)
  const width = Math.max(560, nodes.length * 140)
  const x = (index: number) => 55 + index * 135
  return <div className="product-graph-scroll"><svg className="product-graph" viewBox={`0 0 ${width} 176`} role="img" aria-label="Animated reachable product state graph"><defs><marker id="product-arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L0,6 L7,3 z" fill="currentColor"/></marker></defs>{pairs.map((step, index) => <g key={`edge-${index}`} className="product-graph-edges">{(step.data.transitions as { symbol: string; to: string[] }[] || []).slice(0, 4).map((edge, edgeIndex) => { const found = nodes.findIndex((item) => item[0] === edge.to[0] && item[1] === edge.to[1]); if (found < 0) return null; const sourceX = x(index); const targetX = x(found); const path = found === index ? `M ${sourceX - 21} 59 C ${sourceX - 60} 9 ${sourceX + 60} 9 ${sourceX + 21} 59` : `M ${sourceX + 34} 85 Q ${(sourceX + targetX) / 2} ${found < index || edgeIndex % 2 ? 125 : 45} ${targetX - 34} 85`; return <g key={edgeIndex}><path d={path} markerEnd="url(#product-arrow)"/><text x={found === index ? sourceX : (sourceX + targetX) / 2} y={found === index ? 14 : edgeIndex % 2 ? 132 : 39}>{edge.symbol === ' ' ? 'SP' : edge.symbol}</text></g> })}</g>)}{nodes.map((pair, index) => <motion.g key={`${pair[0]}-${pair[1]}`} initial={{ opacity: 0, scale: .7 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: .25, delay: index * .045 }} className={`product-node ${current?.[0] === pair[0] && current?.[1] === pair[1] ? 'current' : ''}`}><circle cx={x(index)} cy="85" r="34"/><text className="product-pair" x={x(index)} y="82">{pair[0]}</text><text className="product-pair" x={x(index)} y="96">{pair[1]}</text><text className="product-index" x={x(index)} y="137">PAIR {String(index + 1).padStart(2, '0')}</text></motion.g>)}</svg>{!nodes.length && <p>Product trace will appear after you run a comparison.</p>}</div>
}

async function resolvePanel(panel: PanelValue, workspace: Automaton): Promise<Automaton> {
  if (panel.kind === 'workspace') {
    if (!workspace.states.length) throw new Error('Choose a regex or HTTP rule, or create an automaton in Builder first.')
    return workspace
  }
  const pattern = panel.kind === 'http-rule' ? methodPattern : panel.pattern
  const response = await fetch(`${API}/api/regex/compile`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ pattern }) })
  const payload = await response.json()
  if (!response.ok) throw new Error(friendlyDetail(payload.detail, 'That regular expression could not be compiled.'))
  return payload.automaton as Automaton
}

async function simulate(automaton: Automaton, input: string): Promise<RunResult> {
  const response = await fetch(`${API}/api/automata/simulate`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ automaton, input }) })
  const payload = await response.json()
  if (!response.ok) throw new Error('A witness replay could not be completed.')
  return { accepted: Boolean(payload.accepted), trace: payload.trace as TraceStep[], reason: payload.reason as string }
}

function friendlyDetail(detail: unknown, fallback: string): string { return typeof detail === 'string' ? detail : Array.isArray(detail) ? 'One of the automata has invalid fields. Check the Builder model and try again.' : fallback }
function requestLike(value: string): string { return value ? `request-line: ${JSON.stringify(value)}` : 'request-line: ε (empty input)' }
