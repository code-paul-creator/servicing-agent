"""Fee reversal resolution flow: gather -> propose ActionRequest -> (policy+execute happen in graph.py)."""
from __future__ import annotations

from ..core_systems import CoreCardSystem
from ..models import ActionRequest


def build_action_request(member_id: str, entities: dict, core: CoreCardSystem) -> ActionRequest | None:
    fee_type = entities.get("fee_type", "late_fee")
    fee = core.get_recent_fee(member_id, fee_type)
    if not fee:
        return None
    return ActionRequest(type="reverse_fee", params={"fee_type": fee_type, "amount": fee["amount"]})


def missing_info(entities: dict) -> list[str]:
    # fee_type defaults to "late_fee" if unspecified in this scaffold; a fuller
    # implementation would ask which fee when the account has more than one type.
    return []
