import type { Job, Mode, View } from '../types'

// The band's rows, as plain data. This is statusline.py's layout in
// TypeScript, kept beside it on purpose: the status line and the band are two
// views of the same daemon, and a job should read the same in both.

export const WIDTH = 18
// The status line stops at 3 rows so it never pushes the prompt away. The
// band is the engine's to scroll, so it can afford a few more.
export const MAX_ROWS = 6
const RAMP = ' ▏▎▍▌▋▊▉█' // 8 sub-steps per cell, so a small move still shows

export type Row = {
  mark: string
  name: string
  bar: string
  percent: string
  tail: string
  tone: 'suggestion' | 'warning'
}

export function bar(ratio: number, width = WIDTH): string {
  const exact = Math.max(0, Math.min(1, ratio)) * width
  const full = Math.floor(exact)
  let out = '█'.repeat(full)

  if (full < width) {
    const idx = Math.floor((exact - full) * (RAMP.length - 1))
    // Index 0 is a space, which reads as a hole punched in the bar.
    out += idx > 0 ? RAMP[idx] : '░'
    out += '░'.repeat(Math.max(0, width - full - 1))
  }

  return out.slice(0, width)
}

export function dur(seconds: number): string {
  const s = Math.floor(seconds)

  if (s < 60) {
    return `${s}s`
  }

  if (s < 3600) {
    return `${Math.floor(s / 60)}m${String(s % 60).padStart(2, '0')}s`
  }

  return `${Math.floor(s / 3600)}h${String(Math.floor((s % 3600) / 60)).padStart(2, '0')}m`
}

const isLive = (j: Job): boolean =>
  (j.state === 'running' || j.state === 'stalled') && j.progress !== null

/**
 * [root, children] pairs in the daemon's tree order. Direct children get
 * rows; anything deeper already reached its parent through the daemon's
 * rollup. A child whose parent is not in view is drawn as a root rather than
 * under the wrong row.
 */
export function units(jobs: Job[]): Array<[Job, Job[]]> {
  const present = new Set(jobs.map(j => j.uid))
  const out: Array<[Job, Job[]]> = []

  for (const j of jobs) {
    const depth = j.depth ?? 0
    const last = out[out.length - 1]

    if (depth === 0 || j.parent === null || !present.has(j.parent) || last === undefined) {
      out.push([j, []])
    } else if (depth === 1) {
      last[1].push(j)
    }
  }

  return out
}

function row(j: Job, isChild: boolean, folded: Job[]): Row {
  const ratio = j.progress ?? 0
  const mode = j.progress_mode ?? 'creep'
  const isStalled = j.state === 'stalled'
  let name = isChild ? `  ↳ ${(j.name ?? 'job').slice(0, 22)}` : (j.name ?? 'job').slice(0, 26)

  // A subagent's job belongs in this band, but it is not the main loop's work.
  if (j.agent && !isChild) {
    name = `${j.agent.slice(0, 10)}: ${name.slice(0, 20)}`
  }

  // Counted modes show the count; estimates name themselves, so an estimated
  // bar is never read as a measured one.
  let tail = mode === 'items' || mode === 'items+sub' ? `${j.done ?? 0}/${j.total}` : mode

  if (j.eta_seconds) {
    tail += ` · ~${dur(j.eta_seconds)} left`
  }

  if (isStalled) {
    tail += ' · stalled'
  }

  if (j.detached) {
    tail += ` · ${j.detached.slice(0, 30)}`
  }

  const first = folded[0]

  if (first !== undefined) {
    tail += ` · ↳ ${(first.name ?? '').slice(0, 18)} ${Math.round((first.progress ?? 0) * 100)}%`

    if (folded.length > 1) {
      tail += ` +${folded.length - 1}`
    }
  }

  return {
    mark: isStalled ? '!' : '⏳',
    name,
    bar: bar(ratio),
    percent: `${String(Math.round(ratio * 100)).padStart(3)}%`,
    tail,
    tone: isStalled ? 'warning' : 'suggestion',
  }
}

/**
 * Every top-level job gets a row before any child does, so a second pipeline
 * is never pushed out by the first one's steps. Spare rows go to children in
 * order; a child with no row is folded onto its parent's line.
 */
export function rows(jobs: Job[], maxRows = MAX_ROWS): Row[] {
  const shownUnits = units(jobs.filter(isLive)).slice(0, maxRows)
  let spare = maxRows - shownUnits.length
  const out: Row[] = []

  for (const [root, kids] of shownUnits) {
    const shown = kids.slice(0, spare)
    spare -= shown.length
    out.push(row(root, false, kids.slice(shown.length)))

    for (const k of shown) {
      out.push(row(k, true, []))
    }
  }

  // One column for the bars. The status line cannot afford the padding; the
  // band can, and ragged bars are hard to compare at a glance.
  const wide = Math.max(0, ...out.map(r => r.name.length))

  return out.map(r => ({ ...r, name: r.name.padEnd(wide) }))
}

/** `auto` yields to a status line that is already showing these jobs. */
export function isShown(mode: Mode, view: View | null): boolean {
  if (view === null || mode === 'off') {
    return false
  }

  return mode === 'on' || !view.hasStatusLine
}

/** `/progress-bar`, `/progress-bar on|off|auto`: bare toggles what is on screen now. */
export function nextMode(arg: string, mode: Mode, view: View | null): Mode {
  const want = arg.trim().toLowerCase()

  if (want === 'on' || want === 'off' || want === 'auto') {
    return want
  }

  return isShown(mode, view ?? { jobs: [], hasStatusLine: false }) ? 'off' : 'on'
}

export const DEFAULT_PORT = 7717

/**
 * The daemon's port, from PROGRESS_PORT. Only a whole number in range is
 * taken: the value goes into a URL, and `7717@evil.example` or `80/x?` would
 * otherwise point the request somewhere else.
 */
export function port(raw: string | undefined): number {
  const n = /^[0-9]{1,5}$/.test(raw ?? '') ? Number(raw) : 0

  return n >= 1 && n <= 65535 ? n : DEFAULT_PORT
}

// Any process on the machine can register a job, so a name is untrusted text
// about to be drawn in the prompt. Control characters go (an escape sequence
// could recolour or overwrite what is on screen), and so do the bidi and
// zero-width marks that make text read as something it is not.
const UNSAFE = /[\u0000-\u001f\u007f-\u009f\u200b-\u200f\u2028-\u202e\u2066-\u2069\ufeff]/g

export function clean(v: unknown, max = 80): string | null {
  return typeof v === 'string' ? v.replace(UNSAFE, ' ').slice(0, max) : null
}

const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null)

/** One record from the wire, every field checked, or null if it is not a job. */
function job(v: unknown): Job | null {
  if (typeof v !== 'object' || v === null) {
    return null
  }

  const r = v as Record<string, unknown>
  const uid = clean(r.uid, 64)

  if (uid === null) {
    return null
  }

  return {
    uid,
    name: clean(r.name),
    state: clean(r.state, 16) ?? '',
    progress: num(r.progress),
    progress_mode: clean(r.progress_mode, 16),
    done: num(r.done),
    total: num(r.total),
    eta_seconds: num(r.eta_seconds),
    depth: num(r.depth),
    parent: clean(r.parent, 64),
    agent: clean(r.agent, 40),
    detached: clean(r.detached),
  }
}

/** The daemon's reply, or null for anything that is not one. */
export function parse(text: string): View | null {
  try {
    const d: unknown = JSON.parse(text)

    if (typeof d !== 'object' || d === null || !Array.isArray((d as { jobs?: unknown }).jobs)) {
      return null
    }

    const reply = d as { jobs: unknown[]; statusline_seen?: unknown }
    // A cap as well: the band shows six rows, and nothing good is 500 jobs long.
    const jobs = reply.jobs.slice(0, 200).map(job).filter((j): j is Job => j !== null)

    return { jobs, hasStatusLine: reply.statusline_seen === true }
  } catch {
    return null
  }
}

/** What the band would draw, as text: equal strings mean nothing to redraw. */
export function signature(view: View | null): string {
  return view === null ? '' : JSON.stringify([view.hasStatusLine, rows(view.jobs)])
}
