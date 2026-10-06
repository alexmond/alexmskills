import { expect, test } from 'claude-code/testing'

import { rank, report } from './top'
import type { Items } from './top'

const items: Items = {
  totalTokens: 100_000,
  memoryFiles: [
    { path: '/home/u/proj/CLAUDE.md', tokens: 9000 },
    { path: '/home/u/.claude/CLAUDE.md', tokens: 4000 },
  ],
  mcpTools: [
    { name: 'list', serverName: 'unifi', tokens: 6000, isLoaded: true },
    { name: 'get', serverName: 'unifi', tokens: 5000, isLoaded: true },
    { name: 'search', serverName: 'gmail', tokens: 700, isLoaded: true },
    { name: 'huge', serverName: 'deferred', tokens: 99_000, isLoaded: false },
  ],
  agents: [{ agentType: 'dc-scout', tokens: 300 }],
  skills: { skillFrontmatter: [{ name: 'skill-linter', pluginName: 'skill-linter', tokens: 250 }, { name: 'bare', tokens: 0 }] },
}

test('items are ranked largest first, MCP tools grouped by server', () => {
  expect(rank(items).map(e => [e.kind, e.name, e.tokens])).toEqual([
    ['mcp', 'unifi (2 tools)', 11_000],
    ['memory', 'proj/CLAUDE.md', 9000],
    ['memory', '.claude/CLAUDE.md', 4000],
    ['mcp', 'gmail (1 tool)', 700],
    ['agent', 'dc-scout', 300],
    ['skill', 'skill-linter:skill-linter', 250],
  ])
})

test('a deferred tool is not in the window, so it is not ranked', () => {
  expect(rank(items).some(e => e.name.includes('deferred'))).toBe(false)
})

test('two files with the same name are told apart by their folder', () => {
  const names = rank(items).filter(e => e.kind === 'memory').map(e => e.name)
  expect(new Set(names).size).toBe(2)
})

test('the report gives a share, says what each kind is, and what can be done', () => {
  const text = report(items, 3)
  expect(text.split('\n')[0]).toBe('Largest items in the window (24.0k of 100.0k in use):')
  expect(text.includes(' 1. unifi (2 tools)')).toBe(true)
  expect(text.includes('11.0k 11%  mcp')).toBe(true)
  expect(text.includes('… and 3 smaller')).toBe(true)
  expect(text.includes('mcp: MCP server — disconnect it')).toBe(true)
  expect(text.includes('memory: memory file — trim it')).toBe(true)
  expect(text.includes('skill:')).toBe(false)
  expect(text.includes('Built-in tools, messages and the system prompt are not itemized')).toBe(true)
})

test('with nothing itemized it says so instead of printing an empty list', () => {
  expect(report({ totalTokens: 5000 }).startsWith('Nothing itemized to rank')).toBe(true)
  expect(report({ totalTokens: 0, memoryFiles: [{ path: 'a', tokens: 0 }] }).startsWith('Nothing itemized')).toBe(true)
})

test('names from the repo or a server cannot carry control characters into the terminal', () => {
  const hostile: Items = {
    totalTokens: 1000,
    memoryFiles: [{ path: '/x/evil\u001b[2J\u202e.md', tokens: 10 }],
    mcpTools: [{ name: 't', serverName: 'srv\u001b[31m\n', tokens: 20, isLoaded: true }],
  }
  const text = report(hostile)
  expect(text.includes('\u001b')).toBe(false)
  expect(text.includes('\u202e')).toBe(false)
  expect(report({ totalTokens: 10, agents: [{ agentType: 'a'.repeat(5000), tokens: 5 }] }).length < 600).toBe(true)
})

test('junk token counts are dropped, not ranked', () => {
  expect(rank({ totalTokens: 1, agents: [{ agentType: 'a', tokens: Number.NaN }, { agentType: 'b', tokens: -5 }] })).toEqual([])
})
