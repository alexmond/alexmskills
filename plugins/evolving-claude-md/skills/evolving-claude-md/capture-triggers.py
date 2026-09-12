#!/usr/bin/env python3
"""Capture triggers — the write path the audit never had (issue #37, #40).

Every other hook in this plugin is pruning pressure on entries that already
exist. These two are the only mechanisms that fire when the log was never
written to:

  stop    — Stop hook. If this session made commits and edited files but never
            touched CLAUDE.md (and added nothing under docs/decisions/), block
            the stop ONCE with a prompt to nominate 0-3 entries. Zero is
            explicitly allowed — filler is worse than silence.
  commit  — PostToolUse(Bash) hook. If the command was a git commit and the
            fresh commit message contains gotcha-shaped language, emit
            additionalContext suggesting the promotion while the context is
            hot — far higher yield than asking at session end.

Both ship DEFAULT-OFF and are enabled per repo (or globally) in
.claude/evolving-claude-md/config.json:

    {"capture_prompt": "session-end", "commit_mining": true}

The 59%-fire-rate lesson from the retired gotchas check applies: these stay
off until the calibration pass (#43) has measured their noise on real repos.

Routing rule carried in the prompts (one capture engine, two destinations):
repo-durable, team-relevant learnings become D&L entries; machine-personal or
private ones are saved via the learn-on-failure skill to user memory.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

CONFIG_REL = os.path.join(".claude", "evolving-claude-md", "config.json")
STATE_DIR = os.path.join(".claude", "evolving-claude-md")
SPOOL_DIR = os.path.join(STATE_DIR, "incoming")
# Substring that identifies a spool write in a transcript line, so a lane that
# already spooled this session is not prompted again.
SPOOL_MARK = "evolving-claude-md/incoming"

DEFAULTS = {
    "capture_prompt": "off",   # "off" | "session-end"
    "commit_mining": False,
    # Where a lane's nominations go. "auto" spools only from a linked git
    # worktree — the signal that this session is one of several running at
    # once. "branch" also treats any non-default branch as a lane (for fleets
    # that run parallel branches in one tree); "off" restores the old
    # everyone-writes-CLAUDE.md behaviour.
    "lane_spool": "auto",      # "auto" | "branch" | "off"
}

# Gotcha-shaped language in commit messages — each phrase is a finished
# learning that needed only a date and a tag (#37 proposal 5's examples).
GOTCHA_RE = re.compile(
    r"found the hard way|turns out|silently|reports success"
    r"|does n[o']t actually|doesn't actually|was wrong|hid behind"
    r"|root cause|the fix was|off[- ]by[- ]one|red herring",
    re.I,
)

ROUTING = (
    "Route each entry: repo-durable and team-relevant -> a D&L entry in "
    "CLAUDE.md (dated, topic-tagged, <=200 chars, lead with the why); "
    "machine-personal or private -> save via the learn-on-failure skill to "
    "user memory instead. Zero entries is a valid answer - do not invent "
    "filler."
)


BAR = (
    "The bar, applied BEFORE nominating anything: write each candidate as a "
    "sentence that is true about this repo TOMORROW, then name what a future "
    "session would do differently knowing it. If the only true sentence is "
    "'we did X', there is no entry - the changelog, the tickets and git log "
    "already hold that. A delivery earns an entry only when it TAUGHT "
    "something a reader cannot see in the code: a constraint, a trap, a "
    "reversal, a rule. Most sessions nominate zero, and zero is the correct "
    "answer to a session that merely shipped."
)


def _git_line(args: list[str]) -> str:
    """Best-effort single-line git read, stripped. Distinct from `_git` below,
    which returns raw stdout because its caller reads whole commit messages —
    two same-named helpers silently shadowed each other here once, and the
    unstripped branch name became a spool path with a trailing dash."""
    try:
        out = subprocess.run(["git"] + args, capture_output=True, text=True,
                             timeout=5)
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        return ""


def default_branch() -> str:
    ref = _git_line(["symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"])
    if ref.startswith("origin/"):
        return ref.split("/", 1)[1]
    for cand in ("main", "master"):
        if _git_line(["rev-parse", "--verify", "--quiet", cand]):
            return cand
    return "main"


def lane_context(cfg: dict) -> tuple[bool, str]:
    """(is_lane, lane_id) — is this session one of several that would collide?

    A lane is a parallel worker whose CLAUDE.md edit lands on its own branch
    and has to be merged against every sibling's. Measured on one 2,400-commit
    repo running worktree lanes: 86 of 257 non-merge CLAUDE.md edits were made
    on lane branches, and all 50 merge commits touching the file were
    resolving them.

    The default predicate is a LINKED WORKTREE, not merely a non-default
    branch: an ordinary feature branch is one writer at a time and merges
    cleanly, so diverting it would be a false positive. Repos that run
    parallel branches in a single tree opt in with lane_spool="branch".
    """
    mode = cfg.get("lane_spool", "auto")
    if mode == "off":
        return False, ""
    git_dir = _git_line(["rev-parse", "--git-dir"])
    if not git_dir:
        return False, ""            # not a git repo — nothing to collide with
    common = _git_line(["rev-parse", "--git-common-dir"])
    linked = bool(common) and os.path.abspath(git_dir) != os.path.abspath(common)
    branch = _git_line(["rev-parse", "--abbrev-ref", "HEAD"])
    is_lane = linked or (mode == "branch"
                         and branch not in ("", "HEAD", default_branch()))
    lane_id = re.sub(r"[^A-Za-z0-9._-]+", "-", branch or "") or "lane"
    return is_lane, lane_id[:60]


def spool_path(lane_id: str) -> str:
    return os.path.join(SPOOL_DIR, f"{lane_id}.md")


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    for path in (os.path.join(os.path.expanduser("~"), CONFIG_REL), CONFIG_REL):
        try:
            with open(path) as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict):
                cfg.update({k: v for k, v in loaded.items() if k in DEFAULTS})
        except (OSError, ValueError):
            continue
    return cfg


def _git(args: list[str]) -> str:
    try:
        r = subprocess.run(["git", *args], capture_output=True, text=True, timeout=3)
        return r.stdout if r.returncode == 0 else ""
    except Exception:
        return ""


def session_activity(transcript_path: str) -> dict:
    """Stream the session transcript once; return what kind of work happened.

    Line-by-line with a byte cap so a huge transcript can't blow the hook's
    time budget — the signals we need all fit in cheap substring checks.
    """
    act = {"commits": 0, "edits": 0, "claude_md_touched": False,
           "decisions_added": False, "spool_touched": False}
    budget = 8 * 1024 * 1024
    try:
        with open(transcript_path, errors="replace") as fh:
            for line in fh:
                budget -= len(line)
                if budget < 0:
                    break
                if '"name": "Bash"' in line or '"name":"Bash"' in line:
                    if "git commit" in line:
                        act["commits"] += 1
                elif '"name": "Edit"' in line or '"name": "Write"' in line \
                        or '"name":"Edit"' in line or '"name":"Write"' in line:
                    act["edits"] += 1
                    if "CLAUDE.md" in line:
                        act["claude_md_touched"] = True
                    if SPOOL_MARK in line:
                        act["spool_touched"] = True
                    if "docs/decisions/" in line:
                        act["decisions_added"] = True
    except OSError:
        pass
    return act


def run_stop(payload: dict, cfg: dict) -> int:
    if cfg.get("capture_prompt") != "session-end":
        return 0
    session_id = payload.get("session_id", "")
    transcript = payload.get("transcript_path", "")
    if not session_id or not transcript:
        return 0
    # Fire at most once per session, or the blocked stop re-triggers us forever.
    marker = os.path.join(STATE_DIR, f".capture-{session_id}")
    if os.path.exists(marker):
        return 0
    if not os.path.exists("CLAUDE.md"):
        return 0
    act = session_activity(transcript)
    if not act["commits"] or not act["edits"]:
        return 0
    if act["claude_md_touched"] or act["decisions_added"] \
            or act["spool_touched"]:
        return 0
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        open(marker, "w").close()
    except OSError:
        return 0
    is_lane, lane_id = lane_context(cfg)
    if is_lane:
        dest = (
            f"You are on a LANE (`{lane_id}`), so do NOT edit CLAUDE.md — "
            f"parallel lanes editing one file collide at merge, and every "
            f"such merge is a conflict somebody resolves by hand. Append "
            f"nominations to `{spool_path(lane_id)}` instead: one file per "
            f"lane, so distinct paths merge cleanly. The integrator folds the "
            f"spool into CLAUDE.md on the default branch."
        )
    else:
        dest = ROUTING
    json.dump(
        {
            "decision": "block",
            "reason": (
                f"[evolving-claude-md capture] This session committed "
                f"{act['commits']} time(s) and edited files, but CLAUDE.md was "
                f"never touched and no docs/decisions/ file was added. Before "
                f"stopping: nominate 0-3 durable learnings from this session. "
                + BAR + " " + dest
                + " Then stop; this prompt fires once per session."
            ),
        },
        sys.stdout,
    )
    return 0


def run_commit(payload: dict, cfg: dict) -> int:
    if not cfg.get("commit_mining"):
        return 0
    command = (payload.get("tool_input") or {}).get("command", "")
    if "git commit" not in command:
        return 0
    if not os.path.exists("CLAUDE.md"):
        return 0
    msg = _git(["log", "-1", "--format=%B"])
    if not msg:
        return 0
    hits = sorted({m.group(0).lower() for m in GOTCHA_RE.finditer(msg)})
    if not hits:
        return 0
    subject = msg.strip().splitlines()[0][:70]
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": (
                    f"[evolving-claude-md capture] The commit just made "
                    f"(\"{subject}\") contains gotcha-shaped language "
                    f"({', '.join(repr(h) for h in hits[:3])}) — a finished "
                    f"learning that needs only a date and a tag. Offer to "
                    f"promote it now, while the context is hot. " + ROUTING
                ),
            }
        },
        sys.stdout,
    )
    return 0


def _bullets(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines()
            if re.match(r"^\s*[-*]\s+\S", ln)]


# Two lanes describing ONE lesson rarely word it the same way — "lanes must
# not edit the manifest" vs "the manifest must never be edited by a lane"
# share only 25% of their raw words. Light stemming plus dropping the modal
# glue that every rule sentence contains lifts that pair to 75%, which is the
# difference between the fold catching duplicates and not.
_STOP = {"this", "that", "with", "from", "into", "when", "then", "than",
         "they", "them", "have", "been", "were", "will", "only", "must",
         "never", "always", "should", "would", "which", "while", "because",
         "there", "their", "what", "each", "also", "does", "doesn"}


def _stem(w: str) -> str:
    for suf in ("ing", "ed", "ly", "es", "s"):
        if w.endswith(suf) and len(w) > len(suf) + 3:
            return w[: -len(suf)]
    return w


def _words(s: str) -> set[str]:
    return {_stem(w) for w in re.findall(r"[a-z0-9]{4,}", s.lower())
            if w not in _STOP}


def run_fold(_payload: dict, _cfg: dict) -> int:
    """Single-writer fold — print every lane's spooled nominations at once.

    Folding is deliberately a main-session step on the default branch and NOT
    another hook. N lanes working one epic learn the same lesson N times, and
    only a reader holding all of them at once can dedup, apply the bar, and
    write the one entry that survives. Nothing is written here: the fold
    itself is an ordinary CLAUDE.md edit (so the lint hook gates its format),
    after which the spooled files are deleted.
    """
    if not os.path.isdir(SPOOL_DIR):
        print(f"spool empty — no {SPOOL_DIR}/. Lanes write there at session end.")
        return 0
    files = sorted(f for f in os.listdir(SPOOL_DIR) if f.endswith(".md"))
    if not files:
        print(f"spool empty — {SPOOL_DIR}/ has no .md files.")
        return 0

    per_lane: list[tuple[str, list[str]]] = []
    for name in files:
        try:
            with open(os.path.join(SPOOL_DIR, name), encoding="utf-8",
                      errors="replace") as fh:
                per_lane.append((name[:-3], _bullets(fh.read())))
        except OSError:
            continue

    total = sum(len(b) for b in (x[1] for x in per_lane))
    print(f"Spooled nominations: {total} from {len(per_lane)} lane(s)\n")
    for lane, bullets in per_lane:
        print(f"── {lane} ({len(bullets)})")
        for b in bullets:
            print(f"   {b[:300]}")
        print()

    # Cross-lane near-duplicates: the normal case, and the whole reason the
    # fold exists. Jaccard over 4+ char words; same-lane pairs are skipped
    # because a lane repeating itself is that lane's problem, not a merge one.
    dupes = []
    flat = [(lane, b) for lane, bs in per_lane for b in bs]
    for i in range(len(flat)):
        for j in range(i + 1, len(flat)):
            if flat[i][0] == flat[j][0]:
                continue
            a, b = _words(flat[i][1]), _words(flat[j][1])
            if not a or not b:
                continue
            jac = len(a & b) / len(a | b)
            if jac >= 0.5:
                dupes.append((jac, flat[i], flat[j]))
    if dupes:
        print(f"⚠ {len(dupes)} near-duplicate pair(s) across lanes — fold each "
              f"to ONE entry:")
        for jac, (la, ba), (lb, bb) in sorted(dupes, reverse=True)[:10]:
            print(f"   [{jac:.0%}] {la}: {ba[:110]}")
            print(f"          {lb}: {bb[:110]}")
    else:
        print("No cross-lane duplicates detected.")

    print(
        "\nFold as ONE writer, on the default branch: apply the bar (true "
        "about the repo tomorrow + what a session does differently), merge "
        "the duplicates above into single entries, write them into CLAUDE.md "
        "in D&L format (dated, topic-tagged, <=200 chars), then delete the "
        f"folded files from {SPOOL_DIR}/."
    )
    return 0


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    payload = {}
    # `fold` is run by hand; reading a tty here would hang the command.
    if not sys.stdin.isatty():
        try:
            payload = json.load(sys.stdin)
        except Exception:
            payload = {}
    cfg = load_config()
    if mode == "stop":
        return run_stop(payload, cfg)
    if mode == "commit":
        return run_commit(payload, cfg)
    if mode == "fold":
        return run_fold(payload, cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
