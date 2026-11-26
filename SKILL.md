---
name: agent-progress-receipt
description: >-
  Cross-agent progress visualization and paperless receipt generator.
  Harvests daily sessions from Antigravity, Claude Code, Cursor/Codex, or Markdown logs
  through a 4-layer privacy firewall, distills measurable domain progress bars and streaks,
  and outputs a universal Paperless Markdown Receipt (with optional thermal printer PNG/SVG).
---

# Agent Progress Receipt Skill

Turn daily AI-assisted work and study into tangible, visualizable progress:
- **Paperless-First**: Generates a self-contained `journal_YYYY-MM-DD.md` with YAML frontmatter, ASCII progress bars (`[████░] 80%`), streak counters, completed milestones, and tomorrow's anchor. Works in Obsidian, Notion, GitHub, or any cloud drive without hardware.
- **4-Layer Privacy Firewall**:
  1. Source whitelist (user prompts & brief final replies only; drops tool outputs/code dumps) + sensitive-keyword turn filtering.
  2. Deterministic regex redaction (`nvapi-`, `sk-`, `AIza`, `ghp_`, Bearer tokens, phones, emails, ID cards, user home paths, auth URLs).
  3. Abstract-only LLM summarization (strictly forbids PII/secrets/verbatim quotes).
  4. Optional IM sync isolation (private-chat whitelist only when paired with `astrbot_plugin_agent_brief_sync`).
- **Pluggable Adapters**: `antigravity`, `claude_code`, `markdown` (compatible with OpenClaw `MEMORY.md` / daily logs / Cursor exports), and `json_feed` (generic social/status JSON feed items).
- **Optional Thermal Render**: Pass `--thermal-scripts-dir` to also emit 384px 1-bit PNG, realistic paper card PNG, and SVG; omits gracefully with `--md-only` or when `PIL` is absent.

## Quick Usage

```bash
python scripts/generate_receipt.py --adapter markdown --source "./logs/*.md" --output "./output" --today --md-only
```
