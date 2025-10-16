"""IDNA utilities to canonicalise and validate identifiers."""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass


class IDNAError(ValueError):
    """Raised when an identifier fails canonicalisation or validation."""


@dataclass
class CanonicalResult:
    original: str
    canonical: str


def _script(character: str) -> str:
    if not character.isalpha():
        return "COMMON"
    try:
        name = unicodedata.name(character)
    except ValueError:
        return "UNKNOWN"
    for prefix in ("LATIN", "CYRILLIC", "GREEK", "ARABIC", "HEBREW", "DEVANAGARI", "CJK", "HIRAGANA", "KATAKANA"):
        if prefix in name:
            return prefix
    return "COMMON"


def _normalise(value: str) -> str:
    return unicodedata.normalize("NFC", value.strip())


def canonicalise_domain(domain: str) -> CanonicalResult:
    normalised = _normalise(domain)
    if not normalised:
        raise IDNAError("empty domain")
    scripts = { _script(ch) for ch in normalised if ch not in {".", "-"} }
    scripts.discard("COMMON")
    if len(scripts) > 1:
        raise IDNAError("mixed-script domain rejected")
    try:
        ascii_domain = normalised.encode("idna").decode("ascii")
    except UnicodeError as exc:  # pragma: no cover - defensive
        raise IDNAError("idna encoding failed") from exc
    return CanonicalResult(original=domain, canonical=ascii_domain.lower())


def canonicalise_email(email: str) -> CanonicalResult:
    normalised = _normalise(email)
    if "@" not in normalised:
        raise IDNAError("invalid email")
    local, domain = normalised.split("@", 1)
    domain_result = canonicalise_domain(domain)
    local_scripts = { _script(ch) for ch in local if ch.isalpha() }
    local_scripts.discard("COMMON")
    if len(local_scripts) > 1:
        raise IDNAError("mixed-script local part rejected")
    return CanonicalResult(original=email, canonical=f"{local}@{domain_result.canonical}")
