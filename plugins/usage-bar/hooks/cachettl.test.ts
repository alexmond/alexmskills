import { expect, test } from 'claude-code/testing'

import { assume, learn } from './cachettl'
import type { Learned, Observation } from './cachettl'

const MIN = 60_000
const plan: Learned = { minutes: 60, source: 'assumed' }
const api: Learned = { minutes: 5, source: 'assumed' }
// A 200k context. Warm: the turn wrote only its own 3k. Cold: it wrote all 200k again.
const turn = (gapMin: number | null, written: number, over: Partial<Observation> = {}): Observation => ({
  gapMs: gapMin === null ? null : gapMin * MIN,
  written,
  prior: 200_000,
  isSameModel: true,
  isAfterCompact: false,
  ...over,
})

test('a warm turn after a pause longer than five minutes proves an hour', () => {
  expect(learn(api, turn(20, 3000))).toEqual({ minutes: 60, source: 'observed' })
  expect(learn(plan, turn(20, 3000))).toEqual({ minutes: 60, source: 'observed' })
})

test('a cold turn after a pause shorter than an hour proves five minutes', () => {
  expect(learn(plan, turn(20, 200_000))).toEqual({ minutes: 5, source: 'observed' })
  expect(learn(plan, turn(20, 190_000))).toEqual({ minutes: 5, source: 'observed' })
})

test('a pause too short or too long proves nothing either way', () => {
  expect(learn(api, turn(2, 3000))).toBe(api) // warm after 2 min: true of both lifetimes
  expect(learn(plan, turn(5.5, 200_000))).toBe(plan) // inside the margin
  expect(learn(plan, turn(70, 200_000))).toBe(plan) // cold after 70 min: true of both
  expect(learn(plan, turn(58, 200_000))).toBe(plan) // inside the margin
})

test('a cold turn with another explanation is not evidence', () => {
  expect(learn(plan, turn(20, 200_000, { isSameModel: false }))).toBe(plan)
  expect(learn(plan, turn(20, 200_000, { isAfterCompact: true }))).toBe(plan)
})

test('a compaction voids a warm-looking turn too: the context it is measured against is gone', () => {
  expect(learn(api, turn(20, 3000, { isAfterCompact: true }))).toBe(api)
})

test('the session\'s first turn, a small context and an in-between amount prove nothing', () => {
  expect(learn(plan, turn(null, 200_000))).toBe(plan)
  expect(learn(plan, turn(20, 4000, { prior: 4000 }))).toBe(plan)
  expect(learn(plan, turn(20, 140_000))).toBe(plan) // 70% rewritten: neither clearly warm nor cold
  expect(learn(plan, turn(-5, 3000))).toBe(plan)
})

test('a turn summed over many requests after a cold start still reads as cold', () => {
  // The first request wrote the whole context; the next nine read it back.
  // Judged on written tokens, that is a miss — a read share would call it warm.
  expect(learn(plan, turn(20, 205_000))).toEqual({ minutes: 5, source: 'observed' })
})

test('evidence can correct evidence', () => {
  const five = learn(plan, turn(20, 200_000))
  expect(learn(five, turn(30, 2000))).toEqual({ minutes: 60, source: 'observed' })
})

test('the starting assumption: Claude Code\'s switches first, then the kind of account', () => {
  expect(assume({}, true)).toEqual({ minutes: 60, source: 'assumed' })
  expect(assume({}, false)).toEqual({ minutes: 5, source: 'assumed' })
  expect(assume({ force5m: '1' }, true)).toEqual({ minutes: 5, source: 'assumed' })
  expect(assume({ enable1h: 'true' }, false)).toEqual({ minutes: 60, source: 'assumed' })
  expect(assume({ disable: '1', enable1h: '1' }, true)).toBe(null)
  expect(assume({ disable: '0', force5m: '', enable1h: 'false' }, true)).toEqual({ minutes: 60, source: 'assumed' })
})
