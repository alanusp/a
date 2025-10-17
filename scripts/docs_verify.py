#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

REQUIRED_IMAGES = [
    "console_light.png",
    "console_dark.png",
    "openapi.png",
    "predict_call.png",
]
STRICT_IMAGES = REQUIRED_IMAGES + ["pipeline.png"]
CONTACT_FILES = [
    Path("README.md"),
    Path("SECURITY.md"),
    Path("CODE_OF_CONDUCT.md"),
]
NAME = "Alan Uriel Saavedra Pulido"
EMAIL = "alanursapu@gmail.com"


def ensure_screenshots(strict: bool) -> None:
    expected = STRICT_IMAGES if strict else REQUIRED_IMAGES
    for image in expected:
        path = Path("docs/assets") / image
        if not path.exists():
            if strict and image == "pipeline.png":
                raise SystemExit("strict mode requires pipeline screenshot")
            if not strict and image == "pipeline.png":  # pragma: no cover - defensive
                continue
            raise SystemExit(f"missing screenshot: {path}")
        size = path.stat().st_size
        if size <= 51200:
            raise SystemExit(f"screenshot {path} too small: {size} bytes")


def ensure_contacts() -> None:
    for file in CONTACT_FILES:
        text = file.read_text(encoding="utf-8")
        if NAME not in text or EMAIL not in text:
            raise SystemExit(f"contact info missing from {file}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify documentation assets")
    parser.add_argument("--strict", action="store_true", help="Require pipeline screenshot")
    args = parser.parse_args()
    ensure_screenshots(strict=args.strict)
    ensure_contacts()
    print("docs verified")


if __name__ == "__main__":
    main()
