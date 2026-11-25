# -*- coding: utf-8 -*-
"""
Portable Cross-Agent Progress Receipt Generator.
Outputs a first-class Paperless Markdown Receipt (journal_YYYY-MM-DD.md)
and optionally renders 1-bit thermal PNG / realistic share card / SVG.
"""

import argparse
import json
import os
import re
import sys
import tempfile
import unicodedata
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

os.environ["NO_PROXY"] = "127.0.0.1,localhost"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from adapters import ADAPTERS
from sanitizer import DEFAULT_SENSITIVE_KEYWORDS, sanitize_text


def _wrap_cjk(text: str, max_units: int = 30) -> list[str]:
    lines: list[str] = []
    for raw_line in text.splitlines():
        cur, cur_w = "", 0
        for ch in raw_line.strip():
            cw = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
            if cur_w + cw > max_units and cur:
                lines.append(cur)
                cur, cur_w = ch, cw
            else:
                cur += ch
                cur_w += cw
        if cur:
            lines.append(cur)
    return lines or [""]


def _progress_bar(pct: int, width: int = 6, thermal: bool = False) -> str:
    pct = max(0, min(100, int(pct)))
    filled = round(pct / 100 * width)
    fill_ch = "■" if thermal else "█"
    empty_ch = "□" if thermal else "░"
    return "[" + (fill_ch * filled) + (empty_ch * (width - filled)) + f"] {pct}%"


def _update_streak(output_root: str, target_d: date) -> tuple[int, int]:
    os.makedirs(output_root, exist_ok=True)
    streak_path = os.path.join(output_root, "streak.json")
    data = {"streak_days": 0, "total_days": 0, "last_date": "", "dates": []}
    if os.path.exists(streak_path):
        try:
            with open(streak_path, "r", encoding="utf-8") as f:
                data.update(json.load(f))
        except Exception:
            pass

    d_str = target_d.isoformat()
    dates_set = set(data.get("dates", []))
    if d_str not in dates_set:
        dates_set.add(d_str)
        last_str = data.get("last_date", "")
        if last_str:
            try:
                last_d = date.fromisoformat(last_str)
                if (target_d - last_d).days == 1:
                    data["streak_days"] = int(data.get("streak_days", 0)) + 1
                elif target_d > last_d:
                    data["streak_days"] = 1
            except ValueError:
                data["streak_days"] = 1
        else:
            data["streak_days"] = 1
        if not data.get("last_date") or d_str >= data["last_date"]:
            data["last_date"] = d_str
        data["dates"] = sorted(dates_set)
        data["total_days"] = len(data["dates"])
        with open(streak_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    return max(1, int(data.get("streak_days", 1))), max(1, int(data.get("total_days", 1)))


def _sanitize_struct(obj: dict) -> dict:
    tracks = []
    for t in (obj.get("tracks") or [])[:3]:
        if isinstance(t, dict):
            name = sanitize_text(str(t.get("name", "Core Work"))).strip()[:10]
            try:
                pct = max(0, min(100, int(t.get("pct", 60))))
            except (TypeError, ValueError):
                pct = 60
            tracks.append({"name": name or "Core", "pct": pct})
    if not tracks:
        tracks = [{"name": "Core Work", "pct": 70}]

    done = [sanitize_text(str(x)).strip()[:22] for x in (obj.get("done") or [])[:3] if str(x).strip()]
    if not done:
        done = ["Completed today's tracked tasks"]

    try:
        focus = max(1, min(5, int(obj.get("focus_score", 4))))
    except (TypeError, ValueError):
        focus = 4

    return {
        "theme": sanitize_text(str(obj.get("theme", "Daily Progress"))).strip()[:18],
        "mood": sanitize_text(str(obj.get("mood", "MOOD: Focused"))).strip()[:24],
        "focus_score": focus,
        "tracks": tracks,
        "done": done,
        "next_step": sanitize_text(str(obj.get("next_step", "Continue next milestone"))).strip()[:22],
        "closing": sanitize_text(str(obj.get("closing", "Steady progress compounds daily."))).strip()[:36],
    }


def _distill_progress_json(digest_lines: list[str], date_str: str, cfg: dict) -> dict:
    endpoint = cfg.get("endpoint", "")
    api_key = cfg.get("api_key", "")
    models = cfg.get("models") or ["gemini-3.8-flash"]

    if endpoint and api_key and api_key != "YOUR_API_KEY":
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        system_prompt = (
            "You are a personal progress & learning receipt summarizer. Given sanitized session logs, "
            "output strictly valid JSON with fields: "
            '{"theme": "<=10 chars", "mood": "MOOD: ...", "focus_score": 1..5, '
            '"tracks": [{"name": "<=8 chars", "pct": 0..100}], '
            '"done": ["<=16 chars"], "next_step": "<=16 chars", "closing": "<=28 chars"}. '
            "Never include real names, secrets, file paths, or private verbatim details."
        )
        user_content = f"Date: {date_str}\n" + "\n".join(digest_lines)
        for model in models:
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                "temperature": 0.3,
                "max_tokens": 4096,
            }
            req = urllib.request.Request(
                endpoint,
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
                method="POST",
            )
            try:
                with opener.open(req, timeout=45) as resp:
                    raw = (
                        json.loads(resp.read().decode("utf-8"))
                        .get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")
                        .strip()
                    )
                cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.DOTALL).strip()
                m = re.search(r"\{.*\}", cleaned, re.DOTALL)
                if m:
                    return _sanitize_struct(json.loads(m.group(0)))
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
                continue

    return _sanitize_struct(
        {
            "theme": "Focused Deep Work",
            "mood": "MOOD: (•̀ᴗ•́)و ̑̑",
            "focus_score": 4,
            "tracks": [{"name": "Execution", "pct": 75}, {"name": "Learning", "pct": 60}],
            "done": ["Archived sanitized daily sessions", "Advanced primary project milestones"],
            "next_step": "Review progress and start next block",
            "closing": "Small daily steps build lasting momentum.",
        }
    )


def build_paperless_receipt_text(date_str: str, total_days: int, streak_days: int, data: dict) -> str:
    stars = "★" * data["focus_score"] + "☆" * (5 - data["focus_score"])
    lines = [
        "================================",
        f"  AGENT PROGRESS RECEIPT #{total_days:03d}",
        f"  {date_str} | STREAK {streak_days}d",
        "--------------------------------",
        f"THEME: {data['theme']}",
        f"FOCUS: {stars} ({data['focus_score']}/5)",
        "--------------------------------",
        "[ TRACKS ]",
    ]
    for tr in data["tracks"]:
        lines.append(f"  {tr['name']} {_progress_bar(tr['pct'], 5)}")
    lines.extend(["--------------------------------", "[ COMPLETED ]"])
    for item in data["done"]:
        for idx, sub in enumerate(_wrap_cjk(item, 34)):
            lines.append(("  [x] " if idx == 0 else "      ") + sub)
    lines.append("[ NEXT ANCHOR ]")
    for idx, sub in enumerate(_wrap_cjk(data["next_step"], 34)):
        lines.append(("  [ ] " if idx == 0 else "      ") + sub)
    lines.append("--------------------------------")
    for sub in _wrap_cjk(data["closing"], 36):
        lines.append("  " + sub)
    lines.append("================================")
    return "\n".join(lines)


def write_markdown_receipt(
    out_md: str, date_str: str, total_days: int, streak_days: int, data: dict, receipt_txt: str
) -> None:
    stars = "★" * data["focus_score"] + "☆" * (5 - data["focus_score"])
    track_rows = "\n".join(f"| {tr['name']} | `{_progress_bar(tr['pct'], 10)}` |" for tr in data["tracks"])
    done_bullets = "\n".join(f"- [x] {d}" for d in data["done"])

    md = f"""---
date: {date_str}
day_index: {total_days}
streak: {streak_days}
focus_score: {data['focus_score']}
theme: "{data['theme']}"
mood: "{data['mood']}"
tags: [daily-receipt, progress-log]
---

# Progress Receipt · {date_str} (DAY #{total_days})

> **Theme**: {data['theme']} | **Focus**: {stars} | **Streak**: {streak_days}d | {data['mood']}

## 1. Paperless Receipt

```text
{receipt_txt}
```

## 2. Progress Tracks

| Domain | Progress |
| :--- | :--- |
{track_rows}

## 3. Milestones

{done_bullets}
- [ ] **Next Anchor**: {data['next_step']}

> *{data['closing']}*
"""
    os.makedirs(os.path.dirname(out_md), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(out_md), prefix=".tmp_", suffix=".md")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(md)
        os.replace(tmp, out_md)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Cross-Agent Paperless & Thermal Progress Receipt Generator")
    parser.add_argument("--config", default=None, help="Path to config.json")
    parser.add_argument("--adapter", choices=list(ADAPTERS.keys()), default=None)
    parser.add_argument("--source", default=None, help="Source glob pattern override")
    parser.add_argument("--output", default=None, help="Output root directory")
    parser.add_argument("--today", action="store_true")
    parser.add_argument("--date", default=None, help="YYYY-MM-DD")
    parser.add_argument("--md-only", action="store_true", help="Skip optional thermal PNG/SVG rendering")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--thermal-scripts-dir", default=None, help="Optional path to thermal-receipt-artisan scripts")
    args = parser.parse_args()

    cfg = {}
    if args.config and os.path.exists(args.config):
        with open(args.config, "r", encoding="utf-8") as f:
            cfg = json.load(f)

    tz = timezone(timedelta(hours=int(cfg.get("utc_offset_hours", 8))))
    now_local = datetime.now(tz)
    if args.date:
        target_d = date.fromisoformat(args.date)
    elif args.today:
        target_d = now_local.date()
    else:
        target_d = (now_local.date() - timedelta(days=1)) if now_local.hour < 6 else now_local.date()

    adapter_name = args.adapter or cfg.get("adapter", "markdown")
    harvester = ADAPTERS[adapter_name]
    digest_lines = harvester(
        target_d,
        tz,
        source_glob=args.source or cfg.get("source_glob"),
        sensitive_keywords=cfg.get("sensitive_keywords", DEFAULT_SENSITIVE_KEYWORDS),
    )
    if not digest_lines:
        print(f"[Receipt] No entries found for {target_d.isoformat()} using adapter={adapter_name}.")
        return 0

    output_root = args.output or cfg.get("output_dir", "./output")
    streak_days, total_days = _update_streak(output_root, target_d) if not args.dry_run else (1, 1)
    data = _distill_progress_json(digest_lines, target_d.isoformat(), cfg)
    receipt_txt = build_paperless_receipt_text(target_d.isoformat(), total_days, streak_days, data)

    if args.dry_run:
        print(receipt_txt)
        return 0

    day_dir = os.path.join(output_root, target_d.isoformat())
    out_md = os.path.join(day_dir, f"journal_{target_d.isoformat()}.md")
    write_markdown_receipt(out_md, target_d.isoformat(), total_days, streak_days, data, receipt_txt)
    print(f"[Receipt] Paperless Markdown receipt written -> {out_md}")

    thermal_dir = args.thermal_scripts_dir or cfg.get("thermal_scripts_dir")
    if not args.md_only and thermal_dir and os.path.isdir(thermal_dir):
        sys.path.insert(0, thermal_dir)
        try:
            from note_artisan import build_note, export_to_svg, render_social_preview

            stars = "★" * data["focus_score"] + "☆" * (5 - data["focus_score"])
            sep = "─" * 34
            t_lines = [f"THEME: {data['theme']}  {stars}", sep, "[ TRACKS ]"]
            for tr in data["tracks"]:
                t_lines.append(f"  {tr['name']} {_progress_bar(tr['pct'], 5, thermal=True)}")
            t_lines.extend([sep, "[ COMPLETED ]"])
            for item in data["done"]:
                for idx, sub in enumerate(_wrap_cjk(item, 42)):
                    t_lines.append(("  [x] " if idx == 0 else "      ") + sub)
            t_lines.append("[ NEXT ANCHOR ]")
            for idx, sub in enumerate(_wrap_cjk(data["next_step"], 42)):
                t_lines.append(("  [ ] " if idx == 0 else "      ") + sub)
            t_lines.append(sep)
            closing_clean = data["closing"].replace("♡~", "~").replace("♡", "")
            t_lines.extend(_wrap_cjk(closing_clean, 44))

            img_1bit = build_note(
                "journal",
                "57x80",
                custom_data={
                    "weather": f"* {target_d.isoformat()} | DAY #{total_days:03d}",
                    "mood": f"FOCUS {data['focus_score']}/5 | STREAK {streak_days}d",
                    "content": "\n".join(t_lines[:18]),
                },
            )
            img_1bit.save(os.path.join(day_dir, f"journal_{target_d.isoformat()}_1bit.png"))
            render_social_preview(img_1bit).save(os.path.join(day_dir, f"journal_{target_d.isoformat()}_card.png"))
            export_to_svg(img_1bit, os.path.join(day_dir, f"journal_{target_d.isoformat()}.svg"))
            print(f"[Receipt] Thermal assets generated in -> {day_dir}")
        except ImportError as e:
            print(f"[Receipt] Skipping thermal image render ({e}); Markdown receipt preserved.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
