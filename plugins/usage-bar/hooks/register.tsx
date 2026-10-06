import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register, Timer } from 'claude-code'

import type { Reading } from '../types'
import { LABELS, TITLE, filled, percent, resets, tone } from './format'

const WIDTH = 10
const isOn = atom({ plugin: 'usage-bar', key: 'isOn' } as const, true)
const reading = atom({ plugin: 'usage-bar', key: 'reading' } as const, null)

// The plain usage call costs nothing: it reads what the last API response reported.
async function refresh($: EngineInterface): Promise<void> {
  const { rateLimits } = await $.session.usage()
  const next: Reading = { windows: rateLimits, at: await $.clock.now() }
  await update($, reading, () => next)
}

export const register: Register = on => {
  let timer: Timer | undefined

  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'usage-bar',
      description: 'Toggle the rate-limit usage bar above the prompt',
    })
    // `every` returns a Timer, not a function. Calling it — as this did until
    // 0.2.2 — throws on the second session.start (a hot reload, a resume), and
    // the first timer is never stopped.
    timer?.cancel()
    // The countdown moves by the minute, so a minute is the finest tick worth drawing.
    timer = $.clock.every(60_000, () => void refresh($))
    void refresh($)

    return next(e)
  })

  on('command.run', { command: 'usage-bar' }, async $ => {
    const now = !(await read($, isOn))
    await update($, isOn, () => now)

    if (now) {
      await refresh($)
    }

    return { text: `Usage bar ${now ? 'on' : 'off'}.` }
  })

  on('turn.complete', async ($, e, next) => {
    const done = await next(e)
    void refresh($)

    return done
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const now = await read($, reading)

    if (e.props.hasSurvey || now === null || now.windows.length === 0 || !(await read($, isOn))) {
      return next(e)
    }

    const { Box, Text } = $.ui.resolve(e)
    // The band holds ONE tree, so a mod that returns only its own hides every mod beneath it.
    // Draw ours, then whatever the rest of the chain draws.
    const below = await next(e)
    const bars = now.windows.map(w => {
      const n = filled(w.percentUsed, WIDTH)
      // Green with room to spare, yellow from 70%, red from 90% (format.ts).
      // Bar and figure share the colour, so the state reads from either: near
      // the limit the bar is nearly full and the number is what still moves.
      const color = tone(w.percentUsed)

      return (
        <Box>
          <Text>{LABELS[w.kind] ?? w.kind} </Text>
          <Text color={color}>{'█'.repeat(n)}</Text>
          <Text dimColor>{'░'.repeat(WIDTH - n)}</Text>
          <Text color={color}> {percent(w)}</Text>
          <Text dimColor> {resets(w, now.at)}</Text>
        </Box>
      )
    })

    return (
      <Box flexDirection="column">
        <Box columnGap={3} flexWrap="wrap">
          <Text bold>{TITLE}</Text>
          {bars}
        </Box>
        {below}
      </Box>
    )
  })
}
