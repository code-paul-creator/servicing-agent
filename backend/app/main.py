"""FastAPI entrypoint exposing the chat and audit endpoints."""
from __future__ import annotations

from fastapi import FastAPI, HTTPException

from .audit import audit_log
from .graph import run_turn
from .models import ChatResponse, ChatTurn

app = FastAPI(title="Card Servicing Agent")

# session_id -> rolling transcript, for classifier context
_transcripts: dict[str, list[str]] = {}
DEMO_MEMBER_ID = "member_demo"


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
