from app.audit import AuditLog


def test_chain_links_correctly():
    log = AuditLog()
    log.append("s1", "message", "member", {"text": "hi"})
    log.append("s1", "classification", "agent", {"intent": "fee_reversal"})
    valid, broken = log.verify("s1")
    assert valid
    assert broken is None


def test_tamper_detected():
    log = AuditLog()
    e1 = log.append("s1", "message", "member", {"text": "hi"})
    log.append("s1", "classification", "agent", {"intent": "fee_reversal"})
    # simulate tampering with a stored entry's payload after the fact
    e1.payload["text"] = "hacked"
    valid, broken = log.verify("s1")
    assert not valid
    assert broken == e1.id
