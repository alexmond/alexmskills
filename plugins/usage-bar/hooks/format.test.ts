import { expect, test } from 'claude-code/testing'

import { DANGER_AT, LABELS, TITLE, WARN_AT, filled, left, line, percent, resets, tail, tone } from './format'

test('the row names itself, so it is not read as part of the mod above it', () => {
  expect(TITLE).toBe('Usage')
  expect(Object.values(LABELS).includes(TITLE)).toBe(false)
})

test('tone is green with room, yellow from 70, red from 90', () => {
  expect(tone(0)).toBe('success')
  expect(tone(69.9)).toBe('success')
  expect(tone(WARN_AT)).toBe('warning')
  expect(tone(89.9)).toBe('warning')
  expect(tone(DANGER_AT)).toBe('error')
  expect(tone(140)).toBe('error')
})

test('the figure and the reset text are separate, so each takes its own colour', () => {
  const now = new Date(2026, 9, 6, 1, 15).getTime()
  const at = new Date(2026, 9, 6, 6, 0).toISOString()
  const w = { kind: 'five_hour', percentUsed: 91.4, resetsAt: at }

  expect(percent(w)).toBe('91%')
  expect(resets(w, now)).toBe('(resets in 4h45m · 6:00)')
  expect(resets({ kind: 'spend_limit', percentUsed: 5 }, now)).toBe('')
})

test('left keeps the two largest units', () => {
  expect(left((4 * 60 + 45) * 60_000)).toBe('4h45m')
  expect(left((6 * 24 + 23) * 3_600_000)).toBe('6d23h')
  expect(left(12 * 60_000)).toBe('12m')
})

test('line joins both windows in the old status line shape', () => {
  const now = new Date(2026, 9, 6, 1, 15).getTime()
  const five = new Date(2026, 9, 6, 6, 0).toISOString()
  const seven = new Date(2026, 9, 13, 1, 0).toISOString()
  const out = line(
    [
      { kind: 'five_hour', percentUsed: 1, resetsAt: five },
      { kind: 'seven_day', percentUsed: 0.4, resetsAt: seven },
    ],
    now,
  )

  expect(out).toBe('5h 1% (resets in 4h45m · 6:00)  ·  7d 0% (resets in 6d23h · Tue 1:00)')
})

test('no reading clears the status entry', () => {
  expect(line([], 0)).toBe(undefined)
})

test('filled shows one cell for any use and caps at the width', () => {
  expect(filled(0, 10)).toBe(0)
  expect(filled(1, 10)).toBe(1)
  expect(filled(55, 10)).toBe(6)
  expect(filled(140, 10)).toBe(10)
})

test('tail is the text after a bar', () => {
  const now = new Date(2026, 9, 6, 1, 15).getTime()
  const at = new Date(2026, 9, 6, 6, 0).toISOString()

  expect(tail({ kind: 'five_hour', percentUsed: 1, resetsAt: at }, now)).toBe('1% (resets in 4h45m · 6:00)')
})
