# Project Rules

1. Build feature by feature. Never implement features I did not ask for yet.
2. All automata algorithms live in the backend (`/backend/app/automata`) as pure, well-tested Python functions. The frontend only renders and calls APIs.
3. Every algorithm returns both its result and a step-by-step `trace` (list of steps with a title, explanation in plain English, and the data needed to visualize it) so the UI can animate it.
4. Automata JSON schema (single source of truth, define in Pydantic and mirror in TypeScript): `{ type: "DFA"|"NFA"|"EPSILON_NFA", states: [{id,label,isStart,isAccepting,x,y}], alphabet: string[], transitions: [{from,to,symbols:string[]}] }`. Epsilon is the symbol `ε`.
5. Use symbol classes (e.g. `DIGIT`, `ALPHA`, `TCHAR`, `SP`, `CRLF`) in addition to single characters, so diagrams stay readable instead of 256-edge graphs. Backend must expand classes correctly when simulating/converting.
6. Every feature needs pytest/Vitest tests. Run them and fix failures before saying you are done.
7. UI quality bar: dark/light theme, smooth animations, clear empty states, helpful tooltips, keyboard shortcuts, responsive layout, no raw error dumps (friendly error messages).
8. Keep code typed, small modules, no dead code, meaningful comments that explain the theory.
