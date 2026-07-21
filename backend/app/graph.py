"""
State graph: classify -> route -> (gather_info | resolve | escalate) -> respond.

Written against LangGraph's StateGraph API. Every node writes to the audit log
before it hands off, so the trail reflects the decision sequence even for
turns that end in a clarifying question rather than an action.
"""
from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from . import core_systems, policy
from .audit import audit_log
from .classifier import classify
from .flows import card_replacement, fee_reversal, limit_increase
from .models import ActionRequest, ChatResponse, Intent

FLOW_BUILDERS = {
    Intent.FEE_REVERSAL: fee_reversal,
    Intent.CREDIT_LIMIT_INCREASE: limit_increase,
    Intent.CARD_REPLACEMENT: card_replacement,
}

CONFIDENCE_THRESHOLD = 0.6


class AgentState(TypedDict, total=False):
    session_id: str
    member_id: str
    message: str
    conversation_context: str
    entities: dict[str, Any]
    intent: Intent
    action: ActionRequest | None
    resolved: bool
    escalated: bool
    reply: str


def node_classify(state: AgentState) -> AgentState:
    result = classify(state["message"], state.get("conversation_context", ""))
    audit_log.append(
        state["session_id"], "classification", "agent",
        {"intent": result.intent.value, "confidence": result.confidence, "reasoning": result.reasoning},
    )
    state["intent"] = result.intent
    state["entities"] = {**state.get("entities", {}), **result.entities}
    if result.confidence < CONFIDENCE_THRESHOLD:
        state["intent"] = Intent.UNKNOWN
    return state


def node_route(state: AgentState) -> str:
    intent = state["intent"]
    if intent == Intent.ESCALATE:
        return "escalate"
    if intent in FLOW_BUILDERS:
        return "resolve"
    return "clarify"


def node_resolve(state: AgentState) -> AgentState:
    flow = FLOW_BUILDERS[state["intent"]]
    missing = flow.missing_info(state["entities"])
    if missing:
        audit_log.append(state["session_id"], "clarification_needed", "agent", {"missing": missing})
        state["reply"] = f"I just need a bit more info: {', '.join(missing)}."
        return state

    action = flow.build_action_request(state["member_id"], state["entities"], core_systems.core_system)
    if action is None:
        state["reply"] = "I couldn't find a matching item on your account for that request — let me connect you with a specialist."
        state["escalated"] = True
        audit_log.append(state["session_id"], "escalation", "agent", {"reason": "no_matching_account_item"})
        return state

    audit_log.append(state["session_id"], "action_proposed", "agent", {"action": action.model_dump()})
    account = core_systems.core_system.get_account(state["member_id"])
    decision = policy.evaluate(account, action)
    audit_log.append(state["session_id"], "policy_decision", "policy_engine", decision.model_dump())

    if not decision.approved:
        state["escalated"] = True
        audit_log.append(state["session_id"], "escalation", "agent", {"reason": decision.escalation_reason})
        state["reply"] = (
            f"This one needs a specialist's sign-off ({decision.reason}). "
            "I'm handing this off with everything we've discussed so they don't have to ask you again."
        )
        return state

    result = _execute(state["member_id"], action)
    audit_log.append(state["session_id"], "tool_call", f"core_system:{action.type}", {"action": action.model_dump(), "result": result})
    state["resolved"] = True
    state["action"] = action
    state["reply"] = result["member_facing_summary"]
    return state


def _execute(member_id: str, action: ActionRequest) -> dict:
    core = core_systems.core_system
    if action.type == "reverse_fee":
        r = core.reverse_fee(member_id, action.params["fee_type"], action.params["amount"])
        return {**r, "member_facing_summary": f"Done — I've reversed the ${r['amount']:.2f} {r['fee_type'].replace('_', ' ')} and it'll reflect on your account right away."}
    if action.type == "increase_limit":
        r = core.increase_limit(member_id, action.params["new_limit"])
        return {**r, "member_facing_summary": f"Your credit limit is now ${r['new_limit']:,.2f}, effective immediately."}
    if action.type == "replace_card":
        r = core.replace_card(member_id, action.params["reason"], action.params["expedite"])
        eta = "2 business days" if r["expedite"] else "5-7 business days"
        return {**r, "member_facing_summary": f"Your replacement card ending in {r['new_card_last4']} is on its way — arriving in about {eta}."}
    raise ValueError(f"unknown action type {action.type}")


def node_clarify(state: AgentState) -> AgentState:
    audit_log.append(state["session_id"], "clarification_needed", "agent", {"reason": "low_confidence_or_unmatched_intent"})
    state["reply"] = "I want to make sure I route this correctly — could you tell me a bit more about what you need help with (a fee, your credit limit, or a replacement card)?"
    return state


def node_escalate(state: AgentState) -> AgentState:
    state["escalated"] = True
    audit_log.append(state["session_id"], "escalation", "agent", {"reason": "explicit_escalation_intent"})
    state["reply"] = "I'm connecting you with a specialist now and passing along everything we've covered so you won't have to repeat yourself."
    return state


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("classify", node_classify)
    graph.add_node("resolve", node_resolve)
    graph.add_node("clarify", node_clarify)
    graph.add_node("escalate", node_escalate)

    graph.set_entry_point("classify")
    graph.add_conditional_edges("classify", node_route, {"resolve": "resolve", "clarify": "clarify", "escalate": "escalate"})
    graph.add_edge("resolve", END)
    graph.add_edge("clarify", END)
    graph.add_edge("escalate", END)
    return graph.compile()


compiled_graph = build_graph()


def run_turn(session_id: str, member_id: str, message: str, conversation_context: str = "") -> ChatResponse:
    audit_log.append(session_id, "message", "member", {"text": message})
    state: AgentState = {
        "session_id": session_id,
        "member_id": member_id,
        "message": message,
        "conversation_context": conversation_context,
        "entities": {},
    }
    final_state = compiled_graph.invoke(state)
    return ChatResponse(
        reply=final_state.get("reply", ""),
        intent=final_state.get("intent"),
        resolved=final_state.get("resolved", False),
        escalated=final_state.get("escalated", False),
    )
