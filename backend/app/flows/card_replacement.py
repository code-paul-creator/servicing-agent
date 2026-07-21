"""Card replacement resolution flow."""
from __future__ import annotations

from ..core_systems import CoreCardSystem
from ..models import ActionRequest

VALID_REASONS = {"lost", "stolen", "damaged", "expired", "other"}


def build_action_request(member_id: str, entities: dict, core: CoreCardSystem) -> ActionRequest | None:
    reason = entities.get("reason")
    if reason not in VALID_REASONS:
        return None
    return ActionRequest(
        type="replace_card",
        params={"reason": reason, "expedite": bool(entities.get("expedite", reason == "stolen"))},
    )


def missing_info(entities: dict) -> list[str]:
    missing = []
    if entities.get("reason") not in VALID_REASONS:
        missing.append("reason")
    return missing
