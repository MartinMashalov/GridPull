import { useState, useEffect } from 'react'
import { trackEvent } from '@/lib/analytics'
import {
  CreditCard, Check, X, Settings,
  Crown, Rocket, Building2, FileText, AlertTriangle,
  ChevronRight, BarChart3, Clock,
  CheckCircle2, AlertCircle, Loader2,
} from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import api from '@/lib/api'
import toast from 'react-hot-toast'
import { useSearchParams } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Progress } from '@/components/ui/progress'
import { cn } from '@/lib/utils'

interface TierInfo {
  name: string
  display_name: string
  price_monthly: number
  pages_per_month: number
  max_file_size_mb: number
  overage_rate_cents_per_page: number | null
  has_pipeline: boolean
}

interface JobHistoryItem {
  job_id: string
  status: string
  file_count: number
  filenames: string[]
  fields: string[]
  format: string
  cost: number
  created_at: string | null
}

interface JobHistoryData {
  jobs: JobHistoryItem[]
  total: number
  pages_used_this_period: number
  pages_limit: number
  usage_percent: number
  tier: string
}

interface SubscriptionData {
  tier: TierInfo
  status: string
  pages_used: number
  overage_pages: number
  pages_limit: number
  usage_percent: number
  current_period_end: string | null
  all_tiers: TierInfo[]
}

const TIER_ICONS: Record<string, React.ReactNode> = {
  free: <FileText size={18} />,
  starter: <Rocket size={18} />,
  pro: <Crown size={18} />,
  business: <Building2 size={18} />,
}

const TIER_COLORS: Record<string, string> = {
  free: 'text-muted-foreground',
  starter: 'text-blue-500',
  pro: 'text-amber-500',
  business: 'text-violet-500',
}

const TIER_BG: Record<string, string> = {
  free: 'bg-muted/50',
  starter: 'bg-blue-500/10',
  pro: 'bg-amber-500/10',
  business: 'bg-violet-500/10',
}

const TIER_BORDER: Record<string, string> = {
  free: 'border-border',
  starter: 'border-blue-500/30',
  pro: 'border-amber-500/30',
  business: 'border-violet-500/30',
}

export default function SettingsPage() {
  const { user, updateSubscription } = useAuthStore()
  const [searchParams, setSearchParams] = useSearchParams()
  const [sub, setSub] = useState<SubscriptionData | null>(null)
  const [loadingSub, setLoadingSub] = useState(true)
  const [subscribing, setSubscribing] = useState<string | null>(null)
  const [, setCanceling] = useState(false)
  const [confirmTier, setConfirmTier] = useState<TierInfo | null>(null)
  const [savedCard, setSavedCard] = useState<{ brand: string; last4: string } | null | undefined>(undefined)
  const [loadingCard, setLoadingCard] = useState(false)
  const [history, setHistory] = useState<JobHistoryData | null>(null)
  const [loadingHistory, setLoadingHistory] = useState(false)
  const [historyLoaded, setHistoryLoaded] = useState(false)

  const fetchHistory = () => {
    setLoadingHistory(true)
    api.get('/documents/history?limit=50')
      .then(r => setHistory(r.data))
      .catch(() => {})
      .finally(() => { setLoadingHistory(false); setHistoryLoaded(true) })
  }

  const fetchSubscription = () => {
    setLoadingSub(true)
    api.get('/payments/subscription')
      .then(r => {
        setSub(r.data)
        updateSubscription({
          subscription_tier: r.data.tier.name,
          subscription_status: r.data.status,
          pages_used_this_period: r.data.pages_used,
          current_period_end: r.data.current_period_end,
          has_card: r.data.has_card ?? false,
        })
      })
      .catch(err => {
        console.error('Failed to load subscription', err?.response?.status, err?.response?.data || err?.message)
      })
      .finally(() => setLoadingSub(false))
  }

  useEffect(() => {
    fetchSubscription()
    api.get('/payments/saved-card').then(r => setSavedCard(r.data.card)).catch(() => setSavedCard(null))
  }, [])

  useEffect(() => {
    const subscription = searchParams.get('subscription')
    const card = searchParams.get('card')

    if (subscription === 'success') {
      toast.success('Subscription activated!')
      setSearchParams({})
      fetchSubscription()
    }
    if (subscription === 'cancelled') {
      setSearchParams({})
    }
    if (card === 'saved') {
      toast.success('Card saved successfully!')
      api.get('/payments/saved-card').then(r => {
        setSavedCard(r.data.card)
        if (r.data.card) updateSubscription({ has_card: true })
      }).catch(() => {})
      setSearchParams({})
    }
  }, [])

  const confirmAndSubscribe = async (tierName: string) => {
    setSubscribing(tierName)
    setConfirmTier(null)
    try {
      if (sub?.tier.name && sub.tier.name !== 'free' && tierName !== 'free') {
        const r = await api.post('/payments/change-subscription', { tier: tierName })
        if (r.data.checkout_url) {
          window.location.href = r.data.checkout_url
          return
        }
        toast.success(`Plan changed to ${TIERS_DISPLAY[tierName] || tierName}!`)
        fetchSubscription()
      } else {
        const r = await api.post('/payments/create-subscription', { tier: tierName })
        window.location.href = r.data.checkout_url
        return
      }
    } catch (e: any) {
      toast.error(e.response?.data?.detail || 'Failed to change plan')
    } finally {
      setSubscribing(null)
    }
  }

  const TIERS_DISPLAY: Record<string, string> = { free: 'Free', starter: 'Starter', pro: 'Pro', business: 'Business' }

  const TIER_FEATURES: Record<string, string[]> = {
    free: [
      'No credit card required',
      '500 pages/month',
      'All 5 tools unlocked',
    ],
    starter: [
      '7,500 pages/month',
      'Fill Applications, Schedules, and Document Inbox',
      '$0.012/page overage',
    ],
    pro: [
      '25,000 pages/month',
      'All 5 tools',
      '$0.010/page overage',
    ],
    business: [
      '100,000 pages/month',
      'All 5 tools for your entire team',
      '$0.006/page overage',
    ],
  }

  const handleCancel = async () => {
    setCanceling(true)
    try {
      await api.post('/payments/cancel-subscription')
      toast.success('Subscription will cancel at period end')
      trackEvent('subscription_cancel')
      fetchSubscription()
    } catch {
      toast.error('Failed to cancel')
    } finally {
      setCanceling(false)
    }
  }

  const handleReactivate = async () => {
    try {
      await api.post('/payments/reactivate-subscription')
      toast.success('Subscription reactivated!')
      fetchSubscription()
    } catch {
      toast.error('Failed to reactivate')
    }
  }

  const handleRemoveCard = async () => {
    setLoadingCard(true)
    try {
      await api.delete('/payments/saved-card')
      setSavedCard(null)
      updateSubscription({ has_card: false })
      toast.success('Card removed')
    } catch {
      toast.error('Failed to remove card')
    } finally {
      setLoadingCard(false)
    }
  }

  const handleSetupCard = async () => {
    setLoadingCard(true)
    try {
      const r = await api.post('/payments/setup-card')
      window.location.href = r.data.setup_url
    } catch {
      toast.error('Failed to set up card')
      setLoadingCard(false)
    }
  }


  const currentTier = sub?.tier.name || user?.subscription_tier || 'free'
  const tierOrder = ['free', 'starter', 'pro', 'business']

  return (
    <div className="relative p-4 sm:p-8 max-w-4xl mx-auto">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-48 bg-gradient-to-b from-primary/[0.03] to-transparent rounded-t-xl" />

      <div className="relative border-b border-border pb-5 mb-6">
        <div className="flex items-center gap-3 mb-2">
          <div className="p-2 rounded-xl bg-primary/10">
            <Settings size={20} className="text-primary" />
          </div>
          <h1 className="text-xl font-semibold text-foreground">Settings</h1>
        </div>
        <p className="text-muted-foreground text-sm mt-1 max-w-2xl leading-relaxed">
          Start free with 500 pages/month. From solo agents to large brokerages, scale with your business. Process thousands of pages for a fraction of the cost of manual data entry.
        </p>
      </div>

      <Tabs defaultValue={searchParams.get('tab') || 'subscription'}>
        <TabsList className="mb-6 w-full sm:w-auto">
          <TabsTrigger value="subscription"><Crown size={13} />Subscription</TabsTrigger>
          <TabsTrigger value="usage" onClick={() => { if (!historyLoaded) fetchHistory() }}><BarChart3 size={13} />Usage</TabsTrigger>
          <TabsTrigger value="payment"><CreditCard size={13} />Payment</TabsTrigger>
        </TabsList>

        {/* ── Subscription ───────────────────────────────────────────── */}
        <TabsContent value="subscription" className="space-y-5 mt-0">
          {loadingSub ? (
            <div className="flex items-center justify-center py-12">
              <div className="w-5 h-5 border-2 border-border border-t-foreground rounded-full animate-spin" />
            </div>
          ) : sub ? (
            <>
              {/* Current plan card */}
              <div className={cn(
                'relative overflow-hidden rounded-xl border p-6 pb-4',
                TIER_BORDER[currentTier],
                TIER_BG[currentTier],
              )}>
                <div className="flex items-start justify-between">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <div className={cn('p-1.5 rounded-lg', TIER_BG[currentTier], TIER_COLORS[currentTier])}>
                        {TIER_ICONS[currentTier]}
                      </div>
                      <div>
                        <p className="text-sm font-semibold">{sub.tier.display_name} Plan</p>
                        {sub.tier.price_monthly > 0 && (
                          <p className="text-xs text-muted-foreground">${(sub.tier.price_monthly / 100).toFixed(0)}/month</p>
                        )}
                      </div>
                    </div>
                    {sub.status === 'canceled' && (
                      <div className="mt-2 flex items-center gap-1.5">
                        <Badge variant="destructive" className="text-[10px]">Cancels at period end</Badge>
                        <button onClick={handleReactivate} className="text-xs text-primary hover:underline">
                          Reactivate
                        </button>
                      </div>
                    )}
                    {sub.status === 'past_due' && (
                      <Badge variant="destructive" className="mt-2 text-[10px]">Payment past due</Badge>
                    )}
                  </div>
                  {sub.current_period_end && (
                    <p className="text-[11px] text-muted-foreground">
                      Renews {new Date(sub.current_period_end).toLocaleDateString()}
                    </p>
                  )}
                </div>

                {/* Usage meter */}
                <div className="mt-5">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-medium">Pages used this period</span>
                    <span className="text-xs text-muted-foreground tabular-nums">
                      {sub.pages_used.toLocaleString()} / {sub.pages_limit.toLocaleString()}
                    </span>
                  </div>
                  <Progress
                    value={sub.usage_percent}
                    className={cn(
                      sub.usage_percent >= 100 && '[&>div]:bg-red-500',
                      sub.usage_percent >= 80 && sub.usage_percent < 100 && '[&>div]:bg-amber-500',
                    )}
                  />
                  {sub.usage_percent >= 80 && sub.usage_percent < 100 && (
                    <div className="mt-2.5 flex items-center gap-1.5 text-amber-500">
                      <AlertTriangle size={12} />
                      <p className="text-xs font-medium">
                        You've used {sub.pages_used.toLocaleString()} of {sub.pages_limit.toLocaleString()} pages.
                        {currentTier !== 'business' && ' Upgrade to avoid overage charges.'}
                      </p>
                    </div>
                  )}
                  {sub.usage_percent >= 100 && currentTier === 'free' && (
                    <div className="mt-2.5 flex items-center gap-1.5 text-red-500">
                      <AlertTriangle size={12} />
                      <p className="text-xs font-medium">
                        You've hit your free limit. Upgrade to continue extracting.
                      </p>
                    </div>
                  )}
                  {sub.overage_pages > 0 && sub.tier.overage_rate_cents_per_page && (
                    <p className="mt-2 text-xs text-muted-foreground">
                      {sub.overage_pages.toLocaleString()} overage page{sub.overage_pages !== 1 ? 's' : ''} this period
                      (${(sub.tier.overage_rate_cents_per_page / 100).toFixed(3)}/page)
                    </p>
                  )}
                </div>

              </div>

              {/* Tier cards */}
              <div>
                <p className="text-sm font-semibold mb-3">
                  {currentTier === 'free' ? 'Choose a plan' : 'Change plan'}
                </p>
                <div className="grid gap-3">
                  {sub.all_tiers.map(tier => {
                    const isCurrent = tier.name === currentTier
                    const isUp = tierOrder.indexOf(tier.name) > tierOrder.indexOf(currentTier)


                    const features = TIER_FEATURES[tier.name] ?? []

                    return (
                      <div
                        key={tier.name}
                        className={cn(
                          'rounded-xl border p-4 transition-all',
                          isCurrent
                            ? cn(TIER_BORDER[tier.name], TIER_BG[tier.name])
                            : 'border-border hover:shadow-sm hover:border-border/80',
                          tier.name === 'pro' && !isCurrent && 'border-amber-500/30 bg-amber-500/[0.03]',
                        )}
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-3 min-w-0">
                            <div className={cn('p-2 rounded-lg', TIER_BG[tier.name], TIER_COLORS[tier.name])}>
                              {TIER_ICONS[tier.name]}
                            </div>
                            <div className="min-w-0">
                              <div className="flex items-center gap-2 flex-wrap">
                                <p className="text-sm font-semibold">{tier.display_name}</p>
                                {isCurrent && (
                                  <Badge className="text-[10px] bg-primary/15 text-primary border-primary/30">Current</Badge>
                                )}
                                {tier.name === 'pro' && !isCurrent && (
                                  <Badge className="text-[10px] bg-amber-500/20 text-amber-600 border-amber-500/30">Popular</Badge>
                                )}
                              </div>
                            </div>
                          </div>
                          <div className="flex items-center gap-3 flex-shrink-0 ml-3">
                            <div className="text-right">
                              {tier.price_monthly > 0 ? (
                                <>
                                  <p className="text-sm font-bold">${(tier.price_monthly / 100).toFixed(0)}</p>
                                  <p className="text-[10px] text-muted-foreground">/month</p>
                                </>
                              ) : (
                                <p className="text-sm font-bold">Free</p>
                              )}
                            </div>
                            {isCurrent ? (
                              <div className="min-w-[90px] flex justify-center">
                                <Check size={16} className="text-primary" />
                              </div>
                            ) : (
                              <Button
                                size="sm"
                                variant={isUp ? 'default' : 'outline'}
                                disabled={!!subscribing}
                                onClick={() => {
                                  if (tier.name === 'free') {
                                    setConfirmTier(tier)
                                  } else if (currentTier === 'free') {
                                    // Going from free to paid — Stripe Checkout handles card
                                    confirmAndSubscribe(tier.name)
                                  } else {
                                    // Switching between paid plans — show confirmation
                                    setConfirmTier(tier)
                                  }
                                }}
                                className="min-w-[90px]"
                              >
                                {subscribing === tier.name ? (
                                  <div className="w-3.5 h-3.5 border-2 border-current/30 border-t-current rounded-full animate-spin" />
                                ) : tier.name === 'free' ? (
                                  'Downgrade'
                                ) : isUp ? (
                                  <>Upgrade <ChevronRight size={12} /></>
                                ) : (
                                  'Downgrade'
                                )}
                              </Button>
                            )}
                          </div>
                        </div>
                        {features.length > 0 && (
                          <ul className="mt-3 space-y-1.5">
                            {features.map(f => (
                              <li key={f} className="flex items-start gap-2 text-xs text-muted-foreground">
                                <Check size={12} className="text-primary mt-0.5 flex-shrink-0" />
                                <span>{f}</span>
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>

              {/* ── Plan change confirmation modal ── */}
              {confirmTier && (() => {
                const target = confirmTier
                const isUp = tierOrder.indexOf(target.name) > tierOrder.indexOf(currentTier)
                const priceDiff = target.price_monthly - (sub.tier.price_monthly || 0)

                return (
                  <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={() => setConfirmTier(null)}>
                    <div className="bg-card border border-border rounded-2xl shadow-xl w-full max-w-sm mx-4 p-6" onClick={e => e.stopPropagation()}>
                      <div className="text-center mb-5">
                        <div className={cn('inline-flex p-3 rounded-xl mb-3', TIER_BG[target.name], TIER_COLORS[target.name])}>
                          {TIER_ICONS[target.name]}
                        </div>
                        <h3 className="text-base font-semibold">
                          {target.name === 'free' ? 'Downgrade to Free?' : isUp ? `Upgrade to ${target.display_name}?` : `Downgrade to ${target.display_name}?`}
                        </h3>
                      </div>

                      <div className="space-y-2.5 mb-5">
                        <div className="flex justify-between text-sm">
                          <span className="text-muted-foreground">Current plan</span>
                          <span className="font-medium">{sub.tier.display_name} — {sub.tier.price_monthly > 0 ? `$${(sub.tier.price_monthly / 100).toFixed(0)}/mo` : 'Free'}</span>
                        </div>
                        <div className="flex justify-between text-sm">
                          <span className="text-muted-foreground">New plan</span>
                          <span className="font-medium">{target.display_name} — {target.price_monthly > 0 ? `$${(target.price_monthly / 100).toFixed(0)}/mo` : 'Free'}</span>
                        </div>
                        <div className="border-t border-border pt-2.5 flex justify-between text-sm">
                          <span className="text-muted-foreground">{priceDiff > 0 ? 'Price increase' : priceDiff < 0 ? 'Savings' : 'Difference'}</span>
                          <span className={cn('font-semibold', priceDiff > 0 ? 'text-foreground' : priceDiff < 0 ? 'text-emerald-500' : '')}>
                            {priceDiff > 0 ? `+$${(priceDiff / 100).toFixed(0)}/mo` : priceDiff < 0 ? `-$${(Math.abs(priceDiff) / 100).toFixed(0)}/mo` : '$0'}
                          </span>
                        </div>
                        {target.name !== 'free' && (
                          <div className="flex justify-between text-sm">
                            <span className="text-muted-foreground">Pages</span>
                            <span className="font-medium">{target.pages_per_month.toLocaleString()}/mo</span>
                          </div>
                        )}
                      </div>

                      {isUp && (
                        <p className="text-xs text-muted-foreground text-center mb-4">
                          You'll be charged a prorated amount for the rest of this billing period.
                        </p>
                      )}
                      {target.name === 'free' && (
                        <p className="text-xs text-muted-foreground text-center mb-4">
                          Your current plan stays active until the end of the billing period.
                        </p>
                      )}

                      <div className="flex gap-2">
                        <Button variant="outline" className="flex-1" onClick={() => setConfirmTier(null)}>
                          Cancel
                        </Button>
                        <Button
                          className="flex-1"
                          variant={target.name === 'free' ? 'outline' : 'default'}
                          disabled={!!subscribing}
                          onClick={() => {
                            if (target.name === 'free') {
                              handleCancel()
                              setConfirmTier(null)
                            } else {
                              confirmAndSubscribe(target.name)
                            }
                          }}
                        >
                          {subscribing === target.name ? (
                            <div className="w-3.5 h-3.5 border-2 border-current/30 border-t-current rounded-full animate-spin" />
                          ) : target.name === 'free' ? (
                            'Confirm Downgrade'
                          ) : isUp ? (
                            'Confirm Upgrade'
                          ) : (
                            'Confirm Downgrade'
                          )}
                        </Button>
                      </div>
                    </div>
                  </div>
                )
              })()}

            </>
          ) : (
            <div className="rounded-xl border border-border bg-card p-6">
              <div className="flex items-center gap-2 mb-2">
                <AlertCircle size={16} className="text-amber-500" />
                <p className="text-sm font-medium">Couldn't load your subscription</p>
              </div>
              <p className="text-xs text-muted-foreground mb-4">
                You're on the <span className="font-medium capitalize">{currentTier}</span> plan. Refresh the page or try again.
              </p>
              <Button size="sm" variant="outline" onClick={() => fetchSubscription()}>
                Retry
              </Button>
            </div>
          )}
        </TabsContent>

        {/* ── Usage ──────────────────────────────────────────────────── */}
        <TabsContent value="usage" className="space-y-5 mt-0">
          {loadingHistory && !history ? (
            <div className="flex items-center justify-center py-12">
              <div className="w-5 h-5 border-2 border-border border-t-foreground rounded-full animate-spin" />
            </div>
          ) : history ? (
            <>
              {/* Usage summary */}
              <div className="rounded-xl border border-border bg-card p-5">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2">
                    <div className="p-1.5 rounded-lg bg-primary/10">
                      <BarChart3 size={16} className="text-primary" />
                    </div>
                    <div>
                      <p className="text-sm font-semibold">Pages Used</p>
                      <p className="text-xs text-muted-foreground">Current billing period</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="text-2xl font-bold tabular-nums">
                      {history.pages_used_this_period.toLocaleString()}
                      <span className="text-sm font-normal text-muted-foreground"> / {history.pages_limit.toLocaleString()}</span>
                    </p>
                  </div>
                </div>
                <Progress
                  value={history.usage_percent}
                  className={cn(
                    'h-2',
                    history.usage_percent >= 100 && '[&>div]:bg-red-500',
                    history.usage_percent >= 80 && history.usage_percent < 100 && '[&>div]:bg-amber-500',
                  )}
                />
                <div className="flex items-center justify-between mt-2">
                  <span className="text-[11px] text-muted-foreground">
                    {Math.round(history.usage_percent)}% of {history.tier} plan limit
                  </span>
                  <span className="text-[11px] text-muted-foreground">
                    {Math.max(0, history.pages_limit - history.pages_used_this_period).toLocaleString()} remaining
                  </span>
                </div>
              </div>

              {/* Stats row */}
              <div className="grid grid-cols-3 gap-3">
                <div className="rounded-xl border border-border bg-card p-4 text-center">
                  <p className="text-2xl font-bold tabular-nums">{history.total}</p>
                  <p className="text-[11px] text-muted-foreground mt-0.5">Total jobs</p>
                </div>
                <div className="rounded-xl border border-border bg-card p-4 text-center">
                  <p className="text-2xl font-bold tabular-nums">
                    {history.jobs.reduce((sum, j) => sum + j.file_count, 0)}
                  </p>
                  <p className="text-[11px] text-muted-foreground mt-0.5">Total files (all time)</p>
                </div>
                <div className="rounded-xl border border-border bg-card p-4 text-center">
                  <p className="text-2xl font-bold tabular-nums">
                    {history.jobs.filter(j => j.status === 'complete').length}
                  </p>
                  <p className="text-[11px] text-muted-foreground mt-0.5">Completed jobs</p>
                </div>
              </div>

              {/* Job history table */}
              <div>
                <p className="text-sm font-semibold mb-3">Processing History</p>
                {history.jobs.length === 0 ? (
                  <div className="rounded-xl border border-border bg-card p-8 text-center">
                    <FileText size={24} className="text-muted-foreground mx-auto mb-2" />
                    <p className="text-sm text-muted-foreground">No extractions yet</p>
                    <p className="text-xs text-muted-foreground mt-0.5">Upload your first PDF from the Dashboard to get started.</p>
                  </div>
                ) : (
                  <div className="rounded-xl border border-border overflow-hidden">
                    <div className="overflow-auto max-h-[420px] scrollbar-thin">
                      <table className="w-full text-xs">
                        <thead className="sticky top-0 z-10">
                          <tr className="bg-secondary">
                            <th className="px-4 py-2.5 text-left font-semibold text-muted-foreground">Status</th>
                            <th className="px-4 py-2.5 text-left font-semibold text-muted-foreground">Files</th>
                            <th className="px-4 py-2.5 text-left font-semibold text-muted-foreground hidden sm:table-cell">Fields</th>
                            <th className="px-4 py-2.5 text-left font-semibold text-muted-foreground hidden sm:table-cell">Format</th>
                            <th className="px-4 py-2.5 text-right font-semibold text-muted-foreground">Date</th>
                          </tr>
                        </thead>
                        <tbody>
                          {history.jobs.map((job, i) => {
                            const statusIcon = job.status === 'complete'
                              ? <CheckCircle2 size={13} className="text-emerald-500" />
                              : job.status === 'error'
                              ? <AlertCircle size={13} className="text-red-500" />
                              : ['queued', 'processing', 'extracting', 'generating'].includes(job.status)
                              ? <Loader2 size={13} className="text-blue-500 animate-spin" />
                              : <Clock size={13} className="text-muted-foreground" />

                            const fileNames = job.filenames.length > 0
                              ? job.filenames.length <= 2
                                ? job.filenames.join(', ')
                                : `${job.filenames[0]} +${job.filenames.length - 1} more`
                              : `${job.file_count} file${job.file_count !== 1 ? 's' : ''}`

                            return (
                              <tr
                                key={job.job_id}
                                className={cn(
                                  'border-t border-border transition-colors hover:bg-accent/50',
                                  i % 2 === 1 && 'bg-secondary/30',
                                )}
                              >
                                <td className="px-4 py-2.5">
                                  <div className="flex items-center gap-1.5">
                                    {statusIcon}
                                    <span className="capitalize">{job.status}</span>
                                  </div>
                                </td>
                                <td className="px-4 py-2.5">
                                  <div className="flex items-center gap-1.5 max-w-[200px]">
                                    <FileText size={12} className="text-muted-foreground flex-shrink-0" />
                                    <span className="truncate" title={job.filenames.join(', ')}>{fileNames}</span>
                                  </div>
                                </td>
                                <td className="px-4 py-2.5 hidden sm:table-cell">
                                  <span className="text-muted-foreground">
                                    {job.fields.length} field{job.fields.length !== 1 ? 's' : ''}
                                  </span>
                                </td>
                                <td className="px-4 py-2.5 hidden sm:table-cell">
                                  <Badge variant="outline" className="text-[10px] font-mono uppercase">{job.format}</Badge>
                                </td>
                                <td className="px-4 py-2.5 text-right text-muted-foreground whitespace-nowrap">
                                  {job.created_at
                                    ? new Date(job.created_at).toLocaleDateString(undefined, {
                                        month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
                                      })
                                    : '—'
                                  }
                                </td>
                              </tr>
                            )
                          })}
                        </tbody>
                      </table>
                    </div>
                    <div className="px-4 py-2.5 bg-secondary/50 border-t border-border flex items-center justify-between text-[11px] text-muted-foreground">
                      <span>Showing {history.jobs.length} of {history.total} jobs</span>
                      <button
                        onClick={fetchHistory}
                        disabled={loadingHistory}
                        className="text-primary hover:underline disabled:opacity-50"
                      >
                        {loadingHistory ? 'Refreshing...' : 'Refresh'}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="rounded-xl border border-border bg-card p-8 text-center">
              <p className="text-sm text-muted-foreground">Failed to load usage data.</p>
              <Button size="sm" variant="outline" className="mt-3" onClick={fetchHistory}>
                Retry
              </Button>
            </div>
          )}
        </TabsContent>

        {/* ── Payment ────────────────────────────────────────────────── */}
        <TabsContent value="payment" className="space-y-4 mt-0">
          {/* Payment Method */}
          <Card>
            <CardHeader className="pb-4">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-sm">Payment Method</CardTitle>
                  <CardDescription className="text-xs">Card used for your subscription and overages</CardDescription>
                </div>
                <CreditCard size={18} className="text-muted-foreground" />
              </div>
            </CardHeader>
            <CardContent>
              {savedCard === undefined ? (
                <div className="h-8 flex items-center">
                  <div className="w-3.5 h-3.5 border-2 border-border border-t-foreground rounded-full animate-spin" />
                </div>
              ) : savedCard ? (
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-6 bg-secondary border border-border rounded flex items-center justify-center">
                      <CreditCard size={13} className="text-muted-foreground" />
                    </div>
                    <span className="text-sm font-medium capitalize">{savedCard.brand} •••• {savedCard.last4}</span>
                  </div>
                  <button
                    onClick={handleRemoveCard}
                    disabled={loadingCard}
                    className="flex items-center gap-1 text-xs text-muted-foreground hover:text-red-500 transition-colors"
                  >
                    <X size={12} /> Remove
                  </button>
                </div>
              ) : (
                <div className="flex items-center justify-between">
                  <p className="text-xs text-muted-foreground">No card on file. Add one for subscriptions.</p>
                  <Button size="sm" variant="outline" onClick={handleSetupCard} disabled={loadingCard}>
                    {loadingCard ? (
                      <div className="w-3 h-3 border-2 border-current/30 border-t-current rounded-full animate-spin" />
                    ) : (
                      'Add Card'
                    )}
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Billing info */}
          <Card>
            <CardHeader className="pb-4">
              <CardTitle className="text-sm">Billing</CardTitle>
              <CardDescription className="text-xs">Your current billing summary</CardDescription>
            </CardHeader>
            <CardContent>
              {sub ? (
                <div className="space-y-3">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">Plan</span>
                    <span className="font-medium">{sub.tier.display_name}</span>
                  </div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">Monthly price</span>
                    <span className="font-medium">
                      {sub.tier.price_monthly > 0 ? `$${(sub.tier.price_monthly / 100).toFixed(0)}` : 'Free'}
                    </span>
                  </div>
                  {sub.overage_pages > 0 && sub.tier.overage_rate_cents_per_page && (
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">Overage charges (est.)</span>
                      <span className="font-medium text-amber-600">
                        +${((sub.overage_pages * sub.tier.overage_rate_cents_per_page) / 100).toFixed(2)}
                      </span>
                    </div>
                  )}
                  {sub.current_period_end && (
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">Next billing date</span>
                      <span className="font-medium">{new Date(sub.current_period_end).toLocaleDateString()}</span>
                    </div>
                  )}
                </div>
              ) : (
                <p className="text-xs text-muted-foreground">Loading...</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
