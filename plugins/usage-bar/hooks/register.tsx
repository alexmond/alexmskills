import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register, Timer } from 'claude-code'

import type { Activity, Lifetime, Reading } from '../types'
import { assume, learn } from './cachettl'
import { LABELS, TITLE, cache, hasPlanWindows, percent, resets, tone } from './format'
import { ahead, cells, level, pace, pie } from './pace'

const WIDTH = 10
const isOn = atom({ plugin: 'usage-bar', key: 'isOn' } as const, true)
const reading = atom({ plugin: 'usage-bar', key: 'reading' } as const, null)
const IDLE: Activity = { lastAt: null, isBusy: false }
const activity = atom({ plugin: 'usage-bar', key: 'activity' } as const, IDLE)
const showCache = atom({ plugin: 'usage-bar', key: 'showCache' } as const, true)
// Null until the first reading says what kind of account this is.
const lifetime = atom({ plugin: 'usage-bar', key: 'lifetime' } as const, null)
const isCacheOff = atom({ plugin: 'usage-bar', key: 'isCacheOff' } as const, false)

// Claude Code's own cache switches, read once at start.
const env: { disable?: string; force5m?: string; enable1h?: string } = {}

// The plain usage call costs nothing: it reads what the last API response reported.
async function refresh($: EngineInterface): Promise<void> {
  const { rateLimits } = await $.session.usage()
  const next: Reading = { windows: rateLimits, at: await $.clock.now() }
  await update($, reading, () => next)

  // The starting assumption needs to know the kind of account, which only a
  // reading tells. Made once; after that only observed traffic changes it.
  if ((await read($, lifetime)) === null && !(await read($, isCacheOff))) {
    const first: Lifetime = assume(env, hasPlanWindows(rateLimits))

    if (first === null) {
      await update($, isCacheOff, () => true)
    } else {
      await update($, lifetime, () => first)
    }
  }
}

// What the turn that just ended says about how long the cache lives.
async function observe($: EngineInterface, written: number, model: string, at: number): Promise<void> {
  const prev = await read($, activity)
  const known = await read($, lifetime)
  const { context } = await $.session.usage()

  if (known !== null) {
    const next = learn(known, {
      gapMs: prev.lastAt === null || prev.promptAt === undefined ? null : prev.promptAt - prev.lastAt,
      written,
      prior: prev.contextTokens ?? 0,
      isSameModel: prev.model === model,
      isAfterCompact: prev.isAfterCompact === true,
    })

    if (next.minutes !== known.minutes || next.source !== known.source) {
      await update($, lifetime, () => next)
    }
  }

  await update($, activity, () => ({ lastAt: at, isBusy: false, model, contextTokens: context.tokens ?? 0 }))
}

export const register: Register = on => {
  let timer: Timer | undefined

  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'usage-bar',
      description: 'Toggle the rate-limit usage bar above the prompt (or: cache, to show or hide the cache countdown)',
    })

    if ((await $.store.get('showCache')) === false) {
      await update($, showCache, () => false)
    }

    env.disable = await $.env.get('DISABLE_PROMPT_CACHING')
    env.force5m = await $.env.get('FORCE_PROMPT_CACHING_5M')
    env.enable1h = await $.env.get('ENABLE_PROMPT_CACHING_1H')

    // `every` returns a Timer, not a function. Calling it — as this did until
    // 0.2.2 — throws on the second session.start (a hot reload, a resume), and
    // the first timer is never stopped.
    timer?.cancel()
    // The countdown moves by the minute, so a minute is the finest tick worth drawing.
    timer = $.clock.every(60_000, () => void refresh($))
    void refresh($)

    return next(e)
  })

  on('command.run', { command: 'usage-bar' }, async ($, e) => {
    if (e.args.trim().toLowerCase() === 'cache') {
      const shown = !(await read($, showCache))
      await update($, showCache, () => shown)
      await $.store.set('showCache', shown)

      const known = await read($, lifetime)
      const how =
        known === null
          ? ''
          : ` Lifetime ${known.minutes} min, ${known.source === 'observed' ? "observed in this session's traffic" : 'assumed from the kind of account until the traffic shows which'}.`

      return { text: `Cache countdown ${shown ? 'on' : 'off'}.${shown ? how : ''}` }
    }

    const now = !(await read($, isOn))
    await update($, isOn, () => now)

    if (now) {
      await refresh($)
    }

    return { text: `Usage bar ${now ? 'on' : 'off'}.` }
  })

  // The cache is refreshed by every request, so it is warm for as long as the
  // model is answering and starts to age when the turn ends.
  on('prompt.submit', async ($, e, next) => {
    // This hook sits in the path of every prompt. A countdown is not worth a
    // prompt that fails to send, so nothing here may throw past this line.
    try {
      const at = await $.clock.now()
      await update($, activity, a => ({ ...a, isBusy: true, promptAt: at }))
    } catch {
      // The figure will be stale for one turn. That is the whole cost.
    }

    return next(e)
  })

  on('turn.complete', async ($, e, next) => {
    const done = await next(e)
    const at = await $.clock.now()

    if ('usage' in e && e.usage !== undefined) {
      await observe($, e.usage.cache_creation_input_tokens, e.usage.model, at)
    } else {
      // An aborted or refused turn reports no figures: it still answered, so
      // the clock restarts, but it is evidence of nothing.
      await update($, activity, a => ({ ...a, lastAt: at, isBusy: false }))
    }

    void refresh($)

    return done
  })

  // A compaction rewrites the context, so the next turn writes all of it to
  // the cache whatever the lifetime is. That turn must not count as a miss.
  on('session.compact', async ($, e, next) => {
    const done = await next(e)
    await update($, activity, a => ({ ...a, isAfterCompact: true }))

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
    const known = await read($, lifetime)
    const warmth =
      (await read($, showCache)) && known !== null && !(await read($, isCacheOff))
        ? cache(await read($, activity), now.at, known.minutes)
        : null
    let worst = 0
    let worstColor: 'success' | 'warning' | 'error' = 'success'
    const bars = now.windows.map(w => {
      const p = pace(w, now.at)
      const run = level(p)
      // Green with room to spare, yellow from 70%, red from 90% (format.ts) —
      // and never calmer than the pace: a window on course to run out before
      // it resets is yellow at any fill, red when far over.
      const base = tone(w.percentUsed)
      const color = run === 'far' || base === 'error' ? 'error' : run === 'over' || base === 'warning' ? 'warning' : 'success'

      if (w.percentUsed >= worst) {
        worst = w.percentUsed
        worstColor = color
      }

      return (
        <Box>
          <Text>{LABELS[w.kind] ?? w.kind} </Text>
          {cells(w.percentUsed, WIDTH, p).map(c =>
            c.kind === 'used' ? <Text color={color}>{c.text}</Text> : c.kind === 'mark' ? <Text>{c.text}</Text> : <Text dimColor>{c.text}</Text>,
          )}
          <Text color={color}>
            {' '}
            {percent(w)}
            {ahead(p)}
          </Text>
          <Text dimColor> {resets(w, now.at)}</Text>
        </Box>
      )
    })

    return (
      <Box flexDirection="column">
        <Box columnGap={3} flexWrap="wrap">
          <Box>
            {/* A one-cell pie of the fullest window, in its colour: the row's state at a glance. */}
            <Text color={worstColor}>{pie(worst / 100)} </Text>
            <Text bold>{TITLE}</Text>
          </Box>
          {bars}
          {warmth === null ? null : (
            <Text color={warmth.tone === 'warning' ? 'warning' : undefined} dimColor={warmth.tone === 'quiet'}>
              ⚡ {warmth.text}
            </Text>
          )}
        </Box>
        {below}
      </Box>
    )
  })
}
