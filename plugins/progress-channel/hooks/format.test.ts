import { expect, test } from 'claude-code/testing'

import type { Job } from '../types'
import { DEFAULT_PORT, bar, clean, dur, isShown, nextMode, parse, port, rows, signature, units } from './format'

const job = (over: Partial<Job>): Job => ({
  uid: 'u',
  name: 'job',
  state: 'running',
  progress: 0.5,
  progress_mode: 'items',
  done: 5,
  total: 10,
  eta_seconds: null,
  depth: 0,
  parent: null,
  agent: null,
  ...over,
})

test('the bar is always the asked width and never punches a hole', () => {
  expect(bar(0, 10)).toBe('░'.repeat(10))
  expect(bar(1, 10)).toBe('█'.repeat(10))
  expect(bar(0.5, 10)).toBe('█████░░░░░')
  expect(bar(0.56, 10)).toBe('█████▌░░░░')
  expect(bar(7, 10)).toBe('█'.repeat(10))
  expect(bar(-1, 10)).toBe('░'.repeat(10))
  expect(bar(0.333).length).toBe(18)
})

test('durations read like the status line', () => {
  expect(dur(9)).toBe('9s')
  expect(dur(125)).toBe('2m05s')
  expect(dur(3725)).toBe('1h02m')
})

test('a counted job shows its count; an estimate names its mode', () => {
  const [counted] = rows([job({ name: 'reel 03', eta_seconds: 75 })])
  expect(counted?.name).toBe('reel 03')
  expect(counted?.percent).toBe(' 50%')
  expect(counted?.tail).toBe('5/10 · ~1m15s left')
  expect(counted?.tone).toBe('suggestion')

  const [estimate] = rows([job({ progress_mode: 'eta~', done: null, total: null })])
  expect(estimate?.tail).toBe('eta~')
})

test('a stalled job is marked and toned, not hidden', () => {
  const [r] = rows([job({ state: 'stalled' })])
  expect(r?.mark).toBe('!')
  expect(r?.tone).toBe('warning')
  expect(r?.tail).toBe('5/10 · stalled')
})

test('finished jobs and jobs with no fraction are not drawn', () => {
  expect(rows([job({ state: 'done' }), job({ state: 'failed' }), job({ progress: null })])).toEqual([])
})

test('children are indented under their parent', () => {
  const out = rows([
    job({ uid: 'p', name: 'pipeline' }),
    job({ uid: 'c', name: 'ground-round', depth: 1, parent: 'p' }),
  ])
  expect(out.map(r => r.name)).toEqual(['pipeline        ', '  ↳ ground-round'])
  expect(new Set(out.map(r => r.name.length)).size).toBe(1)
})

test('a child whose parent is not in view is drawn as a root, never under the wrong row', () => {
  const out = units([job({ uid: 'a' }), job({ uid: 'c', depth: 1, parent: 'gone' })])
  expect(out.length).toBe(2)
  expect(out[1]?.[1]).toEqual([])
})

test('every top-level job gets a row before any child does; the rest fold onto the parent', () => {
  const jobs = [
    job({ uid: 'p1', name: 'one' }),
    job({ uid: 'c1', name: 'step-a', depth: 1, parent: 'p1', progress: 0.25 }),
    job({ uid: 'c2', name: 'step-b', depth: 1, parent: 'p1' }),
    job({ uid: 'p2', name: 'two' }),
  ]
  const out = rows(jobs, 3)
  expect(out.map(r => r.name)).toEqual(['one       ', '  ↳ step-a', 'two       '])
  expect(out[0]?.tail).toBe('5/10 · ↳ step-b 50%')

  const tight = rows(jobs, 2)
  expect(tight.map(r => r.name)).toEqual(['one', 'two'])
  expect(tight[0]?.tail).toBe('5/10 · ↳ step-a 25% +1')
})

test('a subagent job says whose it is', () => {
  const [r] = rows([job({ name: 'sweep', agent: 'dc-scout' })])
  expect(r?.name).toBe('dc-scout: sweep')
})

test('auto yields to a wired status line; on and off do not care', () => {
  const wired = { jobs: [], hasStatusLine: true }
  const bare = { jobs: [], hasStatusLine: false }
  expect(isShown('auto', wired)).toBe(false)
  expect(isShown('auto', bare)).toBe(true)
  expect(isShown('on', wired)).toBe(true)
  expect(isShown('off', bare)).toBe(false)
  expect(isShown('on', null)).toBe(false)
})

test('the bare command toggles what is on screen; a word sets the mode', () => {
  const wired = { jobs: [], hasStatusLine: true }
  const bare = { jobs: [], hasStatusLine: false }
  expect(nextMode('', 'auto', bare)).toBe('off')
  expect(nextMode('', 'auto', wired)).toBe('on')
  expect(nextMode('', 'off', bare)).toBe('on')
  expect(nextMode(' AUTO ', 'off', bare)).toBe('auto')
  expect(nextMode('nonsense', 'on', bare)).toBe('off')
  expect(nextMode('', 'auto', null)).toBe('off')
})

test('anything that is not the daemon reply parses to null', () => {
  expect(parse('<html>')).toBe(null)
  expect(parse('{"ok":true}')).toBe(null)
  expect(parse('[]')).toBe(null)
  expect(parse('{"jobs":[],"statusline_seen":true}')).toEqual({ jobs: [], hasStatusLine: true })
  expect(parse('{"jobs":[]}')).toEqual({ jobs: [], hasStatusLine: false })
})

test('the port is a whole number in range, or the default — never a piece of a URL', () => {
  expect(port('7741')).toBe(7741)
  expect(port(undefined)).toBe(DEFAULT_PORT)
  expect(port('')).toBe(DEFAULT_PORT)
  expect(port('0')).toBe(DEFAULT_PORT)
  expect(port('65536')).toBe(DEFAULT_PORT)
  expect(port('7717@evil.example')).toBe(DEFAULT_PORT)
  expect(port('80/jobs?x=')).toBe(DEFAULT_PORT)
  expect(port('7717#')).toBe(DEFAULT_PORT)
  expect(port(' 7717')).toBe(DEFAULT_PORT)
  expect(port('1e3')).toBe(DEFAULT_PORT)
})

test('a job name cannot carry control, escape or direction characters into the prompt', () => {
  expect(clean('build\u001b[2J\u001b[31m done')).toBe('build [2J [31m done')
  expect(clean('a\nb\rc\td')).toBe('a b c d')
  expect(clean('safe\u202egnp.exe')).toBe('safe gnp.exe')
  expect(clean('x'.repeat(500))?.length).toBe(80)
  expect(clean('reel 03 — ünïcode ✓')).toBe('reel 03 — ünïcode ✓')
  expect(clean(42)).toBe(null)

  const view = parse(JSON.stringify({ jobs: [{ uid: 'u', name: 'evil\u001b[H', state: 'running', progress: 0.5 }] }))
  expect(rows(view?.jobs ?? [])[0]?.name.includes('\u001b')).toBe(false)
})

test('a malformed record is dropped or defaulted, never a crash in the draw', () => {
  const view = parse(
    JSON.stringify({
      jobs: [
        null,
        'text',
        { name: 'no uid' },
        { uid: 'a', name: 7, state: 'running', progress: 'half', done: {}, agent: [] },
        { uid: 'b', name: 'ok', state: 'running', progress: 0.5, progress_mode: 'items', done: 1, total: 2 },
      ],
    }),
  )
  expect(view?.jobs.map(j => j.uid)).toEqual(['a', 'b'])
  expect(rows(view?.jobs ?? []).map(r => r.name)).toEqual(['ok'])
  expect(parse(JSON.stringify({ jobs: Array.from({ length: 999 }, (_, i) => ({ uid: String(i) })) }))?.jobs.length).toBe(200)
})

test('the signature changes only when the drawing would', () => {
  const a = { jobs: [job({})], hasStatusLine: false }
  const same = { jobs: [job({ uid: 'other-uid' })], hasStatusLine: false }
  const moved = { jobs: [job({ progress: 0.6, done: 6 })], hasStatusLine: false }
  expect(signature(a)).toBe(signature(same))
  expect(signature(a) === signature(moved)).toBe(false)
  expect(signature(null)).toBe('')
  expect(signature({ jobs: [job({ state: 'done' })], hasStatusLine: false }).includes('"mark"')).toBe(false)
})
