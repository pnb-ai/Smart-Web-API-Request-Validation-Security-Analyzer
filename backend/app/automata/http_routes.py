"""HTTP request validation API."""

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.automata.http_validator import validate_http_request
from app.automata.openapi_contract import validate_openapi_contract

router = APIRouter(prefix="/api/http", tags=["http-validation"])


class HttpValidationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rawRequest: str = Field(max_length=2_000_000)
    maxRequestLine: int = Field(default=8000, ge=1, le=65536)
    maxHeaderSection: int = Field(default=65536, ge=1, le=1_000_000)
    customRules: dict[str, Any] = Field(default_factory=dict)


class OpenApiValidationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rawRequest: str = Field(max_length=2_000_000)
    openApiSpec: str | dict[str, Any]
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


@router.post("/validate-contract")
async def validate_openapi_endpoint(request: Request) -> dict[str, Any]:
    """Validate an HTTP message against an uploaded OpenAPI 3.x contract."""
    body = await request.body()
    if len(body) > 3_100_000:
        raise HTTPException(status_code=413, detail="Request and OpenAPI contract exceed the 3.1 MB limit.")
    try:
        payload = OpenApiValidationPayload.model_validate(json.loads(body))
        spec_size = len(payload.openApiSpec.encode("utf-8")) if isinstance(payload.openApiSpec, str) else len(json.dumps(payload.openApiSpec).encode("utf-8"))
        if spec_size > 1_000_000:
            raise HTTPException(status_code=413, detail="OpenAPI contract is limited to 1 MB.")
        return validate_openapi_contract(payload.rawRequest, payload.openApiSpec, max_request_line=payload.maxRequestLine, max_header_section=payload.maxHeaderSection, custom_rules=payload.customRules)
    except HTTPException:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError) as error:
        raise HTTPException(status_code=400, detail="Provide a valid JSON object containing rawRequest and openApiSpec.") from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
