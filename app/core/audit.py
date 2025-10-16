from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Iterable, List, Sequence

from app.core.config import get_settings
from app.core.json_canonical import canonicalize

def _hash_pair(left: str, right: str) -> str:
    return sha256((left + right).encode("utf-8")).hexdigest()


def _merkle_root(hashes: Sequence[str]) -> str:
    if not hashes:
        return sha256(b"").hexdigest()
    level: List[str] = list(hashes)
    while len(level) > 1:
        next_level: List[str] = []
        for index in range(0, len(level), 2):
            left = level[index]
            right = level[index + 1] if index + 1 < len(level) else left
            next_level.append(_hash_pair(left, right))
        level = next_level
    return level[0]


@dataclass(frozen=True, slots=True)
class ProofElement:
    position: str
    hash: str


class MerkleLedger:
    """Append-only Merkle ledger with deterministic anchoring."""

    def __init__(self, ledger_path: Path | None = None, anchor_path: Path | None = None) -> None:
        settings = get_settings()
        self.ledger_path = ledger_path or Path(os.getenv("AUDIT_LEDGER_PATH", settings.audit_ledger_path))
        self.anchor_path = anchor_path or Path(os.getenv("AUDIT_ANCHOR_PATH", settings.audit_anchor_path))
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self.anchor_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._entries: list[dict[str, object]] = []
        self._load()

    # ------------------------------ persistence -----------------------------
    def _load(self) -> None:
        if not self.ledger_path.exists():
            return
        with self.ledger_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                payload = json.loads(line)
                self._entries.append(payload)

    def _persist(self, entry: dict[str, object]) -> None:
        with self.ledger_path.open("a", encoding="utf-8") as handle:
            handle.write(canonicalize(entry) + "\n")

    # ------------------------------ public api ------------------------------
    def append(self, *, event_id: str, payload: dict[str, object]) -> dict[str, object]:
        with self._lock:
            timestamp = datetime.now(timezone.utc).isoformat()
            entry = {
                "index": len(self._entries),
                "event_id": event_id,
                "payload": payload,
                "timestamp": timestamp,
            }
            canonical = canonicalize(entry)
            entry["hash"] = sha256(canonical.encode("utf-8")).hexdigest()
            self._entries.append(entry)
            self._persist(entry)
            self._write_anchor()
            return entry

    def root(self) -> str:
        with self._lock:
            hashes = [str(entry["hash"]) for entry in self._entries]
        return _merkle_root(hashes)

    def proof(self, event_id: str) -> list[ProofElement]:
        with self._lock:
            indexes = {entry["event_id"]: idx for idx, entry in enumerate(self._entries)}
            if event_id not in indexes:
                raise KeyError(f"event {event_id} not found")
            index = indexes[event_id]
            hashes = [str(entry["hash"]) for entry in self._entries]
        proof: list[ProofElement] = []
        level = hashes
        idx = index
        while len(level) > 1:
            is_right = idx % 2 == 1
            sibling_index = idx - 1 if is_right else idx + 1
            if sibling_index >= len(level):
                sibling_hash = level[idx]
            else:
                sibling_hash = level[sibling_index]
            proof.append(ProofElement(position="left" if is_right else "right", hash=sibling_hash))
            idx //= 2
            next_level: list[str] = []
            for pointer in range(0, len(level), 2):
                left = level[pointer]
                right = level[pointer + 1] if pointer + 1 < len(level) else left
                next_level.append(_hash_pair(left, right))
            level = next_level
        return proof

    def verify(self, *, event: dict[str, object], proof: Iterable[ProofElement], root: str) -> bool:
        payload = dict(event)
        payload.pop("hash", None)
        canonical = canonicalize(payload)
        current = sha256(canonical.encode("utf-8")).hexdigest()
        for item in proof:
            if item.position == "left":
                current = _hash_pair(item.hash, current)
            else:
                current = _hash_pair(current, item.hash)
        return current == root

    def entry(self, event_id: str) -> dict[str, object]:
        with self._lock:
            for entry in self._entries:
                if entry["event_id"] == event_id:
                    return dict(entry)
        raise KeyError(f"event {event_id} not found")

    def _write_anchor(self) -> None:
        anchor_payload = {
            "root": self.root(),
            "entries": len(self._entries),
            "anchored_at": datetime.now(timezone.utc).isoformat(),
        }
        with self.anchor_path.open("w", encoding="utf-8") as handle:
            handle.write(canonicalize(anchor_payload))


def get_ledger() -> MerkleLedger:
    return MerkleLedger()
