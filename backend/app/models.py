"""Shared data contracts for the servicing agent."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class Intent(str, Enum):
    FEE_REVERSAL = "fee_reversal"
    CREDIT_LIMIT_INCREASE = "credit_limit_increase"
    CARD_REPLACEMENT = "card_replacement"
    ESCALATE = "escalate"
    UNKNOWN = "unknown"


class ClassificationResult(BaseModel):
    intent: Intent
    confidence: float = Field(ge=0.0, le=1.0)
    entities: dict[str, Any] = Field(default_factory=dict)
    reasoning: str


class ActionRequest(BaseModel):
    """What the agent proposes to do. Never executed directly by the LLM."""
    type: str  # "reverse_fee" | "increase_limit" | "replace_card"
    params: dict[str, Any]


class PolicyDecision(BaseModel):
    approved: bool
    auto_approved: bool
    reason: str
    escalation_reason: Optional[str] = None


class ActionResult(BaseModel):
    success: bool
    detail: dict[str, Any]
    member_facing_summary: str


class Escalation(BaseModel):
    session_id: str
    reason: str
    intent: Intent
    conversation_summary: str
    entities: dict[str, Any]
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ChatTurn(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    reply: str
    intent: Optional[Intent] = None
    resolved: bool = False
    escalated: bool = False
    audit_entry_ids: list[str] = Field(default_factory=list)
