import { useEffect } from 'react'
import { motion } from 'framer-motion'
import { ArrowRight, Binary, Braces, Check, ChevronDown, CircleHelp, GitFork, Keyboard, Moon, Network, Play, Plus, Regex, ScanSearch, ShieldCheck, Sun, Workflow } from 'lucide-react'
import { pages, useAppStore } from './store/appStore'
import { ToastProvider, useToast } from './components/ToastProvider'
import { AutomataBuilder, AutomataSimulator } from './components/AutomataWorkspace'
import { useAutomataStore } from './store/automataStore'
import { TransformWorkspace } from './components/TransformWorkspace'

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
          <div className="page-heading-row"><div><h1>{selected.label}</h1><p className="page-subtitle">Design, explore, and reason about formal languages.</p></div><button className="button button-primary" onClick={() => { if (activePage === 'builder') useAutomataStore.getState().setAutomaton({ type: 'DFA', states: [], alphabet: [], transitions: [] }); else setPage('builder') }}><Plus size={17} /> {activePage === 'builder' ? 'New automaton' : 'Open builder'}</button></div>
          {activePage === 'builder' ? <AutomataBuilder /> : activePage === 'simulator' ? <AutomataSimulator /> : activePage === 'transform' ? <TransformWorkspace /> : <PlaceholderPage page={selected.label} />}
        </motion.div>
        <footer className="workspace-footer"><span><span className="online-dot" /> Local workspace</span><span>Automata Studio <b>·</b> 0.1.0</span></footer>
      </div>
    </main>
  </div>
}

function PlaceholderPage({ page }: { page: string }) {
  return <section className="placeholder-card"><div className="placeholder-icon"><Workflow size={25} /></div><span className="placeholder-tag">COMING UP</span><h2>{page} is ready for its feature</h2><p>This workspace is set up. The tools for this page will be added feature by feature.</p></section>
}

export default function App() { return <ToastProvider><Workspace /></ToastProvider> }
