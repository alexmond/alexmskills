// Renders usage-bar's three colour states with the mod's OWN functions
// (filled / tone / percent / resets from ../hooks/format.ts), at sample
// percentages. Used for demo/states.png: a live recording can only show the
// state the account is actually in, and that is usually green.
//
//   node --experimental-strip-types states.mjs
import { LABELS, filled, percent, resets, tone } from '../hooks/format.ts'

const WIDTH = 10
const ANSI = { success: 32, warning: 33, error: 31 }
const now = new Date(2026, 9, 6, 13, 15).getTime()
const at = (h, m, days = 0) => new Date(2026, 9, 6 + days, h, m).toISOString()

const samples = [
  ['room to spare', [{ kind: 'five_hour', percentUsed: 34, resetsAt: at(18, 0) },
                     { kind: 'seven_day', percentUsed: 12, resetsAt: at(1, 0, 5) }]],
  ['from 70%: yellow', [{ kind: 'five_hour', percentUsed: 78, resetsAt: at(18, 0) },
                        { kind: 'seven_day', percentUsed: 71, resetsAt: at(1, 0, 5) }]],
  ['from 90%: red', [{ kind: 'five_hour', percentUsed: 94, resetsAt: at(18, 0) },
                     { kind: 'seven_day', percentUsed: 91, resetsAt: at(1, 0, 5) }]],
]

for (const [label, windows] of samples) {
  const row = windows.map(w => {
    const n = filled(w.percentUsed, WIDTH)
    const c = ANSI[tone(w.percentUsed)]
    return `${LABELS[w.kind]} \x1b[${c}m${'█'.repeat(n)}\x1b[0m\x1b[2m${'░'.repeat(WIDTH - n)}\x1b[0m`
      + `\x1b[${c}m ${percent(w)}\x1b[0m\x1b[2m ${resets(w, now)}\x1b[0m`
  }).join('   ')
  console.log(`\x1b[2m# ${label}\x1b[0m\n${row}\n`)
}
