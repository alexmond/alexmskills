---
name: research-sweep
description: The "discover" orchestrator on the marketplace's shared role substrate — the counterpart to dev-crew (deliver) and brainstorm-panel (decide). Compose a task-fit team of coverage roles for an information space, partition it into non-overlapping angles, fan the roles out as parallel research agents under one output contract, merge their results from the agent transcripts via jq (without dumping the JSONL back into context), dedup, and adversarially verify the synthesized findings. Use when the user asks for something "comprehensive", "exhaustive", "as many as possible", "every X", a "catalog/survey/landscape of Y", or any large-scale gathering task where one agent's coverage would be insufficient and re-outputting each agent's result into a Write call would burn output tokens unnecessarily.
argument-hint: "[research or catalog question]"
---

# Parallel research sweep

> **Try it:** `/research-sweep:research-sweep every open-source vector database` — or say "give me an exhaustive catalog of public datasets for X".

This is the **discover** orchestrator — one of three that run on the same shared role substrate. Where dev-crew **delivers** a gated artifact (roles related by *handoff*) and brainstorm-panel **decides** a judgment (roles related by *disagreement*), the sweep **discovers** verified, cited findings: it composes a task-fit team of *coverage roles* for an information space, fans them out so each owns a disjoint angle (roles related by *independence* — no clash, no overlap), dedups, and adversarially verifies. The three chain — research discovers the facts, panel decides what to do, crew delivers it — and they share roles: the same `skeptic` is a panel seat, a crew adversarial check, *and this skill's fact-verifier*. (See the Role System architecture for how that shared substrate works across all three.)

For when the user wants coverage that is *exhaustive*, not representative. Compose the coverage roles, launch them as N parallel research agents with disjoint scopes and identical contracts, assemble their YAML/JSON outputs into one file via shell redirect — never letting the agent transcripts pass through the main context — then run an adversarial verification pass before trusting the result.

The methodology has two halves: **fan-out** (parallel coverage roles on disjoint slices) and **verification** (adversarial review of what came back). Skipping the second half produces a large but unreliable dataset.

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

## Coverage roles registry

The sweep is a team of named **coverage roles**, not ad-hoc angles — and that team is *evolving*. The sweep maintains a roles registry at `.claude/roles/research.md` — the **same registry mechanism** dev-crew and brainstorm-panel use, owned here by the sweep. One row per role:

- **name** · one-line **charter** · **when-to-cover** (the trigger / angle that earns it a place — the information-space signal it owns) · **status** (probationary → stable once it has proven useful on three or more runs) · **learnings** (accumulated bullets: which corpora it paid off on, dedup gotchas, source-trust rules, verification failure modes).

Create the file on the sweep's first run in a repo. The roster is composed **from it first** ("Compose the team" below): stable coverage roles whose when-to-cover fits *this* information space keep their place; gaps become fresh probationary rows. After the sweep, per-role wisdom is written back to each row (see "Learn from the sweep"). Same row schema and probationary→stable lifecycle as crew's `crew.md` and the panel's `panel.md` — the sweep is just the third consumer of one mechanism.

### Coverage roles — the searchers, by angle

Coverage roles are the searchers, each owning one angle on the information space. Seed / standard archetypes (each an evolving role, not a fixed cut):

- **`entity-scout`** — partition by the actors in the space: authors, labs, vendors, repositories, organizations.
- **`timeline-scout`** — partition by period: years, decades, technology generations, eras.
- **`source-scout`** — partition by where evidence lives: registries, papers, docs, code hosts, news.
- **`container-scout`** — partition by corpus: one source registry vs another, one index vs another.

When the information space needs an angle no archetype covers, **mint a probationary corpus-specific coverage role** (e.g. `citation-graph-scout` for an academic corpus, `jurisdiction-scout` for a legal one) — the crew seed+mint model: compose from stable roles first, mint the gaps as new probationary rows in `research.md`.

Plus **two persistent roles**, on every sweep:

- **verifier** — this *is* the shared **`skeptic`** role: adversarial fact-checking and primary-source verification (Step 7). It produces no entries; it pressure-tests the ones the coverage roles found.
- **synthesizer** — dedup across roles + assemble the cited findings into the single result (Steps 5–6, 8). It owns the seams where coverage roles nearly touched.

### Compose the team from the information space

Derive the coverage angles from the **information space** = the task + the corpus — the way dev-crew composes from the delivery target and the panel from quality axes. Propose from `research.md` **first** (stable coverage roles whose when-to-cover matches this space), then mint the gaps as probationary rows. The verifier and synthesizer are always on the team.

Present the proposed sweep team as an **editable roster the user signs off on before anything fans out** — a roster checkpoint, exactly like crew's and panel's. List each coverage role numbered, with its charter and the slice / angle it will own, then the verifier and synthesizer. Invite changes (add, remove, swap, retune an angle) and wait for approval before launching. A removed coverage role is a coverage gap — say what it gives up so the user removes it knowingly, then comply.

**Emit a Fable suggestion with the roster (opt-in).** A sweep is *verification-bound* — the coverage
scouts are mechanical breadth, so keep them on Opus/Sonnet; the depth pays on checking, not gathering. So
when you present the roster, also offer to run the **skeptic-verifier** (and optionally the
**synthesizer**) on the Fable tier — that is where harder reasoning improves the result. Always opt-in,
never default: note Fable ≈ 2× Opus quota (API-rate credits after 2026-06-22) and that it can silently
reroute to Opus on security/bio topics. For example:

> Fable (optional): run the *verifier* (and the *synthesizer*) on Fable for a harder check — the scouts
> stay on Opus. ~2× cost, opt-in — or skip.

> Proposed sweep team for this information space:
> 1. **container-scout** — one source registry per agent. *The corpus splits cleanly across registries.*
> 2. **timeline-scout** — pre-2015 / 2015–2020 / post-2020. *The space has a strong temporal spread.*
> 3. **citation-graph-scout** *(new, probationary)* — follow references out of the seed papers. *No archetype covers cross-references here.*
> + **verifier** (shared `skeptic`) — adversarial fact-check of the merged result.
> + **synthesizer** — dedup across angles, assemble the cited output.
>
> Add, remove, swap, or retune any angle — or say go and I'll fan them out.

### Shared-core integration

If shared core role files exist (`.claude/roles/<role>.md`, provided by the optional `roles` plugin) — e.g. a shared `skeptic` that the panel and crew also link to — link the matching `research.md` row to its core role **by name**, and treat research lessons as **graduation candidates** for the core: proposed to the user, never applied silently. Absent them, `research.md` is fully self-sufficient — nothing about the sweep depends on the plugin (no-downgrade). See the Role System architecture for how the shared substrate and graduation work across the three orchestrators.

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

The coverage roles you composed map onto the partition: each role owns an angle no other agent touches. The goal is **disjoint coverage**. Aim for 5–7 slices unless the topic is unusually broad. Each slice should be substantial enough that an agent can work meaningfully on it (each agent will spend several minutes), but narrow enough to fit in one agent's working memory.

Good partitioning axes (these *are* the coverage-role archetypes):
- **By source/author** (`entity-scout`: authors, labs, vendors, repositories)
- **By period / era** (`timeline-scout`: years, decades, technology generations)
- **By source type** (`source-scout`: registries, papers, docs, code hosts)
- **By geography / scope** (regions, languages, jurisdictions — often a minted corpus-specific role)
- **By category / kind** (subtypes, mediums, problem classes)
- **By corpus** (`container-scout`: one source registry vs another, for survey-style tasks)

Bad partitioning:
- Overlapping slices (two agents covering the same subtopic → duplicate IDs and merge work)
- Slices that are too small (5 entries each = overhead dominates)
- Slices defined by Claude's interest rather than the domain (arbitrary cuts)

## Step 3 — Launch agents in parallel, in a single message

Use multiple `Agent` tool calls in one message so they run concurrently — one call per coverage role on the approved roster. Each prompt MUST include:

1. **One-line context** about what the project is and why the data is needed.
2. **The exact schema**, verbatim, in a YAML fenced block.
3. **The slice this agent owns** (the coverage role's angle: source list / corpus / era — be precise).
4. **Source guidance** (specific URLs, registries, categories, search strategies).
5. **Verification rules**: "Only include an entry if you can verify its required fields from a source. Omit unverifiable fields — do NOT fabricate."
6. **Output requirement**: "Return YAML ONLY in a `\`\`\`yaml ... \`\`\`` code block — no prose, no preamble." The code-block wrapper is what makes Step 5 extraction trivial.
7. **Volume target**: a numeric floor ("at least 60 entries"), so the agent doesn't stop at the famous few.
8. **ID uniqueness rule** (disambiguate within the agent's output; cross-agent dedup is the synthesizer's later step).

Run agents with `run_in_background: true`. Don't poll — completion notifications fire automatically.

## Step 4 — Handle partial failures

Expect 1–2 agents per sweep to fail or return thin results. Common causes:
- **Web tool denied** (WebFetch / WebSearch not permitted). Sometimes recoverable by re-running after the user permits; sometimes the agent must work from training-data recall alone (mark these results as best-effort).
- **Slice too sparse** — the topic genuinely doesn't have N entries. Lower the target or merge with an adjacent slice (and note the angle's thinness in its `research.md` row).
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

This is the synthesizer's first job. Before doing anything else:
- `wc -l` and `grep -c '^  - id:'` to confirm the merge produced what you expect.
- `head` to spot-check formatting.
- Commit the file to git so it survives context compaction. The pattern of "agents finish → assistant loses results in a compaction → re-run agents" is the single most expensive failure mode of this skill.

## Step 7 — Adversarially verify the synthesis

This is the verifier role (the shared `skeptic`) — the half people skip. A large dataset that nobody pressure-tested is a liability, not an asset. Run a dedicated verification pass — ideally a *fresh* agent that did not produce the data, so it has no stake in defending it.

Give the verifier an adversarial mandate:
- **Spot-check a random sample** of entries against primary sources. A 10–20% sample surfaces systemic problems (a whole agent that hallucinated) faster than reading everything.
- **Hunt for fabrication.** Agents without web access produce plausible-looking but invented values — especially URLs, dates, and IDs. Flag anything that can't be traced to a source.
- **Check the cross-agent seams.** Duplicates and contradictions cluster where two slices nearly touched. Look there first.
- **Test the volume claim.** Did the sweep actually hit the target, or did a thin agent get papered over? Per-agent counts reveal which slices under-delivered.
- **Find the gaps.** What obvious entries are *missing*? Missing data is as much a coverage failure as wrong data.

Capture the verifier's findings as concrete fix items, not a vibe. Then act on them.

## Step 8 — Dedup, normalize, verify URLs (separate passes)

These are the synthesizer's follow-up tickets, not part of the sweep proper:
- **Dedup** across agents (cross-agent IDs may collide if partitioning wasn't perfect).
- **Naming / punctuation normalization** (agents produce inconsistent typography).
- **URL/external-reference verification** if the schema includes external links — agents without web access will fabricate plausible-looking URLs.
- **Coverage tracking** — if the catalog will grow over multiple iterations, set up a per-entry tracking sidecar so reruns target what's still missing.

## Step 9 — Learn from the sweep

After the sweep, persist per-role wisdom to `.claude/roles/research.md` rows so the next sweep in this space starts from a better roster — the same correction-driven loop crew and panel run. Don't log routine outcomes; record what will change a future roster:

- **Which angles paid off for THIS corpus** — which coverage roles delivered, which came back thin (and whether the thinness was the slice or the agent). Promote a coverage role probationary → stable after three or more useful runs.
- **Dedup gotchas** — which seams collided, which ID scheme prevented it.
- **Source-trust rules** — which registries were authoritative, which fabricated, which needed a second source.
- **Verification failure modes** — what the skeptic caught (a whole agent hallucinating, a class of fabricated URLs), so the verifier's row carries the pattern forward.

The strongest signal is **what the user changed at the roster gate** — an angle they added means the composition missed a cut this space needs; an angle they cut means the default over-covers here. Record those alongside the run.

If shared core role files exist, research lessons that are plainly context-independent become **graduation candidates** for the core (e.g. a `skeptic` verification pattern that also helps the panel and crew) — proposed to the user, never applied silently. Absent them, the row in `research.md` is the whole story.

## Anti-patterns

- **Don't have the assistant re-output the entire YAML into a Write call** to produce the catalog. With 600+ entries that's tens of thousands of output tokens and several minutes of wall time. Use the jq-extract pipeline.
- **Don't read agent JSONL transcripts directly.** They contain the full conversation including tool I/O and can be enormous.
- **Don't reuse the same `Agent` ID across reruns.** Spawn fresh agents — they get new transcript files; old transcripts stay readable for the diff if you want one.
- **Don't trust agent-produced URLs or facts without verification.** Agents lacking web access during the sweep will produce plausible-looking but fabricated values.
- **Don't skip the volume target.** Without "aim for at least N entries", agents stop at the canonical few examples and the sweep underdelivers.
- **Don't skip Step 7.** Fan-out without adversarial verification gives you confident-looking garbage at scale.
- **Don't fan out before the roster is approved.** Composing from `research.md` and gating the team at the roster checkpoint is what keeps the angles disjoint and the corpus-fit roles in the pool.

## Worked example (compressed)

User: "build a catalog of every open-source vector database we can find."

1. Compose from `research.md`: stable `container-scout` (one ecosystem per agent) fits; mint a probationary `by-language` angle for this corpus. Verifier (`skeptic`) + synthesizer seated by default. Roster shown, user approves.
2. Schema: YAML, top-level `databases:`, fields `id, name, language, license, source_url, key_features, first_release`.
3. Partition: by language/ecosystem (Rust / C++ / Go / Python / JVM) plus one slice for "embedded/edge". Six slices, disjoint by implementation language.
4. Launch six `Agent` calls in one message, each with the full schema and its slice's scope.
5. One agent failed (web access denied). Re-ran after permissions, +12 verified entries.
6. Extracted with the jq+awk pipeline → 140 entries in one file; committed immediately.
7. Verification agent spot-checked 20 entries, caught two fabricated `source_url`s and one duplicate across the Go/Rust seam → fixed.
8. Ran dedup/normalization as separate tickets.
9. Wrote back to `research.md`: `by-language` paid off (→ probationary, 1 useful run); the Go/Rust seam is the dedup hotspot for this corpus; the registry it pulled `source_url`s from fabricates under load — the verifier's row now flags it.
