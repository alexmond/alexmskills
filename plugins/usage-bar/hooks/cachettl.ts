// How long does the prompt cache live in THIS session?
//
// The engine does not say. There are two published lifetimes, five minutes
// and an hour, and which one applies depends on the account and its state.
// 0.3.0 guessed from the kind of account. This learns it from the session's
// own traffic instead, and keeps the guess only until there is evidence.
//
// Every turn reports how many tokens it WROTE to the cache. A warm cache
// only takes the new part of the conversation; a cold one has to take all of
// it again. So after a pause of known length, compare what was written with
// how big the context already was:
//
//   - far less written than the context held: the entry outlived the pause.
//     If the pause was longer than five minutes, the lifetime is an hour.
//   - about the whole context written again, on the same model, with no
//     compaction in between: the entry did not outlive it. If the pause was
//     shorter than an hour, the lifetime is five minutes.
//
// Anything else — a small context, a model switch, a compaction, a pause
// under five minutes or over an hour — proves nothing, and changes nothing.
//
// Written tokens, not the read share: a turn's figures may be summed over
// several requests, and after a cold start every request but the first reads
// from the cache it just wrote. A read share would call that turn warm.

export type Minutes = 5 | 60

export type Learned = {
  /** The lifetime in use. */
  minutes: Minutes
  /** `assumed` from the kind of account or an env switch; `observed` from traffic. */
  source: 'assumed' | 'observed'
}

export type Observation = {
  /** Pause between the previous answer and this prompt; null for the session's first. */
  gapMs: number | null
  /** Tokens this turn wrote to the cache. */
  written: number
  /** Tokens the context held when the previous turn ended. */
  prior: number
  /** Whether the model is the one that answered last time. */
  isSameModel: boolean
  /** Whether the context was compacted or cleared since the last answer. */
  isAfterCompact: boolean
}

const MINUTE = 60_000
// A margin either side of each lifetime: a pause of 5m02s that survived is
// not proof of an hour, with clocks and request timing what they are.
const LONGER_THAN_FIVE = 6 * MINUTE
const SHORTER_THAN_HOUR = 55 * MINUTE
// Below this the context is too small for "all of it" and "a little" to differ.
export const MIN_CONTEXT = 8000
/** Written under this share of the context: the cache was warm. Over the other: it was cold. */
export const WARM_UNDER = 0.5
export const COLD_OVER = 0.9

/** What this turn proves about the lifetime, if anything. */
export function learn(prev: Learned, o: Observation): Learned {
  if (o.gapMs === null || o.gapMs < 0 || o.prior < MIN_CONTEXT || o.written < 0 || o.isAfterCompact) {
    return prev
  }

  const share = o.written / o.prior

  if (share < WARM_UNDER && o.gapMs > LONGER_THAN_FIVE) {
    return { minutes: 60, source: 'observed' }
  }

  if (share >= COLD_OVER && o.isSameModel && o.gapMs > LONGER_THAN_FIVE && o.gapMs < SHORTER_THAN_HOUR) {
    return { minutes: 5, source: 'observed' }
  }

  return prev
}

/**
 * The starting assumption. Claude Code's own switches win, then the kind of
 * account. `null` means caching is switched off: there is nothing to count.
 */
export function assume(env: { disable?: string; force5m?: string; enable1h?: string }, hasPlanWindows: boolean): Learned | null {
  const isOn = (v: string | undefined): boolean => v !== undefined && v !== '' && v !== '0' && v.toLowerCase() !== 'false'

  if (isOn(env.disable)) {
    return null
  }

  if (isOn(env.force5m)) {
    return { minutes: 5, source: 'assumed' }
  }

  if (isOn(env.enable1h)) {
    return { minutes: 60, source: 'assumed' }
  }

  return { minutes: hasPlanWindows ? 60 : 5, source: 'assumed' }
}
