import { Component, lazy, Suspense, useEffect, useMemo, useRef, useState, type ErrorInfo, type ReactNode } from 'react'
import { motion } from 'framer-motion'
import { ArrowRight, Binary, BookOpen, Braces, Check, ChevronDown, CircleHelp, Command, FileDown, FileUp, GitFork, Keyboard, Moon, Network, Play, Plus, Regex, ScanSearch, Save, Search, ShieldCheck, Sun, Workflow, X } from 'lucide-react'
import { pages, useAppStore, type PageId } from './store/appStore'
import { ToastProvider, useToast } from './components/ToastProvider'
import { useAutomataStore } from './store/automataStore'
import { LoadingSkeleton } from './components/LoadingSkeleton'

const AutomataBuilder = lazy(() => import('./components/AutomataWorkspace').then((module) => ({ default: module.AutomataBuilder })))
const AutomataSimulator = lazy(() => import('./components/AutomataWorkspace').then((module) => ({ default: module.AutomataSimulator })))
const TransformWorkspace = lazy(() => import('./components/TransformWorkspace').then((module) => ({ default: module.TransformWorkspace })))
const EquivalenceWorkspace = lazy(() => import('./components/EquivalenceWorkspace').then((module) => ({ default: module.EquivalenceWorkspace })))
const RegexWorkspace = lazy(() => import('./components/RegexWorkspace').then((module) => ({ default: module.RegexWorkspace })))
const LexerWorkspace = lazy(() => import('./components/LexerWorkspace').then((module) => ({ default: module.LexerWorkspace })))
const HttpValidatorWorkspace = lazy(() => import('./components/HttpValidatorWorkspace').then((module) => ({ default: module.HttpValidatorWorkspace })))
const SecurityWorkspace = lazy(() => import('./components/SecurityWorkspace').then((module) => ({ default: module.SecurityWorkspace })))
import { useWorkspaceStore, type SavedWorkspace } from './store/workspaceStore'

const icons = { builder: Workflow, simulator: Play, transform: GitFork, equivalence: Network, regex: Regex, lexer: Braces, validator: ShieldCheck, security: ScanSearch }
const theory: Record<PageId, { title: string; paragraphs: string[] }> = {
  builder: { title: 'Finite automata', paragraphs: ['A finite automaton is a graph of states and labeled transitions. One state is the start; accepting states mark strings in the language.', 'Use ε-NFA when a construction needs a move that consumes no input. Symbol classes such as DIGIT and CRLF keep common character sets readable.'] },
  simulator: { title: 'Language membership', paragraphs: ['Simulation follows transitions for each input symbol. A DFA has one active state; an NFA tracks a set of possible states.', 'The string is accepted when the run ends in an accepting state. The trace shows how the current configuration changes.'] },
  transform: { title: 'Subset construction & minimization', paragraphs: ['Subset construction turns an NFA into a DFA. Each DFA state represents a set of NFA states reachable after the same input prefix.', 'Myhill–Nerode equivalence says two states can be merged when no suffix distinguishes their future acceptance. Partition refinement computes the minimal DFA.'] },
  equivalence: { title: 'Myhill–Nerode & product search', paragraphs: ['Two automata are equivalent when they accept exactly the same language. Product BFS explores pairs of states and looks for a pair whose acceptance differs.', 'The path to that pair is a shortest counterexample: a concrete string accepted by one machine and rejected by the other.'] },
  regex: { title: 'Thompson construction', paragraphs: ['Thompson’s construction translates regex syntax into an ε-NFA using small fragments for literals, concatenation, alternation, and repetition.', 'Subset construction then produces a DFA, which can be minimized without changing the recognized language.'] },
  lexer: { title: 'Lexical analysis', paragraphs: ['A lexer represents token patterns as regular languages and combines them into one machine. At each input position, it chooses the best matching token rule.', 'Symbol classes let transitions represent broad character groups without drawing every possible byte.'] },
  validator: { title: 'Protocol validation', paragraphs: ['HTTP validation checks the request line, headers, framing, and configured policy rules against protocol constraints.', 'A formal rule can produce an automaton that explains which request text caused a check to pass or fail.'] },
  security: { title: 'Automata as a security filter', paragraphs: ['Security signatures are regular patterns compiled through Regex Lab and scanned across normalized request text.', 'This is a first line of defense, not a substitute for parameterized queries, context-aware output encoding, and safe application design.'] },
}
const tour = [
  ['Build a machine', 'Create states and transitions in the canvas, or start with a built-in example.'],
  ['Try a string', 'Use Simulator to see whether a machine accepts an input and inspect its trace.'],
  ['Write a regex', 'Regex Lab visualizes Thompson construction and the route to a minimal DFA.'],
  ['Compare languages', 'Equivalence Checker finds a shortest string that distinguishes two rules.'],
  ['Validate requests', 'HTTP Validator and Security Analyzer apply automata to real request text.'],
]
const tourPages: PageId[] = ['builder', 'simulator', 'regex', 'equivalence', 'security']

class ErrorBoundary extends Component<{ children: ReactNode }, { error: boolean }> {
  state = { error: false }
  static getDerivedStateFromError() { return { error: true } }
  componentDidCatch(_error: Error, _info: ErrorInfo) { /* Keep page errors inside the workspace shell. */ }
  render() {
    if (this.state.error) return <section className="placeholder-card" role="alert"><h2>This page hit a problem</h2><p>Your workspace data is still saved. Return to another page or try this page again.</p><button className="button button-secondary" onClick={() => this.setState({ error: false })}>Try again</button></section>
    return this.props.children
  }
}

function Workspace() {
  const { activePage, darkMode, setPage, toggleTheme, regexDraft, setRegexDraft, requestDraft, setRequestDraft } = useAppStore()
  const { notify } = useToast()
  const automaton = useAutomataStore((state) => state.automaton)
  const setAutomaton = useAutomataStore((state) => state.setAutomaton)
  const { workspaces, activeId, save, create, load, importWorkspace } = useWorkspaceStore()
  const selected = pages.find((page) => page.id === activePage)!
  const [palette, setPalette] = useState(false)
  const [paletteQuery, setPaletteQuery] = useState('')
  const [paletteIndex, setPaletteIndex] = useState(0)
  const [learn, setLearn] = useState(false)
  const [help, setHelp] = useState(false)
  const [tourStep, setTourStep] = useState<number | null>(null)
  const [workspaceDialog, setWorkspaceDialog] = useState(false)
  const [workspaceName, setWorkspaceName] = useState('')
  const [demoBusy, setDemoBusy] = useState(false)
  const [demoMessage, setDemoMessage] = useState('')
  const paletteRef = useRef<HTMLInputElement>(null)
  const dialogRef = useRef<HTMLElement>(null)
  const importRef = useRef<HTMLInputElement>(null)
  const filteredPages = useMemo(() => pages.filter((page) => page.label.toLowerCase().includes(paletteQuery.toLowerCase())), [paletteQuery])
  const currentWorkspace = workspaces.find((workspace) => workspace.id === activeId)

  useEffect(() => { document.documentElement.dataset.theme = darkMode ? 'dark' : 'light' }, [darkMode])
  useEffect(() => { if (palette) paletteRef.current?.focus() }, [palette])
  useEffect(() => {
    if (!palette && !help && !workspaceDialog && tourStep === null) return
    const root = dialogRef.current
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const focusable = () => [...(root?.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled]), select:not([disabled]), [href], [tabindex]:not([tabindex="-1"])') || [])]
    if (!palette) focusable()[0]?.focus()
    const trapFocus = (event: KeyboardEvent) => {
      if (event.key !== 'Tab') return
      const items = focusable()
      if (!items.length) { event.preventDefault(); return }
      if (event.shiftKey && document.activeElement === items[0]) { event.preventDefault(); items.at(-1)?.focus() }
      else if (!event.shiftKey && document.activeElement === items.at(-1)) { event.preventDefault(); items[0].focus() }
    }
    document.addEventListener('keydown', trapFocus)
    return () => { document.removeEventListener('keydown', trapFocus); if (previous?.isConnected) previous.focus() }
  }, [palette, help, workspaceDialog, tourStep])
  useEffect(() => {
    if (!localStorage.getItem('automata-studio-tour-v1')) setTourStep(0)
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); setPalette(true); setPaletteQuery(''); setPaletteIndex(0) }
      if ((event.ctrlKey || event.metaKey) && event.key === '/') { event.preventDefault(); setHelp(true) }
      if (event.key === 'Escape') { setPalette(false); setHelp(false); setWorkspaceDialog(false); document.activeElement instanceof HTMLElement && document.activeElement.blur() }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const snapshot = () => ({ automaton, regexes: regexDraft ? [regexDraft] : [], requests: requestDraft ? [requestDraft] : [] })
  const loadSaved = (workspace: SavedWorkspace) => {
    setAutomaton(workspace.automaton); setRegexDraft(workspace.regexes[0] || ''); setRequestDraft(workspace.requests[0] || '')
    notify(`Loaded ${workspace.name}`)
  }
  const exportWorkspace = () => {
    const data = currentWorkspace ? { ...currentWorkspace, ...snapshot(), updatedAt: new Date().toISOString() } : { id: activeId, name: 'My Workspace', ...snapshot(), updatedAt: new Date().toISOString() }
    const link = document.createElement('a'); link.href = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })); link.download = `${data.name.replace(/[^\w-]+/g, '-')}.json`; link.click(); URL.revokeObjectURL(link.href)
  }
  const importFile = async (file?: File) => { if (!file) return; try { const workspace = importWorkspace(JSON.parse(await file.text())); loadSaved(workspace) } catch (error) { notify(error instanceof Error ? error.message : 'Could not import this workspace file.') }; if (importRef.current) importRef.current.value = '' }
  const runDemo = async () => {
    setDemoBusy(true); setDemoMessage('1/5 · Writing a regular-expression rule…')
    const api = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'
    try {
      const oldRule = '(ab|ac)'
      const changedRule = '(ab|ac|ad)'
      const compiledResponse = await fetch(`${api}/api/regex/convert`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ pattern: oldRule }) })
      const compiled = await compiledResponse.json()
      if (!compiledResponse.ok) throw new Error('The Regex Lab could not compile the demo rule.')
      setRegexDraft(oldRule)
      setPage('regex')
      setDemoMessage('2/5 · Checking a malicious request…')
      const request = 'GET /search?q=%3Cscript%3Ealert(1)%3C/script%3E HTTP/1.1\r\nHost: demo.local\r\n\r\n'
      const securityResponse = await fetch(`${api}/api/security/analyze`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ rawRequest: request }) })
      const securityReport = await securityResponse.json()
      if (!securityResponse.ok || !securityReport.findings?.length) throw new Error('The Security Analyzer did not flag the demo request as expected.')
      setRequestDraft(request)
      setPage('security')
      setDemoMessage('3/5 · Updating the rule and finding the counterexample…')
      const diffResponse = await fetch(`${api}/api/security/rule-diff`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ oldPattern: oldRule, newPattern: changedRule, testPayloads: ['ab', 'ac', 'ad', 'aa'] }) })
      const diff = await diffResponse.json()
      if (!diffResponse.ok || diff.equivalent || !diff.counterexample) throw new Error('The Equivalence Checker did not find the expected rule counterexample.')
      setRegexDraft(changedRule)
      setPage('equivalence')
      setDemoMessage(`4/5 · Counterexample found: ${diff.counterexample || 'none'}. Minimizing the automaton…`)
      const minimizedResponse = await fetch(`${api}/api/transform`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ automaton: compiled.minimalDfa, operation: 'minimize-hopcroft', minimizer: 'hopcroft' }) })
      const minimized = await minimizedResponse.json()
      if (!minimizedResponse.ok) throw new Error('The demo automaton could not be minimized.')
      setAutomaton(minimized.result || compiled.minimalDfa)
      setPage('transform')
      setDemoMessage(`5/5 · Demo complete. Rule changed from ${oldRule} to ${changedRule}; ${diff.counterexample ? `shortest witness: ${diff.counterexample}` : 'no witness'}; minimized to ${(minimized.result || compiled.minimalDfa).states.length} states.`)
    } catch (error) { setDemoMessage(error instanceof TypeError ? 'Demo needs the backend. Start it on port 8000 and retry.' : error instanceof Error ? error.message : 'The demo stopped unexpectedly.') }
    finally { setDemoBusy(false) }
  }

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark"><Binary size={21} /></div><div><strong>Automata<span>Studio</span></strong><small>FORMAL SYSTEMS LAB</small></div></div>
      <label className="project-switcher"><div className="project-icon"><Network size={17} /></div><span><strong>Workspace</strong><select aria-label="Saved workspace" value={activeId} onChange={(event) => { const workspace = load(event.target.value); if (workspace) loadSaved(workspace) }}>{workspaces.map((workspace) => <option key={workspace.id} value={workspace.id}>{workspace.name}</option>)}</select></span><ChevronDown size={15} /></label>
      <div className="workspace-tools"><button onClick={() => { save(snapshot()); notify('Workspace saved locally') }} title="Save this workspace"><Save size={14}/> Save</button><button onClick={() => setWorkspaceDialog(true)} title="Create a workspace"><Plus size={14}/> New</button><button onClick={exportWorkspace} title="Export workspace JSON"><FileDown size={14}/></button><button onClick={() => importRef.current?.click()} title="Import workspace JSON"><FileUp size={14}/></button><input ref={importRef} type="file" accept=".json,application/json" hidden onChange={(event) => void importFile(event.target.files?.[0])}/></div>
      <nav aria-label="Main navigation">{['WORKSPACE', 'ANALYSIS', 'SECURITY'].map((group) => <div className="nav-group" key={group}><p className="nav-heading">{group}</p>{pages.filter((page) => page.group === group).map((page) => { const Icon = icons[page.id]; return <button key={page.id} className={`nav-link ${page.id === activePage ? 'active' : ''}`} onClick={() => setPage(page.id)} aria-current={page.id === activePage ? 'page' : undefined}><Icon size={17} /><span>{page.label}</span>{page.id === activePage && <span className="active-dot" />}</button> })}</div>)}</nav>
      <div className="sidebar-bottom"><button className="demo-button" onClick={() => void runDemo()} disabled={demoBusy}><Play size={14}/>{demoBusy ? 'Running demo…' : 'Run Demo Story'}</button><button className="help-link" onClick={() => setHelp(true)}><CircleHelp size={16}/> Help & shortcuts <span>?</span></button><div className="profile"><div className="avatar">A</div><div><strong>Local workspace</strong><small>{automaton.states.length} states in machine</small></div><button className="icon-button" title={darkMode ? 'Switch to light theme' : 'Switch to dark theme'} onClick={toggleTheme}>{darkMode ? <Sun size={17} /> : <Moon size={17} />}</button></div></div>
    </aside>
    <main className="main-area">
      <header className="topbar"><div className="breadcrumbs"><span>Workspace</span><ArrowRight size={13} /><strong>{selected.label}</strong></div><div className="top-actions"><span className="save-status"><Check size={14} /> Local workspace</span><button className="icon-button" aria-label="Open command palette" title="Command palette (Ctrl+K)" onClick={() => { setPalette(true); setPaletteIndex(0) }}><Command size={17}/></button><button className="icon-button" aria-label="Learn about this page" title="Learn about this page" onClick={() => setLearn((open) => !open)}><BookOpen size={17}/></button><button className="icon-button shortcut-button" aria-label="Keyboard shortcuts" title="Keyboard shortcuts (Ctrl+/)" onClick={() => setHelp(true)}><Keyboard size={17} /></button></div></header>
      <div className="content-wrap"><motion.div key={activePage} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.22 }}>
        <div className="page-eyebrow"><span className="eyebrow-line" /> FINITE AUTOMATA WORKBENCH <span className="version-chip">BETA</span></div>
        <div className="page-heading-row"><div><h1>{selected.label}</h1><p className="page-subtitle">Design, explore, and reason about formal languages.</p></div><div className="page-actions">{automaton.states.length > 0 && <><button className="button button-secondary" onClick={() => { setPage('simulator'); notify('Automaton opened in Simulator') }}><Play size={14}/> Simulator</button><button className="button button-secondary" onClick={() => setPage('transform')}><GitFork size={14}/> Transform</button><button className="button button-secondary" onClick={() => { useAppStore.getState().setEquivalenceSeedFromBuilder(true); setPage('equivalence') }}><Network size={14}/> Equivalence</button></>}<button className="button button-primary" onClick={() => { if (activePage === 'builder') setAutomaton({ type: 'DFA', states: [], alphabet: [], transitions: [] }); else setPage('builder') }}><Plus size={17} /> {activePage === 'builder' ? 'New automaton' : 'Open builder'}</button></div></div>
        <ErrorBoundary><Suspense fallback={<LoadingSkeleton label={`Loading ${selected.label}`}/>}>{activePage === 'builder' ? <AutomataBuilder /> : activePage === 'simulator' ? <AutomataSimulator /> : activePage === 'transform' ? <TransformWorkspace /> : activePage === 'equivalence' ? <EquivalenceWorkspace /> : activePage === 'regex' ? <RegexWorkspace /> : activePage === 'lexer' ? <LexerWorkspace /> : activePage === 'validator' ? <HttpValidatorWorkspace /> : <SecurityWorkspace />}</Suspense></ErrorBoundary>
      </motion.div><footer className="workspace-footer"><span><span className="online-dot" /> Local workspace</span><span>Automata Studio <b>·</b> 0.2.0</span></footer></div>
    </main>
    {learn && <aside className="learn-panel" aria-label={`${selected.label} theory`}><div className="learn-heading"><div><span className="inspector-kicker">LEARN</span><h2>{theory[activePage].title}</h2></div><button className="icon-button" aria-label="Close Learn panel" onClick={() => setLearn(false)}><X size={17}/></button></div>{theory[activePage].paragraphs.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}<small>Concept notes · Automata Studio</small></aside>}
    {palette && <div className="overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setPalette(false) }}><section ref={dialogRef} className="command-palette" role="dialog" aria-modal="true" aria-label="Command palette"><div className="palette-input"><Search size={17}/><input ref={paletteRef} aria-label="Search pages" placeholder="Jump to a page…" value={paletteQuery} onChange={(event) => { setPaletteQuery(event.target.value); setPaletteIndex(0) }} onKeyDown={(event) => { if (event.key === 'ArrowDown') { event.preventDefault(); setPaletteIndex((index) => Math.min(index + 1, filteredPages.length - 1)) } else if (event.key === 'ArrowUp') { event.preventDefault(); setPaletteIndex((index) => Math.max(index - 1, 0)) } else if (event.key === 'Enter' && filteredPages[paletteIndex]) { setPage(filteredPages[paletteIndex].id); setPalette(false) } }}/><kbd>ESC</kbd></div><div className="palette-results">{filteredPages.map((page, index) => <button key={page.id} className={index === paletteIndex ? 'selected' : ''} onMouseEnter={() => setPaletteIndex(index)} onClick={() => { setPage(page.id); setPalette(false) }}>{page.label}<span>{page.group}</span></button>)}{!filteredPages.length && <p>No matching pages.</p>}</div><small>Use ↑ ↓ to browse · Enter to open</small></section></div>}
    {help && <div className="overlay" onMouseDown={(event) => { if (event.target === event.currentTarget) setHelp(false) }}><section ref={dialogRef} className="modal-card" role="dialog" aria-modal="true" aria-labelledby="shortcuts-title"><div className="modal-heading"><h2 id="shortcuts-title">Keyboard shortcuts</h2><button className="icon-button" aria-label="Close shortcuts" onClick={() => setHelp(false)}><X size={17}/></button></div><dl className="shortcut-list"><div><dt>Open command palette</dt><dd>Ctrl / ⌘ + K</dd></div><div><dt>Show shortcuts</dt><dd>Ctrl / ⌘ + /</dd></div><div><dt>Close dialog or clear focus</dt><dd>Esc</dd></div><div><dt>Undo / redo in Builder</dt><dd>Ctrl / ⌘ + Z / Shift + Z</dd></div></dl></section></div>}
    {workspaceDialog && <div className="overlay"><form ref={(element) => { dialogRef.current = element }} className="modal-card" role="dialog" aria-modal="true" onSubmit={(event) => { event.preventDefault(); create(workspaceName, snapshot()); setWorkspaceDialog(false); setWorkspaceName(''); notify('New workspace created') }}><div className="modal-heading"><h2>New workspace</h2><button type="button" className="icon-button" aria-label="Close" onClick={() => setWorkspaceDialog(false)}><X size={17}/></button></div><label className="field-wrap"><span className="field-label">Workspace name</span><input autoFocus className="text-input" value={workspaceName} onChange={(event) => setWorkspaceName(event.target.value)} placeholder="e.g. HTTP request rules"/></label><button className="button button-primary" type="submit">Create workspace</button></form></div>}
    {tourStep !== null && <div ref={(element) => { dialogRef.current = element }} className="tour-card" role="dialog" aria-label="Getting started tour" aria-modal="true"><div className="modal-heading"><span className="inspector-kicker">GETTING STARTED · {tourStep + 1}/5</span><button className="icon-button" aria-label="Close tour" onClick={() => { setTourStep(null); localStorage.setItem('automata-studio-tour-v1', 'done') }}><X size={16}/></button></div><h2>{tour[tourStep][0]}</h2><p>{tour[tourStep][1]}</p><div className="tour-actions"><button className="button button-secondary" onClick={() => { setTourStep(null); localStorage.setItem('automata-studio-tour-v1', 'done') }}>Skip tour</button><button className="button button-primary" onClick={() => { if (tourStep === 4) { setPage(tourPages[tourStep]); setTourStep(null); localStorage.setItem('automata-studio-tour-v1', 'done') } else { setPage(tourPages[tourStep + 1]); setTourStep((step) => (step ?? 0) + 1) } }}>{tourStep === 4 ? 'Finish' : 'Next'}</button></div></div>}
    {demoMessage && <div className="demo-status" role="status"><span>{demoMessage}</span><button className="icon-button" aria-label="Dismiss demo status" onClick={() => setDemoMessage('')}><X size={15}/></button></div>}
  </div>
}

export default function App() { return <ToastProvider><Workspace /></ToastProvider> }
