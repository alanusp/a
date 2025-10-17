from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.flags import FeatureFlagSet


def test_feature_flag_gate(tmp_path: Path) -> None:
    flags_dir = tmp_path / "flags"
    flags_dir.mkdir()
    (flags_dir / "rollout.json").write_text(json.dumps({"new_schema": True, "traffic.candidate_pct": 12.5}))
    flag_set = FeatureFlagSet(flags_dir)
    assert flag_set.enabled("new_schema") is True
    assert flag_set.value("traffic.candidate_pct") == 12.5
    with pytest.raises(RuntimeError):
        flag_set.ensure("missing")
