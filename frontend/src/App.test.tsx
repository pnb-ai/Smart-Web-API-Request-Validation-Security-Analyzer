import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import App from './App'
import { Button, Card, TextInput } from './components/ui'

describe('Automata Studio shell', () => {
  it('shows the builder empty state and navigation pages', () => {
    render(<App />)
    expect(screen.getByRole('heading', { name: 'Automata Builder' })).toBeInTheDocument()
    expect(screen.getByText('Your canvas is ready')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /HTTP Validator/ })).toBeInTheDocument()
  })

  it('switches to a placeholder page from the sidebar', () => {
    render(<App />)
    fireEvent.click(within(screen.getByRole('navigation', { name: 'Main navigation' })).getByRole('button', { name: /Simulator/ }))
    expect(screen.getByRole('heading', { name: 'Simulator' })).toBeInTheDocument()
    expect(screen.getByText('Simulator is ready for its feature')).toBeInTheDocument()
  })

  it('exposes accessible reusable design primitives', () => {
    render(<><Card aria-label="Settings"><Button variant="primary">Save</Button><TextInput label="Alphabet" hint="Use symbols or classes." /></Card></>)
    expect(screen.getByRole('region', { name: 'Settings' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save' })).toHaveClass('button-primary')
    expect(screen.getByLabelText('Alphabet')).toHaveAttribute('aria-describedby', 'alphabet-hint')
  })
})
