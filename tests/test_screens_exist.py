from pathlib import Path

import pytest

SCREENSHOTS = [
    "console_light.png",
    "console_dark.png",
    "openapi.png",
    "predict_call.png",
]


@pytest.mark.parametrize("name", SCREENSHOTS)
def test_screenshot_exists_and_large(name: str) -> None:
    path = Path("docs/assets") / name
    assert path.exists(), f"missing {path}"
    size = path.stat().st_size
    assert size > 50_000, f"{path} too small: {size} bytes"
