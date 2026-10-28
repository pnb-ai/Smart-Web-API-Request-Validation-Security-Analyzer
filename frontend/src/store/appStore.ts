import { create } from 'zustand'

export const pages = [
  { id: 'builder', label: 'Automata Builder', group: 'WORKSPACE' },
  { id: 'simulator', label: 'Simulator', group: 'WORKSPACE' },
  { id: 'transform', label: 'Transform & Optimize', group: 'ANALYSIS' },
  { id: 'equivalence', label: 'Equivalence Checker', group: 'ANALYSIS' },
  { id: 'regex', label: 'Regex Lab', group: 'ANALYSIS' },
  { id: 'lexer', label: 'Lexer', group: 'ANALYSIS' },
  { id: 'validator', label: 'HTTP Validator', group: 'SECURITY' },
  { id: 'security', label: 'Security Analyzer', group: 'SECURITY' },
] as const

export type PageId = typeof pages[number]['id']
type AppState = { activePage: PageId; darkMode: boolean; regexDraft: string; requestDraft: string; equivalenceSeedFromBuilder: boolean; setEquivalenceSeedFromBuilder: (value: boolean) => void; setRegexDraft: (pattern: string) => void; setRequestDraft: (request: string) => void; setPage: (page: PageId) => void; toggleTheme: () => void }

export const useAppStore = create<AppState>((set) => ({
  activePage: 'builder',
  darkMode: true,
  regexDraft: '',
  requestDraft: '',
  equivalenceSeedFromBuilder: false,
  setEquivalenceSeedFromBuilder: (equivalenceSeedFromBuilder) => set({ equivalenceSeedFromBuilder }),
  setRegexDraft: (regexDraft) => set({ regexDraft }),
  setRequestDraft: (requestDraft) => set({ requestDraft }),
  setPage: (activePage) => set({ activePage }),
  toggleTheme: () => set((state) => ({ darkMode: !state.darkMode })),
}))
