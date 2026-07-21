"""
Mock connectors standing in for real core-banking / card-processor APIs
(e.g. a card management platform, a fee/billing engine, a card-issuance
vendor). Each method is written as the seam where a real integration would
plug in — swap the body for an HTTP call to the actual system and nothing
above this layer needs to change.
"""
from __future__ import annotations

import random
import string
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional


@dataclass
class Account:
    member_id: str
    account_open_date: date
    credit_limit: float
    available_credit: float
    late_payments_last_12mo: int
    fees_last_12mo: list[dict]
    card_status: str = "active"
    card_last4: str = "4321"


class CoreCardSystem:
    """Deterministic mock backend so the demo is reproducible."""

    def __init__(self) -> None:
        self._accounts: dict[str, Account] = {
            "member_demo": Account(
                member_id="member_demo",
                account_open_date=date.today() - timedelta(days=540),
                credit_limit=5000.0,
                available_credit=4200.0,
                late_payments_last_12mo=0,
                fees_last_12mo=[],
            )
        }

    def get_account(self, member_id: str) -> Account:
        if member_id not in self._accounts:
            raise KeyError(f"unknown member {member_id}")
        return self._accounts[member_id]

    # --- Fee reversal -----------------------------------------------------
    def get_recent_fee(self, member_id: str, fee_type: str) -> Optional[dict]:
        acct = self.get_account(member_id)
        matches = [f for f in acct.fees_last_12mo if f["type"] == fee_type and not f.get("reversed")]
        return matches[-1] if matches else None

    def reverse_fee(self, member_id: str, fee_type: str, amount: float) -> dict:
        acct = self.get_account(member_id)
        for f in acct.fees_last_12mo:
            if f["type"] == fee_type and not f.get("reversed"):
                f["reversed"] = True
        acct.available_credit += amount
        return {"member_id": member_id, "fee_type": fee_type, "amount": amount, "status": "reversed"}

    # --- Credit limit increase --------------------------------------------
    def increase_limit(self, member_id: str, new_limit: float) -> dict:
        acct = self.get_account(member_id)
        delta = new_limit - acct.credit_limit
        acct.credit_limit = new_limit
        acct.available_credit += delta
        return {"member_id": member_id, "new_limit": new_limit, "status": "applied"}

    # --- Card replacement ---------------------------------------------------
    def replace_card(self, member_id: str, reason: str, expedite: bool) -> dict:
        acct = self.get_account(member_id)
        acct.card_status = "replacement_ordered"
        acct.card_last4 = "".join(random.choices(string.digits, k=4))
        eta_days = 2 if expedite else 7
        return {
            "member_id": member_id,
            "reason": reason,
            "expedite": expedite,
            "new_card_last4": acct.card_last4,
            "eta_days": eta_days,
            "status": "ordered",
        }


core_system = CoreCardSystem()
# Seed one recent fee for the demo account so a fee-reversal flow has something to act on.
core_system.get_account("member_demo").fees_last_12mo.append(
    {"type": "late_fee", "amount": 35.0, "date": str(date.today() - timedelta(days=6)), "reversed": False}
)
