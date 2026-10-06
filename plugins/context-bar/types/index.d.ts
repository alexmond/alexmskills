export type Slice = {
  name: string
  tokens: number
  color: string
  kind: 'used' | 'free' | 'buffer'
}

export type Snapshot = { slices: Slice[]; total: number; max: number }

declare module 'claude-code' {
  interface PluginState {
    'context-bar': { isOn: boolean; snapshot: Snapshot | null }
  }
}
