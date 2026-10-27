import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import App from './App'
import { Button, Card, TextInput } from './components/ui'

vi.mock('./components/AutomataWorkspace', () => ({
  AutomataBuilder: () => <div>Your canvas is ready</div>,
  AutomataSimulator: () => <div>Trace the machine</div>,
}))

describe('Automata Studio shell', () => {
  it('shows the builder empty state and navigation pages', () => {
    render(<App />)
    expect(screen.getByRole('heading', { name: 'Automata Builder' })).toBeInTheDocument()
    expect(screen.getByText('Your canvas is ready')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /HTTP Validator/ })).toBeInTheDocument()
  })

  it('switches to the simulator page from the sidebar', () => {
    render(<App />)
    fireEvent.click(within(screen.getByRole('navigation', { name: 'Main navigation' })).getByRole('button', { name: /Simulator/ }))
    expect(screen.getByRole('heading', { name: 'Simulator' })).toBeInTheDocument()
    expect(screen.getByText('Trace the machine')).toBeInTheDocument()
  })

  it('exposes accessible reusable design primitives', () => {
    render(<><Card aria-label="Settings"><Button variant="primary">Save</Button><TextInput label="Alphabet" hint="Use symbols or classes." /></Card></>)
    expect(screen.getByRole('region', { name: 'Settings' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save' })).toHaveClass('button-primary')
    expect(screen.getByLabelText('Alphabet')).toHaveAttribute('aria-describedby', 'alphabet-hint')
  })
})
