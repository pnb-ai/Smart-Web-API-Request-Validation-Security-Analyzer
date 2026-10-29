import { useMemo, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { ArrowLeft, ArrowRight, Check, GitCompareArrows, LoaderCircle, RotateCcw, Send, Sparkles, ZoomIn, ZoomOut } from 'lucide-react'
import { useAutomataStore } from '../store/automataStore'
import { useAppStore } from '../store/appStore'
import { useToast } from './ToastProvider'
import type { Automaton, AutomatonState, TraceStep } from '../types/automata'
import { LoadingSkeleton } from './LoadingSkeleton'

const API = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'
type Operation = 'epsilon-elimination' | 'subset-construction' | 'minimize-table' | 'minimize-hopcroft' | 'pipeline'
type Stage = { operation: string; title: string; before: Automaton; after: Automaton; trace: TraceStep[] }
type TransformResponse = { result: Automaton; trace: TraceStep[]; intermediateAutomata: { operation: string; automaton: Automaton; trace: TraceStep[] }[] }
type RecordRow = Record<string, unknown>

const stageTitle: Record<string, string> = {
  'epsilon-elimination': 'ε-NFA → NFA',
  'subset-construction': 'NFA → DFA',
  'minimize-table': 'Minimal DFA · Table filling',
  'minimize-hopcroft': 'Minimal DFA · Hopcroft',
}
const sampleTokens: Record<string, string[]> = { DIGIT: ['0', '3', '7'], ALPHA: ['a', 'B', 'z'], HEXDIG: ['0', 'A', 'f'], TCHAR: ['a', '-', '_'], SP: [' '], CRLF: ['\r\n'], VCHAR: ['!', 'a', '0'] }

export function TransformWorkspace() {
  const source = useAutomataStore((state) => state.automaton)
  const setAutomaton = useAutomataStore((state) => state.setAutomaton)
  const setPage = useAppStore((state) => state.setPage)
  const { notify } = useToast()
  const [minimizer, setMinimizer] = useState<'table' | 'hopcroft'>('table')
  const [stages, setStages] = useState<Stage[]>([])
  const [stageIndex, setStageIndex] = useState(0)
  const [traceIndex, setTraceIndex] = useState(0)
  const [busy, setBusy] = useState(false)
  const [comparisonBusy, setComparisonBusy] = useState(false)
  const [error, setError] = useState('')
  const [comparison, setComparison] = useState<{ tested: number; mismatches: string[] } | null>(null)
  const currentStage = stages[stageIndex]
  const currentStep = currentStage?.trace[traceIndex]
  const traceData = currentStep?.data || {}
  const tableRows = useMemo(() => getTraceRows(traceData), [traceData])

  const runPipeline = async () => {
    if (!source.states.length) { setError('Create or load an automaton in the Builder first.'); return }
    setBusy(true); setError(''); setStages([]); setComparison(null)
    try {
      const response = await fetch(`${API}/api/transform`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ automaton: source, operation: 'pipeline' satisfies Operation, minimizer }) })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'The transformation could not be completed.')
      const result = payload as TransformResponse
      let before = source
      const nextStages = result.intermediateAutomata.map((item) => {
        const stage = { operation: item.operation, title: stageTitle[item.operation] || item.operation, before, after: item.automaton, trace: item.trace }
        before = item.automaton
        return stage
      })
      setStages(nextStages); setStageIndex(0); setTraceIndex(0)
      if (!nextStages.length) setError('There were no applicable transformation steps for this automaton.')
    } catch (err) {
      setError(err instanceof TypeError ? 'Can’t reach the transform API. Make sure the backend is running on port 8000.' : err instanceof Error ? err.message : 'The transformation could not be completed.')
    } finally { setBusy(false) }
  }

  const sendToSimulator = () => {
    if (!stages.length) return
    setAutomaton(stages[stages.length - 1].after)
    setPage('simulator')
    notify('Minimal automaton sent to Simulator')
  }

  const compareLanguages = async () => {
    if (!stages.length) return
    setComparisonBusy(true); setComparison(null); setError('')
    try {
      const candidate = stages[stages.length - 1].after
      const tokens = [...new Set(source.alphabet.flatMap((symbol) => sampleTokens[symbol] || [symbol]))].filter((symbol) => symbol !== 'ε')
      const alphabet = tokens.length ? tokens : ['a', 'b']
      const strings = Array.from({ length: 50 }, () => {
        const size = Math.floor(Math.random() * 7)
        return Array.from({ length: size }, () => alphabet[Math.floor(Math.random() * alphabet.length)]).join('')
      })
      const mismatches: string[] = []
      for (let offset = 0; offset < strings.length; offset += 5) {
        const group = strings.slice(offset, offset + 5)
        const results = await Promise.all(group.map(async (input) => {
          const [left, right] = await Promise.all([simulate(source, input), simulate(candidate, input)])
          return { input, left, right }
        }))
        mismatches.push(...results.filter((item) => item.left !== item.right).map((item) => item.input || 'ε'))
      }
      setComparison({ tested: strings.length, mismatches })
    } catch (err) {
      setError(err instanceof TypeError ? 'Can’t reach the simulation API. Check that the backend is running.' : err instanceof Error ? err.message : 'The comparison could not be completed.')
    } finally { setComparisonBusy(false) }
  }

  return <motion.section className="transform-workspace" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
    <div className="transform-toolbar"><div><span className="inspector-kicker">CONVERSION PIPELINE</span><h2>Transform & Optimize</h2><p>Convert your machine without changing the language it accepts.</p></div><div className="transform-actions"><label className="transform-minimizer"><span>Minimization</span><select className="text-input" value={minimizer} onChange={(event) => setMinimizer(event.target.value as 'table' | 'hopcroft')}><option value="table">Table filling</option><option value="hopcroft">Hopcroft refinement</option></select></label><button className="button button-primary" onClick={() => void runPipeline()} disabled={busy}>{busy ? <LoaderCircle className="spin" size={15}/> : <Sparkles size={15}/>} {busy ? 'Transforming…' : 'Run full pipeline'}</button></div></div>
    {error && <div className="transform-error" role="alert">{error}</div>}
    {busy && <LoadingSkeleton label="Transforming automaton"/>}
    {!source.states.length && !stages.length ? <div className="transform-empty"><div className="transform-empty-icon"><Sparkles size={22}/></div><h3>Ready when your automaton is</h3><p>Build or load an ε-NFA, NFA, or DFA, then run the conversion pipeline here.</p><button className="button button-secondary" onClick={() => setPage('builder')}>Open Automata Builder <ArrowRight size={14}/></button></div> : <>
      <div className="pipeline-card"><div className="pipeline-steps">{['ε-NFA', 'NFA', 'DFA', 'Minimal DFA'].map((label, index) => { const stepState = pipelinePosition(source.type, stages, index); const operation = operationForPipelineStep(index, source.type); const isSelected = Boolean(currentStage && operation && (operation === 'minimize' ? currentStage.operation.startsWith('minimize-') : currentStage.operation === operation)); return <button key={label} className={`pipeline-step ${stepState > 0 ? 'complete' : ''} ${isSelected ? 'selected' : ''}`} onClick={() => { const matching = stages.findIndex((stage) => operation === 'minimize' ? stage.operation.startsWith('minimize-') : stage.operation === operation); if (matching >= 0) { setStageIndex(matching); setTraceIndex(0) } }} disabled={stepState < 0}><span className="pipeline-marker">{stepState > 0 ? <Check size={12}/> : `0${index + 1}`}</span><span>{label}</span></button> })}</div><div className="pipeline-progress"><span style={{ width: stages.length ? '100%' : '0%' }}/></div>{stages.length > 0 && <div className="pipeline-caption"><span>Pipeline complete</span><span>{stages.length} transformation {stages.length === 1 ? 'step' : 'steps'} · {minimizer === 'table' ? 'table filling' : 'Hopcroft'}</span></div>}</div>
      {currentStage ? <>
        <div className="transform-diagrams"><AutomatonDiagram automaton={currentStage.before} heading="Before" caption={`${currentStage.before.type} · ${currentStage.before.states.length} states`}/><div className="diagram-arrow"><ArrowRight size={21}/><strong>{currentStage.before.states.length} → {currentStage.after.states.length}</strong></div><AutomatonDiagram automaton={currentStage.after} heading="After" caption={`${currentStage.after.type} · ${currentStage.after.states.length} states`}/></div>
        <section className="trace-panel"><div className="trace-heading"><div><span className="inspector-kicker">{currentStage.title}</span><h3>{currentStep?.title || 'Transformation trace'}</h3></div><div className="trace-controls"><button className="icon-button" aria-label="Previous trace step" title="Previous step" disabled={traceIndex <= 0} onClick={() => setTraceIndex((index) => Math.max(index - 1, 0))}><ArrowLeft size={15}/></button><span>{currentStage.trace.length ? traceIndex + 1 : 0} / {currentStage.trace.length}</span><button className="icon-button" aria-label="Next trace step" title="Next step" disabled={traceIndex >= currentStage.trace.length - 1} onClick={() => setTraceIndex((index) => Math.min(index + 1, currentStage.trace.length - 1))}><ArrowRight size={15}/></button></div></div><p className="trace-explanation">{currentStep?.explanation || 'Choose a pipeline stage to inspect its trace.'}</p>
          <div className="trace-data">{tableRows.length ? <TraceDataTable rows={tableRows} highlighted={traceData.sourceState as string | undefined} /> : <pre>{JSON.stringify(traceData, null, 2)}</pre>}</div>
          <div className="trace-footer"><button className="button button-secondary" disabled={stageIndex <= 0} onClick={() => { setStageIndex((index) => Math.max(index - 1, 0)); setTraceIndex(0) }}><ArrowLeft size={14}/> Previous transformation</button><span>Step-by-step algorithm trace</span><button className="button button-secondary" disabled={stageIndex >= stages.length - 1} onClick={() => { setStageIndex((index) => Math.min(index + 1, stages.length - 1)); setTraceIndex(0) }}>Next transformation <ArrowRight size={14}/></button></div>
        </section>
        <div className="transform-bottom-actions"><button className="button button-primary" onClick={sendToSimulator}><Send size={14}/> Send result to Simulator</button><button className="button button-secondary" onClick={() => void compareLanguages()} disabled={comparisonBusy}>{comparisonBusy ? <LoaderCircle className="spin" size={14}/> : <GitCompareArrows size={14}/>} {comparisonBusy ? 'Comparing…' : 'Compare language preserved'}</button>{comparison && <div className={`comparison-result ${comparison.mismatches.length ? 'mismatch' : ''}`}><strong>{comparison.mismatches.length ? 'Mismatch found' : 'Languages match'}</strong><span>{comparison.mismatches.length ? `${comparison.mismatches.length} of ` : ''}{comparison.tested} random strings checked{comparison.mismatches.length ? ` · examples: ${comparison.mismatches.slice(0, 3).join(', ')}` : ''}</span></div>}</div>
      </> : <div className="pipeline-placeholder"><p>Run the pipeline to see each intermediate automaton and trace.</p></div>}
    </>}
  </motion.section>
}

async function simulate(automaton: Automaton, input: string): Promise<boolean> {
  const response = await fetch(`${API}/api/automata/simulate`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ automaton, input }) })
  if (!response.ok) throw new Error('A simulation request failed during comparison.')
  const payload = await response.json() as { accepted: boolean }
  return payload.accepted
}

function operationForPipelineStep(index: number, type: Automaton['type']): string | null {
  if (type === 'EPSILON_NFA') return index <= 1 ? 'epsilon-elimination' : index === 2 ? 'subset-construction' : 'minimize'
  if (type === 'NFA') return index <= 2 ? 'subset-construction' : 'minimize'
  return index >= 2 ? 'minimize' : null
}
function pipelinePosition(type: Automaton['type'], stages: Stage[], index: number): number {
  if (!stages.length) return index === (type === 'EPSILON_NFA' ? 0 : type === 'NFA' ? 1 : 2) ? 0 : -1
  const first = type === 'EPSILON_NFA' ? 0 : type === 'NFA' ? 1 : 2
  return index < first ? -1 : 1
}

function getTraceRows(data: Record<string, unknown>): RecordRow[] {
  for (const key of ['transitions', 'subsetTable', 'newlyMarked', 'markedPairs', 'equivalenceClasses', 'partitions', 'splits', 'initiallyMarked', 'missingTransitions']) {
    const value = data[key]
    if (Array.isArray(value)) {
      if (value.every((item) => Array.isArray(item))) return value.map((states, index) => ({ class: `P${index + 1}`, states }))
      return value.map((item, index) => item && typeof item === 'object' ? item as RecordRow : { index: index + 1, value: item })
    }
  }
  if (data.source && data.symbol) return [{ source: data.source, symbol: data.symbol, sourceClosure: data.sourceClosure, movedStates: data.movedStates, destinationClosure: data.destinationClosure }]
  return []
}

function TraceDataTable({ rows, highlighted }: { rows: RecordRow[]; highlighted?: string }) {
  const columns = [...new Set(rows.flatMap((row) => Object.keys(row)))].slice(0, 5)
  return <div className="transform-table-scroll"><table className="transform-table"><thead><tr>{columns.map((column) => <th key={column}>{column.replace(/[A-Z]/g, (char) => ` ${char}`).toUpperCase()}</th>)}</tr></thead><tbody>{rows.map((row, index) => { const isHighlighted = highlighted ? Object.values(row).some((value) => value === highlighted) : index === 0; return <tr key={index} className={isHighlighted ? 'current-computation' : ''}>{columns.map((column) => <td key={column}>{formatCell(row[column])}</td>)}</tr> })}</tbody></table></div>
}
function formatCell(value: unknown): string { return Array.isArray(value) ? value.map((item) => Array.isArray(item) ? `{${item.join(', ')}}` : String(item)).join(' · ') : typeof value === 'object' && value !== null ? JSON.stringify(value) : String(value ?? '—') }

function diagramLayout(automaton: Automaton) {
  const states = automaton.states
  const outgoing = new Map(states.map((state) => [state.id, automaton.transitions.filter((edge) => edge.from === state.id).map((edge) => edge.to)]))
  const ranks = new Map<string, number>()
  const start = states.find((state) => state.isStart) || states[0]
  if (start) {
    ranks.set(start.id, 0)
    const queue = [start.id]
    for (let cursor = 0; cursor < queue.length; cursor += 1) {
      const from = queue[cursor]
      for (const to of outgoing.get(from) || []) if (!ranks.has(to)) { ranks.set(to, (ranks.get(from) || 0) + 1); queue.push(to) }
    }
  }
  const lastRank = Math.max(0, ...ranks.values())
  states.forEach((state) => { if (!ranks.has(state.id)) ranks.set(state.id, lastRank + 1) })
  const layers = new Map<number, AutomatonState[]>()
  states.forEach((state) => { const layer = ranks.get(state.id) || 0; layers.set(layer, [...(layers.get(layer) || []), state]) })
  const largestLayer = Math.max(1, ...[...layers.values()].map((layer) => layer.length))
  const width = Math.max(460, 160 + Math.max(0, layers.size - 1) * 145)
  const height = Math.max(250, 130 + (largestLayer - 1) * 105)
  const positions = new Map<string, { x: number; y: number }>()
  for (const [rank, layer] of layers) {
    const firstY = (height - (layer.length - 1) * 105) / 2
    layer.forEach((state, index) => positions.set(state.id, { x: 80 + rank * 145, y: firstY + index * 105 }))
  }
  return { positions, width, height }
}

function AutomatonDiagram({ automaton, heading, caption }: { automaton: Automaton; heading: string; caption: string }) {
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const dragPoint = useRef<{ x: number; y: number } | null>(null)
  const states = automaton.states
  const { positions: locations, width: worldWidth, height: worldHeight } = diagramLayout(automaton)
  const parallel = new Map<string, number>()
  const directedCounts = new Map<string, number>()
  automaton.transitions.forEach((edge) => { const key = String(edge.from) + String.fromCharCode(58) + String(edge.to); directedCounts.set(key, (directedCounts.get(key) || 0) + 1) })
  const viewWidth = worldWidth / zoom
  const viewHeight = worldHeight / zoom
  const maxPanX = (worldWidth - viewWidth) / 2
  const maxPanY = (worldHeight - viewHeight) / 2
  const viewX = Math.max(0, Math.min(worldWidth - viewWidth, (worldWidth - viewWidth) / 2 - pan.x))
  const viewY = Math.max(0, Math.min(worldHeight - viewHeight, (worldHeight - viewHeight) / 2 - pan.y))
  const viewBox = viewX + ' ' + viewY + ' ' + viewWidth + ' ' + viewHeight
  const panBy = (dx: number, dy: number) => setPan((current) => ({ x: Math.max(-maxPanX, Math.min(maxPanX, current.x + dx)), y: Math.max(-maxPanY, Math.min(maxPanY, current.y + dy)) }))
  const resetView = () => { setZoom(1); setPan({ x: 0, y: 0 }) }
  return <div className="diagram-card"><div className="diagram-heading"><div><strong>{heading}</strong><small>{caption} · drag to pan</small></div><div className="diagram-controls"><span>{automaton.transitions.length} edges</span><button className="icon-button" title={`Zoom in ${heading} diagram`} aria-label={`Zoom in ${heading} diagram`} onClick={() => setZoom((value) => Math.min(3, value + .5))} disabled={zoom >= 3}><ZoomIn size={14}/></button><button className="icon-button" title={`Zoom out ${heading} diagram`} aria-label={`Zoom out ${heading} diagram`} onClick={() => setZoom((value) => Math.max(1, value - .5))} disabled={zoom <= 1}><ZoomOut size={14}/></button><button className="icon-button" title={`Reset ${heading} diagram view`} aria-label={`Reset ${heading} diagram view`} onClick={resetView} disabled={zoom === 1 && pan.x === 0 && pan.y === 0}><RotateCcw size={13}/></button><span className="zoom-level" title="Current diagram zoom">{Math.round(zoom * 100)}%</span></div></div><svg className="automaton-diagram" viewBox={viewBox} role="img" aria-label={heading + ' automaton diagram. Drag to pan, or focus and use arrow keys to pan.'} tabIndex={0} onPointerDown={(event) => { if (event.button === 0) { dragPoint.current = { x: event.clientX, y: event.clientY }; event.currentTarget.setPointerCapture(event.pointerId) } }} onPointerMove={(event) => { if (!dragPoint.current) return; const rect = event.currentTarget.getBoundingClientRect(); const dx = event.clientX - dragPoint.current.x; const dy = event.clientY - dragPoint.current.y; dragPoint.current = { x: event.clientX, y: event.clientY }; panBy(dx * viewWidth / rect.width, dy * viewHeight / rect.height) }} onPointerUp={(event) => { dragPoint.current = null; if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId) }} onPointerCancel={() => { dragPoint.current = null }} onKeyDown={(event) => { const amount = 35 / zoom; if (event.key === 'ArrowLeft') { event.preventDefault(); panBy(-amount, 0) } else if (event.key === 'ArrowRight') { event.preventDefault(); panBy(amount, 0) } else if (event.key === 'ArrowUp') { event.preventDefault(); panBy(0, -amount) } else if (event.key === 'ArrowDown') { event.preventDefault(); panBy(0, amount) } }}><defs><marker id={`arrow-${heading.replaceAll(' ', '-')}`} markerWidth="10" markerHeight="10" markerUnits="userSpaceOnUse" refX="9" refY="5" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="var(--soft)"/></marker></defs>
    {automaton.transitions.map((edge, index) => { const from = locations.get(edge.from); const to = locations.get(edge.to); if (!from || !to) return null; const key = String(edge.from) + String.fromCharCode(58) + String(edge.to); const offset = parallel.get(key) || 0; parallel.set(key, offset + 1); const loop = edge.from === edge.to; let d: string; let labelX: number; let labelY: number; if (loop) { d = 'M ' + (from.x - 18) + ' ' + (from.y - 25) + ' C ' + (from.x - 60) + ' ' + (from.y - 85 - offset * 18) + ', ' + (from.x + 60) + ' ' + (from.y - 85 - offset * 18) + ', ' + (from.x + 18) + ' ' + (from.y - 25); labelX = from.x; labelY = from.y - 68 - offset * 15 } else { const dx = to.x - from.x; const dy = to.y - from.y; const length = Math.max(1, Math.hypot(dx, dy)); const normalX = -dy / length; const normalY = dx / length; const reverseKey = String(edge.to) + String.fromCharCode(58) + String(edge.from); const hasReverse = directedCounts.has(reverseKey); const count = directedCounts.get(key) || 1; const curve = hasReverse ? (offset + 1) * 22 : (offset - (count - 1) / 2) * 28; const cx = (from.x + to.x) / 2 + normalX * curve; const cy = (from.y + to.y) / 2 + normalY * curve; const startLength = Math.max(1, Math.hypot(cx - from.x, cy - from.y)); const endLength = Math.max(1, Math.hypot(to.x - cx, to.y - cy)); const sx = from.x + (cx - from.x) / startLength * 28; const sy = from.y + (cy - from.y) / startLength * 28; const ex = to.x - (to.x - cx) / endLength * 28; const ey = to.y - (to.y - cy) / endLength * 28; d = 'M ' + sx + ' ' + sy + ' Q ' + cx + ' ' + cy + ' ' + ex + ' ' + ey; labelX = (sx + 2 * cx + ex) / 4; labelY = (sy + 2 * cy + ey) / 4 - 7 } return <g key={`edge-${index}`} className="diagram-edge"><path d={d} markerEnd={`url(#arrow-${heading.replaceAll(' ', '-')})`}/><text x={labelX} y={labelY} textAnchor="middle">{edge.symbols.join(', ')}</text></g> })}
    {states.map((state) => { const { x, y } = locations.get(state.id)!; return <g key={state.id} className={`diagram-state ${state.isStart ? 'start' : ''}`}><circle cx={x} cy={y} r="25"/><circle className="accept-ring" cx={x} cy={y} r="20" visibility={state.isAccepting ? 'visible' : 'hidden'}/>{state.isStart && <path className="start-arrow" d={`M ${x - 53} ${y} L ${x - 28} ${y}`} markerEnd={`url(#arrow-${heading.replaceAll(' ', '-')})`}/>}<text className="state-label" x={x} y={state.label === state.id ? y + 4 : y - 3}>{state.label === state.id ? state.id : state.label}</text>{state.label !== state.id && <text className="state-id" x={x} y={y + 12}>{state.id}</text>}</g> })}</svg>
    {!states.length && <div className="diagram-empty">No states</div>}
  </div>
}
