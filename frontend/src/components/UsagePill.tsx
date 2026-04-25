import { useEffect, useState } from 'react'
import { Badge } from '@/components/ui/badge'
import api from '@/lib/api'
import { useAuthStore } from '@/store/authStore'

interface UsageWarning {
  warning: string | null
  pages_used: number
  pages_limit: number
  overage_pages: number
  overage_rate_cents_per_page: number | null
  usage_percent: number
  tier: string
  next_tier: { name: string; display_name: string; price_monthly: number; pages_per_month: number } | null
}

export default function UsagePill() {
  const { user } = useAuthStore()
  const [usage, setUsage] = useState<UsageWarning | null>(null)

  useEffect(() => {
    const refresh = () => {
      api.get('/payments/usage-warning').then(r => setUsage(r.data)).catch(() => {})
    }
    refresh()
    window.addEventListener('gridpull:usage-changed', refresh)
    return () => window.removeEventListener('gridpull:usage-changed', refresh)
  }, [])

  if (!usage) return null
  const tier = (usage.tier || user?.subscription_tier || 'free')
  const tierLabel = tier.charAt(0).toUpperCase() + tier.slice(1)

  return (
    <div className="flex items-center gap-2 flex-shrink-0">
      <span className="hidden sm:inline text-xs text-muted-foreground whitespace-nowrap">
        {usage.pages_used.toLocaleString()}/{usage.pages_limit.toLocaleString()} pages
      </span>
      <Badge
        variant={usage.usage_percent >= 80 ? 'destructive' : 'blue'}
        className="font-mono text-[11px]"
      >
        {tierLabel}
      </Badge>
    </div>
  )
}
