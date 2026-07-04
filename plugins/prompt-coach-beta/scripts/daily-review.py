#!/usr/bin/env python3
"""prompt-coach-beta v0.21+ — /prompt-coach-beta:daily-review.

Aggregate prompt-coach activity across every repo under a search root
(default: ~/IdeaProjects) and render a scannable daily brief.

Usage
-----
    daily-review.py                          # today (since local midnight)
    daily-review.py --yesterday              # yesterday only
    daily-review.py --days 7                 # last 7 days
    daily-review.py --since 2026-07-01 --until 2026-07-03
    daily-review.py --search-root ~/code
    daily-review.py --repos /a/b,/c/d        # explicit repo paths
    daily-review.py --json                   # machine-readable

Reads every `<repo>/.claude/prompt-coach/log.md` under the search root
plus the global mastery state at `~/.claude/prompt-coach/state.json`.

v0.22+: Default behavior maintains a watermark at
`~/.claude/prompt-coach/daily-review/last-reviewed.json` so daily runs
only see new activity since the last review. Explicit window flags (--since,
--days, --yesterday) skip the watermark entirely so ad-hoc queries
don't disturb the daily cadence. Escape hatches: --no-mark,
--reset-mark, --show-mark.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── Log format ─────────────────────────────────────────────────────────
#
# One entry per prompt. `corrected=[...]` is optional (only present when
# the typo normalizer substituted at least one token). Everything else is
# always emitted. The em dash — is used as a "none/empty" sentinel.
#
#   - [YYYY-MM-DDTHH:MM:SSZ] fired=[<rules>|—] chosen=<rule>|— \
#     positives=[<positives>|—] [corrected=[<from→to>,…]] praise=<val>|— \
#     outcome=<outcome> prompt=«<preview>»
#
LOG_LINE_RE = re.compile(
    r"^- \[(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)\] "
    r"fired=\[(?P<fired>[^\]]*)\] "
    r"chosen=(?P<chosen>\S+) "
    r"positives=\[(?P<positives>[^\]]*)\] "
    r"(?:corrected=\[(?P<corrected>[^\]]*)\] )?"
    r"praise=(?P<praise>\S+) "
    r"outcome=(?P<outcome>\S+) "
    r"prompt=«(?P<preview>.*)»$"
)

# outcome format: nudged:<style>:<level>:v<idx>:p=<preset>:src=<source>
#              or refresher:<style>
#              or skipped:conversational  |  no-emit  |  paused
#              or silenced:saturation
OUTCOME_KIND_RE = re.compile(
    r"^(?P<kind>nudged|refresher|praised|skipped|silenced|paused|no-emit)"
)

EM_DASH = "—"


def _parse_ts(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _split_list(s: str) -> list[str]:
    """Parse `foo, bar, baz` → ['foo', 'bar', 'baz']. Em-dash → []."""
    if not s or s == EM_DASH:
        return []
    return [t.strip() for t in s.split(",") if t.strip() and t.strip() != EM_DASH]


def _parse_entry(m: re.Match, repo: str) -> dict:
    ts = _parse_ts(m["ts"])
    kind_m = OUTCOME_KIND_RE.match(m["outcome"])
    kind = kind_m["kind"] if kind_m else "unknown"
    return {
        "ts": ts,
        "repo": repo,
        "fired": _split_list(m["fired"]),
        "chosen": None if m["chosen"] == EM_DASH else m["chosen"],
        "positives": _split_list(m["positives"]),
        "corrected": _split_list(m["corrected"] or ""),
        "praise": None if m["praise"] == EM_DASH else m["praise"],
        "outcome": m["outcome"],
        "outcome_kind": kind,
        "preview": m["preview"],
    }


# ── Repo discovery ─────────────────────────────────────────────────────

def find_coach_logs(search_root: Path, max_depth: int = 6) -> list[Path]:
    """Find every .claude/prompt-coach/log.md under search_root. Depth-capped
    to avoid worst-case scans in a deep tree."""
    results = []

    def walk(d: Path, depth: int):
        if depth > max_depth:
            return
        try:
            for entry in d.iterdir():
                if entry.is_dir():
                    # If this dir contains the coach log, harvest it and stop
                    candidate = entry / ".claude" / "prompt-coach" / "log.md"
                    if candidate.exists():
                        results.append(candidate)
                    walk(entry, depth + 1)
        except (PermissionError, OSError):
            pass

    if search_root.exists():
        walk(search_root, 0)
    return sorted(results)


# ── State (global mastery ledger) ──────────────────────────────────────

def load_global_state() -> dict:
    p = Path.home() / ".claude" / "prompt-coach" / "state.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        return {}


# ── Watermark (v0.22+) ─────────────────────────────────────────────────

def _watermark_path() -> Path:
    # v0.22+ — daily-review owns its own state subdirectory under
    # ~/.claude/prompt-coach/ so the watermark file belongs to the
    # daily-review skill, not the coach's top-level namespace.
    return (Path.home() / ".claude" / "prompt-coach" / "daily-review"
            / "last-reviewed.json")


def load_watermark() -> datetime | None:
    """Return the last-review timestamp as UTC, or None if unset."""
    p = _watermark_path()
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
        s = data.get("last_reviewed")
        if not s:
            return None
        # Support both plain ISO and 'Z'-suffixed strings
        if s.endswith("Z"):
            return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc
            )
        return datetime.fromisoformat(s).astimezone(timezone.utc)
    except (json.JSONDecodeError, ValueError):
        return None


def save_watermark(ts: datetime) -> None:
    """Write ts (UTC) as the new watermark. Preserves any other keys."""
    p = _watermark_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if p.exists():
        try:
            existing = json.loads(p.read_text())
        except json.JSONDecodeError:
            existing = {}
    existing["last_reviewed"] = ts.astimezone(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    p.write_text(json.dumps(existing, indent=2) + "\n")


def reset_watermark() -> bool:
    """Delete the watermark. Returns True if a file was removed."""
    p = _watermark_path()
    if p.exists():
        p.unlink()
        return True
    return False


def load_candidates(repo_root: Path) -> list[dict]:
    """Read .claude/prompt-coach/candidates.jsonl (bug-report queue). One
    JSON object per line."""
    p = repo_root / ".claude" / "prompt-coach" / "candidates.jsonl"
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


# ── Aggregation ─────────────────────────────────────────────────────────

def collect_entries(log_paths: list[Path], since: datetime,
                    until: datetime) -> tuple[list[dict], dict[str, dict]]:
    """Read every log_path, filter by [since, until), return entries +
    per-repo summary."""
    entries: list[dict] = []
    per_repo: dict[str, dict] = {}
    for p in log_paths:
        repo = p.parent.parent.parent.name
        repo_root = p.parent.parent.parent
        per_repo.setdefault(repo, {
            "path": str(repo_root),
            "log_path": str(p),
            "count": 0,
            "nudges": 0,
            "praises": 0,
            "refreshers": 0,
            "skipped": 0,
            "silenced": 0,
            "candidates": len(load_candidates(repo_root)),
        })
        try:
            content = p.read_text()
        except OSError:
            continue
        for line in content.splitlines():
            m = LOG_LINE_RE.match(line)
            if not m:
                continue
            try:
                e = _parse_entry(m, repo)
            except (ValueError, KeyError):
                continue
            if since <= e["ts"] < until:
                entries.append(e)
                per_repo[repo]["count"] += 1
                if e["outcome_kind"] == "nudged":
                    per_repo[repo]["nudges"] += 1
                elif e["outcome_kind"] == "praised":
                    per_repo[repo]["praises"] += 1
                elif e["outcome_kind"] == "refresher":
                    per_repo[repo]["refreshers"] += 1
                elif e["outcome_kind"] == "skipped":
                    per_repo[repo]["skipped"] += 1
                elif e["outcome_kind"] == "silenced":
                    per_repo[repo]["silenced"] += 1
    return entries, per_repo


# ── Report ─────────────────────────────────────────────────────────────

_BAR = "━" * 68


def _section(title: str) -> str:
    return f"{_BAR}\n{title}\n{_BAR}"


def _pct(numer: int, denom: int) -> str:
    if denom == 0:
        return "0%"
    return f"{100 * numer / denom:.1f}%"


def render_report(entries: list[dict], per_repo: dict[str, dict],
                  since: datetime, until: datetime,
                  global_state: dict) -> str:
    lines = []

    # ── Header ────────────────────────────────────────────────────────
    since_local = since.astimezone()
    day_span = (until - since).days
    if day_span == 1 and since_local.hour == 0:
        header_scope = since_local.strftime("%Y-%m-%d (%a)")
    elif day_span == 1:
        header_scope = "last 24 hours"
    else:
        header_scope = (
            f"{since_local.strftime('%Y-%m-%d')} → "
            f"{until.astimezone().strftime('%Y-%m-%d')} ({day_span} days)"
        )

    active_repos = sum(1 for r in per_repo.values() if r["count"] > 0)
    total_repos = len(per_repo)
    lines.append("═" * 68)
    lines.append(f"📊 prompt-coach daily review — {header_scope}")
    lines.append("═" * 68)
    lines.append(f"Scope: {total_repos} repos scanned · "
                 f"{active_repos} with activity · "
                 f"since {since.astimezone().isoformat(timespec='minutes')}")
    lines.append("")

    if not entries:
        lines.append("No prompts recorded in the selected window.")
        lines.append("")
        lines.append("If you expected activity, check:")
        lines.append("  - The coach's nudge_style isn't 'log-only' with a "
                     "stale log")
        lines.append("  - Your search root includes the repos you use")
        lines.append("")
        return "\n".join(lines)

    # ── Volume ────────────────────────────────────────────────────────
    lines.append(_section("VOLUME"))
    total = len(entries)
    counts = Counter(e["outcome_kind"] for e in entries)
    nudges = counts["nudged"]
    praises = counts["praised"]
    refreshers = counts["refresher"]
    skipped = counts["skipped"]
    silenced = counts["silenced"]
    no_emit = counts["no-emit"]

    lines.append(f"  {total:4d} prompts analyzed")
    lines.append(f"  {nudges:4d} nudges emitted  ({_pct(nudges, total)} emit rate)")
    lines.append(f"  {praises:4d} praises awarded")
    if refreshers:
        lines.append(f"  {refreshers:4d} refresher fires (mastered rules)")
    lines.append(f"  {skipped:4d} skipped (approvals, task-notifications, etc.)")
    if silenced:
        lines.append(f"  {silenced:4d} silenced-by-saturation events")
    lines.append(f"  {no_emit:4d} no-emit (rule matched but cooldown/policy skipped)")
    lines.append("")

    # ── Top-fired rules ──────────────────────────────────────────────
    lines.append(_section("TOP-FIRED RULES (nudges + refreshers)"))
    fired_counter: Counter[str] = Counter()
    for e in entries:
        if e["chosen"]:
            fired_counter[e["chosen"]] += 1
    if fired_counter:
        rules = global_state.get("rules", {})
        for rid, n in fired_counter.most_common(10):
            r_state = rules.get(rid, {})
            status = r_state.get("status", "practicing")
            streak = r_state.get("clean_streak", 0)
            fires_total = r_state.get("fires_total", 0)
            note = ("mastered" if status == "mastered"
                    else f"streak {streak}/15 (fires_total {fires_total})")
            lines.append(f"  {n:3d}  {rid:32s}  {note}")
    else:
        lines.append("  (no rule fires in this window)")
    lines.append("")

    # ── Positives (praise-eligible detections) ───────────────────────
    positive_counter: Counter[str] = Counter()
    for e in entries:
        for pid in e["positives"]:
            positive_counter[pid] += 1
    if positive_counter:
        lines.append(_section("POSITIVE DETECTIONS (praise-eligible)"))
        for pid, n in positive_counter.most_common(8):
            lines.append(f"  {n:3d}  {pid}")
        lines.append("")

    # ── Typo corrections ────────────────────────────────────────────
    corrections: Counter[str] = Counter()
    for e in entries:
        for c in e["corrected"]:
            corrections[c] += 1
    if corrections:
        lines.append(_section("TOP TYPO CORRECTIONS"))
        for c, n in corrections.most_common(8):
            lines.append(f"  {n:3d}  {c}")
        lines.append("")

    # ── By repo ──────────────────────────────────────────────────────
    active = [(r, s) for r, s in per_repo.items() if s["count"] > 0]
    if active:
        lines.append(_section("BY REPO"))
        active.sort(key=lambda x: -x[1]["count"])
        for repo, s in active:
            share = _pct(s["count"], total)
            extras = []
            if s["nudges"]: extras.append(f"{s['nudges']} nudge")
            if s["praises"]: extras.append(f"{s['praises']} praise")
            if s["refreshers"]: extras.append(f"{s['refreshers']} refresh")
            if s["silenced"]: extras.append(f"{s['silenced']} silenced")
            extras_str = " · ".join(extras) if extras else "no fires"
            lines.append(f"  {repo:32s}  {s['count']:3d} prompts "
                         f"({share:>5s})   {extras_str}")
        lines.append("")

    # ── Flagged for review ──────────────────────────────────────────
    all_candidates = [(r, s) for r, s in per_repo.items() if s["candidates"] > 0]
    if all_candidates:
        lines.append(_section("FLAGGED FOR REVIEW (candidates.jsonl)"))
        total_cands = sum(s["candidates"] for r, s in all_candidates)
        lines.append(f"  {total_cands} candidate(s) queued for /prompt-coach-beta:report-issue:")
        for repo, s in all_candidates:
            lines.append(f"    {repo}: {s['candidates']} candidate(s)")
        lines.append("")

    # ── Health signal ────────────────────────────────────────────────
    emit_rate = nudges / total if total else 0
    health_notes = []
    if emit_rate > 0.20:
        health_notes.append(
            f"Emit rate is {emit_rate*100:.0f}% (>20%) — you're being nudged "
            "often. Run /prompt-coach-beta:config mastery to see which rules "
            "keep catching you."
        )
    if silenced:
        health_notes.append(
            f"{silenced} silenced-by-saturation event(s). The coach went "
            "quiet on repeat-firing rules; check log.md around those events "
            "to see if a rule needs tuning."
        )
    close_to_mastery = []
    rules = global_state.get("rules", {})
    for rid, r_state in rules.items():
        streak = r_state.get("clean_streak", 0)
        if 12 <= streak < 15 and r_state.get("status", "practicing") == "practicing":
            close_to_mastery.append((rid, streak))
    if close_to_mastery:
        rid, streak = min(close_to_mastery, key=lambda x: -x[1])
        health_notes.append(
            f"{len(close_to_mastery)} rule(s) close to mastery: e.g. "
            f"{rid} at streak {streak}/15."
        )
    if health_notes:
        lines.append(_section("HEALTH SIGNALS"))
        for n in health_notes:
            # Simple word-wrap at 66 chars w/ 4-space continuation
            import textwrap
            for wrapped in textwrap.wrap(n, width=66,
                                          initial_indent="  · ",
                                          subsequent_indent="    "):
                lines.append(wrapped)
        lines.append("")

    lines.append("═" * 68)
    return "\n".join(lines)


# ── CLI ────────────────────────────────────────────────────────────────

def _parse_since_until(args) -> tuple[datetime, datetime, bool]:
    """Resolve --since/--until/--days/--yesterday into a UTC (since, until)
    pair. Returns (since, until, uses_watermark). When no explicit window
    flag is given (v0.22+), default to since=watermark (if present, else
    today's local midnight) → until=now; the caller updates the watermark
    to `until` after a successful render unless --no-mark is set."""
    now_local = datetime.now().astimezone()
    now_utc = now_local.astimezone(timezone.utc)
    explicit_flag = any([args.yesterday, args.days is not None,
                          args.since, args.until])

    if args.yesterday:
        y = now_local.date() - timedelta(days=1)
        since = datetime(y.year, y.month, y.day, tzinfo=now_local.tzinfo)
        until = since + timedelta(days=1)
    elif args.days is not None:
        until = now_local
        since = until - timedelta(days=args.days)
    elif args.since or args.until:
        if args.since:
            y, m, d = [int(x) for x in args.since.split("-")]
            since = datetime(y, m, d, tzinfo=now_local.tzinfo)
        else:
            t = now_local.date()
            since = datetime(t.year, t.month, t.day, tzinfo=now_local.tzinfo)
        if args.until:
            y, m, d = [int(x) for x in args.until.split("-")]
            until = datetime(y, m, d, tzinfo=now_local.tzinfo) + timedelta(days=1)
        else:
            until = since + timedelta(days=1)
    else:
        # v0.22+ default: since = watermark (or today's midnight), until = now
        watermark = load_watermark()
        if watermark:
            since = watermark
        else:
            t = now_local.date()
            since = datetime(t.year, t.month, t.day, tzinfo=now_local.tzinfo)
        until = now_local

    return (since.astimezone(timezone.utc),
            until.astimezone(timezone.utc),
            not explicit_flag)


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="daily-review", description=__doc__)
    p.add_argument("--since", help="YYYY-MM-DD (local time; inclusive)")
    p.add_argument("--until", help="YYYY-MM-DD (local time; inclusive)")
    p.add_argument("--days", type=int, help="last N days (overrides --since/--until)")
    p.add_argument("--yesterday", action="store_true",
                    help="yesterday only (00:00 → 24:00 local)")
    p.add_argument("--search-root", default=str(Path.home() / "IdeaProjects"),
                    help="root under which to find repos (default: ~/IdeaProjects)")
    p.add_argument("--repos", help="comma-separated repo paths (overrides "
                    "--search-root)")
    p.add_argument("--json", action="store_true", dest="as_json")
    # v0.22+ watermark flags
    p.add_argument("--no-mark", action="store_true",
                    help="don't update the last-reviewed watermark after "
                         "this run (default: update on the auto-window)")
    p.add_argument("--reset-mark", action="store_true",
                    help="delete the watermark and exit")
    p.add_argument("--show-mark", action="store_true",
                    help="print the current watermark and exit")
    args = p.parse_args(argv)

    # Watermark management (v0.22+)
    if args.reset_mark:
        if reset_watermark():
            print(f"watermark cleared: {_watermark_path()}")
        else:
            print(f"no watermark to clear ({_watermark_path()} did not exist)")
        return 0
    if args.show_mark:
        wm = load_watermark()
        if wm:
            print(f"watermark: {wm.isoformat()}")
            print(f"  file: {_watermark_path()}")
        else:
            print(f"watermark unset (no file at {_watermark_path()})")
        return 0

    since, until, uses_watermark = _parse_since_until(args)

    if args.repos:
        log_paths = []
        for r in args.repos.split(","):
            r = Path(r).expanduser()
            candidate = r / ".claude" / "prompt-coach" / "log.md"
            if candidate.exists():
                log_paths.append(candidate)
    else:
        log_paths = find_coach_logs(Path(args.search_root).expanduser())

    entries, per_repo = collect_entries(log_paths, since, until)
    global_state = load_global_state()

    if args.as_json:
        out = {
            "since": since.isoformat(),
            "until": until.isoformat(),
            "search_root": args.search_root if not args.repos else None,
            "logs_scanned": len(log_paths),
            "prompt_count": len(entries),
            "counts": dict(Counter(e["outcome_kind"] for e in entries)),
            "top_fired_rules": Counter(
                e["chosen"] for e in entries if e["chosen"]
            ).most_common(20),
            "top_positives": Counter(
                p for e in entries for p in e["positives"]
            ).most_common(20),
            "top_corrections": Counter(
                c for e in entries for c in e["corrected"]
            ).most_common(20),
            "per_repo": {
                repo: {k: v for k, v in s.items() if k != "log_path"}
                for repo, s in per_repo.items()
            },
            "global_prompt_count": global_state.get("prompt_count"),
        }
        print(json.dumps(out, indent=2, default=str))
        if uses_watermark and not args.no_mark:
            save_watermark(until)
        return 0

    print(render_report(entries, per_repo, since, until, global_state))
    # v0.22+ — update watermark after successful render on the auto-window
    if uses_watermark and not args.no_mark:
        save_watermark(until)
        print(f"  Watermark advanced to {until.isoformat(timespec='minutes')}.")
        print(f"  Next default run will start from there. To skip this, "
              f"use --no-mark; to redo, --reset-mark.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
