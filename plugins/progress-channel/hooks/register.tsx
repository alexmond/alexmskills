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
const live = { url: '', drawn: '', ticks: 0, isBusy: false, busySince: 0, inFlight: 0 }

// The host's fetch takes no timeout. A reply that never comes must not hold
// the one-at-a-time guard forever, or the band would freeze on its last frame.
const GIVE_UP_AFTER = 10
// ...but giving up on a request does not end it. Without a ceiling, a daemon
// that never answers would collect one more open request every ten seconds
// for as long as the session lives. Three, then the band waits.
const MAX_IN_FLIGHT = 3

// One GET to the daemon on this machine. `view=mod` tells it this is not a
// status line asking, so `auto` can still tell whether one is wired.
async function refresh($: EngineInterface): Promise<void> {
  const isStuck = live.isBusy && live.ticks - live.busySince > GIVE_UP_AFTER

  if ((live.isBusy && !isStuck) || live.url === '' || live.inFlight >= MAX_IN_FLIGHT) {
    return
  }

  live.inFlight += 1
  live.isBusy = true
  live.busySince = live.ticks
  const mine = live.busySince

  try {
    // The host reads the whole body before this returns and offers no size
    // limit, so `parse` can only refuse an oversized reply, not avoid reading
    // it. The address is fixed to this machine, which is what bounds that.
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
    live.inFlight -= 1

    // Only the newest request clears the guard; a stuck one that finally
    // returns must not release a guard a later request is holding.
    if (live.busySince === mine) {
      live.isBusy = false
    }
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
