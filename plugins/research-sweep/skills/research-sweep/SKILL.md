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

## Files this skill owns

- `<repo>/.claude/roles/research.md` — the coverage-roles registry (per-role wisdom). Created on first run by copying the shared mechanism crew and panel use.
- `<repo>/.claude/research-sweep/log.md` — append-only run log; the substrate the learning loop reads from to graduate stable angles, demote thin ones, retire dead ones, and lift cross-corpus patterns into the repo's `## Research sweep` CLAUDE.md block. The synthesizer seeds it on first run from this skill's shipped `log.md` (a read-only schema seed — never write to the installed copy). **Every `log.md` reference below means this repo file.**

## Coverage roles registry

The sweep is a team of named **coverage roles**, not ad-hoc angles — and that team is *evolving*. The sweep maintains a roles registry at `.claude/roles/research.md` — the **same registry mechanism** dev-crew and brainstorm-panel use, owned here by the sweep. One row per role:

- **name** · one-line **charter** · **when-to-cover** (the trigger / angle that earns it a place — the information-space signal it owns) · **status** (probationary → stable once it has proven useful on three or more runs; demoted to probationary on two thin runs with no fix; retired after three thin runs or three user-cut events at the roster gate) · **learnings** (accumulated bullets: which corpora it paid off on, dedup gotchas, source-trust rules, verification failure modes).

Create the file on the sweep's first run in a repo. The roster is composed **from it first** ("Compose the team" below): stable coverage roles whose when-to-cover fits *this* information space keep their place; gaps become fresh probationary rows. After the sweep, per-role wisdom is written back to each row, and the per-run record goes to `log.md` (see "Learn from the sweep"). Same row schema and probationary→stable lifecycle as crew's `crew.md` and the panel's `panel.md` — the sweep is just the third consumer of one mechanism.

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

## Step 4 — Handle partial failures (thin-agent diagnosis)

Expect 1–2 agents per sweep to fail or return thin results. **Thin is a diagnosis, not a verdict** — borrow crew's capability-vs-ownership framing. Before re-running, classify:

- **slice-thin** — the corpus genuinely has fewer entries than the target. The angle is right; the floor is wrong. Lower the target, merge with an adjacent slice, or accept partial. Note the slice's true depth in the coverage role's `research.md` learnings so the next sweep doesn't over-target it.
- **agent-thin** — the corpus is plentiful but the agent under-delivered. Three sub-causes, three different fixes:
  - *Web tool denied* (WebFetch / WebSearch not permitted) → re-run after the user permits, or mark as best-effort training-data recall.
  - *Prompt under-emphasized volume* → re-run with a stronger "as many as possible" floor and an explicit "do not stop at the canonical few".
  - *Wrong angle* (the role doesn't actually cover this corpus's structure) → **re-role**: mint a probationary corpus-specific coverage role to replace it, the same way crew re-roles on an ownership gap.

For each thin result, decide: re-run, accept partial, or re-role. **Log every thin event** as `thin:` in the run entry (`log.md`) with the diagnosis and the action taken. Two thin runs on the same role with no fix demote it to probationary; three retire it. Recurring re-role events on the same corpus are the mint trigger for a new stable coverage role here.

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

After the sweep, persist learning at **three layers** so the next sweep in this space starts from a better roster — the same correction-driven loop crew and panel run.

### 9a. Per-run log (one entry per sweep)

Append a structured entry to `.claude/research-sweep/log.md` (schema from this skill's shipped `log.md` seed): run-id, question, corpus, roster, partition, per-role volume + thin diagnosis, verifier findings (sample size, fabrications, duplicates, gaps, verdict), dedup hotspots, source-trust, steering (what the user changed at the gate), outcome, and any graduations written back this run. The log is the substrate the graduation pass reads — without it, the registry is a snapshot with no history.

### 9b. Per-role wisdom (back to the registry)

Write what will change a future roster to the role's row in `.claude/roles/research.md`. Don't log routine outcomes:

- **Which angles paid off for THIS corpus** — promote probationary → stable after three or more useful runs.
- **Demote** a stable role after **two thin runs** with no fix (back to probationary, with the diagnosis recorded). **Retire** after three thin runs, or after the user has cut it at the roster gate three times — the default is over-covering here.
- **Dedup gotchas** — which seams collided, which ID scheme prevented it.
- **Source-trust rules** — which registries were authoritative, which fabricated, which needed a second source.
- **Verification failure modes** — what the skeptic caught (a whole agent hallucinating, a class of fabricated URLs), so the verifier's row carries the pattern forward.

The strongest signal is **what the user changed at the roster gate** — an angle they added means the composition missed a cut this space needs; an angle they cut means the default over-covers here. Record those alongside the run.

### 9c. Graduate stable patterns into the repo

When the log shows a pattern holding across **three or more sweeps** in this repo — a coverage role that's always stable here, an authoritative source list, a fabrication-prone source the verifier always flags, an ID-disambiguation rule that always prevents the same seam collision — graduate it into the repo's `CLAUDE.md` under a `## Research sweep` block so future sweeps pick it up without re-deriving:

```markdown
## Research sweep
- **Default roster** for <corpus type>: <coverage roles> + verifier + synthesizer.
- **Authoritative sources** for this corpus: <list>. Always seed coverage there.
- **Untrusted sources**: <list> — verifier must re-check; flag fabricated <field type>.
- **ID rule**: <disambiguation pattern that has prevented the recurring seam collision>.
- **Skip angles**: <coverage roles repeatedly cut at the gate here> — propose only if asked.
```

Then prune the graduated entries from `log.md` so it stays evidence, not history. Periodically (or once the log passes ~30 entries) consolidate: merge duplicates, drop anything superseded, verify referenced paths still exist. The block above is the "always seat here" layer; the registry holds the lifecycle; the log is the evidence trail.

### 9d. Shared-core graduation (when the `roles` plugin is installed)

If shared core role files exist, research lessons that are plainly context-independent become **graduation candidates** for the core (e.g. a `skeptic` verification pattern that also helps the panel and crew) — proposed to the user, never applied silently. Absent them, the row in `research.md` plus the repo's `## Research sweep` block is the whole story.

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
