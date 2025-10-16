#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.model_guard import ModelGuard


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate model and calibrator drift")
    parser.add_argument("--threshold", type=float, default=None)
    parser.add_argument("--json", action="store_true", help="Emit JSON report")
    args = parser.parse_args()

    guard = ModelGuard(threshold=args.threshold)
    report = guard.evaluate()
    payload = {
        "cosine_similarity": report.cosine_similarity,
        "bias_delta": report.bias_delta,
        "calibrator_delta": report.calibrator_delta,
        "threshold": report.threshold,
        "within_bounds": report.within_bounds,
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(
            "cosine={:.6f} bias_delta={:.6f} calibrator_delta={:.6f} threshold={:.4f}".format(
                report.cosine_similarity,
                report.bias_delta,
                report.calibrator_delta,
                report.threshold,
            )
        )
    if not report.within_bounds:
        sys.exit(1)


if __name__ == "__main__":
    main()
