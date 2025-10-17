from pathlib import Path

FILES = ["README.md", "SECURITY.md", "CODE_OF_CONDUCT.md"]


def test_docs_contain_maintainer_details() -> None:
    for filename in FILES:
        text = Path(filename).read_text(encoding="utf-8")
        assert "Alan Uriel Saavedra Pulido" in text
        assert "alanursapu@gmail.com" in text
