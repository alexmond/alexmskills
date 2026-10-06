export type Window = { kind: string; percentUsed: number; resetsAt?: string }

export type Reading = { windows: Window[]; at: number }

/** When the model last answered, and whether it is answering now. */
export type Activity = { lastAt: number | null; isBusy: boolean }

declare module 'claude-code' {
  interface PluginState {
    'usage-bar': { isOn: boolean; reading: Reading | null; activity: Activity; showCache: boolean }
  }
}
