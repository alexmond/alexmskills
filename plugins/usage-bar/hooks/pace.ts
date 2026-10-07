import type { Window } from '../types'

// Limits against the clock.
//
// "62% used" means little alone. With an hour gone of five it means you will
// run out long before the reset; with four hours gone it means you are fine.
// Each window has a fixed length and reports when it resets, so the share of
// the window that has ELAPSED is known, and usage can be read against it.

const HOUR = 3_600_000
/** How long each window lasts. A kind that is not here has no pace. */
export const WINDOW_MS: Record<string, number> = { five_hour: 5 * HOUR, seven_day: 7 * 24 * HOUR }

// Projecting from the first minutes of a window divides by almost nothing:
// 2% used after 1% elapsed is "200% by reset" and means nothing yet.
export const MIN_ELAPSED = 0.1
/** Projected use at reset from which the row speaks up, and from which it is red. */
export const OVER_AT = 100
export const FAR_OVER_AT = 150

export type Pace = {
  /** Share of the window that has passed, 0 to 1. */
  elapsed: number
  /** Use at the reset if the rest of the window goes like the part so far; null while it is too early to say. */
  projected: number | null
}

/** Where this window stands against the clock, or null when that cannot be known. */
export function pace(w: Window, nowMs: number): Pace | null {
  const length = WINDOW_MS[w.kind]
  const at = w.resetsAt ? new Date(w.resetsAt).getTime() : Number.NaN

  if (length === undefined || Number.isNaN(at)) {
    return null
  }

  const left = at - nowMs

  // A reset in the past is a stale reading; one further off than the window
  // is long is not this window. Neither can be read against the clock.
  if (left <= 0 || left > length) {
    return null
  }

  const elapsed = 1 - left / length

  return { elapsed, projected: elapsed >= MIN_ELAPSED ? w.percentUsed / elapsed : null }
}

export type Level = 'ok' | 'over' | 'far'

/** `over` when the window is on course to run out before it resets. */
export function level(p: Pace | null): Level {
  if (p === null || p.projected === null || p.projected < OVER_AT) {
    return 'ok'
  }

  return p.projected >= FAR_OVER_AT ? 'far' : 'over'
}

/** ` ▲ ~140% by reset`, or nothing while usage is not running ahead of time. */
export function ahead(p: Pace | null): string {
  if (p === null || p.projected === null || level(p) === 'ok') {
    return ''
  }

  // Past 999% the number stops meaning anything; the arrow has made the point.
  return ` ▲ ~${Math.min(999, Math.round(p.projected))}% by reset`
}

export type Cell = { text: string; kind: 'used' | 'free' | 'mark' }

/**
 * The bar as runs of cells, with one cell marking where the clock is.
 *
 * The mark left of the fill's end means usage is ahead of time; right of it,
 * behind. No pace, no mark: the bar is then exactly the plain one.
 */
export function cells(percentUsed: number, width: number, p: Pace | null): Cell[] {
  const share = Math.min(100, Math.max(0, percentUsed)) / 100
  const used = percentUsed > 0 ? Math.max(1, Math.round(share * width)) : 0
  const mark = p === null ? -1 : Math.min(width - 1, Math.max(0, Math.floor(p.elapsed * width)))
  const out: Cell[] = []

  for (let i = 0; i < width; i += 1) {
    const kind: Cell['kind'] = i === mark ? 'mark' : i < used ? 'used' : 'free'
    const text = kind === 'mark' ? '│' : kind === 'used' ? '█' : '░'
    const last = out[out.length - 1]

    if (last !== undefined && last.kind === kind) {
      last.text += text
    } else {
      out.push({ text, kind })
    }
  }

  return out
}

/** A one-cell pie for a share from 0 to 1: ○ ◔ ◑ ◕ ●. Single-width, so it never shifts a bar. */
export function pie(share: number): string {
  const s = Number.isFinite(share) ? Math.min(1, Math.max(0, share)) : 0

  return ['○', '◔', '◑', '◕', '●'][Math.round(s * 4)] ?? '○'
}
