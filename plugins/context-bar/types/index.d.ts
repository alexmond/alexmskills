export type Slice = {
  name: string
  tokens: number
  color: string
  kind: 'used' | 'free' | 'buffer'
}

export type Snapshot = {
  slices: Slice[]
  total: number
  max: number
  /** Where auto-compaction runs; absent when it is off. */
  threshold?: number
  /** Tokens each recent turn added, newest last. */
  growth: number[]
  /** Compactions so far this session. */
  compactions: number
}

declare module 'claude-code' {
  interface PluginState {
    'context-bar': { isOn: boolean; snapshot: Snapshot | null }
  }
}
