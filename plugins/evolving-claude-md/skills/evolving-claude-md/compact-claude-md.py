#!/usr/bin/env python3
"""Plan a CLAUDE.md compaction — the data behind /evolving-claude-md:compact.

Read-only. Lists the entries each downward pressure applies to, in the order
the command acts on them:

  1. supersede   entries naming a target that is unstruck or missing
  2. mirror      entries naming a version CHANGELOG.md already documents —
                 keep what the release TAUGHT, drop what it shipped
  3. merge       one day with many entries: likely one piece of work
  4. graduate    a topic-tag 3+ times, newest >= recent_days old: a stable
                 pattern that belongs in Conventions / Gotchas
  5. split       entries over the mega-entry cap
  6. stale       entries citing artifacts the tree no longer has
  7. age-out     entries older than recent_days, archived LAST

Order matters. Graduation must run before age-out, or a durable lesson goes
into the quarterly archive instead of the always-loaded Conventions; mirrors
and merges run first because they shrink what the later steps have to read.

It decides nothing. Which mirror entry still carries a lesson, whether a
same-day cluster really is one piece of work, what a graduated rule should say
— those are judgment, made by the session running the command and approved by
the user. The only mechanical step, age-out, is delegated to
archive-decisions.py, which already knows how to do it safely.

    compact-claude-md.py            # human-readable plan
    compact-claude-md.py --json     # for tooling
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import os
import sys
import time
from collections import defaultdict

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "_audit", os.path.join(_HERE, "audit-claude-md.py"))
audit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(audit)


def _head(body: str, n: int = 90) -> str:
    # The topic is shown separately; repeating it wastes the preview.
    one = " ".join(audit.re.sub(r"^\*\*[^*]+\*\*\s*—\s*", "", body.strip()).split())
    return one if len(one) <= n else one[: n - 1] + "…"


def build_plan(text: str, root: str = ".", today: dt.date | None = None,
               cfg: dict | None = None) -> dict:
    cfg = cfg or audit.load_config(root)
    today = today or dt.date.today()
    section = audit.recent_section(text)
    if section is None:
        return {"error": f"no `{audit.SECTION_HEADING}` section"}
    entries = audit.ENTRY_PAT.findall(section)
    # A strike is written on the DATE (`- ~~2026-07-10~~ — …`), which the
    # captured body doesn't carry — read it off the whole matched line.
    live = [(m.group(1), m.group(2)) for m in audit.ENTRY_PAT.finditer(section)
            if not m.group(0).startswith("- ~~")]

    recent_days = int(cfg.get("recent_days", 14))
    cutoff = today - dt.timedelta(days=recent_days)

    # 1. supersede links that point at nothing, or at something still live
    supersede = audit.supersede_gaps(section, cfg)

    # 2. release mirrors
    chlog = audit.read_changelog(root)
    mirror = [{"date": d, "topic": audit.entry_topic(b), "versions": v,
               "head": _head(b)}
              for d, b, v in audit.mirror_hits(live, chlog)] if chlog else []

    # 3. same-day clusters
    by_day: dict[str, list[str]] = defaultdict(list)
    for d, b in live:
        by_day[d].append(audit.entry_topic(b) or "?")
    merge = [{"date": d, "count": len(t), "topics": t}
             for d, t in sorted(by_day.items(), reverse=True)
             if len(t) >= int(cfg.get("merge_cluster", 4))]

    # 4. graduation: the same tag repeatedly, and stable (newest old enough)
    by_topic: dict[str, list[str]] = defaultdict(list)
    for d, b in live:
        t = audit.entry_topic(b)
        if t:
            by_topic[t].append(d)
    graduate = [{"topic": t, "count": len(ds), "dates": sorted(ds, reverse=True)}
                for t, ds in by_topic.items()
                if len(ds) >= int(cfg["topic_cluster"])
                and dt.date.fromisoformat(max(ds)) <= cutoff]
    graduate.sort(key=lambda g: -g["count"])

    # 5. mega entries
    cap = int(cfg["mega_entry_chars"])
    split = [{"date": d, "topic": audit.entry_topic(b), "chars": len(b),
              "head": _head(b)} for d, b in live if len(b) > cap]

    # 6. stale: same predicate and budget the audit uses
    stale = []
    deadline = time.monotonic() + audit.STALENESS_TIME_BUDGET_S
    for d, b in reversed(live):
        if time.monotonic() > deadline:
            break
        toks = audit.freshness.artifact_tokens(b)
        if not toks:
            continue
        miss = audit.freshness.missing_artifacts(toks, root, deadline=deadline)
        if len(miss) >= audit.STALENESS_MIN_MISSING:
            stale.append({"date": d, "topic": audit.entry_topic(b),
                          "missing": miss})

    # 7. age-out, with the graduation overlap called out — those must move to
    # Conventions/Gotchas first or they leave the always-loaded context.
    aged = [(d, b) for d, b in entries if dt.date.fromisoformat(d) <= cutoff]
    grad_topics = {g["topic"] for g in graduate}
    age_out = {
        "cutoff": cutoff.isoformat(),
        "count": len(aged),
        # Listed so the session can review each for a durable rule before it
        # is archived. Tag-based graduation misses lessons that recur by THEME
        # under different tags — a log that gives every entry its own tag
        # (common, and not wrong) never trips the 3-of-a-tag rule at all.
        "entries": [{"date": d, "topic": audit.entry_topic(b)} for d, b in aged],
        "graduate_first": sorted({audit.entry_topic(b) for _, b in aged
                                  if audit.entry_topic(b) in grad_topics}),
        "command": f"archive-decisions.py --cutoff {cutoff.isoformat()} --apply",
    }

    kb = len(text.encode("utf-8")) / 1024.0
    return {
        "today": today.isoformat(),
        "size": {"kb": round(kb, 1), "entries": len(entries),
                 "lines": section.count("\n")},
        "thresholds": {"entries_recommend": cfg["entries_recommend"],
                       "lines_recommend": cfg["lines_recommend"],
                       "file_recommend_kb": cfg["file_recommend_kb"]},
        "supersede": supersede, "mirror": mirror, "merge": merge,
        "graduate": graduate, "split": split, "stale": stale,
        "age_out": age_out,
    }


def render(plan: dict) -> str:
    if "error" in plan:
        return f"compact: {plan['error']} — nothing to compact."
    s, out = plan["size"], []
    out.append(f"CLAUDE.md: {s['kb']} KB · {s['entries']} entries · "
               f"{s['lines']} lines in Decisions & Learnings")
    t = plan["thresholds"]
    out.append(f"  (compaction recommended past {t['entries_recommend']} entries,"
               f" {t['lines_recommend']} lines or {t['file_recommend_kb']} KB)\n")

    def section(n, title, items, fmt, why):
        out.append(f"{n}. {title} — {len(items)}")
        if items:
            out.append(f"   {why}")
            for it in items[:12]:
                out.append("   · " + fmt(it))
            if len(items) > 12:
                out.append(f"   · …and {len(items) - 12} more")
        out.append("")

    section(1, "supersede gaps", plan["supersede"], str,
            "Strike the target, or fix the link.")
    section(2, "release mirrors", plan["mirror"],
            lambda m: f"{m['date']} **{m['topic']}** ({', '.join(m['versions'])}) — {m['head']}",
            "Rewrite each to the lesson the release taught, or drop it if it "
            "only says what shipped (CHANGELOG.md has that).")
    section(3, "same-day clusters", plan["merge"],
            lambda m: f"{m['date']}: {m['count']} entries — {', '.join(m['topics'])}",
            "If one piece of work, collapse to one entry; detail goes to "
            "docs/decisions/{date}-{topic}.md.")
    section(4, "graduation candidates", plan["graduate"],
            lambda g: f"**{g['topic']}** ×{g['count']} ({', '.join(g['dates'])})",
            "One-line rule in Conventions (or Gotchas for a trap); strike the "
            "entries; leave one 'graduated → see Conventions' line.")
    section(5, "mega entries", plan["split"],
            lambda m: f"{m['date']} **{m['topic']}** ({m['chars']} chars) — {m['head']}",
            "Keep a one-line teaser; move the detail to docs/decisions/.")
    section(6, "stale candidates", plan["stale"],
            lambda m: f"{m['date']} **{m['topic']}** — missing: {', '.join(m['missing'][:4])}",
            "Verify against the tree: fix, strike, or keep with a note.")
    a = plan["age_out"]
    out.append(f"7. age-out — {a['count']} entries on or before {a['cutoff']}")
    if a["count"]:
        if a["graduate_first"]:
            out.append("   Graduate FIRST (these topics are aging out): "
                       + ", ".join(f"**{x}**" for x in a["graduate_first"]))
        out.append("   Review each for a durable rule before it leaves "
                   "the always-loaded file (graduate those to Conventions/Gotchas):")
        topics = [e["topic"] or "?" for e in a["entries"]]
        out.append("   " + ", ".join(topics[:40])
                   + (f", …+{len(topics) - 40}" if len(topics) > 40 else ""))
        out.append(f"   Then: {a['command']}")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--today", help="YYYY-MM-DD (tests)")
    a = ap.parse_args()
    path = audit.CLAUDE_MD
    if not os.path.exists(path):
        print(f"compact: no {path} in {os.getcwd()}", file=sys.stderr)
        return 2
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    today = dt.date.fromisoformat(a.today) if a.today else None
    plan = build_plan(text, ".", today)
    print(json.dumps(plan, indent=1) if a.json else render(plan))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
