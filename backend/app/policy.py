"""
Business rules that decide whether a proposed action can be auto-approved.
Kept separate from the LLM and from the graph so compliance/risk can own and
version this file independently of the conversational layer.
"""
from __future__ import annotations

from datetime import date

from .core_systems import Account
from .models import ActionRequest, PolicyDecision

FEE_AUTO_APPROVE_CEILING = 100.0
FEE_REVERSALS_ALLOWED_PER_12MO = 1
LIMIT_INCREASE_AUTO_APPROVE_MAX_PCT = 0.25
MIN_ACCOUNT_AGE_DAYS_FOR_LIMIT_INCREASE = 365


def evaluate_fee_reversal(account: Account, action: ActionRequest) -> PolicyDecision:
    amount = action.params.get("amount", 0)
    already_reversed = sum(1 for f in account.fees_last_12mo if f.get("reversed"))

    if amount > FEE_AUTO_APPROVE_CEILING:
        return PolicyDecision(
            approved=False,
            auto_approved=False,
            reason=f"Fee amount ${amount:.2f} exceeds auto-approval ceiling of ${FEE_AUTO_APPROVE_CEILING:.2f}.",
            escalation_reason="fee_amount_over_auto_approval_ceiling",
        )
    if already_reversed >= FEE_REVERSALS_ALLOWED_PER_12MO:
        return PolicyDecision(
            approved=False,
            auto_approved=False,
            reason="Member has already received the maximum courtesy reversals in the last 12 months.",
            escalation_reason="fee_reversal_limit_reached",
        )
    return PolicyDecision(approved=True, auto_approved=True, reason="Within auto-approval policy.")


def evaluate_limit_increase(account: Account, action: ActionRequest) -> PolicyDecision:
    requested = action.params.get("new_limit", 0)
    account_age_days = (date.today() - account.account_open_date).days
    max_auto = account.credit_limit * (1 + LIMIT_INCREASE_AUTO_APPROVE_MAX_PCT)

    if account.late_payments_last_12mo > 0:
        return PolicyDecision(
            approved=False,
            auto_approved=False,
            reason="Late payments on file in the last 12 months.",
            escalation_reason="late_payment_history",
        )
    if account_age_days < MIN_ACCOUNT_AGE_DAYS_FOR_LIMIT_INCREASE:
        return PolicyDecision(
            approved=False,
            auto_approved=False,
            reason="Account younger than the 12-month minimum for self-serve increases.",
            escalation_reason="account_too_new",
        )
    if requested > max_auto:
        return PolicyDecision(
            approved=False,
            auto_approved=False,
            reason=f"Requested limit exceeds the {int(LIMIT_INCREASE_AUTO_APPROVE_MAX_PCT*100)}% auto-approval cap.",
            escalation_reason="requested_increase_over_cap",
        )
    return PolicyDecision(approved=True, auto_approved=True, reason="Within auto-approval policy.")


def evaluate_card_replacement(account: Account, action: ActionRequest) -> PolicyDecision:
    # Card replacement is low-risk and always available self-serve, unless the
    # account is already flagged (not modeled in this mock).
    return PolicyDecision(approved=True, auto_approved=True, reason="Card replacement always self-serve eligible.")


DISPATCH = {
    "reverse_fee": evaluate_fee_reversal,
    "increase_limit": evaluate_limit_increase,
    "replace_card": evaluate_card_replacement,
}


def evaluate(account: Account, action: ActionRequest) -> PolicyDecision:
    fn = DISPATCH.get(action.type)
    if not fn:
        return PolicyDecision(approved=False, auto_approved=False, reason="Unknown action type.", escalation_reason="unknown_action")
    return fn(account, action)
