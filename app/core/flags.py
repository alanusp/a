from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict


@dataclass(slots=True)
class FeatureFlagSet:
    root: Path
    _flags: Dict[str, object] = field(default_factory=dict)

    def load(self) -> None:
        self._flags.clear()
        if not self.root.exists():
            return
        for path in sorted(self.root.glob("*.json")):
            data = json.loads(path.read_text())
            for key, value in data.items():
                self._flags[key] = value

    def enabled(self, name: str) -> bool:
        if not self._flags:
            self.load()
        return bool(self._flags.get(name, False))

    def value(self, name: str, default: object | None = None) -> object | None:
        if not self._flags:
            self.load()
        return self._flags.get(name, default)

    def ensure(self, name: str) -> None:
        if not self.enabled(name):
            raise RuntimeError(f"Feature flag '{name}' must be enabled")


_FLAG_SET: FeatureFlagSet | None = None


def get_feature_flags(root: Path | None = None) -> FeatureFlagSet:
    global _FLAG_SET
    if _FLAG_SET is None:
        location = root or Path("flags")
        _FLAG_SET = FeatureFlagSet(location)
    return _FLAG_SET
