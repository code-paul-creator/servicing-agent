"""FastAPI entrypoint exposing the chat, audit, and Gemini-proxy endpoints."""
from __future__ import annotations

import os

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from google.genai import types
from pydantic import BaseModel

from .audit import audit_log
from .graph import run_turn
from .models import ChatResponse, ChatTurn

app = FastAPI(title="Card Servicing Agent")

# Set ALLOWED_ORIGINS on your host (e.g. Render) to your exact frontend origin,
# e.g. "https://code-paul-creator.github.io" -- no trailing slash, no path.
# Comma-separate multiple origins. Defaults to "*" only for local dev.
_raw_origins = os.environ.get("ALLOWED_ORIGINS", "*")
_allowed_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# session_id -> rolling transcript, for classifier context
_transcripts: dict[str, list[str]] = {}
DEMO_MEMBER_ID = "member_demo"


@app.get("/health")
def health():
    return {"status": "ok", "allowed_origins": _allowed_origins}


@app.post("/chat", response_model=ChatResponse)
def chat(turn: ChatTurn) -> ChatResponse:
    context = "\n".join(_transcripts.get(turn.session_id, [])[-6:])
    response = run_turn(turn.session_id, DEMO_MEMBER_ID, turn.message, context)
    _transcripts.setdefault(turn.session_id, []).append(f"member: {turn.message}")
    _transcripts[turn.session_id].append(f"agent: {response.reply}")
    return response


@app.get("/audit/{session_id}")
def get_audit(session_id: str):
    return [e.to_dict() for e in audit_log.get_chain(session_id)]


@app.get("/audit/{session_id}/verify")
def verify_audit(session_id: str):
    valid, broken_id = audit_log.verify(session_id)
    if not valid:
        raise HTTPException(status_code=409, detail={"valid": False, "broken_entry": broken_id})
    return {"valid": True, "entries": len(audit_log.get_chain(session_id))}


# ---------------------------------------------------------------------------
# Gemini proxy -- lets the static demo (servicing-agent-demo.html) call the
# model without ever holding the real GEMINI_API_KEY. The browser sends its
# messages here instead of to generativelanguage.googleapis.com directly;
# this service attaches the real key server-side.
#
# PROXY_ACCESS_KEY is NOT a secret in the same sense as GEMINI_API_KEY -- it
# still ships to the browser and is visible to anyone who opens dev tools.
# What it buys you: you can rotate/revoke it independently of your billed
# Gemini key, rate-limit or disable it without touching Google Cloud, and it
# stops the endpoint being trivially scraped by bots crawling for open
# proxies. It is a speed bump, not a security boundary -- if you need a real
# boundary, put this behind real auth (API keys per client, OAuth, etc.).
# ---------------------------------------------------------------------------
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
_proxy_access_key = os.environ.get("PROXY_ACCESS_KEY", "")
_gemini_client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))


class GenerateMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class GenerateRequest(BaseModel):
    system: str
    messages: list[GenerateMessage]


class GenerateResponse(BaseModel):
    text: str


@app.post("/api/generate", response_model=GenerateResponse)
def generate(req: GenerateRequest, x_proxy_key: str = Header(default="")):
    if _proxy_access_key and x_proxy_key != _proxy_access_key:
        raise HTTPException(status_code=401, detail="invalid or missing X-Proxy-Key header")

    contents = [
        {"role": "model" if m.role == "assistant" else "user", "parts": [{"text": m.content}]}
        for m in req.messages
    ]
    response = _gemini_client.models.generate_content(
        model=GEMINI_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=req.system,
            max_output_tokens=500,
            temperature=0.4,
        ),
    )
    return GenerateResponse(text=response.text or "")
