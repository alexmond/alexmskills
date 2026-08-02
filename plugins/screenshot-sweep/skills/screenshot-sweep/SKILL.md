---
name: screenshot-sweep
description: >-
  Use whenever a screenshot is captured or supplied — a bug report, a Playwright
  capture, a design review, a "does this look right". Read the WHOLE image, not
  just the thing you came for: sweep it against the defect checklist below, file
  what you find, and add it to the todo list. When a defect is later reported
  that this sweep should have caught, append the miss to the Misses log and add
  the check that would have caught it, so the checklist grows tighter over time.
---

# Screenshot sweep

> Not `screenshot-tour`, which *produces* a presentation deck of a product. This
> one *audits* a capture you already have, for defects.

A screenshot is a free full-page audit that most people spend on one bug.

You were sent the image to look at one thing. Look at everything, because the
cost of the extra look is seconds and the cost of missing it is that the user
finds it later and reports it — which is strictly more expensive for them than
for you.

## The rule

**One screenshot, one sweep, then answer the question you were asked.**

Do the sweep first. If you answer the question first you will stop looking, and
the sweep will not happen.

Anything you find that is *not* what you were asked about:

1. **File it.** A real defect with a real symptom gets an issue, with the
   evidence you can see and — where you can get it — the measurement behind it.
2. **Add it to the todo list**, so it survives the conversation.
3. **Do not fix it now** unless it is a one-liner adjacent to the work in hand.
   Scope creep in a bug fix is its own defect. Say what you found and move on.

Do NOT file:

- Things you *suspect* but cannot see in the image. "This might be slow" is not
  a screenshot finding.
- Aesthetic preferences. "I would have used more padding" is not a defect.
- The same thing twice — check open issues first.

## The checklist

Run every line against every screenshot. Most will be "fine" in a second.

**Legibility**
- Any text you have to work to read? Low-contrast text on a tinted or coloured
  background is the classic. Measure before claiming — see "measure, don't
  eyeball" below.
- Text on a background of the *same family* (dark on dark, light on light) —
  usually a colour that was set for one theme and inherited into the other.
- Prose stretched to a very long line. Over ~90 characters is uncomfortable;
  over ~200 is a defect.

**Reachability**
- Controls pushed off the edge — check the top-right corner especially, where
  close/expand/overflow buttons live and where a long title shoves them.
- Content cut off at a container edge with no visible way to scroll to it.
- Anything clipped, overlapping, or drawn on top of something else.

**Consistency**
- The same kind of thing styled two ways *in the same image* or between two
  screens one click apart — a status shown as a pill in one table and bare text
  in another.
- Alignment: a column of values that does not line up; labels and controls on
  different baselines.
- Two spellings, two capitalisations, or two date/number formats for one idea.

**Truthfulness**
- Numbers that disagree with each other — a count in a badge versus the rows
  actually listed, a total that is not the sum of its parts.
- A state that contradicts itself: a spinner over an error, "no results" beside
  populated rows, an empty table where a failure should be reported.
- Placeholder or debug text that shipped.

**Use of space**
- Large empty regions beside cramped ones.
- A layout that clearly does not use the width it has — everything in one narrow
  column on a wide screen.
- Elements at their minimum size while their container is huge, or vice versa.

## Measure, don't eyeball

Colour and size judgements made by eye are wrong often enough to be worthless,
and confidently wrong findings waste more time than silence.

If the app can be driven, get the number:

- **Contrast**: compute it from the rendered pixels, compositing translucent
  layers over what is actually behind them. A tint over a panel is not the tint's
  own colour, and stopping at the first non-transparent ancestor gives answers
  that are far off.
- **Widths and overflow**: compare an element's `getBoundingClientRect()` against
  its container's. "Is it cut off" has an exact answer.
- **Line length**: element width divided by approximate glyph width.

If you cannot measure, say the finding is visual-only and unmeasured. That is
honest and still useful.

Beware the oracle. When a measurement contradicts sound reasoning, suspect the
measurement first: a sample point that landed on a glyph, a comparison of encoded
image bytes rather than decoded pixels, a machine under load inflating every
timing. Check the instrument before rewriting the code.

## Screenshots taken under load are not evidence of slowness

If the machine is busy — parallel builds, other agents — timing and rendering
observations are worthless and will make you report a hang that is not there.
Check load before reporting anything time-related, and say so when you cannot
separate the app's cost from the machine's. Layout and colour findings survive
load; timing findings do not.

## Self-improvement — the part that matters

This skill is only as good as its checklist, and the checklist is wrong until
something slips past it.

**When the user reports a UI defect that was visible in a screenshot you had
already looked at**, that is a miss. Do this, in the same turn:

1. Add a dated line to **Misses** below: what was missed, and what check would
   have caught it.
2. If no existing checklist line covers it, **add one**, phrased as something
   observable rather than a category. "Check that controls in the top-right
   corner are inside the panel" beats "check for layout bugs".
3. If a line exists but did not fire, sharpen it and note why it failed.

Do not delete Misses entries. When one has held for a while and its check is
established, it can be compressed to a single line, but the checklist item it
produced stays.

## Misses

Format: `- YYYY-MM-DD — what was missed → the check that would have caught it.`

- 2026-08-01 — Overview stat cards rendered black-on-black in dark mode (1.34:1)
  and were reported twice by the user before being investigated. The screenshots
  had been looked at for other reasons. → *Legibility:* text on a background of
  the same family. Root cause worth remembering: the card was a `<button>` when
  clickable, and a `<button>` does not inherit `color` — the UA stylesheet gives
  it black, which is invisible on a dark panel and fine on a light one. **Any
  element that changes tag by state can change colour by state.**
- 2026-08-01 — A detail drawer's close and expand buttons were off-screen for
  objects with long names; the user reported "missing close and max size
  buttons". → *Reachability:* controls pushed off the edge, top-right especially.
  The mechanism was a flex child with `min-width: auto` refusing to shrink, so
  the header grew past its own panel. Reproduce with the longest name available,
  not a typical one.
- 2026-08-02 — Diagnosis prose ran to ~338 characters a line on a wide screen.
  Never noticed because every screenshot had been taken at ~1400px. → *Use of
  space* and *Legibility:* check at the widest plausible viewport, not only the
  one you happen to be using.
- 2026-08-02 — A table was cut off at the right edge; the user asked why that one
  behaved differently from the others. It did not — it was simply the widest, and
  every table had a fixed minimum width that never shrank. → *Reachability:*
  content cut off at a container edge. When one instance looks broken, check
  whether the others differ **in kind or only in degree** before calling it a
  special case.
- 2026-08-02 — A status column badged one value and left the rest as bare text,
  while another table badged every value. Both screens had been seen many times.
  → *Consistency:* the same kind of thing styled two ways between screens one
  click apart.
