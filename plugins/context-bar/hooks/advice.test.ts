import { expect, test } from 'claude-code/testing'

import { GROWTH_KEPT, advise, pace, pie, track, turnsLeft } from './advice'
import type { Reading } from './advice'

// A 1M window whose auto-compaction runs at 900k.
const at = (total: number, over: Partial<Reading> = {}): Reading => ({
  total,
  max: 1_000_000,
  threshold: 900_000,
  growth: [],
  compactions: 0,
  ...over,
})

test('below 70% of the way there is nothing to say', () => {
  expect(advise(at(100_000))).toBe(null)
  expect(advise(at(620_000))).toBe(null)
})

test('the level rises with the distance to auto-compact, not to the raw window', () => {
  // 70% of 900k is 630k: a hint, though it is only 63% of the model's window.
  expect(advise(at(630_000))?.level).toBe('hint')
  expect(advise(at(770_000))?.level).toBe('warn')
  expect(advise(at(860_000))?.level).toBe('danger')
})

test('each level says what to do, and the urgent one says what is lost', () => {
  expect(advise(at(640_000))?.text).toBe('71% of the way to auto-compact. Between tasks is the cheap time to /compact.')
  expect(advise(at(800_000))?.text).toBe(
    '~100.0k left until auto-compact. Compact at your next stopping point: /compact keep <decisions, open tasks>.',
  )
  const danger = advise(at(880_000))?.text ?? ''
  expect(danger.includes('keep only a summary')).toBe(true)
  expect(danger.includes('/compact now and say what to keep')).toBe(true)
  expect(danger.length <= 120).toBe(true)
  expect(danger.includes('~20.0k left')).toBe(true)
})

test('the pace is the median turn, so one huge read does not set it', () => {
  expect(pace([])).toBe(null)
  expect(pace([5000])).toBe(null)
  expect(pace([4000, 6000])).toBe(5000)
  expect(pace([4000, 5000, 300_000])).toBe(5000)
  expect(pace([0, -20, 4000, 6000])).toBe(5000)
})

test('turns left is the runway at that pace', () => {
  expect(turnsLeft(at(800_000, { growth: [10_000, 10_000, 10_000] }))).toBe(10)
  expect(turnsLeft(at(895_000, { growth: [10_000, 10_000] }))).toBe(0)
  expect(turnsLeft(at(800_000))).toBe(null)
  expect(advise(at(800_000, { growth: [10_000, 10_000] }))?.text.includes('about 10 turns')).toBe(true)
  expect(advise(at(890_000, { growth: [10_000, 10_000] }))?.text.includes('about 1 turn,')).toBe(false)
  expect(advise(at(890_000, { growth: [10_000, 10_000] }))?.text.includes('about 1 turn)')).toBe(true)
})

test('a short runway raises the level before the fill would', () => {
  // 72% of the way, but each turn adds 60k: about four turns left.
  const fast = at(650_000, { growth: [60_000, 60_000, 60_000] })
  expect(advise(fast)?.level).toBe('warn')
  expect(advise(at(650_000, { growth: [120_000, 130_000] }))?.level).toBe('danger')
})

test('a fast start in a nearly empty window is not a trend', () => {
  expect(advise(at(200_000, { growth: [150_000, 150_000] }))).toBe(null)
})

test('with auto-compact off the limit is the window, and the words say so', () => {
  const off = (total: number): Reading => ({ total, max: 200_000, growth: [], compactions: 0 })
  expect(advise(off(120_000))).toBe(null)
  expect(advise(off(150_000))?.text.includes('the window is full')).toBe(true)
  expect(advise(off(195_000))?.text.includes('auto-compact is off')).toBe(true)
  expect(advise(off(195_000))?.text.includes('/clear')).toBe(true)
})

test('a second compaction is worth saying whatever the fill', () => {
  expect(advise(at(100_000, { compactions: 1 }))).toBe(null)
  expect(advise(at(100_000, { compactions: 2 }))).toEqual({
    level: 'hint',
    text: 'Compacted 2× — early detail is a summary of a summary.',
  })
  expect(advise(at(800_000, { compactions: 3 }))?.text.endsWith('Compacted 3× — early detail is a summary of a summary.')).toBe(true)
  expect(advise(at(800_000, { compactions: 3 }))?.level).toBe('warn')
})

test('growth keeps the newest few turns and ignores a drop', () => {
  expect(track([], 100, 150)).toEqual([50])
  expect(track([1, 2, 3, 4, 5], 100, 160)).toEqual([2, 3, 4, 5, 60])
  expect(track([1, 2], 500_000, 40_000)).toEqual([1, 2])
  expect(track([1, 2], 100, 100)).toEqual([1, 2])
  expect(track([1, 2, 3, 4, 5, 6, 7], 0, 1).length).toBe(GROWTH_KEPT)
})

test('past the limit, and with nonsense input, it still answers sanely', () => {
  expect(advise(at(950_000))?.text.includes('~0 left')).toBe(true)
  expect(advise({ total: 5, max: 0, growth: [], compactions: 0 })).toBe(null)
})

test('the label icon is a one-cell pie of the fill', () => {
  expect([0, 0.05, 0.3, 0.5, 0.8, 0.95, 1.4].map(pie).join('')).toBe('○○◔◑◕●●')
  expect(pie(Number.NaN)).toBe('○')
})
