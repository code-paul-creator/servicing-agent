<div align="center">

# 🔗 Ledger
### An End-to-End Card Servicing Agent

*Conversational resolution for fee reversals, credit-limit increases, and card replacements — with a verifiable, hash-chained audit trail on every decision, and a full-context handoff when a human is needed.*

**Prepared by Paulami Bhosle**

[![Live Demo](https://img.shields.io/badge/demo-live-4FD1AE?style=for-the-badge)](#)
[![Backend](https://img.shields.io/badge/backend-FastAPI%20%2B%20LangGraph-6C9CFF?style=for-the-badge)](#)
[![Audit](https://img.shields.io/badge/audit-hash--chained-F0A63B?style=for-the-badge)](#)

</div>

---

## What this is

Card issuers get the same three requests constantly — *"waive this fee," "raise my limit," "I lost my card."* Ledger resolves all three end-to-end inside a single conversation: it classifies intent, checks the request against versioned eligibility rules, executes the change, and confirms it — or, when a request falls outside policy, escalates with full context so a human agent never has to ask the member to repeat themselves.

Every decision along the way — classification, policy check, system call — is written to an **append-only, hash-chained audit ledger** before the corresponding action runs. The ledger isn't just a log you have to trust; it's independently re-verifiable, and the live demo lets you prove that yourself.

## Where to look

| | |
|---|---|
| 🖥️ **Live demo** | Chat interface + real-time audit ledger, side by side |
| 🧠 **Decision flow** | Classify → policy check → execute or escalate → confirm |
| 🔒 **Tamper detection** | Click *Verify chain integrity*, then *Simulate tamper*, then verify again — watch it get caught |
| 🏗️ **Backend architecture** | `backend/` — FastAPI + LangGraph state machine, policy engine, mock core-system connectors, unit-tested audit log |
| 📄 **Full write-up** | `project_description.pdf` — problem, architecture, classification algorithm, policy rules, evaluation plan |
| 🎞️ **Slides** | `presentation.pptx` |

## Try it in under a minute

1. Open the live demo link above.
2. Try one of the quick prompts: a fee reversal, a limit increase, a lost card, or a fraud claim — notice the last one escalates immediately instead of attempting auto-approval.
3. Watch the ledger fill in on the right as each decision happens, in real time, before the corresponding action executes.
4. Click **Verify chain integrity**, then **Simulate tamper**, then verify again.

## What makes the audit trail different

Each entry embeds the SHA-256 hash of the entry before it — the same tamper-evidence principle a blockchain relies on, applied to a single authoritative log instead of a distributed one, which is what a servicing audit trail actually needs. Alter any entry, even one written months earlier, and every hash after it breaks — caught by re-verification, not by trusting nobody touched the table.

## Architecture at a glance

```
Member message → Classify (rules + LLM) → Route → Policy check → Execute / Escalate → Confirm
                         │                              │                │
                         ▼                              ▼                ▼
                  audit: classification        audit: policy_decision   audit: tool_call / escalation
```

The model never holds authority to move money or change an account — it proposes an action; a separate, versioned policy engine approves or declines it; only then does a core-system connector execute it.
