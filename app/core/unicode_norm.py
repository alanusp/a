from __future__ import annotations

import re
import re
import unicodedata
from typing import Iterable

from app.core.idna import IDNAError, canonicalise_email


CONFUSABLE_SCRIPTS = ("CYRILLIC", "GREEK", "FULLWIDTH", "ARABIC")


def normalize_identifier(value: str) -> str:
    return unicodedata.normalize("NFC", value.strip())


def canonical_email(value: str) -> str:
    value = normalize_identifier(value)
    try:
        result = canonicalise_email(value)
        return result.canonical.lower()
    except IDNAError:
        if "@" not in value:
            return value.lower()
        local, domain = value.split("@", 1)
        return f"{local.strip().lower()}@{domain.strip().lower()}"


def canonical_phone(value: str) -> str:
    digits = re.sub(r"\D", "", normalize_identifier(value))
    if not digits:
        return ""
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("0") and len(digits) > 1:
        digits = digits[1:]
    return "+" + digits


def has_homoglyphs(value: str) -> bool:
    normalized = normalize_identifier(value)
    for char in normalized:
        if ord(char) < 128:
            continue
        name = unicodedata.name(char, "")
        if any(tag in name for tag in CONFUSABLE_SCRIPTS):
            return True
    return False


def normalize_fields(payload: dict[str, object], fields: Iterable[str]) -> dict[str, object]:
    result = dict(payload)
    for field in fields:
        raw = payload.get(field)
        if isinstance(raw, str):
            result[field] = normalize_identifier(raw)
    return result
