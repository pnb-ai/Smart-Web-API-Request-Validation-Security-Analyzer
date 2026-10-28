"""HTTP request validation API."""

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.automata.http_validator import validate_http_request

router = APIRouter(prefix="/api/http", tags=["http-validation"])


class HttpValidationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rawRequest: str = Field(max_length=2_000_000)
    maxRequestLine: int = Field(default=8000, ge=1, le=65536)
    maxHeaderSection: int = Field(default=65536, ge=1, le=1_000_000)
    customRules: dict[str, Any] = Field(default_factory=dict)


@router.post("/validate")
async def validate_http_endpoint(request: Request) -> dict[str, Any]:
    """Accept either raw text or a JSON object with validator settings."""
    body = await request.body()
    if len(body) > 2_000_000:
        raise HTTPException(status_code=413, detail="Request text exceeds the 2 MB limit.")
    try:
        if "application/json" in request.headers.get("content-type", ""):
            payload = HttpValidationPayload.model_validate(json.loads(body))
        else:
            payload = HttpValidationPayload(rawRequest=body.decode("utf-8"))
        return validate_http_request(payload.rawRequest, max_request_line=payload.maxRequestLine, max_header_section=payload.maxHeaderSection, custom_rules=payload.customRules)
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError) as error:
        raise HTTPException(status_code=400, detail="Provide valid UTF-8 request text or a validator JSON object.") from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
