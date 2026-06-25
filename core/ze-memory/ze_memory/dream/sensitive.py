from __future__ import annotations

import re
from typing import Any

_FINANCIAL_ENTITY_TYPES = frozenset({"account", "bank", "card", "financial"})
_HEALTH_ENTITY_TYPES = frozenset({"health", "medical", "condition", "medication"})
_CREDENTIAL_ENTITY_TYPES = frozenset({"credential", "password", "secret", "token", "api_key"})

_FINANCIAL_KEYWORDS = re.compile(
    r"\b(bank|iban|swift|credit\s*card|debit\s*card|account\s*number|routing\s*number|"
    r"salary|invoice|tax\s*id|ssn|social\s*security|cpf|nif|vat)\b",
    re.IGNORECASE,
)
_HEALTH_KEYWORDS = re.compile(
    r"\b(diagnosis|medication|prescription|symptom|allergy|condition|therapy|"
    r"hospital|clinic|doctor|patient|mental\s*health|depression|anxiety)\b",
    re.IGNORECASE,
)
_CREDENTIAL_KEYWORDS = re.compile(
    r"\b(password|passwd|api[_\s-]?key|secret|token|private\s*key|"
    r"access\s*key|auth\s*code|otp|2fa|mfa)\b",
    re.IGNORECASE,
)


def is_sensitive_entity(
    entity_type: str,
    canonical_name: str,
    attrs: dict[str, Any] | None = None,
) -> bool:
    et = (entity_type or "").strip().lower()
    if et in _FINANCIAL_ENTITY_TYPES | _HEALTH_ENTITY_TYPES | _CREDENTIAL_ENTITY_TYPES:
        return True

    text = canonical_name or ""
    if attrs:
        for value in attrs.values():
            if isinstance(value, str):
                text = f"{text} {value}"

    if _FINANCIAL_KEYWORDS.search(text):
        return True
    if _HEALTH_KEYWORDS.search(text):
        return True
    if _CREDENTIAL_KEYWORDS.search(text):
        return True
    return False
