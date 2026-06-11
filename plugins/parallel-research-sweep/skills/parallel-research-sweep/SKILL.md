---
name: parallel-research-sweep
description: Tackle a broad research or exploration question by partitioning it into non-overlapping angles, launching parallel research agents with an identical output contract, then merging their results from the agent transcripts via jq (without dumping the JSONL back into context) and adversarially verifying the synthesized findings. Use when the user asks for something "comprehensive", "exhaustive", "as many as possible", "every X", a "catalog/survey/landscape of Y", or any large-scale gathering task where one agent's coverage would be insufficient and re-outputting each agent's result into a Write call would burn output tokens unnecessarily.
---

# Parallel research sweep

For when the user wants coverage that is *exhaustive*, not representative. Launch N parallel research agents with disjoint scopes and identical contracts, assemble their YAML/JSON outputs into one file via shell redirect — never letting the agent transcripts pass through the main context — then run an adversarial verification pass before trusting the result.

The methodology has two halves: **fan-out** (parallel agents on disjoint slices) and **verification** (adversarial review of what came back). Skipping the second half produces a large but unreliable dataset.

## When to invoke

Strong triggers:
- "as many as possible", "until you run out of tokens", "exhaustive", "comprehensive"
- "catalog of …", "every X by …", "all known …"
- Domain surveys / landscapes: "all open-source tools for X", "every public dataset for Y", "the full competitive landscape of Z"

Weak triggers (consider whether one agent would suffice first):
- "a list of …" with no quantity hint
- "research X" — could be a single Explore agent

Skip this skill if:
- The user wants 5–20 items (single Explore or general-purpose agent is enough)
- The domain is narrow enough that one agent can cover it well
- The data already exists in the repo and just needs querying

## Step 1 — Commit to a schema BEFORE launching agents

The whole pattern collapses if agents return data in subtly different shapes. Lock the schema first.

Decide:
- **Format:** YAML for hand-curatable catalogs; JSON for programmatic consumption.
- **Top-level container:** `items:`, `tools:`, `papers:`, `findings:`, etc. — a single list at the root.
- **Per-entry required fields** (≤ 5; what *must* be present).
- **Per-entry optional fields** (the rest).
- **Disambiguation rule** for IDs when multiple entries share a name (suffix by source/origin).
- **Forbidden behaviors** (no fabrication; omit unknown fields rather than guess).

Write the schema once and **paste it verbatim into every agent prompt**. Identical contracts produce mergeable outputs.

## Step 2 — Partition the topic into non-overlapping angles

The goal is **disjoint coverage**: each agent owns an angle no other agent touches. Aim for 5–7 slices unless the topic is unusually broad. Each slice should be substantial enough that an agent can work meaningfully on it (each agent will spend several minutes), but narrow enough to fit in one agent's working memory.

Good partitioning axes:
- **By source/author** (authors, labs, vendors, repositories)
- **By period / era** (years, decades, technology generations)
- **By geography / scope** (regions, languages, jurisdictions)
- **By category / kind** (subtypes, mediums, problem classes)
- **By corpus** (one source registry vs another, for survey-style tasks)

Bad partitioning:
- Overlapping slices (two agents covering the same subtopic → duplicate IDs and merge work)
- Slices that are too small (5 entries each = overhead dominates)
- Slices defined by Claude's interest rather than the domain (arbitrary cuts)

## Step 3 — Launch agents in parallel, in a single message

Use multiple `Agent` tool calls in one message so they run concurrently. Each prompt MUST include:

1. **One-line context** about what the project is and why the data is needed.
2. **The exact schema**, verbatim, in a YAML fenced block.
3. **The slice this agent owns** (source list / corpus / era — be precise).
4. **Source guidance** (specific URLs, registries, categories, search strategies).
5. **Verification rules**: "Only include an entry if you can verify its required fields from a source. Omit unverifiable fields — do NOT fabricate."
6. **Output requirement**: "Return YAML ONLY in a `\`\`\`yaml ... \`\`\`` code block — no prose, no preamble." The code-block wrapper is what makes Step 5 extraction trivial.
7. **Volume target**: a numeric floor ("at least 60 entries"), so the agent doesn't stop at the famous few.
8. **ID uniqueness rule** (disambiguate within the agent's output; cross-agent dedup is a later step).

Run agents with `run_in_background: true`. Don't poll — completion notifications fire automatically.

## Step 4 — Handle partial failures

Expect 1–2 agents per sweep to fail or return thin results. Common causes:
- **Web tool denied** (WebFetch / WebSearch not permitted). Sometimes recoverable by re-running after the user permits; sometimes the agent must work from training-data recall alone (mark these results as best-effort).
- **Slice too sparse** — the topic genuinely doesn't have N entries. Lower the target or merge with an adjacent slice.
- **Agent exits early** — usually a prompt that didn't sufficiently emphasize "as many as possible".

For each failure, decide: re-run, accept partial output, or skip. Record the decision in CLAUDE.md if there is one.

## Step 5 — Extract via jq, never via Read

Agent results sit in JSONL transcripts at:

```
~/.claude/projects/<encoded-cwd>/<session-id>/subagents/agent-<agent-id>.jsonl
```

(Resolve `<encoded-cwd>` and `<session-id>` from the task notification path; both are also visible in `ls ~/.claude/projects/`.)

**Do not Read these files** — they're full transcripts and can blow out context. Instead, extract just the final assistant message's text, pipe through awk to strip the YAML fence, and redirect to the catalog file. The shell never echoes the data back to you:

```bash
TASKS=~/.claude/projects/<encoded-cwd>/<session-id>/subagents
OUT=data/<catalog>.yaml

{
  echo "# <catalog name> — seeded by N parallel research agents on $(date +%F)"
  echo "# Schema in CLAUDE.md."
  echo ""
  echo "<top-level-key>:"

  for id in <agent-id-1> <agent-id-2> <agent-id-3>; do
    F="$TASKS/agent-$id.jsonl"
    [ -f "$F" ] || continue
    echo ""
    echo "  # === agent $id ==="
    jq -rs '[.[] | select(.type == "assistant")] | last | .message.content[]? | select(.type == "text") | .text' "$F" \
      | awk '/^```yaml/{flag=1; next} /^```$/{flag=0; next} flag'
  done
} > "$OUT"

# Sanity checks — fine to surface these
wc -l "$OUT"
grep -c '^  - id:' "$OUT"
head -10 "$OUT"
```

The `jq -rs` slurps the JSONL into an array, picks the **last** assistant message (the agent's final result), pulls the text content, then awk extracts the YAML fenced block. Section comments per agent (`# === agent <id> ===`) make later debugging easy.

## Step 6 — Merge and commit immediately

Before doing anything else:
- `wc -l` and `grep -c '^  - id:'` to confirm the merge produced what you expect.
- `head` to spot-check formatting.
- Commit the file to git so it survives context compaction. The pattern of "agents finish → assistant loses results in a compaction → re-run agents" is the single most expensive failure mode of this skill.

## Step 7 — Adversarially verify the synthesis

This is the half people skip. A large dataset that nobody pressure-tested is a liability, not an asset. Run a dedicated verification pass — ideally a *fresh* agent that did not produce the data, so it has no stake in defending it.

Give the verifier an adversarial mandate:
- **Spot-check a random sample** of entries against primary sources. A 10–20% sample surfaces systemic problems (a whole agent that hallucinated) faster than reading everything.
- **Hunt for fabrication.** Agents without web access produce plausible-looking but invented values — especially URLs, dates, and IDs. Flag anything that can't be traced to a source.
- **Check the cross-agent seams.** Duplicates and contradictions cluster where two slices nearly touched. Look there first.
- **Test the volume claim.** Did the sweep actually hit the target, or did a thin agent get papered over? Per-agent counts reveal which slices under-delivered.
- **Find the gaps.** What obvious entries are *missing*? Missing data is as much a coverage failure as wrong data.

Capture the verifier's findings as concrete fix items, not a vibe. Then act on them.

## Step 8 — Dedup, normalize, verify URLs (separate passes)

These are follow-up tickets, not part of the sweep:
- **Dedup** across agents (cross-agent IDs may collide if partitioning wasn't perfect).
- **Naming / punctuation normalization** (agents produce inconsistent typography).
- **URL/external-reference verification** if the schema includes external links — agents without web access will fabricate plausible-looking URLs.
- **Coverage tracking** — if the catalog will grow over multiple iterations, set up a per-entry tracking sidecar so reruns target what's still missing.

## Anti-patterns

- **Don't have the assistant re-output the entire YAML into a Write call** to produce the catalog. With 600+ entries that's tens of thousands of output tokens and several minutes of wall time. Use the jq-extract pipeline.
- **Don't read agent JSONL transcripts directly.** They contain the full conversation including tool I/O and can be enormous.
- **Don't reuse the same `Agent` ID across reruns.** Spawn fresh agents — they get new transcript files; old transcripts stay readable for the diff if you want one.
- **Don't trust agent-produced URLs or facts without verification.** Agents lacking web access during the sweep will produce plausible-looking but fabricated values.
- **Don't skip the volume target.** Without "aim for at least N entries", agents stop at the canonical few examples and the sweep underdelivers.
- **Don't skip Step 7.** Fan-out without adversarial verification gives you confident-looking garbage at scale.

## Worked example (compressed)

User: "build a catalog of every open-source vector database we can find."

1. Schema: YAML, top-level `databases:`, fields `id, name, language, license, source_url, key_features, first_release`.
2. Partition: by language/ecosystem (Rust / C++ / Go / Python / JVM) plus one slice for "embedded/edge". Six slices, disjoint by implementation language.
3. Launch six `Agent` calls in one message, each with the full schema and its slice's scope.
4. One agent failed (web access denied). Re-ran after permissions, +12 verified entries.
5. Extracted with the jq+awk pipeline → 140 entries in one file; committed immediately.
6. Verification agent spot-checked 20 entries, caught two fabricated `source_url`s and one duplicate across the Go/Rust seam → fixed.
7. Ran dedup/normalization as separate tickets.
