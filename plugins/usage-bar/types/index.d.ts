export type Window = { kind: string; percentUsed: number; resetsAt?: string }

export type Reading = { windows: Window[]; at: number }

/** When the model last answered, and whether it is answering now. */
export type Activity = {
  lastAt: number | null
  isBusy: boolean
  /** When the current prompt was sent: the end of the pause the cache had to outlive. */
  promptAt?: number
  /** Which model answered last, and how big the context was then. */
  model?: string
  contextTokens?: number
  /** A compaction or clear happened since the last answer. */
  isAfterCompact?: boolean
}

/** The cache lifetime in use: assumed until the session's traffic shows which. Null when caching is off. */
export type Lifetime = { minutes: 5 | 60; source: 'assumed' | 'observed' } | null

declare module 'claude-code' {
  interface PluginState {
    'usage-bar': {
      isOn: boolean
      reading: Reading | null
      activity: Activity
      showCache: boolean
      lifetime: Lifetime
      isCacheOff: boolean
    }
  }
}
