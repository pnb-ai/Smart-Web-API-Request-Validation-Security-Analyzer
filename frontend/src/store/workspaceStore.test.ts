import { beforeEach, describe, expect, it } from 'vitest'
import { useWorkspaceStore } from './workspaceStore'

const empty = { type: 'DFA' as const, states: [], alphabet: [], transitions: [] }

describe('saved workspaces', () => {
  beforeEach(() => {
    localStorage.removeItem('automata-studio-workspaces')
    useWorkspaceStore.setState({ activeId: 'default', workspaces: [{ id: 'default', name: 'My Workspace', updatedAt: new Date(0).toISOString(), automaton: empty, regexes: [], requests: [] }] })
  })

  it('saves and loads automata, regexes, and requests', () => {
    const store = useWorkspaceStore.getState()
    store.create('HTTP rules', { automaton: { ...empty, alphabet: ['TCHAR'] }, regexes: ['[A-Z]+'], requests: ['GET / HTTP/1.1'] })
    const workspace = useWorkspaceStore.getState().workspaces.at(-1)!
    expect(workspace.name).toBe('HTTP rules')
    expect(workspace.regexes).toEqual(['[A-Z]+'])
    useWorkspaceStore.getState().load('default')
    expect(useWorkspaceStore.getState().load(workspace.id)?.requests).toEqual(['GET / HTTP/1.1'])
  })

  it('rejects malformed workspace imports and accepts valid JSON shape', () => {
    expect(() => useWorkspaceStore.getState().importWorkspace({ name: 'broken' })).toThrow(/valid Automata Studio workspace/i)
    const imported = useWorkspaceStore.getState().importWorkspace({ name: 'shared', automaton: empty, regexes: ['a*'], requests: [] })
    expect(imported.name).toBe('shared')
    expect(useWorkspaceStore.getState().activeId).toBe(imported.id)
  })
})
