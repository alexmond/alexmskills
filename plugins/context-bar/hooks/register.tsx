import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Slice, Snapshot } from '../types'
import { cells, short } from './layout'

const isOn = atom({ plugin: 'context-bar', key: 'isOn' } as const, true)
const snapshot = atom({ plugin: 'context-bar', key: 'snapshot' } as const, null)

// 'summary' estimates locally and sends no token-count requests, so a
// refresh after every turn costs nothing. /context itself counts 'full'.
async function refresh($: EngineInterface): Promise<void> {
  const { context } = await $.session.usage({ breakdown: 'summary' })
  const b = context.breakdown

  if (!b) {
    return
  }

  const slices: Slice[] = []

  for (const c of b.categories) {
    if (c.kind !== 'deferred' && c.tokens > 0) {
      slices.push({ name: c.name, tokens: c.tokens, color: c.color, kind: c.kind })
    }
  }

  const next: Snapshot = { slices, total: b.totalTokens, max: b.rawMaxTokens }
  await update($, snapshot, () => next)
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'context-bar',
      description: 'Toggle the context window bar above the prompt',
    })
    void refresh($)

    return next(e)
  })

  on('command.run', { command: 'context-bar' }, async $ => {
    const now = !(await read($, isOn))
    await update($, isOn, () => now)

    if (now) {
      await refresh($)
    }

    return { text: `Context bar ${now ? 'on' : 'off'}.` }
  })

  on('turn.complete', async ($, e, next) => {
    const done = await next(e)

    if (await read($, isOn)) {
      void refresh($)
    }

    return done
  })

  on('session.compact', async ($, e, next) => {
    const done = await next(e)
    void refresh($)

    return done
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const snap = await read($, snapshot)

    if (e.props.hasSurvey || snap === null || !(await read($, isOn))) {
      return next(e)
    }

    const { Box, Text } = $.ui.resolve(e)
    // bodyColumns, not viewport.columns: the engine keeps five cells at the
    // right end of the band for its own `[-]`, and a bar sized to the whole
    // terminal wraps a stub onto a second row.
    const width = Math.max(10, e.props.bodyColumns)
    const widths = cells(snap.slices, snap.max, width)
    const percent = Math.round((snap.total / snap.max) * 100)

    // The band holds ONE tree, so a mod that returns only its own hides every mod beneath it.
    // Draw ours, then whatever the rest of the chain draws.
    const below = await next(e)

    return (
      <Box flexDirection="column">
        <Box flexDirection="column">
          <Box>
            {snap.slices.map((s, i) => (
              <Text color={s.color} dimColor={s.kind !== 'used'}>
                {(s.kind === 'used' ? '█' : s.kind === 'buffer' ? '▒' : '░').repeat(widths[i] ?? 0)}
              </Text>
            ))}
          </Box>
          <Box columnGap={2} flexWrap="wrap">
            {/* Named, like every row in the shared band: unlabelled rows from
                two mods read as one block. */}
            <Text bold>Context</Text>
            <Text dimColor>
              {short(snap.total)}/{short(snap.max)} ({percent}%)
            </Text>
            {snap.slices.map(s => (
              <Box>
                <Text color={s.color}>{s.kind === 'used' ? '█' : s.kind === 'buffer' ? '▒' : '░'}</Text>
                <Text dimColor>
                  {' '}
                  {s.name} {short(s.tokens)}
                </Text>
              </Box>
            ))}
          </Box>
        </Box>
        {below}
      </Box>
    )
  })
}
