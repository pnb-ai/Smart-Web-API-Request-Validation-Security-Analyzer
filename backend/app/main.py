from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.automata.routes import router as automata_router, transform_router

app = FastAPI(
    title="Smart Web/API Request Validation & Security Analyzer",
    version="0.1.0",
    description="API for automata-based request validation and security analysis.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(automata_router)
app.include_router(transform_router)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    """Report that the API process is ready to accept requests."""
    return {"status": "ok"}
