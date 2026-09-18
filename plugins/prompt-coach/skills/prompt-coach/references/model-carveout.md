# Model carve-out (v1.4+)

A prompting rule is advice about a *model*, and models move. A rule that was
sound guidance for one model can become redundant on the next — or worse, can
teach a habit the newer model already overdoes.

Rules carry an `obsolete_on` list of model-id prefixes. When the session is
running such a model, the rule is suppressed rather than nudged.

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

- `model_carveout: false` — evaluate every rule regardless of model.
- `model_override: "<model-id>"` — pin the id instead of reading the
  transcript. For tests, and for a harness whose transcript the coach can't
  see.
- `/prompt-coach:config mastery` lists what is suppressed and why.

## Adding a carve-out

Set `obsolete_on` and `obsolete_why` on the `Rule`. Both are required — the
harness fails a rule that carries a carve-out with no rationale, because a
suppression nobody can argue with is one nobody can re-litigate when the next
model lands.

Keep `OPUS_5`-style prefix constants narrow. Every rule carved out here is
carved out on published guidance about *that specific model*. Widening a
carve-out to a whole model generation without equivalent per-model evidence is
how a carve-out turns into a blind spot.
