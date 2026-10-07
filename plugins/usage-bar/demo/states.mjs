// Renders usage-bar's states with the mod's OWN functions (format.ts, pace.ts)
// at sample readings. Used for demo/states.png: a live recording can only show
// the state the account is actually in, and that is usually green.
//
//   node --experimental-strip-types states.mjs
import { LABELS, TITLE, percent, resets, tone } from '../hooks/format.ts'
import { ahead, cells, level, pace, pie } from '../hooks/pace.ts'

const WIDTH = 10
const ANSI = { success: 32, warning: 33, error: 31 }
const HOUR = 3_600_000
const now = new Date(2026, 9, 6, 13, 15).getTime()
// A window with `gone` of its length already behind us.
const win = (kind, percentUsed, gone) => {
  const length = kind === 'five_hour' ? 5 * HOUR : 7 * 24 * HOUR
  return { kind, percentUsed, resetsAt: new Date(now + length * (1 - gone)).toISOString() }
}

const samples = [
  ['room to spare, behind the clock', [win('five_hour', 34, 0.6), win('seven_day', 12, 0.3)]],
  ['from 70%: yellow', [win('five_hour', 78, 0.85), win('seven_day', 71, 0.8)]],
  ['ahead of the clock: yellow at any fill', [win('five_hour', 40, 0.3), win('seven_day', 30, 0.22)]],
  ['from 90%, or far ahead: red', [win('five_hour', 94, 0.9), win('seven_day', 45, 0.15)]],
]

for (const [label, windows] of samples) {
  let worst = 0
  let worstColor = 'success'
  const row = windows.map(w => {
    const p = pace(w, now)
    const run = level(p)
    const base = tone(w.percentUsed)
    const color = run === 'far' || base === 'error' ? 'error' : run === 'over' || base === 'warning' ? 'warning' : 'success'
    if (w.percentUsed >= worst) { worst = w.percentUsed; worstColor = color }
    const c = ANSI[color]
    const bar = cells(w.percentUsed, WIDTH, p)
      .map(x => (x.kind === 'used' ? `\x1b[${c}m${x.text}\x1b[0m` : x.kind === 'mark' ? x.text : `\x1b[2m${x.text}\x1b[0m`))
      .join('')
    return `${LABELS[w.kind]} ${bar}\x1b[${c}m ${percent(w)}${ahead(p)}\x1b[0m\x1b[2m ${resets(w, now)}\x1b[0m`
  }).join('   ')
  console.log(`\x1b[2m# ${label}\x1b[0m\n\x1b[${ANSI[worstColor]}m${pie(worst / 100)}\x1b[0m \x1b[1m${TITLE}\x1b[0m   ${row}\n`)
}
