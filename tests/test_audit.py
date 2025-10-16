from __future__ import annotations

from app.core.audit import MerkleLedger


def test_merkle_ledger_detects_tampering(tmp_path):
    ledger_path = tmp_path / "ledger.jsonl"
    anchor_path = tmp_path / "anchor.txt"
    ledger = MerkleLedger(ledger_path=ledger_path, anchor_path=anchor_path)

    ledger.append(event_id="tenant-trace-0000000000000001", payload={"value": 1})
    ledger.append(event_id="tenant-trace-0000000000000002", payload={"value": 2})

    root = ledger.root()
    entry = ledger.entry("tenant-trace-0000000000000001")
    proof = ledger.proof("tenant-trace-0000000000000001")

    assert ledger.verify(event=entry, proof=proof, root=root)

    tampered = dict(entry)
    tampered_payload = dict(tampered["payload"])  # type: ignore[index]
    tampered_payload["value"] = 99
    tampered["payload"] = tampered_payload

    assert not ledger.verify(event=tampered, proof=proof, root=root)
    assert anchor_path.exists()
