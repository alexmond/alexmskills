export type Window = { kind: string; percentUsed: number; resetsAt?: string }

export type Reading = { windows: Window[]; at: number }

declare module 'claude-code' {
  interface PluginState {
    'usage-bar': { isOn: boolean; reading: Reading | null }
  }
}
