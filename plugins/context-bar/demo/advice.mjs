// Renders context-bar's compaction advice at each level with the mod's OWN
// function (advise from ../hooks/advice.ts), over sample readings. Used for
// demo/advice.png: a live recording would need a session that is actually
// 70%, 85% and 95% of the way to auto-compact.
//
//   node --experimental-strip-types advice.mjs
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'

// advice.ts imports './layout' the way the engine's bundler resolves it; plain
// node wants a file extension. Join the two files into one module instead of
// changing how the mod is written for the sake of a demo.
const here = new URL('../hooks/', import.meta.url)
const src = name => readFileSync(new URL(name, here), 'utf8')
const dir = mkdtempSync(join(tmpdir(), 'context-bar-'))
const file = join(dir, 'advice.ts')
writeFileSync(file, src('layout.ts').replace(/^import .*$/gm, '') + src('advice.ts').replace(/^import .*$/gm, ''))
const { advise } = await import(pathToFileURL(file).href)

const ANSI = { hint: '2', warn: '33', danger: '31' }
const MARK = { hint: '·', warn: '!', danger: '⚠' }
const base = { max: 1_000_000, threshold: 967_000, growth: [], compactions: 0 }
const samples = [
  ['70% of the way: a quiet hint', { ...base, total: 690_000 }],
  ['85%, or about six turns left: a warning', { ...base, total: 840_000, growth: [22_000, 26_000, 24_000] }],
  ['95%, or two turns left: what will be lost', { ...base, total: 930_000, growth: [22_000, 26_000, 24_000] }],
  ['after a second compaction, at any fill', { ...base, total: 120_000, compactions: 2 }],
]

for (const [label, reading] of samples) {
  const a = advise(reading)
  console.log(`\x1b[2m# ${label}\x1b[0m\n\x1b[${ANSI[a.level]}m${MARK[a.level]} ${a.text}\x1b[0m\n`)
}
