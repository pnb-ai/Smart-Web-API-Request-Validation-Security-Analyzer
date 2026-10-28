import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { Automaton } from '../types/automata'

export interface SavedWorkspace {
  id: string
  name: string
  updatedAt: string
  automaton: Automaton
  regexes: string[]
  requests: string[]
}

interface WorkspaceState {
  activeId: string
  workspaces: SavedWorkspace[]
  save: (data: Pick<SavedWorkspace, 'automaton' | 'regexes' | 'requests'>) => void
  create: (name: string, data: Pick<SavedWorkspace, 'automaton' | 'regexes' | 'requests'>) => void
  load: (id: string) => SavedWorkspace | undefined
  importWorkspace: (value: unknown) => SavedWorkspace
}

const createId = () => `workspace-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
const isAutomaton = (value: unknown): value is Automaton => {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Partial<Automaton>
  if (!['DFA', 'NFA', 'EPSILON_NFA'].includes(candidate.type || '') || !Array.isArray(candidate.states) || !Array.isArray(candidate.alphabet) || !Array.isArray(candidate.transitions)) return false
  const ids = new Set(candidate.states.map((state) => state && typeof state.id === 'string' ? state.id : ''))
  return candidate.alphabet.every((symbol) => typeof symbol === 'string') &&
    candidate.states.every((state) => state && typeof state.id === 'string' && state.id.length > 0 && typeof state.label === 'string' && typeof state.isStart === 'boolean' && typeof state.isAccepting === 'boolean' && Number.isFinite(state.x) && Number.isFinite(state.y)) &&
    ids.size === candidate.states.length &&
    candidate.transitions.every((edge) => edge && ids.has(edge.from) && ids.has(edge.to) && Array.isArray(edge.symbols) && edge.symbols.every((symbol) => typeof symbol === 'string'))
}

export const useWorkspaceStore = create<WorkspaceState>()(persist((set, get) => ({
  activeId: 'default',
  workspaces: [{ id: 'default', name: 'My Workspace', updatedAt: new Date(0).toISOString(), automaton: { type: 'DFA', states: [], alphabet: [], transitions: [] }, regexes: [], requests: [] }],
  save: (data) => set((state) => {
    const current = state.workspaces.find((workspace) => workspace.id === state.activeId)
    const saved: SavedWorkspace = { ...data, id: state.activeId, name: current?.name || 'My Workspace', updatedAt: new Date().toISOString() }
    return { workspaces: [...state.workspaces.filter((workspace) => workspace.id !== state.activeId), saved] }
  }),
  create: (name, data) => {
    const workspace: SavedWorkspace = { ...data, id: createId(), name: name.trim() || 'Untitled Workspace', updatedAt: new Date().toISOString() }
    set((state) => ({ activeId: workspace.id, workspaces: [...state.workspaces, workspace] }))
  },
  load: (id) => {
    const workspace = get().workspaces.find((item) => item.id === id)
    if (workspace) set({ activeId: id })
    return workspace
  },
  importWorkspace: (value) => {
    const candidate = value as Partial<SavedWorkspace>
    if (!candidate || !isAutomaton(candidate.automaton) || !Array.isArray(candidate.regexes) || !candidate.regexes.every((item) => typeof item === 'string') || !Array.isArray(candidate.requests) || !candidate.requests.every((item) => typeof item === 'string')) {
      throw new Error('This file is not a valid Automata Studio workspace.')
    }
    const workspace: SavedWorkspace = { id: createId(), name: typeof candidate.name === 'string' ? candidate.name : 'Imported Workspace', updatedAt: new Date().toISOString(), automaton: candidate.automaton, regexes: candidate.regexes, requests: candidate.requests }
    set((state) => ({ activeId: workspace.id, workspaces: [...state.workspaces, workspace] }))
    return workspace
  },
}), { name: 'automata-studio-workspaces', version: 1 }))
