import { expect, test } from 'claude-code/testing'

import type { Slice } from '../types'
import { cells, short } from './layout'

const slice = (name: string, tokens: number, kind: Slice['kind'] = 'used'): Slice => ({
  name,
  tokens,
  color: 'inactive',
  kind,
})

test('cells always sum to the bar width', () => {
  const slices = [slice('Messages', 877_100), slice('Memory', 30_200), slice('Free', 23_900, 'free')]
  const out = cells(slices, 1_000_000, 78)

  expect(out.reduce((a, b) => a + b, 0)).toBe(78)
})

test('a small non-empty slice still gets one cell', () => {
  const out = cells([slice('Messages', 990_000), slice('MCP tools', 663)], 1_000_000, 40)

  expect(out[1]).toBe(1)
})

test('short formats tokens as /context does', () => {
  expect(short(663)).toBe('663')
  expect(short(30_200)).toBe('30.2k')
  expect(short(1_000_000)).toBe('1.0m')
})
