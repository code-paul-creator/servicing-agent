"""Credit limit increase resolution flow."""
from __future__ import annotations

from ..core_systems import CoreCardSystem
from ..models import ActionRequest


def build_action_request(member_id: str, entities: dict, core: CoreCardSystem) -> ActionRequest | None:
    requested = entities.get("requested_limit")
    if requested is None:
        return None
    account = core.get_account(member_id)
    return ActionRequest(
        type="increase_limit",
        params={"new_limit": float(requested), "current_limit": account.credit_limit},
    )


def missing_info(entities: dict) -> list[str]:
    missing = []
    if entities.get("requested_limit") is None:
        missing.append("requested_limit")
    return missing
