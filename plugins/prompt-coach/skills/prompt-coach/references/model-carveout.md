# Per-model gate (v1.4+)

A prompting rule is advice about a *model*, and models move. A rule that was
sound guidance for one model can become redundant on the next — or worse, can
teach a habit the newer model already overdoes.

Rules **and tips** carry model-id prefix lists, and the gate runs both ways:

- `obsolete_on` — advice this model has made redundant or harmful. Suppressed.
- `applies_only_on` — advice that is *only* correct on certain models. Inert
  everywhere else.

Both directions are needed because drift runs both ways. A behaviour a model
grew is as real as one it lost, and "don't ask this model to double-check
itself" is advice that would be actively wrong to give someone on Opus 4.8.

## Tips are gated too

A tip is the same advice in a friendlier voice, so a gate that stops the rule
and leaves the tip is not a gate at all. `tip-verify-loop` and
`tip-chain-of-thought` mirror two of the carved rules and are gated with them.

Tips carry their **own** gate fields rather than inheriting from a paired
rule. The `_TIP_ON_MASTERY` pairing is a *learning sequence* — master a
fundamental, unlock an advanced technique — not a claim that the two teach the
same thing. `tip-verify-loop` is unlocked by `no-definition-of-done`, a rule
with no verification content at all, so deriving the gate through that map
would have gated the wrong tip.

Both tip paths are covered: the on-topic matcher and the graduation-unlock
path, which never consults the tip's own heuristic and so needs the gate
applied independently.

## What's carved out, and why

Three rules are suppressed on Claude Opus 5:

| Rule | Why it's off |
|---|---|
| `no-verify-loop` | Opus 5 verifies its own work unprompted. Instructions telling it to verify cause over-verification with no capability gain; Anthropic's migration guidance calls removing them "a delete, not a rewrite". |
| `no-chain-of-thought` | Extended thinking is on by default, so the reasoning already happens. Asking for it *in the response* only converts silent thinking into narration — and over-narration is already the behaviour this model needs tuned down. |
| `no-agents-for-parallel-lookup` | Opus 5 reaches for subagents more readily than Opus 4.8 did, which reverses the rule's premise. The two-or-three lookups it fires on are the exact case the guidance names as *not* worth a subagent: work finishable in a handful of tool calls. |

The shape is the one Anthropic's Opus 5 guidance explicitly asks for — on
self-check instructions it notes this "inverts a standard prompting best
practice … so a prompt library that applies it uniformly needs a carve-out for
this model rather than a global rule."

Local evidence agrees on the first: `no-verify-loop` is the noisiest rule in
the eval set, 10 rows at 0.00 precision.

## What is deliberately kept

`no-adversarial-check` and `workflow-fanout-no-verify` look similar and are
**not** carved out. They ask for a *separate reviewer with its own context*,
which is the writer-verifier split the same guidance endorses — not the
self-check it warns against. The distinction is "don't tell one agent to
double-check itself", not "don't verify".

`no-workflow-for-fanout` is also kept. It requires a fan-out phrase *and* a
count of five or more items, which is the "genuinely independent and
parallelizable" case the guidance still endorses delegating.

## How it behaves

- **Per-model, not a deletion.** On Opus 4.8, Sonnet, Haiku and any
  unrecognized model, the full catalog still runs.
- **Prefix match**, so dated and suffixed ids (`claude-opus-5-20260115`,
  `claude-opus-5[1m]`) resolve.
- **Fail-safe.** The model is read from the transcript's most recent assistant
  turn — the only place the running model is stated, since the
  `UserPromptSubmit` payload doesn't carry it and an env var would report the
  CLI default rather than what `/model` switched to. When it can't be
  determined the carve-out does nothing, so an unknown model can only ever
  leave behaviour exactly as it was.
- **Suppressed before the status machinery**, so a carved rule neither fires
  nor accrues a clean streak. Calling a rule "mastered" when it never got to
  evaluate would be a lie about the evidence.

## Config and inspection

- `model_rules` — **the per-model switch.** A model-id prefix maps to a table
  of ids and `"on"` / `"off"`:

  ```json
  {
    "model_rules": {
      "claude-opus-5":      { "no-verify-loop": "on" },
      "claude-opus-5-2026": { "tip-verify-loop": "off" }
    }
  }
  ```

  `"on"` forces an item back on for that model, overriding a shipped gate;
  `"off"` silences one the shipped gate leaves on. Longest matching prefix
  wins, so a pin for one build beats a family-wide entry. This is the escape
  hatch in both directions — the shipped gates encode what published guidance
  says, and a user's own measurements on their own workload outrank them.
- `model_carveout: false` — evaluate everything regardless of model.
- `model_override: "<model-id>"` — pin the id instead of reading the
  transcript. For tests, and for a harness whose transcript the coach can't
  see.
- `/prompt-coach:config mastery` lists what is switched off and why.

## Other clients

The model is read from the transcript's last assistant turn. Codex rollout
records carry no Claude model id, so `detect_model` returns `""` there and the
gate is a no-op: **a Codex session gets the full catalog.** That is the right
outcome — Codex's default model is not Opus 5, so Opus 5 gates shouldn't apply
— but it is reached by the fail-safe rather than by knowing. The coach cannot
currently tell "Codex on another vendor's model" from "Claude session, first
prompt, no transcript yet"; both get everything. Gating rules for a non-Claude
model would need that model's id plumbed through the Codex normalizer first,
plus behavioural evidence for it of the kind Anthropic publishes for its own.

## Adding a carve-out

Set `obsolete_on` and `obsolete_why` on the `Rule`. Both are required — the
harness fails a rule that carries a carve-out with no rationale, because a
suppression nobody can argue with is one nobody can re-litigate when the next
model lands.

Keep `OPUS_5`-style prefix constants narrow. Every rule carved out here is
carved out on published guidance about *that specific model*. Widening a
carve-out to a whole model generation without equivalent per-model evidence is
how a carve-out turns into a blind spot.
