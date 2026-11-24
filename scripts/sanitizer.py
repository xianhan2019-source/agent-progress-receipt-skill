# -*- coding: utf-8 -*-
"""
Deterministic Layer-2 Privacy Sanitizer.
Redacts API keys, tokens, PII, home directory paths, and auth query parameters.
"""

import re
from typing import Iterable

DEFAULT_SENSITIVE_KEYWORDS = (
    "password",
    "private_key",
    "secret_key",
    "密码",
    "银行卡",
    "身份证",
    "病历",
    "体检",
)

_REDACT_PATTERNS = [
    (re.compile(r"nvapi-[A-Za-z0-9_-]+"), "[REDACTED_KEY]"),
    (re.compile(r"sk-[A-Za-z0-9_-]{12,}"), "[REDACTED_KEY]"),
    (re.compile(r"AIza[0-9A-Za-z_-]{20,}"), "[REDACTED_KEY]"),
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"), "[REDACTED_KEY]"),
    (re.compile(r"Bearer\s+[A-Za-z0-9._-]+", re.IGNORECASE), "Bearer [REDACTED]"),
    (
        re.compile(
            r"(?i)\b(password|passwd|pwd|secret|token|api_key|apikey|cookie)\s*[:=]\s*[\"']?[^\s\"',;]+[\"']?"
        ),
        r"\1=[REDACTED]",
    ),
    (re.compile(r"(?i)([?&](?:token|key|auth|sig|password|secret)=)[^&\s]+"), r"\1[REDACTED]"),
    (re.compile(r"[A-Za-z]:\\Users\\[^\\\s\"'`]+"), r"[REDACTED_USER_PATH]"),
    (re.compile(r"/(?:home|Users)/[^/\s\"'`]+"), r"/[REDACTED_USER_PATH]"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[REDACTED_EMAIL]"),
    (re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "[REDACTED_PHONE]"),
    (re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"), "[REDACTED_ID]"),
    (re.compile(r"(?i)(qq|群|号)[:：\s]*\d{5,11}"), r"\1:[REDACTED_ID]"),
]


def sanitize_text(text: str) -> str:
    if not text:
        return ""
    cleaned = text
    for pattern, repl in _REDACT_PATTERNS:
        cleaned = pattern.sub(repl, cleaned)
    return cleaned


def is_sensitive_turn(text: str, keywords: Iterable[str] = DEFAULT_SENSITIVE_KEYWORDS) -> bool:
    if not text:
        return False
    lower = text.lower()
    return any(str(kw).lower() in lower for kw in keywords)
