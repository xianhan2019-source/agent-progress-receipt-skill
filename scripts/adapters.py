# -*- coding: utf-8 -*-
"""
Pluggable cross-agent transcript adapters (Antigravity, Claude Code, Markdown/OpenClaw).
"""

import glob
import json
import os
import re
import time
from datetime import date, datetime, timedelta, timezone
from typing import Iterable

from sanitizer import DEFAULT_SENSITIVE_KEYWORDS, is_sensitive_turn, sanitize_text


def _parse_iso_local(ts_str: str, tz: timezone) -> datetime | None:
    if not ts_str:
        return None
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(tz)
    except ValueError:
        return None


def _time_window(target_date: date, tz: timezone) -> tuple[datetime, datetime]:
    start = datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0, tzinfo=tz)
    return start, start + timedelta(days=1)


def _extract_user_request(content: str) -> str:
    m = re.search(r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", content, re.DOTALL)
    if m:
        text = m.group(1)
    else:
        text = re.sub(r"<ADDITIONAL_METADATA>.*?</ADDITIONAL_METADATA>", "", content, flags=re.DOTALL)
        text = re.sub(r"<USER_SETTINGS_CHANGE>.*?</USER_SETTINGS_CHANGE>", "", text, flags=re.DOTALL)
    return re.sub(r"\s+", " ", text).strip()[:300]


def harvest_antigravity(
    target_date: date,
    tz: timezone,
    source_glob: str | None = None,
    sensitive_keywords: Iterable[str] = DEFAULT_SENSITIVE_KEYWORDS,
) -> list[str]:
    pattern = os.path.expanduser(
        source_glob or "~/.gemini/antigravity/brain/*/.system_generated/logs/transcript.jsonl"
    )
    start, end = _time_window(target_date, tz)
    mtime_cutoff = time.time() - 72 * 3600
    entries: list[tuple[datetime, str]] = []

    for path in glob.glob(pattern):
        try:
            if os.path.getmtime(path) < mtime_cutoff:
                continue
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    step_type = obj.get("type")
                    if step_type not in ("USER_INPUT", "PLANNER_RESPONSE"):
                        continue
                    dt = _parse_iso_local(obj.get("created_at", ""), tz)
                    if dt is None or not (start <= dt < end):
                        continue
                    if step_type == "USER_INPUT" and obj.get("source") == "USER_EXPLICIT":
                        raw = _extract_user_request(obj.get("content") or "")
                        if raw and not is_sensitive_turn(raw, sensitive_keywords):
                            entries.append((dt, f"[{dt:%H:%M}] User: {sanitize_text(raw)}"))
                    elif step_type == "PLANNER_RESPONSE" and obj.get("content") and not obj.get("tool_calls"):
                        raw = re.sub(r"\s+", " ", str(obj.get("content"))).strip()[:150]
                        if raw and not is_sensitive_turn(raw, sensitive_keywords):
                            entries.append((dt, f"[{dt:%H:%M}] Outcome: {sanitize_text(raw)}"))
        except OSError:
            continue

    entries.sort(key=lambda x: x[0])
    return [t for _, t in entries[-60:]]


def harvest_claude_code(
    target_date: date,
    tz: timezone,
    source_glob: str | None = None,
    sensitive_keywords: Iterable[str] = DEFAULT_SENSITIVE_KEYWORDS,
) -> list[str]:
    pattern = os.path.expanduser(source_glob or "~/.claude/projects/*/*.jsonl")
    start, end = _time_window(target_date, tz)
    entries: list[tuple[datetime, str]] = []

    for path in glob.glob(pattern):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if obj.get("type") != "user":
                        continue
                    dt = _parse_iso_local(obj.get("timestamp", ""), tz)
                    if dt is None or not (start <= dt < end):
                        continue
                    msg = obj.get("message", {})
                    content = msg.get("content") if isinstance(msg, dict) else ""
                    if isinstance(content, list):
                        content = " ".join(
                            c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"
                        )
                    raw = re.sub(r"\s+", " ", str(content or "")).strip()[:300]
                    if raw and not is_sensitive_turn(raw, sensitive_keywords):
                        entries.append((dt, f"[{dt:%H:%M}] User: {sanitize_text(raw)}"))
        except OSError:
            continue

    entries.sort(key=lambda x: x[0])
    return [t for _, t in entries[-60:]]


def harvest_markdown(
    target_date: date,
    tz: timezone,
    source_glob: str | None = None,
    sensitive_keywords: Iterable[str] = DEFAULT_SENSITIVE_KEYWORDS,
) -> list[str]:
    pattern = os.path.expanduser(source_glob or "./logs/*.md")
    lines_out: list[str] = []
    date_str = target_date.isoformat()

    for path in sorted(glob.glob(pattern)):
        try:
            mtime_d = datetime.fromtimestamp(os.path.getmtime(path), tz=tz).date()
            if date_str not in os.path.basename(path) and mtime_d != target_date:
                continue
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for raw in f:
                    s = raw.strip()
                    if not s or s.startswith("#") or is_sensitive_turn(s, sensitive_keywords):
                        continue
                    lines_out.append(sanitize_text(s)[:240])
        except OSError:
            continue

    return lines_out[-60:]


ADAPTERS = {
    "antigravity": harvest_antigravity,
    "claude_code": harvest_claude_code,
    "markdown": harvest_markdown,
}
