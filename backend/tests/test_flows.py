from datetime import date, timedelta

from app.core_systems import Account
from app.models import ActionRequest
from app import policy


def make_account(**overrides):
    base = dict(
        member_id="m1",
        account_open_date=date.today() - timedelta(days=540),
        credit_limit=5000.0,
        available_credit=4200.0,
        late_payments_last_12mo=0,
        fees_last_12mo=[],
    )
    base.update(overrides)
    return Account(**base)


def test_fee_reversal_auto_approved_under_ceiling():
    account = make_account()
    action = ActionRequest(type="reverse_fee", params={"fee_type": "late_fee", "amount": 35.0})
    decision = policy.evaluate(account, action)
    assert decision.approved and decision.auto_approved


def test_fee_reversal_escalates_over_ceiling():
    account = make_account()
    action = ActionRequest(type="reverse_fee", params={"fee_type": "late_fee", "amount": 250.0})
    decision = policy.evaluate(account, action)
    assert not decision.approved
    assert decision.escalation_reason == "fee_amount_over_auto_approval_ceiling"


def test_limit_increase_escalates_for_new_account():
    account = make_account(account_open_date=date.today() - timedelta(days=30))
    action = ActionRequest(type="increase_limit", params={"new_limit": 5500.0})
    decision = policy.evaluate(account, action)
    assert not decision.approved
    assert decision.escalation_reason == "account_too_new"


def test_limit_increase_auto_approved_within_cap():
    account = make_account()
    action = ActionRequest(type="increase_limit", params={"new_limit": 6000.0})  # 20% increase
    decision = policy.evaluate(account, action)
    assert decision.approved and decision.auto_approved
