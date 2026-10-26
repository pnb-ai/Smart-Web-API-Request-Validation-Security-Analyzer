import { useEffect } from 'react'
import { motion } from 'framer-motion'
import { Activity, ArrowDownRight, ArrowRight, Binary, Braces, Check, ChevronDown, CircleHelp, Command, GitFork, Keyboard, Moon, Network, Play, Plus, Regex, ScanSearch, ShieldCheck, Sun, Workflow } from 'lucide-react'
import { pages, useAppStore } from './store/appStore'
import { ToastProvider, useToast } from './components/ToastProvider'

const icons = { builder: Workflow, simulator: Play, transform: GitFork, equivalence: Network, regex: Regex, lexer: Braces, validator: ShieldCheck, security: ScanSearch }

function Workspace() {
  const { activePage, darkMode, setPage, toggleTheme } = useAppStore()
  const { notify } = useToast()
  const selected = pages.find((page) => page.id === activePage)!
  useEffect(() => { document.documentElement.dataset.theme = darkMode ? 'dark' : 'light' }, [darkMode])
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); setPage('builder') }
      if (event.key === 'Escape') document.activeElement instanceof HTMLElement && document.activeElement.blur()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [setPage])

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark"><Binary size={21} /></div><div><strong>Automata<span>Studio</span></strong><small>FORMAL SYSTEMS LAB</small></div></div>
      <button className="project-switcher" title="Choose a project"><div className="project-icon"><Network size={17} /></div><span><strong>Request Guard</strong><small>Personal workspace</small></span><ChevronDown size={15} /></button>
      <nav aria-label="Main navigation">
        {['WORKSPACE', 'ANALYSIS', 'SECURITY'].map((group) => <div className="nav-group" key={group}><p className="nav-heading">{group}</p>{pages.filter((page) => page.group === group).map((page) => {
          const Icon = icons[page.id]
          return <button key={page.id} className={`nav-link ${page.id === activePage ? 'active' : ''}`} onClick={() => setPage(page.id)}><Icon size={17} /><span>{page.label}</span>{page.id === activePage && <span className="active-dot" />}</button>
        })}</div>)}
      </nav>
      <div className="sidebar-bottom"><div className="usage-card"><div className="usage-title"><span>Workspace status</span><span className="status-pulse" /></div><strong>Ready to build</strong><div className="usage-track"><span /></div><small>Start by creating an automaton</small></div><button className="help-link" onClick={() => notify('Keyboard shortcut: Ctrl/⌘ + K returns to Automata Builder')}><CircleHelp size={16} /> Help & shortcuts <span>?</span></button><div className="profile"><div className="avatar">P</div><div><strong>Project workspace</strong><small>Local environment</small></div><button className="icon-button" title={darkMode ? 'Switch to light theme' : 'Switch to dark theme'} onClick={toggleTheme}>{darkMode ? <Sun size={17} /> : <Moon size={17} />}</button></div></div>
    </aside>
    <main className="main-area">
      <header className="topbar"><div className="breadcrumbs"><span>Workspace</span><ArrowRight size={13} /><strong>{selected.label}</strong></div><div className="top-actions"><span className="save-status"><Check size={14} /> All changes saved</span><button className="icon-button shortcut-button" title="Keyboard shortcuts" onClick={() => notify('Ctrl/⌘ + K: Automata Builder · Esc: clear focus')}><Keyboard size={17} /></button><button className="avatar avatar-small" title="Workspace profile">P</button></div></header>
      <div className="content-wrap">
        <motion.div key={activePage} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.22 }}>
          <div className="page-eyebrow"><span className="eyebrow-line" /> FINITE AUTOMATA WORKBENCH <span className="version-chip">BETA</span></div>
          <div className="page-heading-row"><div><h1>{selected.label}</h1><p className="page-subtitle">Design, explore, and reason about formal languages.</p></div><button className="button button-primary" onClick={() => notify('Automaton creation will be available in the builder feature.')}><Plus size={17} /> New automaton</button></div>
          {activePage === 'builder' ? <BuilderEmptyState onCreate={() => notify('Automaton creation will be available in the builder feature.')} onExample={() => notify('Example automata are coming in a later feature.')} /> : <PlaceholderPage page={selected.label} />}
        </motion.div>
        <footer className="workspace-footer"><span><span className="online-dot" /> Local workspace</span><span>Automata Studio <b>·</b> 0.1.0</span></footer>
      </div>
    </main>
  </div>
}

function BuilderEmptyState({ onCreate, onExample }: { onCreate: () => void; onExample: () => void }) {
  return <section className="builder-layout">
    <div className="canvas-card"><div className="canvas-toolbar"><div><span className="canvas-title">Untitled automaton</span><span className="draft-chip">DRAFT</span></div><div className="canvas-tools"><button className="icon-button" title="Automata canvas controls"><Command size={16} /></button><button className="button button-small" onClick={onCreate}><Plus size={15} /> Add state</button></div></div>
      <div className="canvas-empty"><div className="empty-orbit orbit-one" /><div className="empty-orbit orbit-two" /><div className="empty-visual"><div className="empty-node node-a" /><div className="empty-node node-b" /><div className="empty-node node-c" /><ArrowDownRight className="edge-arrow" size={36} /></div><h2>Your canvas is ready</h2><p>Add states and connect them to start<br className="desktop-break" /> modeling a finite automaton.</p><button className="button button-primary" onClick={onCreate}><Plus size={17} /> Create your first state</button><div className="canvas-hint"><Keyboard size={14} /> Tip: use <kbd>Space</kbd> to pan the canvas</div></div>
      <div className="canvas-legend"><span><i className="legend-start" /> Start state</span><span><i className="legend-accept" /> Accepting state</span><span className="legend-right">DFA <ChevronDown size={13} /></span></div>
    </div>
    <aside className="inspector-card"><div className="inspector-header"><div><span className="inspector-kicker">INSPECTOR</span><h3>Getting started</h3></div><button className="icon-button" title="Inspector help"><CircleHelp size={16} /></button></div><div className="inspector-divider"/><p className="inspector-copy">Your automaton properties and transition settings will appear here.</p><div className="getting-started"><div className="step-icon"><span>01</span></div><div><strong>Choose a model</strong><p>Start with a DFA, NFA, or ε-NFA.</p></div></div><div className="getting-started"><div className="step-icon"><span>02</span></div><div><strong>Add your states</strong><p>Mark start and accepting states.</p></div></div><div className="getting-started"><div className="step-icon"><span>03</span></div><div><strong>Define transitions</strong><p>Connect states with symbols.</p></div></div><div className="inspector-tip"><Activity size={16} /><p><strong>Need a starting point?</strong><br />Load an example automaton to explore the canvas.</p><button className="text-button" onClick={onExample}>Browse examples <ArrowRight size={14} /></button></div></aside>
  </section>
}

function PlaceholderPage({ page }: { page: string }) {
  return <section className="placeholder-card"><div className="placeholder-icon"><Workflow size={25} /></div><span className="placeholder-tag">COMING UP</span><h2>{page} is ready for its feature</h2><p>This workspace is set up. The tools for this page will be added feature by feature.</p></section>
}

export default function App() { return <ToastProvider><Workspace /></ToastProvider> }
