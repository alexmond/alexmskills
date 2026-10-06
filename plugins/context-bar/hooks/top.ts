import { short } from './layout'

// `/context-bar top`: what, specifically, is filling the window.
//
// The bar shows categories — "Memory files 14.3k". That says where to look,
// not what to cut. The breakdown the bar already fetches also lists every
// memory file, MCP tool, agent and skill with its own token count; this ranks
// them, so the answer is "the 9k CLAUDE.md" or "the server with 40 tools".

/** The parts of the engine's breakdown this reads. */
export type Items = {
  totalTokens: number
  memoryFiles?: ReadonlyArray<{ path: string; tokens: number }>
  mcpTools?: ReadonlyArray<{ name: string; serverName: string; tokens: number; isLoaded: boolean }>
  agents?: ReadonlyArray<{ agentType: string; tokens: number }>
  skills?: { skillFrontmatter: ReadonlyArray<{ name: string; pluginName?: string; tokens: number }> }
}

export type Entry = { kind: 'memory' | 'mcp' | 'agent' | 'skill'; name: string; tokens: number }

// Untrusted text about to be printed: a file path or a tool name comes from
// the repo or from a server. Control and direction characters go.
const UNSAFE = /[\u0000-\u001f\u007f-\u009f\u200b-\u200f\u2028-\u202e\u2066-\u2069\ufeff]/g
const clean = (s: string, max = 60): string => s.slice(0, 400).replace(UNSAFE, ' ').slice(-max)

/** The last two path segments: enough to tell two CLAUDE.md files apart. */
function tail(path: string): string {
  const parts = path.split(/[\\/]/).filter(Boolean)

  return parts.slice(-2).join('/')
}

/** Every countable item, largest first. MCP tools are grouped by server: you connect or disconnect a server, not a tool. */
export function rank(b: Items): Entry[] {
  const out: Entry[] = []

  for (const f of b.memoryFiles ?? []) {
    out.push({ kind: 'memory', name: clean(tail(f.path)), tokens: f.tokens })
  }

  const servers = new Map<string, { tokens: number; tools: number }>()

  for (const t of b.mcpTools ?? []) {
    // A deferred tool's schema is not in the window until the tool is loaded.
    if (t.isLoaded) {
      const s = servers.get(t.serverName) ?? { tokens: 0, tools: 0 }
      servers.set(t.serverName, { tokens: s.tokens + t.tokens, tools: s.tools + 1 })
    }
  }

  for (const [server, s] of servers) {
    out.push({ kind: 'mcp', name: `${clean(server, 40)} (${s.tools} ${s.tools === 1 ? 'tool' : 'tools'})`, tokens: s.tokens })
  }

  for (const a of b.agents ?? []) {
    out.push({ kind: 'agent', name: clean(a.agentType), tokens: a.tokens })
  }

  for (const s of b.skills?.skillFrontmatter ?? []) {
    out.push({ kind: 'skill', name: clean(s.pluginName ? `${s.pluginName}:${s.name}` : s.name), tokens: s.tokens })
  }

  return out.filter(e => Number.isFinite(e.tokens) && e.tokens > 0).sort((x, y) => y.tokens - x.tokens)
}

const HOW: Record<Entry['kind'], string> = {
  memory: 'memory file — trim it, or move detail into a file that is read on demand',
  mcp: 'MCP server — disconnect it for sessions that do not use it',
  agent: 'custom agent — its description is listed in every session',
  skill: 'skill — its description is listed in every session; shorten it or uninstall',
}

/** The reply to `/context-bar top`: the largest few, each with its share and what can be done about it. */
export function report(b: Items, n = 8): string {
  const all = rank(b)

  if (all.length === 0) {
    return 'Nothing itemized to rank: no memory files, loaded MCP tools, custom agents or skills are counted in this session.'
  }

  const shown = all.slice(0, n)
  const width = Math.max(...shown.map(e => e.name.length))
  const lines = shown.map((e, i) => {
    const share = b.totalTokens > 0 ? ` ${String(Math.round((e.tokens / b.totalTokens) * 100)).padStart(2)}%` : ''

    return `${String(i + 1).padStart(2)}. ${e.name.padEnd(width)}  ${short(e.tokens).padStart(6)}${share}  ${e.kind}`
  })
  const kinds = [...new Set(shown.map(e => e.kind))]
  const rest = all.length - shown.length
  const sum = shown.reduce((a, e) => a + e.tokens, 0)

  return [
    `Largest items in the window (${short(sum)} of ${short(b.totalTokens)} in use):`,
    ...lines,
    ...(rest > 0 ? [`    … and ${rest} smaller`] : []),
    '',
    ...kinds.map(k => `${k}: ${HOW[k]}`),
    'Built-in tools, messages and the system prompt are not itemized — see the bar, or /context.',
  ].join('\n')
}
