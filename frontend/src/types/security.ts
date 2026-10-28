import type { Automaton, TraceStep } from './automata'

export type SeverityLevel = 'low' | 'medium' | 'high' | 'critical'

export interface PositionInfo {
  offset: number
  length: number
  line: number
  column: number
  section: string
}

export interface SecurityFinding {
  id: string
  ruleId: string
  ruleName: string
  category: string
  severity: SeverityLevel
  matchedText: string
  position: PositionInfo | null
  explanation: string
  recommendedFix: string
  normalizationStep: 'raw' | 'url_decode_1' | 'url_decode_2' | 'lowercase' | 'collapse_whitespace'
  automatonId: string | null
}

export interface NormalizationStep {
  step: string
  label: string
  description: string
}

export interface NormalizationEvent {
  ruleId: string
  section: string
  stage: string
  stageLabel: string
  match: string
}

export interface SecurityReport {
  status: 'CLEAN' | 'LOW_RISK' | 'SUSPICIOUS' | 'MALICIOUS'
  riskScore: number
  findings: SecurityFinding[]
  findingsSummary: {
    critical: number
    high: number
    medium: number
    low: number
    total: number
  }
  categoriesDetected: string[]
  normalizationSteps: NormalizationStep[]
  normalizationTrace: NormalizationEvent[]
  automata: Record<string, Automaton>
  trace: TraceStep[]
  defenseDisclaimer: string
  requestParts: {
    method: string
    target: string
    version: string
    headers: Record<string, string>
    hasBody: boolean
    bodyLength: number
  }
}

export interface PayloadEvaluation {
  payload: string
  blockedByOld: boolean
  blockedByNew: boolean
  behavior: 'blocked_by_both' | 'allowed_by_both' | 'newly_blocked' | 'newly_allowed'
}

export interface RuleDiffResult {
  equivalent: boolean
  counterexample: string | null
  oldPattern: string
  newPattern: string
  oldDfa: Automaton
  newDfa: Automaton
  leftSubsetRight: boolean
  payloadEvaluations: PayloadEvaluation[]
  trace: TraceStep[]
}
