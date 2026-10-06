import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register, Timer } from 'claude-code'

import type { Mode, View } from '../types'
import { isShown, nextMode, parse, port, rows, signature } from './format'

const mode = atom({ plugin: 'progress-channel', key: 'mode' } as const, 'auto')
const view = atom({ plugin: 'progress-channel', key: 'view' } as const, null)

// A second while something is running, so the bar moves; a slower look
// otherwise, which is only there to notice the next job starting. Polling
// rather than hooking `tool.call`: a hook there sits in the path of every
// tool call, and a progress bar has no business being able to break one.
const IDLE_EVERY = 2

// Module state: it starts over on a hot reload, which is right — the next
// tick fetches again and redraws.
const live = { url: '', drawn: '', ticks: 0, isBusy: false }

// One GET to the daemon on this machine. `view=mod` tells it this is not a
// status line asking, so `auto` can still tell whether one is wired.
async function refresh($: EngineInterface): Promise<void> {
  if (live.isBusy || live.url === '') {
    return
  }

  live.isBusy = true

  try {
    const { ok, text } = await $.http.fetch(live.url)
    const next: View | null = ok ? parse(text) : null
    const sig = signature(next)

    // Most ticks change nothing. Writing only on a change is what keeps an
    // idle session from redrawing the band every second.
    if (sig !== live.drawn) {
      live.drawn = sig
      await update($, view, () => next)
    }
  } catch {
    // No daemon is the normal state until the first job: draw nothing.
    if (live.drawn !== '') {
      live.drawn = ''
      await update($, view, () => null)
    }
  } finally {
    live.isBusy = false
  }
}

export const register: Register = on => {
  let timer: Timer | undefined

  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'progress-bar',
      description: 'Show or hide the live job bars above the prompt (on, off, auto)',
    })

    // The host is fixed and the port is a checked number, so the request can
    // only ever go to this machine.
    const at = port(await $.env.get('PROGRESS_PORT'))
    const session = encodeURIComponent(await $.session.id())
    live.url = `http://127.0.0.1:${at}/jobs?session=${session}&view=mod`

    const saved = await $.store.get('mode')

    if (saved === 'on' || saved === 'off' || saved === 'auto') {
      await update($, mode, () => saved)
    }

    timer?.cancel()
    timer = $.clock.every(1000, () => {
      live.ticks += 1

      if (live.drawn.includes('"mark"') || live.ticks % IDLE_EVERY === 0) {
        void refresh($)
      }
    })
    void refresh($)

    return next(e)
  })

  on('command.run', { command: 'progress-bar' }, async ($, e) => {
    const now: Mode = nextMode(e.args, await read($, mode), await read($, view))
    await update($, mode, () => now)
    await $.store.set('mode', now)
    await refresh($)

    const note = { on: 'on', off: 'off', auto: 'auto (hidden while a status line shows the same jobs)' }

    return { text: `Progress bar ${note[now]}.` }
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const now = await read($, view)
    const lines = now === null ? [] : rows(now.jobs)

    if (e.props.hasSurvey || lines.length === 0 || !isShown(await read($, mode), now)) {
      return next(e)
    }

    const { Box, Text } = $.ui.resolve(e)
    // The band holds ONE tree, so a mod that returns only its own hides every mod beneath it.
    // Draw ours, then whatever the rest of the chain draws.
    const below = await next(e)

    return (
      <Box flexDirection="column">
        {lines.map(r => (
          <Box>
            <Text color={r.tone}>
              {r.mark} {r.name} {r.bar}
            </Text>
            <Text> {r.percent}</Text>
            <Text dimColor> {r.tail}</Text>
          </Box>
        ))}
        {below}
      </Box>
    )
  })
}
