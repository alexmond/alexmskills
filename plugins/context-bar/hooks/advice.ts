import { short } from './layout'

// When to say something about compaction, and what.
//
// Compaction replaces the conversation with a summary. Done by hand at a
// stopping point, you choose the moment and can say what must be kept. Done
// automatically, it happens wherever the window happens to fill — often in the
// middle of a task — and whatever was only in the conversation survives as
// whatever the summary made of it. This module watches the distance to that
// point and speaks up while there is still a choice.
//
// The texts are kept to about one terminal row: a warning that wraps to three
// lines pushes the prompt down at the moment the person most needs it.
//
// Everything here is arithmetic on figures the engine reports. It makes no
// claim about answer quality at a given fill: that is not something a bar can
// measure.

export type Level = 'hint' | 'warn' | 'danger'

export type Advice = { level: Level; text: string }

export type Reading = {
  /** Tokens in the window now. */
  total: number
  /** The window the bar is drawn against. */
  max: number
  /** Where auto-compaction runs; absent when it is off. */
  threshold?: number
  /** How much each recent turn added, newest last. */
  growth: readonly number[]
  /** Compactions so far this session. */
  compactions: number
}

// Fractions of the way to the limit. Below HINT_AT the row stays quiet: a bar
// that always has an opinion is a bar nobody reads.
export const HINT_AT = 0.7
export const WARN_AT = 0.85
export const DANGER_AT = 0.95
// Turns of runway that raise the level on their own, however full the window
// looks: three big tool results can cover the last 30% in one go.
export const WARN_TURNS = 6
export const DANGER_TURNS = 2
// Growth figures kept, and the fewest needed before a "turns left" is offered.
export const GROWTH_KEPT = 5
const GROWTH_NEEDED = 2

/** The typical recent turn: the median, so one huge file read does not set the pace. */
export function pace(growth: readonly number[]): number | null {
  const real = growth.filter(g => g > 0)

  if (real.length < GROWTH_NEEDED) {
    return null
  }

  const sorted = [...real].sort((a, b) => a - b)
  const mid = Math.floor(sorted.length / 2)
  const median = sorted.length % 2 === 1 ? sorted[mid] : ((sorted[mid - 1] ?? 0) + (sorted[mid] ?? 0)) / 2

  return median ?? null
}

/** The newest `GROWTH_KEPT` turn sizes, with this turn's added. A drop (a compaction, a /clear) is not growth. */
export function track(growth: readonly number[], before: number, after: number): number[] {
  return after > before ? [...growth, after - before].slice(-GROWTH_KEPT) : [...growth]
}

/** Whole turns of runway at the recent pace, or null when the pace is unknown. */
export function turnsLeft(r: Reading): number | null {
  const per = pace(r.growth)
  const limit = r.threshold ?? r.max

  return per === null ? null : Math.max(0, Math.floor((limit - r.total) / per))
}

function levelOf(fraction: number, turns: number | null): Level | null {
  if (fraction >= DANGER_AT || (turns !== null && turns <= DANGER_TURNS)) {
    return 'danger'
  }

  if (fraction >= WARN_AT || (turns !== null && turns <= WARN_TURNS)) {
    return 'warn'
  }

  return fraction >= HINT_AT ? 'hint' : null
}

/** What to tell the person now, or null when there is nothing worth a row. */
export function advise(r: Reading): Advice | null {
  const limit = r.threshold ?? r.max

  if (limit <= 0) {
    return null
  }

  const isAuto = r.threshold !== undefined
  const left = Math.max(0, limit - r.total)
  const turns = turnsLeft(r)
  // The turn count only raises the level once the window is at least half
  // used: a fresh session's first two big reads are not a trend.
  const level = levelOf(r.total / limit, r.total / limit >= 0.5 ? turns : null)
  // A second compaction is worth saying whatever the fill: what was summarized
  // once has now been summarized again.
  const depth = r.compactions >= 2 ? ` Compacted ${r.compactions}× — early detail is a summary of a summary.` : ''

  if (level === null) {
    return depth === '' ? null : { level: 'hint', text: depth.trim() }
  }

  const room = turns === null ? `~${short(left)} left` : `~${short(left)} left, about ${turns} ${turns === 1 ? 'turn' : 'turns'}`
  const what = isAuto ? 'auto-compact' : 'the window is full'

  if (level === 'danger') {
    return {
      level,
      text: isAuto
        ? `Auto-compact is close (${room}) and will keep only a summary, mid-task. /compact now and say what to keep.${depth}`
        : `Window nearly full (${room}) and auto-compact is off. /compact or /clear before a request fails.${depth}`,
    }
  }

  if (level === 'warn') {
    return {
      level,
      text: `${room} until ${what}. Compact at your next stopping point: /compact keep <decisions, open tasks>.${depth}`,
    }
  }

  return {
    level,
    text: `${Math.round((r.total / limit) * 100)}% of the way to ${what}. Between tasks is the cheap time to /compact.${depth}`,
  }
}

/** A one-cell pie for a share from 0 to 1: ○ ◔ ◑ ◕ ●. Single-width, so it never shifts the legend. */
export function pie(share: number): string {
  const s = Number.isFinite(share) ? Math.min(1, Math.max(0, share)) : 0

  return ['○', '◔', '◑', '◕', '●'][Math.round(s * 4)] ?? '○'
}
