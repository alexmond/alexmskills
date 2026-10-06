/** One live job as the daemon's `/jobs` reports it (only the fields the band reads). */
export type Job = {
  uid: string
  name: string | null
  state: string
  progress: number | null
  progress_mode: string | null
  done: number | null
  total: number | null
  eta_seconds: number | null
  depth: number | null
  parent: string | null
  agent: string | null
  detached?: string | null
}

/** `auto` draws the band only while no status line is showing the same jobs. */
export type Mode = 'auto' | 'on' | 'off'

export type View = { jobs: Job[]; hasStatusLine: boolean }

declare module 'claude-code' {
  interface PluginState {
    'progress-channel': { mode: Mode; view: View | null }
  }
}
