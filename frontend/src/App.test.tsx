import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { Button, Card, TextInput } from './components/ui'
import { useAppStore } from './store/appStore'

vi.mock('./components/AutomataWorkspace', () => ({
  AutomataBuilder: () => <div>Your canvas is ready</div>,
  AutomataSimulator: () => <div>Trace the machine</div>,
}))

describe('Automata Studio shell', () => {
  beforeEach(() => { localStorage.setItem('automata-studio-tour-v1', 'done'); localStorage.setItem('automata-studio-theme', 'dark'); useAppStore.setState({ darkMode: true }) })
  afterEach(() => useAppStore.setState({ activePage: 'builder', equivalenceSeedFromBuilder: false }))
  it('shows the builder empty state and navigation pages', async () => {
    render(<App />)
    expect(screen.getByRole('heading', { name: 'Automata Builder' })).toBeInTheDocument()
    expect(await screen.findByText('Your canvas is ready')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /HTTP Validator/ })).toBeInTheDocument()
  })

  it('switches to the simulator page from the sidebar', async () => {
    render(<App />)
    fireEvent.click(within(screen.getByRole('navigation', { name: 'Main navigation' })).getByRole('button', { name: /Simulator/ }))
    expect(screen.getByRole('heading', { name: 'Simulator' })).toBeInTheDocument()
    expect(await screen.findByText('Trace the machine')).toBeInTheDocument()
  })

  it('opens the command palette with Ctrl+K and jumps to a filtered page', async () => {
    render(<App />)
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true })
    const search = screen.getByRole('textbox', { name: 'Search pages' })
    fireEvent.change(search, { target: { value: 'Equivalence' } })
    fireEvent.keyDown(search, { key: 'Enter' })
    expect(await screen.findByRole('heading', { name: 'Do these rules accept the same language?' })).toBeInTheDocument()
  })

  it('opens a page specific Learn panel', () => {
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Learn about this page' }))
    expect(screen.getByRole('complementary', { name: 'Automata Builder theory' })).toBeInTheDocument()
    expect(screen.getByText(/finite automaton is a graph/i)).toBeInTheDocument()
  })

  it('makes the workspace switcher useful when only one workspace exists', () => {
    render(<App />)
    const selector = screen.getByRole('combobox', { name: 'Saved workspace' })
    expect(within(selector).getByRole('option', { name: 'My Workspace' })).toBeInTheDocument()
    expect(within(selector).getByRole('option', { name: '＋ Create workspace…' })).toBeInTheDocument()
    fireEvent.change(selector, { target: { value: '__create__' } })
    expect(screen.getByRole('heading', { name: 'New workspace' })).toBeInTheDocument()
  })

  it('shows the first-time tour on an opaque high-contrast card', () => {
    localStorage.removeItem('automata-studio-tour-v1')
    render(<App />)
    expect(screen.getByRole('dialog', { name: 'Getting started tour' })).toHaveClass('tour-card')
    expect(screen.getByRole('heading', { name: 'Build a machine' })).toBeInTheDocument()
  })

  it('switches between light and dark mode and remembers the choice', async () => {
    render(<App />)
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe('dark'))
    fireEvent.click(screen.getByRole('button', { name: 'Switch to light mode' }))
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe('light'))
    expect(localStorage.getItem('automata-studio-theme')).toBe('light')
    expect(screen.getByRole('button', { name: 'Switch to dark mode' })).toBeInTheDocument()
  })

  it('exposes accessible reusable design primitives', () => {
    render(<><Card aria-label="Settings"><Button variant="primary">Save</Button><TextInput label="Alphabet" hint="Use symbols or classes." /></Card></>)
    expect(screen.getByRole('region', { name: 'Settings' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save' })).toHaveClass('button-primary')
    expect(screen.getByLabelText('Alphabet')).toHaveAttribute('aria-describedby', 'alphabet-hint')
  })
})
