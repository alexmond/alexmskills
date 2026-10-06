#!/usr/bin/env node
// A Node producer. No package to install: it calls the CLI.
//
//   PROGRESS_CLI="python3 <plugin>/scripts/progress.py" node node-job.mjs
//   node node-job.mjs               # no PROGRESS_CLI: runs untracked
//
// The CLI is the contract for every language without a library. Three calls:
//   start --name <n> --total <n>   → prints a token
//   step  <token> [-n N] [--detail text]
//   finish <token> [--fail "why"]
// `step` is throttled inside the CLI, but each call is still a process, so
// batch your steps (-n) in a hot loop rather than calling once per item.
import { execFileSync } from 'node:child_process'

const cli = (process.env.PROGRESS_CLI ?? '').split(' ').filter(Boolean)
const DELAY = Number(process.env.DELAY ?? 0.05) * 1000
const sleep = ms => new Promise(r => setTimeout(r, ms))

// Never throws: a missing or broken tracker must not fail the job it watches.
function progress(...args) {
  if (cli.length === 0) return ''
  try {
    // --pid: liveness is tied to THIS process, not the short-lived CLI call.
    const extra = args[0] === 'start' ? ['--pid', String(process.pid)] : []
    return execFileSync(cli[0], [...cli.slice(1), ...args, ...extra], {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'ignore'],
      timeout: 5000,
    }).trim()
  } catch {
    return ''
  }
}

const pages = Array.from({ length: 40 }, (_, i) => `page-${i + 1}.html`)
const token = progress('start', '--name', 'node render', '--total', String(pages.length))
const BATCH = 5

try {
  for (let i = 0; i < pages.length; i += 1) {
    await sleep(DELAY) // ← the real work goes here
    if ((i + 1) % BATCH === 0 && token) {
      progress('step', token, '-n', String(BATCH), '--detail', pages[i])
    }
  }
  if (token) progress('finish', token)
  console.log(`rendered ${pages.length} pages`)
} catch (err) {
  if (token) progress('finish', token, '--fail', String(err?.message ?? err).slice(0, 200))
  throw err
}
