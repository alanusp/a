from __future__ import annotations

from app.core.unicode_norm import canonical_email, canonical_phone, has_homoglyphs, normalize_identifier


def test_email_phone_normalisation() -> None:
    assert canonical_email("USER@Example.COM") == "user@example.com"
    assert canonical_phone("(555) 123-4567") == "+5551234567"


def test_homoglyph_detection() -> None:
    suspicious = "pаypal"  # uses Cyrillic a
    assert has_homoglyphs(suspicious) is True
    assert normalize_identifier("abc") == "abc"
