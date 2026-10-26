from typing import Any

from pydantic import BaseModel, ConfigDict


class TraceStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    explanation: str
    data: dict[str, Any]
