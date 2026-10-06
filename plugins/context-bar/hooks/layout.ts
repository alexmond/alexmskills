import type { Slice } from '../types'

/**
 * Cells per slice for a bar `width` cells wide over a window of `max` tokens.
 * Every non-empty slice gets at least one cell; the largest slice absorbs the
 * rounding so the cells always sum to `width`.
 */
export function cells(slices: readonly Slice[], max: number, width: number): number[] {
  if (slices.length === 0 || width <= 0 || max <= 0) {
    return slices.map(() => 0)
  }

  const out = slices.map(s =>
    s.tokens > 0 ? Math.max(1, Math.round((s.tokens / max) * width)) : 0,
  )
  const biggest = out.indexOf(Math.max(...out))
  const drift = width - out.reduce((a, b) => a + b, 0)
  out[biggest] = Math.max(0, out[biggest] + drift)

  return out
}

export function short(tokens: number): string {
  if (tokens >= 1_000_000) {
    return `${(tokens / 1_000_000).toFixed(1)}m`
  }

  return tokens >= 1000 ? `${(tokens / 1000).toFixed(1)}k` : `${tokens}`
}
