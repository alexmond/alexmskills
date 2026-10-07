import { expect, test } from 'claude-code/testing'

import type { Window } from '../types'
import { ahead, cells, level, pace, pie } from './pace'

const NOW = new Date(2026, 9, 6, 12, 0).getTime()
const HOUR = 3_600_000
// A 5-hour window with `gone` hours of it behind us.
const five = (percentUsed: number, gone: number): Window => ({
  kind: 'five_hour',
  percentUsed,
  resetsAt: new Date(NOW + (5 - gone) * HOUR).toISOString(),
})

test('elapsed is the share of the window behind us', () => {
  expect(Math.round((pace(five(10, 1), NOW)?.elapsed ?? -1) * 1000) / 1000).toBe(0.2)
  expect(Math.round((pace(five(10, 4), NOW)?.elapsed ?? -1) * 1000) / 1000).toBe(0.8)
  const week: Window = { kind: 'seven_day', percentUsed: 5, resetsAt: new Date(NOW + 3.5 * 24 * HOUR).toISOString() }
  expect(Math.round((pace(week, NOW)?.elapsed ?? -1) * 1000) / 1000).toBe(0.5)
})

test('the projection is use at reset if the rest goes like the part so far', () => {
  expect(Math.round((pace(five(60, 1), NOW)?.projected ?? -1) * 1000) / 1000).toBe(300)
  expect(Math.round((pace(five(60, 4), NOW)?.projected ?? -1) * 1000) / 1000).toBe(75)
})

test('too early in the window, there is no projection', () => {
  // 2% used after 1% elapsed is not "200% by reset".
  expect(pace(five(2, 0.05), NOW)?.projected).toBe(null)
  expect(level(pace(five(2, 0.05), NOW))).toBe('ok')
  expect(ahead(pace(five(2, 0.05), NOW))).toBe('')
})

test('no pace without a known window length or a usable reset time', () => {
  expect(pace({ kind: 'spend_limit', percentUsed: 40, resetsAt: new Date(NOW + HOUR).toISOString() }, NOW)).toBe(null)
  expect(pace({ kind: 'five_hour', percentUsed: 40 }, NOW)).toBe(null)
  expect(pace({ kind: 'five_hour', percentUsed: 40, resetsAt: 'not a date' }, NOW)).toBe(null)
  // already reset, or further off than the window is long: a stale or foreign reading
  expect(pace({ kind: 'five_hour', percentUsed: 40, resetsAt: new Date(NOW - HOUR).toISOString() }, NOW)).toBe(null)
  expect(pace({ kind: 'five_hour', percentUsed: 40, resetsAt: new Date(NOW + 9 * HOUR).toISOString() }, NOW)).toBe(null)
})

test('the level and the words follow the projection', () => {
  expect(level(pace(five(30, 2.5), NOW))).toBe('ok')
  expect(ahead(pace(five(30, 2.5), NOW))).toBe('')
  expect(level(pace(five(60, 2.5), NOW))).toBe('over')
  expect(ahead(pace(five(60, 2.5), NOW))).toBe(' ▲ ~120% by reset')
  expect(level(pace(five(60, 1), NOW))).toBe('far')
  expect(ahead(pace(five(60, 1), NOW))).toBe(' ▲ ~300% by reset')
  expect(ahead(pace(five(99, 0.6), NOW))).toBe(' ▲ ~825% by reset')
  // past 999 the number stops meaning anything
  expect(ahead(pace(five(250, 1), NOW))).toBe(' ▲ ~999% by reset')
})

test('the bar is always the asked width, with one cell marking the clock', () => {
  const text = (percentUsed: number, gone: number | null): string =>
    cells(percentUsed, 10, gone === null ? null : pace(five(percentUsed, gone), NOW))
      .map(c => c.text)
      .join('')
  expect(text(30, null)).toBe('███░░░░░░░')
  // usage behind the clock: the mark sits in the empty part
  expect(text(30, 3.5)).toBe('███░░░░│░░')
  // usage ahead of the clock: the mark sits inside the fill
  expect(text(80, 1.5)).toBe('███│████░░')
  expect(text(0, 2.5)).toBe('░░░░░│░░░░')
  expect(text(100, 4.99)).toBe('█████████│')
  expect(text(250, 0.01)).toBe('│█████████')
  for (const p of [0, 1, 37, 100]) {
    expect(text(p, 2.2).length).toBe(10)
  }
})

test('runs of the same kind are merged, so the drawing is three or four spans, not ten', () => {
  expect(cells(50, 10, null).map(c => c.kind)).toEqual(['used', 'free'])
  expect(cells(30, 10, pace(five(30, 3.5), NOW)).map(c => c.kind)).toEqual(['used', 'free', 'mark', 'free'])
})

test('the pie is one cell for any share', () => {
  expect([0, 0.1, 0.2, 0.5, 0.7, 0.9, 1].map(pie).join('')).toBe('○○◔◑◕●●')
  expect(pie(-3)).toBe('○')
  expect(pie(40)).toBe('●')
  expect(pie(Number.NaN)).toBe('○')
})
