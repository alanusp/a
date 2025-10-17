from __future__ import annotations

from pathlib import Path

from scripts import gen_scenarios


def test_scenario_generation_deterministic(tmp_path: Path) -> None:
    scenario_path = tmp_path / "scenario.yaml"
    scenario_path.write_text(
        """
{
  "name": "deterministic",
  "seed": 123,
  "volume": 3,
  "patterns": [
    {
      "type": "burst",
      "user_ids": ["u1"],
      "amount": 10,
      "probability": 0.8,
      "duration": 2
    }
  ],
  "label_lag_minutes": 15
}
""".strip(),
        encoding="utf-8",
    )
    data = gen_scenarios._load_scenario(scenario_path)
    events_a = gen_scenarios._synthesise(data)
    events_b = gen_scenarios._synthesise(data)
    assert events_a == events_b
