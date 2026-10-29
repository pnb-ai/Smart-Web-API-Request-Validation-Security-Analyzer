import { useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { AlertCircle, CheckCircle2, Circle, ExternalLink, FileCheck2, LoaderCircle, ShieldAlert, Upload, X } from 'lucide-react'
import { useAppStore } from '../store/appStore'
import { useAutomataStore } from '../store/automataStore'
import type { Automaton } from '../types/automata'
import { LoadingSkeleton } from './LoadingSkeleton'

const API = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'
type Check = { id: string; title: string; status: 'pass' | 'fail' | 'warn'; message: string; rfc: string; contractPath?: string; position: { offset: number; line: number; column: number } | null; automatonId: string | null; input: string | null }
type Segment = { type: string; start: number; end: number }
type Report = { overall: 'VALID' | 'INVALID'; checks: Check[]; parts: { segments: Segment[] }; automata: Record<string, { automaton: Automaton }> }
type CustomRules = { allowedMethods: string[]; pathRegex: string; requiredHeaders: string[]; allowedContentTypes: string[] }

const sampleContract = `openapi: 3.1.0
info:
  title: Example Users API
  version: 1.0.0
servers:
  - url: https://api.example.com
paths:
  /api/users:
    get:
      parameters:
        - name: page
          in: query
          schema: { type: integer, minimum: 1 }
      responses:
        '200': { description: OK }
    post:
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [name]
              properties:
                name: { type: string, minLength: 1 }
      responses:
        '201': { description: Created }`

const sampleRequests = [
  { name: 'Valid GET', text: 'GET /api/users?page=1 HTTP/1.1\r\nHost: api.example.com\r\nAccept: application/json\r\n\r\n' },
  { name: 'Valid POST JSON', text: 'POST /api/users HTTP/1.1\r\nHost: api.example.com\r\nContent-Type: application/json\r\nContent-Length: 14\r\n\r\n{"name":"Ada"}' },
  { name: 'Bad version', text: 'GET / HTTP/2.0\r\nHost: example.com\r\n\r\n' },
  { name: 'Space in path', text: 'GET /api/user list HTTP/1.1\r\nHost: example.com\r\n\r\n' },
  { name: 'Missing Host', text: 'GET / HTTP/1.1\r\nUser-Agent: Demo/1.0\r\n\r\n' },
  { name: 'CL + TE conflict', text: 'POST /upload HTTP/1.1\r\nHost: example.com\r\nContent-Length: 4\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n' },
  { name: 'Bad percent-encoding', text: 'GET /files/%zz HTTP/1.1\r\nHost: example.com\r\n\r\n' },
  { name: 'Space before colon', text: 'GET / HTTP/1.1\r\nHost : example.com\r\n\r\n' },
]

export function HttpValidatorWorkspace() {
  const requestDraft = useAppStore(state => state.requestDraft)
  const setRequestDraft = useAppStore(state => state.setRequestDraft)
  const [raw, setRaw] = useState(requestDraft || sampleRequests[0].text)
  const [report, setReport] = useState<Report | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [maxLine, setMaxLine] = useState('8000')
  const [maxHeaders, setMaxHeaders] = useState('65536')
  const [allowedMethods, setAllowedMethods] = useState('GET, POST')
  const [pathRegex, setPathRegex] = useState('^/api/v1/users/[0-9]+$')
  const [requiredHeaders, setRequiredHeaders] = useState('authorization')
  const [allowedTypes, setAllowedTypes] = useState('application/json')
  const [policyEnabled, setPolicyEnabled] = useState(false)
  const [contractEnabled, setContractEnabled] = useState(false)
  const [openApiText, setOpenApiText] = useState('')
  const [contractFileName, setContractFileName] = useState('')
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const setPage = useAppStore(state => state.setPage)
  const setAutomaton = useAutomataStore(state => state.setAutomaton)
  const setSimulationInput = useAutomataStore(state => state.setSimulationInput)
  const setSimulationAutoRun = useAutomataStore(state => state.setSimulationAutoRun)

  const validate = async () => {
    setBusy(true); setError('')
    const customRules: CustomRules = {
      allowedMethods: splitList(allowedMethods), pathRegex,
      requiredHeaders: splitList(requiredHeaders), allowedContentTypes: splitList(allowedTypes),
    }
    try {
      const requestPayload = { rawRequest: raw, maxRequestLine: Number(maxLine), maxHeaderSection: Number(maxHeaders), customRules: policyEnabled ? customRules : {} }
      const response = await fetch(`${API}/api/http/${contractEnabled && openApiText.trim() ? 'validate-contract' : 'validate'}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(contractEnabled && openApiText.trim() ? { ...requestPayload, openApiSpec: openApiText } : requestPayload) })
      const responsePayload = await response.json()
      if (!response.ok) throw new Error(typeof responsePayload.detail === 'string' ? responsePayload.detail : 'Check the request and try again.')
      setReport(responsePayload as Report)
    } catch (cause) {
      setReport(null)
      setError(cause instanceof TypeError ? 'The validator service is unavailable. Start the backend and try again.' : cause instanceof Error ? cause.message : 'Could not validate this request.')
    } finally { setBusy(false) }
  }

  useEffect(() => { const timer = window.setTimeout(() => void validate(), 250); return () => window.clearTimeout(timer) }, [raw, maxLine, maxHeaders, policyEnabled, allowedMethods, pathRegex, requiredHeaders, allowedTypes, contractEnabled, openApiText])
  const jumpTo = (check: Check) => {
    if (check.position && inputRef.current) {
      inputRef.current.focus()
      const utf16Offset = Array.from(raw).slice(0, check.position.offset).join('').length
      inputRef.current.setSelectionRange(utf16Offset, utf16Offset + 1)
      inputRef.current.scrollTop = Math.max(0, (check.position.line - 1) * 20)
    }
  }
  const visualize = (check: Check) => {
    if (!check.automatonId || !report) return
    const artifact = report.automata[check.automatonId]
    if (!artifact) return
    setAutomaton(artifact.automaton)
    setSimulationInput(check.input ?? '')
    setSimulationAutoRun(true)
    setPage('simulator')
  }
  const segments = report?.parts.segments || []

  return <motion.section className="http-validator" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
    <div className="http-validator-heading"><div><span className="inspector-kicker">RFC 9112 · RFC 9110 · RFC 3986</span><h2>Validate a raw HTTP/1.1 request</h2><p>Finite automata check regular syntax. Separate protocol rules check framing, field relationships, and method semantics.</p></div><span className={`http-overall ${report?.overall === 'VALID' ? 'valid' : report ? 'invalid' : ''}`}>{report?.overall || (busy ? 'CHECKING' : 'READY')}</span></div>
    <div className="http-validator-grid">
      <div className="http-validator-main">
        <section className="http-panel"><div className="http-panel-title"><div><span className="inspector-kicker">RAW MESSAGE</span><strong>Request editor</strong></div><label className="http-sample-select"><span>Load sample</span><select className="text-input" aria-label="Load sample" defaultValue="" onChange={event => { const item = sampleRequests[Number(event.target.value)]; if (item) { setRaw(item.text); setRequestDraft(item.text) }; event.target.value = '' }}><option value="" disabled>Choose an example…</option>{sampleRequests.map((sample, index) => <option value={index} key={sample.name}>{sample.name}</option>)}</select></label></div>
          <textarea ref={inputRef} aria-label="Raw HTTP request" className="text-input http-raw-editor" spellCheck={false} value={raw} onChange={event => { setRaw(event.target.value); setRequestDraft(event.target.value) }} onKeyDown={event => { if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') { event.preventDefault(); void validate() } }} />
          <div className="http-edit-footer"><span>Ctrl/⌘ + Enter to validate · offsets are zero-based</span><button className="button button-primary" onClick={() => void validate()} disabled={busy}>{busy ? <LoaderCircle className="spin" size={14}/> : <FileCheck2 size={14}/>} Validate request</button></div>
        </section>
        <section className="http-panel http-contract"><div className="http-panel-title"><div><span className="inspector-kicker">OPENAPI 3.0 / 3.1</span><strong>Validate against an API contract</strong></div><label className="http-toggle"><input type="checkbox" checked={contractEnabled} onChange={event => setContractEnabled(event.target.checked)}/> Enforce contract</label></div>
          <p className="http-contract-intro">Check the request path, method, declared parameters, authentication credentials, Content-Type, and JSON body schema against your OpenAPI definition. Your contract stays in this browser.</p>
          <div className="http-contract-actions"><button className="button" onClick={() => { setOpenApiText(sampleContract); setContractFileName('Example Users API'); setContractEnabled(true) }}>Load example contract</button><label className="button http-file-button"><Upload size={13}/> Import JSON/YAML<input aria-label="Import OpenAPI contract" type="file" accept=".json,.yaml,.yml,application/json,text/yaml" onChange={async event => { const file = event.target.files?.[0]; if (file) { setOpenApiText(await file.text()); setContractFileName(file.name); setContractEnabled(true) }; event.target.value = '' }}/></label>{contractFileName && <span className="http-muted">{contractFileName}</span>}{openApiText && <button className="http-contract-clear" aria-label="Clear OpenAPI contract" title="Clear OpenAPI contract" onClick={() => { setOpenApiText(''); setContractFileName(''); setContractEnabled(false) }}><X size={14}/></button>}</div>
          {contractEnabled && <textarea className="text-input http-contract-editor" aria-label="OpenAPI contract" spellCheck={false} placeholder="Paste an OpenAPI 3.0 or 3.1 JSON/YAML document" value={openApiText} onChange={event => { setOpenApiText(event.target.value); if (contractFileName) setContractFileName('') }} />}
          {contractEnabled && !openApiText.trim() && <small className="http-contract-hint">Paste a contract, import a file, or load the example to enable contract checks.</small>}
          <small className="http-contract-hint">Local $refs supported; external references are blocked. JSON body schemas are validated. Security checks verify credential presence only, not token validity or authorization.</small>
        </section>
        {report && <section className="http-panel"><div className="http-panel-title"><div><span className="inspector-kicker">PARSED MESSAGE</span><strong>Request parts</strong></div><span className="http-muted">Hover a part for its byte range</span></div><div className="http-parts">{segments.map((part, index) => <span key={`${part.type}-${index}`} className={`http-part ${part.type}`} title={`${part.type} · offsets ${part.start}–${part.end}`}>{raw.slice(part.start, part.end) || (part.type === 'body' ? '(empty body)' : '')}</span>)}</div></section>}
        <section className="http-panel http-policy"><div className="http-panel-title"><div><span className="inspector-kicker">OPTIONAL API POLICY</span><strong>Custom API rules</strong></div><label className="http-toggle"><input type="checkbox" checked={policyEnabled} onChange={event => setPolicyEnabled(event.target.checked)}/> Enforce</label></div><div className={`http-policy-fields ${policyEnabled ? '' : 'disabled'}`}>
          <label>Allowed methods<input className="text-input" value={allowedMethods} onChange={event => setAllowedMethods(event.target.value)} placeholder="GET, POST" /></label>
          <label>Path regex<input className="text-input" value={pathRegex} onChange={event => setPathRegex(event.target.value)} placeholder="^/api/v1/users/[0-9]+$" /></label>
          <label>Required headers<input className="text-input" value={requiredHeaders} onChange={event => setRequiredHeaders(event.target.value)} placeholder="authorization, x-api-key" /></label>
          <label>Allowed content types<input className="text-input" value={allowedTypes} onChange={event => setAllowedTypes(event.target.value)} placeholder="application/json" /></label>
          <small>Comma-separated values. Path patterns use the Regex Lab syntax and match the full path.</small>
        </div></section>
        <section className="http-panel http-limits"><div className="http-panel-title"><div><span className="inspector-kicker">LOCAL SAFETY LIMITS</span><strong>Configurable size checks</strong></div></div><label>Request line (octets)<input className="text-input" type="number" min="1" max="65536" value={maxLine} onChange={event => setMaxLine(event.target.value)} /></label><label>Header section (octets)<input className="text-input" type="number" min="1" max="1000000" value={maxHeaders} onChange={event => setMaxHeaders(event.target.value)} /></label></section>
      </div>
      <aside className="http-panel http-checklist"><div className="http-panel-title"><div><span className="inspector-kicker">VALIDATION REPORT</span><strong>Rule checklist</strong></div>{report && <span className="http-count">{report.checks.filter(item => item.status === 'fail').length} errors · {report.checks.filter(item => item.status === 'warn').length} warnings</span>}</div>
        {error && <div className="http-friendly-error" role="alert"><AlertCircle size={15}/>{error}</div>}
        {busy && !report && <LoadingSkeleton label="Validating HTTP request"/>}
        {!busy && !report && !error && <div className="http-empty"><ShieldAlert size={22}/><strong>Waiting for a request</strong><span>Type a request or choose a sample to see its validation checks.</span></div>}
        {report && <div className="http-check-list">{report.checks.map((check, index) => <motion.article key={`${check.id}-${index}`} className={`http-check ${check.status}`} initial={{ opacity: 0, x: 8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: Math.min(index * 0.012, 0.3) }}>
          <div className="http-check-icon">{check.status === 'pass' ? <CheckCircle2 size={16}/> : check.status === 'fail' ? <AlertCircle size={16}/> : <Circle size={16}/>}</div><div className="http-check-body"><strong>{check.title}</strong><p>{check.message}</p><small>{check.rfc}{check.contractPath ? ` · ${check.contractPath}` : ''}{check.position ? ` · line ${check.position.line}, col ${check.position.column}` : ''}</small><div className="http-check-actions">{check.position && <button onClick={() => jumpTo(check)} title="Select the offending character in the editor">Jump to character</button>}{check.automatonId && report.automata[check.automatonId] && <button onClick={() => visualize(check)} title="Open this rule DFA in Simulator and run the exact checked text">Visualize DFA <ExternalLink size={11}/></button>}</div></div>
        </motion.article>)}</div>}
      </aside>
    </div>
  </motion.section>
}

function splitList(value: string): string[] { return value.split(',').map(item => item.trim()).filter(Boolean) }
