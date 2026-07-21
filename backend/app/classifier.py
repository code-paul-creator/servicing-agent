"""
Two-stage classification:
1. A cheap rules pass catches unambiguous, high-frequency phrasings without an
   API call (lower latency and cost for the majority of traffic).
2. Anything the rules pass doesn't confidently match goes to the LLM, which
   returns a strict JSON object: intent, confidence, entities, reasoning.

Routing threshold: confidence < 0.6 -> agent asks a clarifying question instead
of guessing; the graph (not this module) owns that decision.

Uses the Gemini API (google-genai SDK). Set GEMINI_API_KEY in the environment
(get one from Google AI Studio: https://aistudio.google.com/apikey).
"""
from __future__ import annotations

import json
import os
import re

from google import genai
from google.genai import types

from .models import ClassificationResult, Intent

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
_client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))

_RULES: list[tuple[re.Pattern, Intent]] = [
    (re.compile(r"\b(waive|reverse|refund)\b.*\bfee\b", re.I), Intent.FEE_REVERSAL),
    (re.compile(r"\bfee\b.*\b(waive|reverse|refund|remove)\b", re.I), Intent.FEE_REVERSAL),
    (re.compile(r"\b(increase|raise|higher)\b.*\b(limit|credit line)\b", re.I), Intent.CREDIT_LIMIT_INCREASE),
    (re.compile(r"\b(lost|stolen|damaged|broken)\b.*\bcard\b", re.I), Intent.CARD_REPLACEMENT),
    (re.compile(r"\breplace(ment)?\b.*\bcard\b", re.I), Intent.CARD_REPLACEMENT),
]

_SYSTEM_PROMPT = """You are the intent classifier for a credit card servicing agent.
Classify the member's message into exactly one of:
fee_reversal, credit_limit_increase, card_replacement, escalate, unknown

"escalate" = fraud, disputes over $ amounts the member disputes, threats of legal
action, complaints about a human agent, or anything explicitly requesting a person.
"unknown" = doesn't fit any category or is a general question.

Extract any entities mentioned (fee_type, amount, requested_limit, reason, expedite).

Respond with ONLY valid JSON, no markdown fences, no preamble:
{"intent": "...", "confidence": 0.0-1.0, "entities": {}, "reasoning": "one sentence"}
"""


def _rules_pass(message: str) -> ClassificationResult | None:
    for pattern, intent in _RULES:
        if pattern.search(message):
            return ClassificationResult(
                intent=intent, confidence=0.9, entities={}, reasoning=f"Matched rule pattern for {intent.value}."
            )
    return None


def classify(message: str, conversation_context: str = "") -> ClassificationResult:
    rule_hit = _rules_pass(message)
    if rule_hit:
        return rule_hit

    response = _client.models.generate_content(
        model=GEMINI_MODEL,
        contents=f"Conversation so far:\n{conversation_context}\n\nLatest message: {message}",
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM_PROMPT,
            max_output_tokens=300,
            temperature=0.2,
            response_mime_type="application/json",
        ),
    )
    text = (response.text or "").strip()
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        data = json.loads(text)
        return ClassificationResult(**data)
    except Exception:
        return ClassificationResult(intent=Intent.UNKNOWN, confidence=0.0, entities={}, reasoning="Classifier parse failure; routed to fallback.")
