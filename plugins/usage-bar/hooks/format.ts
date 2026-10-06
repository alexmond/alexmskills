import type { Window } from '../types'

const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
export const LABELS: Record<string, string> = { five_hour: '5h', seven_day: '7d', spend_limit: 'spend' }

// What the row is. Several mods share the band above the prompt, and a row of
// bars with no name reads as part of whatever is drawn above it.
export const TITLE = 'Usage'

/** `4h45m`, `6d23h` or `12m`: the two largest units, as the old status line wrote it. */
export function left(ms: number): string {
  const minutes = Math.max(0, Math.round(ms / 60_000))
  const d = Math.floor(minutes / 1440)
  const h = Math.floor((minutes % 1440) / 60)
  const m = minutes % 60

  if (d > 0) {
    return `${d}d${h}h`
  }

  return h > 0 ? `${h}h${m}m` : `${m}m`
}

/** `6:00` when the reset is within a day, `Tue 1:00` when it is further off; local time. */
export function clock(at: Date, now: Date): string {
  const time = `${at.getHours()}:${String(at.getMinutes()).padStart(2, '0')}`

  return at.getTime() - now.getTime() < 86_400_000 ? time : `${DAYS[at.getDay()]} ${time}`
}

export function line(windows: readonly Window[], nowMs: number): string | undefined {
  const now = new Date(nowMs)
  const parts = windows.map(w => {
    const head = `${LABELS[w.kind] ?? w.kind} ${Math.round(w.percentUsed)}%`
    const at = w.resetsAt ? new Date(w.resetsAt) : undefined

    if (!at || Number.isNaN(at.getTime())) {
      return head
    }

    return `${head} (resets in ${left(at.getTime() - nowMs)} · ${clock(at, now)})`
  })

  return parts.length > 0 ? parts.join('  ·  ') : undefined
}

/** `1%`: the figure beside a bar, drawn in the bar's own colour. */
export function percent(w: Window): string {
  return `${Math.round(w.percentUsed)}%`
}

/** `(resets in 4h45m · 6:00)`, or nothing when the window reports no reset. */
export function resets(w: Window, nowMs: number): string {
  const at = w.resetsAt ? new Date(w.resetsAt) : undefined

  if (!at || Number.isNaN(at.getTime())) {
    return ''
  }

  return `(resets in ${left(at.getTime() - nowMs)} · ${clock(at, new Date(nowMs))})`
}

/** What follows a window's bar: `1% (resets in 4h45m · 6:00)`. */
export function tail(w: Window, nowMs: number): string {
  const rest = resets(w, nowMs)

  return rest ? `${percent(w)} ${rest}` : percent(w)
}

export const WARN_AT = 70
export const DANGER_AT = 90

/**
 * The colour a window is drawn in: green with room to spare, yellow from
 * `WARN_AT`, red from `DANGER_AT`. Theme names, so each terminal theme picks
 * its own green, yellow and red.
 */
export function tone(percentUsed: number): 'success' | 'warning' | 'error' {
  if (percentUsed >= DANGER_AT) {
    return 'error'
  }

  return percentUsed >= WARN_AT ? 'warning' : 'success'
}

/** Filled cells of a `width`-cell bar; any use at all shows one cell. */
export function filled(percentUsed: number, width: number): number {
  const n = Math.round((Math.min(100, Math.max(0, percentUsed)) / 100) * width)

  return percentUsed > 0 ? Math.max(1, n) : 0
}
