# -*- coding: utf-8 -*-
"""
Unit checks for agent-progress-receipt-skill (sanitizer, MarkdownLogAdapter, paperless receipt output).
"""

import os
import sys
import tempfile
from datetime import date, timedelta, timezone

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from adapters import harvest_markdown
from generate_receipt import build_paperless_receipt_text, write_markdown_receipt
from sanitizer import is_sensitive_turn, sanitize_text

raw = (
    "key=nvapi-1234567890abcdef sk-abcdef1234567890 "
    "phone=13812345678 id=11010119900101123X "
    "email=alice@example.com win=C:\\Users\\Alice\\file.txt "
    "unix=/home/alice/secret.key url=https://x.io/?token=mysecret"
)
cleaned = sanitize_text(raw)
for forbidden in ("nvapi-", "sk-abcdef", "13812345678", "11010119900101123X", "alice@example.com", "Alice", "alice", "mysecret"):
    assert forbidden not in cleaned, f"Leak detected: {forbidden} in {cleaned}"
assert is_sensitive_turn("reset my password please") is True
assert is_sensitive_turn("completed unit tests") is False
print("[PASS] Sanitizer checks passed")

with tempfile.TemporaryDirectory() as tmp:
    log_path = os.path.join(tmp, "2026-11-24.md")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("# Daily Log\nBuilt feature X\nMy password=12345\nFinished review\n")

    lines = harvest_markdown(date(2026, 11, 24), timezone(timedelta(hours=8)), source_glob=os.path.join(tmp, "*.md"))
    assert len(lines) == 2, f"Expected 2 non-sensitive lines, got {lines}"

    sample_data = {
        "theme": "Open Source",
        "mood": "MOOD: Focused",
        "focus_score": 5,
        "tracks": [{"name": "Coding", "pct": 80}],
        "done": ["Shipped v1.0"],
        "next_step": "Publish to GitHub",
        "closing": "Consistent progress wins.",
    }
    receipt_txt = build_paperless_receipt_text("2026-11-24", 1, 1, sample_data)
    assert "[████░] 80%" in receipt_txt
    out_md = os.path.join(tmp, "journal_2026-11-24.md")
    write_markdown_receipt(out_md, "2026-11-24", 1, 1, sample_data, receipt_txt)
    assert os.path.isfile(out_md) and os.path.getsize(out_md) > 100
print("[PASS] Markdown adapter & paperless receipt checks passed")
