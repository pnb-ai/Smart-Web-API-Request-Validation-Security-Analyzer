import { useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Download,
  ExternalLink,
  GitCompare,
  Layers,
  LoaderCircle,
  Printer,
  ScanSearch,
  Shield,
  ShieldCheck,
} from 'lucide-react'
import { useAppStore } from '../store/appStore'
import { useAutomataStore } from '../store/automataStore'
import { useToast } from './ToastProvider'
import type {
  RuleDiffResult,
  SecurityFinding,
  SecurityReport,
} from '../types/security'

const API = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'

export const attackSamples = [
  {
    name: "Clean Request (Benign O'Brien)",
    category: 'benign',
    text: "GET /api/users?name=O'Brien&role=engineer HTTP/1.1\r\nHost: api.example.com\r\nUser-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64)\r\nAccept: application/json\r\n\r\n",
  },
  {
    name: "SQL Injection: Tautology (' OR 1=1)",
    category: 'sql_injection',
    text: "POST /login HTTP/1.1\r\nHost: api.example.com\r\nContent-Type: application/x-www-form-urlencoded\r\nContent-Length: 29\r\n\r\nusername=admin%27%20OR%201=1--",
  },
  {
    name: 'SQL Injection: UNION SELECT Exfiltration',
    category: 'sql_injection',
    text: 'GET /products?category=electronics%20UNION%20SELECT%20username,%20password%20FROM%20users HTTP/1.1\r\nHost: api.example.com\r\n\r\n',
  },
  {
    name: 'SQL Injection: Stacked DROP TABLE',
    category: 'sql_injection',
    text: 'POST /account/delete HTTP/1.1\r\nHost: api.example.com\r\nContent-Type: application/json\r\n\r\n{"id": "100; DROP TABLE users;--"}',
  },
  {
    name: 'XSS: Reflected Script Tag (<script>)',
    category: 'xss',
    text: 'GET /search?q=%3Cscript%3Ealert(document.cookie)%3C/script%3E HTTP/1.1\r\nHost: api.example.com\r\n\r\n',
  },
  {
    name: 'XSS: Inline Event Handler (onerror=)',
    category: 'xss',
    text: 'GET /avatar?url=%22%3E%3Cimg%20src=x%20onerror=alert(1)%3E HTTP/1.1\r\nHost: api.example.com\r\n\r\n',
  },
  {
    name: 'XSS: JavaScript URL Scheme (javascript:)',
    category: 'xss',
    text: 'GET /redirect?url=javascript:alert(window.origin) HTTP/1.1\r\nHost: api.example.com\r\n\r\n',
  },
  {
    name: 'Path Traversal: Directory Climbing (../../)',
    category: 'path_traversal',
    text: 'GET /view?file=../../../../etc/passwd HTTP/1.1\r\nHost: api.example.com\r\n\r\n',
  },
  {
    name: 'Path Traversal: Double-Encoded (%252e%252e)',
    category: 'path_traversal',
    text: 'GET /doc?path=%252e%252e%252f%252e%252e%252fwindows/win.ini HTTP/1.1\r\nHost: api.example.com\r\n\r\n',
  },
  {
    name: 'Command Injection: Semicolon & Chaining (; cat)',
    category: 'command_injection',
    text: 'POST /network/ping HTTP/1.1\r\nHost: api.example.com\r\nContent-Type: application/x-www-form-urlencoded\r\n\r\nip=127.0.0.1; cat /etc/passwd',
  },
  {
    name: 'Null Byte Injection (%00 Truncation)',
    category: 'null_byte',
    text: 'GET /download?file=invoice.pdf%00.exe HTTP/1.1\r\nHost: api.example.com\r\n\r\n',
  },
  {
    name: 'CRLF Injection / Header Splitting (%0d%0a)',
    category: 'crlf_injection',
    text: 'GET /redirect?url=dashboard%0d%0aSet-Cookie:%20session=evil_admin HTTP/1.1\r\nHost: api.example.com\r\n\r\n',
  },
  {
    name: 'Scanner Probe: SQLMap User-Agent',
    category: 'suspicious_client',
    text: 'GET /admin HTTP/1.1\r\nHost: api.example.com\r\nUser-Agent: sqlmap/1.6.4#stable (https://sqlmap.org)\r\n\r\n',
  },
  {
    name: 'Oversized Parameter Flooding',
    category: 'oversized_parameter',
    text: 'GET /api/search?q=' + 'A'.repeat(1200) + ' HTTP/1.1\r\nHost: api.example.com\r\n\r\n',
  },
]

const ruleDiffPresets = [
  {
    name: 'Path Traversal: Unix only vs Unix+Windows',
    oldRule: String.raw`(\.\./)`,
    newRule: String.raw`(\.\./|\.\.\\)`,
  },
  {
    name: 'SQLi Tautology: Strict vs Relaxed quotes',
    oldRule: String.raw`(' OR 1=1)`,
    newRule: String.raw`('([ \t]*)OR([ \t]*)1=1|'([ \t]*)OR([ \t]*)'1'='1)`,
  },
  {
    name: 'XSS Script Tag: Case sensitive vs Case folded',
    oldRule: '(<script)',
    newRule: '(<script|<SCRIPT|<Script)',
  },
  {
    name: 'Command Injection: Semicolon only vs Chaining Operators',
    oldRule: String.raw`(;[ \t]*(cat|ls|id|whoami))`,
    newRule: String.raw`(;[ \t]*(cat|ls|id|whoami)|&&|\|)`,
  },
]

export function SecurityWorkspace() {
  const [activeTab, setActiveTab] = useState<'analyzer' | 'diff' | 'trace'>('analyzer')
  const [rawRequest, setRawRequest] = useState(attackSamples[1].text)
  const [report, setReport] = useState<SecurityReport | null>(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [error, setError] = useState('')
  const [selectedFinding, setSelectedFinding] = useState<SecurityFinding | null>(null)
  const [traceStepIndex, setTraceStepIndex] = useState(0)

  // Rule Diff states
  const [oldRule, setOldRule] = useState(ruleDiffPresets[0].oldRule)
  const [newRule, setNewRule] = useState(ruleDiffPresets[0].newRule)
  const [diffResult, setDiffResult] = useState<RuleDiffResult | null>(null)
  const [diffing, setDiffing] = useState(false)
  const [diffError, setDiffError] = useState('')
  const [customTestInput, setCustomTestInput] = useState('')

  const requestInputRef = useRef<HTMLTextAreaElement>(null)
  const { notify } = useToast()
  const setPage = useAppStore((state) => state.setPage)
  const setAutomaton = useAutomataStore((state) => state.setAutomaton)
  const setSimulationInput = useAutomataStore((state) => state.setSimulationInput)
  const setSimulationAutoRun = useAutomataStore((state) => state.setSimulationAutoRun)

  const runAnalysis = async (requestText = rawRequest) => {
    setAnalyzing(true)
    setError('')
    try {
      const response = await fetch(`${API}/api/security/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rawRequest: requestText }),
      })
      const data = await response.json()
      if (!response.ok) {
        throw new Error(typeof data.detail === 'string' ? data.detail : 'Security analysis failed.')
      }
      setReport(data as SecurityReport)
      setSelectedFinding(data.findings?.[0] || null)
      setTraceStepIndex(0)
    } catch (err) {
      setReport(null)
      setError(
        err instanceof TypeError
          ? 'Security analyzer backend service is offline. Start the backend and try again.'
          : err instanceof Error
            ? err.message
            : 'Could not complete security analysis.'
      )
    } finally {
      setAnalyzing(false)
    }
  }

  // Initial automatic analysis
  useEffect(() => {
    void runAnalysis(rawRequest)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const runRuleDiff = async () => {
    setDiffing(true)
    setDiffError('')
    try {
      const payloads = customTestInput.trim()
        ? [customTestInput.trim()]
        : undefined
      const response = await fetch(`${API}/api/security/rule-diff`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          oldPattern: oldRule,
          newPattern: newRule,
          testPayloads: payloads,
        }),
      })
      const data = await response.json()
      if (!response.ok) {
        throw new Error(typeof data.detail === 'string' ? data.detail : 'Rule diff check failed.')
      }
      setDiffResult(data as RuleDiffResult)
    } catch (err) {
      setDiffResult(null)
      setDiffError(err instanceof Error ? err.message : 'Could not compare rule patterns.')
    } finally {
      setDiffing(false)
    }
  }

  const highlightFindingInEditor = (finding: SecurityFinding) => {
    setSelectedFinding(finding)
    if (finding.position && requestInputRef.current) {
      const start = finding.position.offset
      const end = start + finding.position.length
      requestInputRef.current.focus()
      requestInputRef.current.setSelectionRange(start, end)
      requestInputRef.current.scrollTop = Math.max(0, (finding.position.line - 1) * 20)
    }
  }

  const sendAutomatonToSimulator = (finding: SecurityFinding) => {
    if (!finding.automatonId || !report) return
    const automaton = report.automata[finding.automatonId]
    if (!automaton) return
    setAutomaton(automaton)
    setSimulationInput(finding.matchedText)
    setSimulationAutoRun(true)
    setPage('simulator')
    notify(`Loaded DFA for '${finding.ruleName}' into Simulator`)
  }

  // One-click JSON export
  const exportJsonReport = () => {
    if (!report) return
    const exportData = {
      title: 'API Request Security Analyzer Report',
      timestamp: new Date().toISOString(),
      status: report.status,
      riskScore: report.riskScore,
      findingsSummary: report.findingsSummary,
      findings: report.findings,
      categoriesDetected: report.categoriesDetected,
      normalizationTrace: report.normalizationTrace,
      defenseDisclaimer: report.defenseDisclaimer,
      requestSummary: report.requestParts,
      rawRequest,
    }
    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `security-report-${Date.now()}.json`
    a.click()
    URL.revokeObjectURL(url)
    notify('Security report downloaded as JSON')
  }

  // One-click Printable HTML report
  const exportPrintableReport = () => {
    if (!report) return
    const printWindow = window.open('', '_blank')
    if (!printWindow) {
      notify('Please allow popups to open the printable report')
      return
    }

    const findingsHtml = report.findings
      .map(
        (f, i) => `
      <tr class="severity-${f.severity}">
        <td><strong>#${i + 1}</strong></td>
        <td><span class="badge ${f.severity}">${f.severity.toUpperCase()}</span></td>
        <td><strong>${escapeHtml(f.ruleName)}</strong><br/><small>${escapeHtml(f.category)}</small></td>
        <td><code>${escapeHtml(f.matchedText)}</code></td>
        <td><span class="norm-tag">${escapeHtml(f.normalizationStep)}</span></td>
        <td>${escapeHtml(f.explanation)}<br/><div class="fix-box"><strong>Fix:</strong> ${escapeHtml(f.recommendedFix)}</div></td>
      </tr>
    `
      )
      .join('')

    const htmlContent = `
      <!DOCTYPE html>
      <html>
      <head>
        <title>Security Analysis Audit Report - ${new Date().toLocaleDateString()}</title>
        <style>
          body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; color: #1a202c; line-height: 1.5; padding: 32px; background: #fff; }
          .header { border-bottom: 2px solid #e2e8f0; padding-bottom: 20px; margin-bottom: 24px; display: flex; justify-content: space-between; align-items: flex-end; }
          .title h1 { margin: 0 0 6px; font-size: 26px; }
          .title p { margin: 0; color: #718096; font-size: 13px; }
          .score-card { text-align: right; }
          .score-num { font-size: 38px; font-weight: bold; color: ${report.riskScore >= 70 ? '#e53e3e' : report.riskScore >= 40 ? '#dd6b20' : '#38a169'}; }
          .disclaimer { background: #ebf8ff; border-left: 4px solid #3182ce; padding: 12px 16px; margin: 20px 0; font-size: 12px; color: #2b6cb0; }
          table { width: 100%; border-collapse: collapse; margin-top: 16px; font-size: 12px; }
          th { background: #edf2f7; text-align: left; padding: 10px; border-bottom: 2px solid #cbd5e0; }
          td { padding: 10px; border-bottom: 1px solid #e2e8f0; vertical-align: top; }
          .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 10px; font-weight: bold; text-transform: uppercase; color: #fff; }
          .badge.critical { background: #e53e3e; }
          .badge.high { background: #dd6b20; }
          .badge.medium { background: #d69e2e; }
          .badge.low { background: #3182ce; }
          .norm-tag { font-family: monospace; font-size: 10px; background: #edf2f7; padding: 2px 6px; border-radius: 3px; }
          .fix-box { background: #f7fafc; border: 1px solid #e2e8f0; padding: 6px 10px; border-radius: 4px; margin-top: 6px; font-size: 11px; }
          pre { background: #2d3748; color: #f7fafc; padding: 12px; border-radius: 6px; font-size: 11px; overflow-x: auto; white-space: pre-wrap; }
          @media print { body { padding: 0; } button { display: none; } }
        </style>
      </head>
      <body>
        <div class="header">
          <div class="title">
            <h1>API Request Security Audit Report</h1>
            <p>Automata-Based Syntax & Exploit Signature Inspection</p>
            <p><small>Generated at ${new Date().toLocaleString()} · Automata Studio</small></p>
          </div>
          <div class="score-card">
            <div>Risk Assessment</div>
            <div class="score-num">${report.riskScore}/100</div>
            <div><strong>${report.status}</strong></div>
          </div>
        </div>

        <div class="disclaimer">
          <strong>Defense-in-Depth Principle:</strong> ${report.defenseDisclaimer}
        </div>

        <h3>Vulnerability Findings (${report.findings.length})</h3>
        ${
          report.findings.length > 0
            ? `
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Severity</th>
                <th>Rule / Category</th>
                <th>Offending Substring</th>
                <th>Normalization</th>
                <th>Explanation & Remediation</th>
              </tr>
            </thead>
            <tbody>
              ${findingsHtml}
            </tbody>
          </table>
        `
            : '<p>No attack signatures or suspicious vectors detected. Request evaluated as CLEAN.</p>'
        }

        <h3 style="margin-top: 32px;">Analyzed Raw HTTP Request</h3>
        <pre>${escapeHtml(rawRequest)}</pre>

        <script>
          window.onload = function() { window.print(); }
        </script>
      </body>
      </html>
    `
    printWindow.document.write(htmlContent)
    printWindow.document.close()
    notify('Printable report opened in new tab')
  }

  return (
    <motion.section
      className="security-workspace"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
    >
      {/* Top Header */}
      <div className="security-top-header">
        <div className="security-title-group">
          <div className="security-eyebrow">
            <span className="eyebrow-chip">SECURITY LAYER</span>
            <span>REGEX LAB DETECTION AUTOMATA · 5-STAGE NORMALIZATION</span>
          </div>
          <h2>Smart HTTP Security Analyzer</h2>
          <p>
            Scans requests for injection patterns, traversal vectors, and scanner probes using
            minimized DFAs compiled from formal regular expressions.
          </p>
        </div>

        {/* Global Tab Navigation */}
        <div className="security-nav-tabs">
          <button
            className={`sec-tab-btn ${activeTab === 'analyzer' ? 'active' : ''}`}
            onClick={() => setActiveTab('analyzer')}
          >
            <ScanSearch size={15} />
            <span>Analyzer & Findings</span>
          </button>
          <button
            className={`sec-tab-btn ${activeTab === 'diff' ? 'active' : ''}`}
            onClick={() => setActiveTab('diff')}
          >
            <GitCompare size={15} />
            <span>Rule Diff & Equivalence</span>
          </button>
          <button
            className={`sec-tab-btn ${activeTab === 'trace' ? 'active' : ''}`}
            onClick={() => setActiveTab('trace')}
          >
            <Layers size={15} />
            <span>Normalization Trace</span>
          </button>
        </div>
      </div>

      {/* Defense-in-Depth Honesty Banner */}
      <div className="defense-banner">
        <div className="defense-icon">
          <Shield size={18} />
        </div>
        <div className="defense-text">
          <strong>Defense-in-Depth Principle:</strong>
          <span>
            Automata-based regular expression filters serve as a high-speed first line of defense
            and request hygiene layer. They are <em>not</em> a replacement for parameterized queries
            (prepared statements) and context-aware output encoding.
          </span>
        </div>
      </div>

      {/* MAIN ANALYZER TAB */}
      {activeTab === 'analyzer' && (
        <div className="sec-analyzer-grid">
          {/* Left Column: Request Input & Highlighting */}
          <div className="sec-left-col">
            <section className="sec-panel">
              <div className="sec-panel-header">
                <div>
                  <span className="sec-kicker">HTTP/1.1 MESSAGE</span>
                  <strong>Request Payload Editor</strong>
                </div>

                {/* Sample Attack Presets */}
                <div className="sec-sample-picker">
                  <span className="sample-label">Attack Presets:</span>
                  <select
                    className="text-input sec-select"
                    defaultValue=""
                    onChange={(e) => {
                      const idx = Number(e.target.value)
                      if (!isNaN(idx) && attackSamples[idx]) {
                        setRawRequest(attackSamples[idx].text)
                        void runAnalysis(attackSamples[idx].text)
                        notify(`Loaded ${attackSamples[idx].name}`)
                      }
                      e.target.value = ''
                    }}
                  >
                    <option value="" disabled>
                      Select an attack payload…
                    </option>
                    {attackSamples.map((sample, idx) => (
                      <option key={sample.name} value={idx}>
                        {sample.name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Text Area Input */}
              <div className="sec-editor-wrapper">
                <textarea
                  ref={requestInputRef}
                  className="text-input sec-raw-textarea"
                  value={rawRequest}
                  onChange={(e) => setRawRequest(e.target.value)}
                  placeholder="Paste HTTP request here..."
                  spellCheck={false}
                  onKeyDown={(e) => {
                    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                      e.preventDefault()
                      void runAnalysis()
                    }
                  }}
                />
              </div>

              {/* Editor Bottom Actions */}
              <div className="sec-editor-footer">
                <span className="sec-hint-text">
                  Ctrl/⌘ + Enter to analyze · Auto-normalized across 5 stages
                </span>
                <div className="sec-action-btns">
                  <button
                    className="button button-primary"
                    onClick={() => void runAnalysis()}
                    disabled={analyzing}
                  >
                    {analyzing ? (
                      <LoaderCircle className="spin" size={14} />
                    ) : (
                      <ScanSearch size={14} />
                    )}
                    <span>Analyze Request</span>
                  </button>
                </div>
              </div>
            </section>

            {/* Error Banner */}
            {error && (
              <div className="sec-error-banner">
                <AlertCircle size={16} />
                <span>{error}</span>
              </div>
            )}

            {/* Highlighted Request Inspector */}
            {report && (
              <section className="sec-panel">
                <div className="sec-panel-header">
                  <div>
                    <span className="sec-kicker">INSPECTION</span>
                    <strong>Interactive Vulnerability Map</strong>
                  </div>
                  <span className="sec-hint-text">
                    Click any highlighted region to view finding
                  </span>
                </div>

                <div className="sec-highlight-display">
                  <pre className="sec-highlight-pre">
                    {renderHighlightedRequest(rawRequest, report.findings, selectedFinding, (f) =>
                      setSelectedFinding(f)
                    )}
                  </pre>
                </div>
              </section>
            )}
          </div>

          {/* Right Column: Risk Gauge, Summary & Findings List */}
          <div className="sec-right-col">
            {/* Risk Gauge Card */}
            <section className="sec-panel sec-gauge-card">
              <div className="sec-panel-header">
                <div>
                  <span className="sec-kicker">THREAT LEVEL</span>
                  <strong>Risk Assessment Score</strong>
                </div>
                <div className="sec-export-group">
                  <button
                    className="button button-small"
                    title="Export JSON report"
                    onClick={exportJsonReport}
                    disabled={!report}
                  >
                    <Download size={13} />
                    <span>JSON</span>
                  </button>
                  <button
                    className="button button-small button-primary"
                    title="Print or PDF report"
                    onClick={exportPrintableReport}
                    disabled={!report}
                  >
                    <Printer size={13} />
                    <span>Print</span>
                  </button>
                </div>
              </div>

              {/* SVG Animated Risk Gauge */}
              <div className="risk-gauge-container">
                <RiskGauge score={report?.riskScore ?? 0} />

                {/* Severity Breakdown Pills */}
                <div className="severity-summary-row">
                  <div className="sev-pill crit">
                    <span className="sev-dot" />
                    <span className="sev-count">{report?.findingsSummary.critical ?? 0}</span>
                    <span className="sev-name">Critical</span>
                  </div>
                  <div className="sev-pill high">
                    <span className="sev-dot" />
                    <span className="sev-count">{report?.findingsSummary.high ?? 0}</span>
                    <span className="sev-name">High</span>
                  </div>
                  <div className="sev-pill med">
                    <span className="sev-dot" />
                    <span className="sev-count">{report?.findingsSummary.medium ?? 0}</span>
                    <span className="sev-name">Medium</span>
                  </div>
                  <div className="sev-pill low">
                    <span className="sev-dot" />
                    <span className="sev-count">{report?.findingsSummary.low ?? 0}</span>
                    <span className="sev-name">Low</span>
                  </div>
                </div>
              </div>
            </section>

            {/* Findings List */}
            <section className="sec-panel sec-findings-panel">
              <div className="sec-panel-header">
                <div>
                  <span className="sec-kicker">SECURITY FINDINGS</span>
                  <strong>Detected Violations ({report?.findings.length ?? 0})</strong>
                </div>
                {report && report.findings.length === 0 && (
                  <span className="clean-pill">
                    <CheckCircle2 size={13} /> CLEAN
                  </span>
                )}
              </div>

              {/* List */}
              <div className="findings-scroll-list">
                {report?.findings.map((finding) => (
                  <FindingCard
                    key={finding.id}
                    finding={finding}
                    isSelected={selectedFinding?.id === finding.id}
                    onSelect={() => highlightFindingInEditor(finding)}
                    onOpenDfa={() => sendAutomatonToSimulator(finding)}
                  />
                ))}

                {(!report || report.findings.length === 0) && (
                  <div className="findings-empty">
                    <ShieldCheck size={38} className="empty-shield-icon" />
                    <strong>No Malicious Signatures Detected</strong>
                    <p>
                      The request is clean of known SQLi, XSS, Path Traversal, and Command
                      Injection patterns.
                    </p>
                  </div>
                )}
              </div>
            </section>
          </div>
        </div>
      )}

      {/* RULE DIFF & EQUIVALENCE TAB */}
      {activeTab === 'diff' && (
        <section className="sec-panel sec-diff-panel">
          <div className="sec-panel-header">
            <div>
              <span className="sec-kicker">FORMAL VERIFICATION</span>
              <h2>Security Rule Diff & Equivalence Checker</h2>
              <p>
                Modify a security detection regular expression and mathematically verify whether
                the updated rule preserves language equivalence or creates false positives/gaps.
              </p>
            </div>

            {/* Presets */}
            <div className="sec-sample-picker">
              <span className="sample-label">Presets:</span>
              <select
                className="text-input sec-select"
                defaultValue=""
                onChange={(e) => {
                  const idx = Number(e.target.value)
                  if (!isNaN(idx) && ruleDiffPresets[idx]) {
                    setOldRule(ruleDiffPresets[idx].oldRule)
                    setNewRule(ruleDiffPresets[idx].newRule)
                    notify(`Loaded diff preset: ${ruleDiffPresets[idx].name}`)
                  }
                  e.target.value = ''
                }}
              >
                <option value="" disabled>
                  Load a rule diff preset…
                </option>
                {ruleDiffPresets.map((p, i) => (
                  <option key={p.name} value={i}>
                    {p.name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Side by side rule editors */}
          <div className="rule-diff-grid">
            <div className="rule-card old-rule">
              <div className="rule-card-header">
                <span className="rule-badge old">ORIGINAL RULE (L₁)</span>
                <small>Existing signature regex</small>
              </div>
              <input
                className="text-input rule-input"
                value={oldRule}
                onChange={(e) => setOldRule(e.target.value)}
                placeholder="e.g. (\.\./)"
                spellCheck={false}
              />
            </div>

            <div className="rule-card new-rule">
              <div className="rule-card-header">
                <span className="rule-badge new">PROPOSED RULE (L₂)</span>
                <small>Modified candidate regex</small>
              </div>
              <input
                className="text-input rule-input"
                value={newRule}
                onChange={(e) => setNewRule(e.target.value)}
                placeholder="e.g. (\.\./|\.\.\\)"
                spellCheck={false}
              />
            </div>
          </div>

          {/* Test bench & Run button */}
          <div className="diff-run-bar">
            <div className="diff-custom-input">
              <span className="sample-label">Test with Custom Payload:</span>
              <input
                className="text-input"
                value={customTestInput}
                onChange={(e) => setCustomTestInput(e.target.value)}
                placeholder="Enter string to test (or leave empty for test suite)"
              />
            </div>

            <button
              className="button button-primary diff-compare-btn"
              onClick={runRuleDiff}
              disabled={diffing || !oldRule.trim() || !newRule.trim()}
            >
              {diffing ? <LoaderCircle className="spin" size={14} /> : <GitCompare size={14} />}
              <span>Compare Rules with Equivalence Checker</span>
            </button>
          </div>

          {diffError && (
            <div className="sec-error-banner">
              <AlertCircle size={16} />
              <span>{diffError}</span>
            </div>
          )}

          {/* Equivalence Outcome Display */}
          {diffResult && (
            <div className="diff-results-area">
              <div
                className={`diff-verdict-card ${diffResult.equivalent ? 'equivalent' : 'distinguishable'}`}
              >
                <div className="verdict-icon-box">
                  {diffResult.equivalent ? (
                    <CheckCircle2 size={30} className="text-green" />
                  ) : (
                    <AlertTriangle size={30} className="text-amber" />
                  )}
                </div>
                <div className="verdict-text">
                  <h3>
                    {diffResult.equivalent
                      ? 'Rules are Formally Equivalent: L(Old) = L(New)'
                      : 'Rules are Distinguishable: Languages Differ'}
                  </h3>
                  <p>
                    {diffResult.equivalent
                      ? 'Both regular expressions recognize the exact same set of attack strings under DFA minimization.'
                      : 'The two automata accept differing sets of inputs. Below is the shortest counterexample and payload impact table.'}
                  </p>
                </div>
                {!diffResult.equivalent && diffResult.counterexample && (
                  <div className="witness-chip">
                    <small>Shortest Distinguishing Witness:</small>
                    <code>{diffResult.counterexample}</code>
                  </div>
                )}
              </div>

              {/* Behavior Comparison Table */}
              <div className="diff-table-card">
                <div className="sec-panel-header">
                  <strong>Payload Impact Matrix (Allowed vs Blocked)</strong>
                  <span className="sec-hint-text">
                    Shows which attack requests are newly caught or allowed
                  </span>
                </div>

                <div className="diff-table-scroll">
                  <table className="diff-table">
                    <thead>
                      <tr>
                        <th>Payload</th>
                        <th>Old Rule (L₁)</th>
                        <th>New Rule (L₂)</th>
                        <th>Impact Verdict</th>
                      </tr>
                    </thead>
                    <tbody>
                      {diffResult.payloadEvaluations.map((pe, idx) => (
                        <tr key={idx}>
                          <td>
                            <code>{pe.payload}</code>
                          </td>
                          <td>
                            <span
                              className={`status-pill ${pe.blockedByOld ? 'blocked' : 'allowed'}`}
                            >
                              {pe.blockedByOld ? 'BLOCKED' : 'ALLOWED'}
                            </span>
                          </td>
                          <td>
                            <span
                              className={`status-pill ${pe.blockedByNew ? 'blocked' : 'allowed'}`}
                            >
                              {pe.blockedByNew ? 'BLOCKED' : 'ALLOWED'}
                            </span>
                          </td>
                          <td>
                            <span className={`impact-badge ${pe.behavior}`}>
                              {pe.behavior === 'newly_blocked' && '🛡️ Newly Blocked (Tightened)'}
                              {pe.behavior === 'newly_allowed' && '⚠️ Newly Allowed (Relaxed)'}
                              {pe.behavior === 'blocked_by_both' && 'Blocked by Both'}
                              {pe.behavior === 'allowed_by_both' && 'Allowed by Both'}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </section>
      )}

      {/* NORMALIZATION & TRACE TAB */}
      {activeTab === 'trace' && report && (
        <section className="sec-panel sec-trace-panel">
          <div className="sec-panel-header">
            <div>
              <span className="sec-kicker">NORMALIZATION PIPELINE & TRACE</span>
              <h2>Multi-Stage Input Decoding & Execution Steps</h2>
              <p>
                To prevent filter evasion, input is systematically normalized across 5 stages
                before automata matching.
              </p>
            </div>
          </div>

          {/* Normalization Stages Visual Timeline */}
          <div className="norm-timeline">
            {report.normalizationSteps.map((ns, idx) => {
              const matchedEvents = report.normalizationTrace.filter((e) => e.stage === ns.step)
              const hasTrigger = matchedEvents.length > 0
              return (
                <div key={ns.step} className={`norm-stage-card ${hasTrigger ? 'triggered' : ''}`}>
                  <div className="norm-stage-header">
                    <span className="norm-idx">{idx + 1}</span>
                    <div>
                      <strong>{ns.label}</strong>
                      <small>{ns.description}</small>
                    </div>
                  </div>
                  {hasTrigger && (
                    <div className="norm-trigger-alert">
                      <AlertTriangle size={13} />
                      <span>Exposed {matchedEvents.length} attack pattern(s) at this stage!</span>
                    </div>
                  )}
                </div>
              )
            })}
          </div>

          {/* Step-by-Step Algorithm Execution Trace */}
          <div className="trace-player-card">
            <div className="trace-player-header">
              <span className="sec-kicker">TRACE STEP {traceStepIndex + 1} OF {report.trace.length}</span>
              <div className="trace-player-nav">
                <button
                  className="button button-small"
                  onClick={() => setTraceStepIndex((i) => Math.max(0, i - 1))}
                  disabled={traceStepIndex === 0}
                >
                  Previous
                </button>
                <button
                  className="button button-small"
                  onClick={() =>
                    setTraceStepIndex((i) => Math.min(report.trace.length - 1, i + 1))
                  }
                  disabled={traceStepIndex === report.trace.length - 1}
                >
                  Next
                </button>
              </div>
            </div>

            {report.trace[traceStepIndex] && (
              <div className="trace-step-content">
                <h3>{report.trace[traceStepIndex].title}</h3>
                <p>{report.trace[traceStepIndex].explanation}</p>
                <pre className="trace-json-box">
                  {JSON.stringify(report.trace[traceStepIndex].data, null, 2)}
                </pre>
              </div>
            )}
          </div>
        </section>
      )}
    </motion.section>
  )
}

// Sub-component: Finding Card
function FindingCard({
  finding,
  isSelected,
  onSelect,
  onOpenDfa,
}: {
  finding: SecurityFinding
  isSelected: boolean
  onSelect: () => void
  onOpenDfa: () => void
}) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div
      className={`finding-card ${finding.severity} ${isSelected ? 'selected' : ''}`}
      onClick={onSelect}
    >
      <div className="finding-top">
        <div className="finding-meta">
          <span className={`finding-sev-badge ${finding.severity}`}>
            {finding.severity.toUpperCase()}
          </span>
          <strong className="finding-title">{finding.ruleName}</strong>
          <span className="finding-cat">{finding.category}</span>
        </div>

        <button
          className="finding-expand-btn"
          onClick={(e) => {
            e.stopPropagation()
            setExpanded(!expanded)
          }}
          title="Toggle details"
        >
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>
      </div>

      <div className="finding-snippet-row">
        <span className="finding-match-label">Matched:</span>
        <code className="finding-match-code">{finding.matchedText}</code>
        <span className="finding-stage-chip" title="Transformation stage exposing the pattern">
          Exposed at: {finding.normalizationStep}
        </span>
      </div>

      <AnimatePresence>
        {expanded && (
          <motion.div
            className="finding-details"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
          >
            <p className="finding-explanation">{finding.explanation}</p>
            <div className="finding-fix-box">
              <strong>Recommended Fix:</strong>
              <p>{finding.recommendedFix}</p>
            </div>
            {finding.automatonId && (
              <div className="finding-dfa-btn-row">
                <button
                  className="button button-small"
                  onClick={(e) => {
                    e.stopPropagation()
                    onOpenDfa()
                  }}
                >
                  <ExternalLink size={12} />
                  <span>Inspect Rule DFA in Simulator</span>
                </button>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// Sub-component: Animated SVG Risk Gauge
function RiskGauge({ score }: { score: number }) {
  // Arc calculation for 180-degree semi-circle gauge
  const radius = 68
  const circumference = Math.PI * radius
  const strokeDashoffset = circumference - (score / 100) * circumference

  const statusLabel =
    score === 0
      ? 'Clean / Safe'
      : score < 40
        ? 'Low Risk'
        : score < 70
          ? 'Suspicious'
          : 'Malicious Vector'

  const gaugeColor =
    score === 0
      ? 'var(--accent)'
      : score < 40
        ? '#57d6ff'
        : score < 70
          ? '#eab308'
          : '#ef4444'

  return (
    <div className="risk-gauge-wrap">
      <svg className="risk-gauge-svg" viewBox="0 0 180 110">
        <defs>
          <linearGradient id="gaugeGradient" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#4ade80" />
            <stop offset="35%" stopColor="#38bdf8" />
            <stop offset="65%" stopColor="#facc15" />
            <stop offset="100%" stopColor="#f87171" />
          </linearGradient>
        </defs>

        {/* Background track */}
        <path
          d="M 20 95 A 68 68 0 0 1 160 95"
          fill="none"
          stroke="var(--border)"
          strokeWidth="14"
          strokeLinecap="round"
        />

        {/* Filled progress arc */}
        <path
          d="M 20 95 A 68 68 0 0 1 160 95"
          fill="none"
          stroke="url(#gaugeGradient)"
          strokeWidth="14"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={strokeDashoffset}
          style={{ transition: 'stroke-dashoffset 0.6s cubic-bezier(0.16, 1, 0.3, 1)' }}
        />
      </svg>

      <div className="gauge-score-readout">
        <strong style={{ color: gaugeColor }}>{score}</strong>
        <small>/ 100</small>
        <span className="gauge-status-badge" style={{ borderColor: gaugeColor, color: gaugeColor }}>
          {statusLabel}
        </span>
      </div>
    </div>
  )
}

// Request Highlighter Helper
function renderHighlightedRequest(
  text: string,
  findings: SecurityFinding[],
  selected: SecurityFinding | null,
  onSelect: (f: SecurityFinding) => void
) {
  if (!findings || findings.length === 0) {
    return text
  }

  // Collect regions with offset and length
  const regions: { start: number; end: number; finding: SecurityFinding }[] = []
  for (const f of findings) {
    if (f.position && f.position.offset >= 0 && f.position.length > 0) {
      regions.push({
        start: f.position.offset,
        end: Math.min(text.length, f.position.offset + f.position.length),
        finding: f,
      })
    }
  }

  regions.sort((a, b) => a.start - b.start)

  const elements: React.ReactNode[] = []
  let cursor = 0

  regions.forEach((region, idx) => {
    if (region.start > cursor) {
      elements.push(text.slice(cursor, region.start))
    }

    const matchedSubstring = text.slice(region.start, region.end)
    const isFocused = selected?.id === region.finding.id

    elements.push(
      <span
        key={idx}
        className={`sec-code-highlight ${region.finding.severity} ${isFocused ? 'focused' : ''}`}
        onClick={() => onSelect(region.finding)}
        title={`${region.finding.ruleName} (${region.finding.severity.toUpperCase()})`}
      >
        {matchedSubstring}
      </span>
    )
    cursor = Math.max(cursor, region.end)
  })

  if (cursor < text.length) {
    elements.push(text.slice(cursor))
  }

  return elements
}

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}
