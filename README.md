# Smart Web/API Request Validation & Security Analyzer

An Automata Theory project for building, simulating, transforming and comparing finite automata, then applying them to HTTP request validation.

## Security Analyzer limitations

The Security Analyzer compiles detection patterns through the Regex Lab engine and checks requests after up to two URL-decoding passes, case folding, and whitespace normalization. These automata-based filters are a first line of defense only. They do not replace parameterized database queries, context-appropriate output encoding, input validation, or other application security controls. A clean result is not proof that a request or application is safe, and findings should be reviewed in context.

## Stack

- **Frontend:** React, TypeScript, Vite, Tailwind CSS, React Flow, Framer Motion, Zustand, Vitest
- **Backend:** Python 3.11+, FastAPI, Pydantic, pytest
- **Layout:** `frontend/` and `backend/` monorepo

## Run locally

### Frontend

```bash
npm install
npm run dev
```

Vite serves the app at http://localhost:5173.

### Backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

The API health check is at http://localhost:8000/health and interactive API docs are at http://localhost:8000/docs.

### Checks

```bash
npm test
npm run build
cd backend && pytest
```

The backend allows the Vite development origin at `http://localhost:5173`. Automata algorithms are intentionally added feature by feature in `backend/app/automata`.
