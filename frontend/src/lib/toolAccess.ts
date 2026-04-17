export type ToolKey = 'form-filling' | 'schedules' | 'inbox' | 'proposals' | 'pipelines'

const LOCKED_BY_TIER: Record<string, Set<ToolKey>> = {
  free: new Set(),
  starter: new Set(['proposals', 'pipelines']),
  pro: new Set(),
  business: new Set(),
}

export function getLockedTools(tier: string | undefined | null): Set<ToolKey> {
  return LOCKED_BY_TIER[tier || 'free'] ?? new Set()
}

export function isToolLocked(tier: string | undefined | null, tool: ToolKey): boolean {
  return getLockedTools(tier).has(tool)
}
