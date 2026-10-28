"""Security analysis HTTP API routes."""

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.automata.security import DEFENSE_DISCLAIMER, SECURITY_RULES, analyze_request_security, diff_security_rules

router = APIRouter(prefix="/api/security", tags=["security-analyzer"])


class SecurityAnalyzePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rawRequest: str = Field(max_length=2_000_000)
    customRules: list[dict[str, Any]] = Field(default_factory=list)


class RuleDiffPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    oldPattern: str = Field(min_length=1, max_length=256)
    newPattern: str = Field(min_length=1, max_length=256)
    testPayloads: list[str] = Field(default_factory=list)


@router.get("/rules")
def get_security_rules() -> dict[str, Any]:
    """Return the active library of security detection rules and the defense disclaimer."""
    return {
        "rules": SECURITY_RULES,
        "defenseDisclaimer": DEFENSE_DISCLAIMER,
    }


@router.post("/analyze")
async def analyze_security_endpoint(request: Request) -> dict[str, Any]:
    """Analyze an HTTP request for security vulnerabilities and injection patterns."""
    body = await request.body()
    if len(body) > 2_000_000:
        raise HTTPException(status_code=413, detail="Request text exceeds the 2 MB limit.")

    try:
        if "application/json" in request.headers.get("content-type", ""):
            payload = SecurityAnalyzePayload.model_validate(json.loads(body))
        else:
            payload = SecurityAnalyzePayload(rawRequest=body.decode("utf-8"))
        return analyze_request_security(payload.rawRequest, custom_rules=payload.customRules)
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError) as error:
        raise HTTPException(
            status_code=400,
            detail="Provide valid UTF-8 request text or a SecurityAnalyzePayload JSON object.",
        ) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/rule-diff")
def diff_rules_endpoint(payload: RuleDiffPayload) -> dict[str, Any]:
    """Compare two security regex patterns using the Equivalence Checker."""
    try:
        return diff_security_rules(payload.oldPattern, payload.newPattern, test_payloads=payload.testPayloads or None)
    except Exception as error:
        raise HTTPException(status_code=400, detail=f"Failed to compare rule patterns: {error}") from error
