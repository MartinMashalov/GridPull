import { useState, useEffect } from 'react'
import { trackEvent } from '@/lib/analytics'
import {
  CreditCard, User, Zap, Check, StickyNote, Trash2, X,
  Crown, Rocket, Building2, FileText, AlertTriangle,
  Sparkles, ChevronRight, BarChart3, Clock,
  CheckCircle2, AlertCircle, Loader2,
} from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import { getInitials } from '@/lib/utils'
import api from '@/lib/api'
import toast from 'react-hot-toast'
import { useSearchParams } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Label } from '@/components/ui/label'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Progress } from '@/components/ui/progress'
import { cn } from '@/lib/utils'

interface DefaultField {
  name: string
  description: string
}

interface TierInfo {
  name: string
  display_name: string
  price_monthly: number
  files_per_month: number
  max_pages_per_file: number
  overage_rate: number | null
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
  files_used_this_period: number
  files_limit: number
  usage_percent: number
  tier: string
}

interface SubscriptionData {
  tier: TierInfo
  status: string
  files_used: number
  overage_files: number
  files_limit: number
  usage_percent: number
  current_period_end: string | null
  all_tiers: TierInfo[]
  first_month_discount_available: boolean
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

const DEFAULT_FIELDS = [
  'Date', 'Total Amount', 'Company Name', 'Invoice Number',
  'Revenue', 'Net Income', 'Contract Value', 'Effective Date',
  'Address', 'Signatory', 'Description', 'Tax Amount',
]

export default function SettingsPage() {
  const { user, updateSubscription } = useAuthStore()
  const [searchParams, setSearchParams] = useSearchParams()
  const [sub, setSub] = useState<SubscriptionData | null>(null)
  const [loadingSub, setLoadingSub] = useState(true)
  const [subscribing, setSubscribing] = useState<string | null>(null)
  const [, setCanceling] = useState(false)
  const [savedCard, setSavedCard] = useState<{ brand: string; last4: string } | null | undefined>(undefined)
  const [loadingCard, setLoadingCard] = useState(false)
  const [defaultFields, setDefaultFields] = useState<DefaultField[]>([
    { name: 'Invoice Number', description: '' },
    { name: 'Date', description: '' },
    { name: 'Total Amount', description: '' },
  ])
  const [customField, setCustomField] = useState('')
  const [expandedDesc, setExpandedDesc] = useState<number | null>(null)
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
          files_used_this_period: r.data.files_used,
          current_period_end: r.data.current_period_end,
        })
      })
      .catch(() => {})
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
      api.get('/payments/saved-card').then(r => setSavedCard(r.data.card)).catch(() => {})
      setSearchParams({})
    }
  }, [])

  const handleSubscribe = async (tierName: string) => {
    setSubscribing(tierName)
    try {
      if (sub?.tier.name && sub.tier.name !== 'free' && tierName !== 'free') {
        const r = await api.post('/payments/change-subscription', { tier: tierName })
        if (r.data.checkout_url) {
          window.location.href = r.data.checkout_url
          return
        }
        toast.success(`Switched to ${tierName}!`)
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

  const toggleDefault = (name: string) => {
    const exists = defaultFields.find(f => f.name === name)
    if (exists) {
      setDefaultFields(prev => prev.filter(f => f.name !== name))
    } else {
      setDefaultFields(prev => [...prev, { name, description: '' }])
    }
  }

  const addCustomDefault = () => {
    const trimmed = customField.trim()
    if (trimmed && !defaultFields.find(f => f.name === trimmed)) {
      setDefaultFields(prev => [...prev, { name: trimmed, description: '' }])
      setCustomField('')
    }
  }

  const updateDescription = (index: number, desc: string) => {
    setDefaultFields(prev => prev.map((f, i) => i === index ? { ...f, description: desc } : f))
  }

  const removeDefaultField = (index: number) => {
    setDefaultFields(prev => prev.filter((_, i) => i !== index))
    if (expandedDesc === index) setExpandedDesc(null)
  }

  const currentTier = sub?.tier.name || user?.subscription_tier || 'free'
  const tierOrder = ['free', 'starter', 'pro', 'business']

  return (
    <div className="p-4 sm:p-8 max-w-3xl mx-auto">
      <div className="mb-7">
        <h1 className="text-xl font-semibold">Settings</h1>
        <p className="text-muted-foreground text-sm mt-0.5">Manage your subscription, payment method, and extraction defaults</p>
      </div>

      <Tabs defaultValue="subscription">
        <TabsList className="mb-6 w-full sm:w-auto">
          <TabsTrigger value="subscription"><Crown size={13} />Subscription</TabsTrigger>
          <TabsTrigger value="usage" onClick={() => { if (!historyLoaded) fetchHistory() }}><BarChart3 size={13} />Usage</TabsTrigger>
          <TabsTrigger value="payment"><CreditCard size={13} />Payment</TabsTrigger>
          <TabsTrigger value="defaults"><Zap size={13} />Default Fields</TabsTrigger>
          <TabsTrigger value="profile"><User size={13} />Profile</TabsTrigger>
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
                    <span className="text-xs font-medium">Files used this period</span>
                    <span className="text-xs text-muted-foreground tabular-nums">
                      {sub.files_used} / {sub.files_limit}
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
                        You've used {sub.files_used} of {sub.files_limit} files.
                        {currentTier !== 'business' && ' Upgrade to avoid overage charges.'}
                      </p>
                    </div>
                  )}
                  {sub.usage_percent >= 100 && currentTier === 'free' && (
                    <div className="mt-2.5 flex items-center gap-1.5 text-red-500">
                      <AlertTriangle size={12} />
                      <p className="text-xs font-medium">
                        You've hit your free limit. Upgrade to continue processing files.
                      </p>
                    </div>
                  )}
                  {sub.overage_files > 0 && sub.tier.overage_rate && (
                    <p className="mt-2 text-xs text-muted-foreground">
                      {sub.overage_files} overage file{sub.overage_files !== 1 ? 's' : ''} this period
                      (${(sub.tier.overage_rate / 100).toFixed(2)}/file)
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
                  {sub.all_tiers.filter(t => t.name !== currentTier).map(tier => {
                    const isUpgrade = tierOrder.indexOf(tier.name) > tierOrder.indexOf(currentTier)
                    const isStarter = tier.name === 'starter'
                    const showDiscount = isStarter && sub.first_month_discount_available && currentTier === 'free'

                    return (
                      <div
                        key={tier.name}
                        className={cn(
                          'rounded-xl border p-4 flex items-center justify-between transition-all hover:shadow-sm',
                          tier.name === 'pro' ? 'border-amber-500/30 bg-amber-500/[0.03]' : 'border-border',
                        )}
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          <div className={cn('p-2 rounded-lg', TIER_BG[tier.name], TIER_COLORS[tier.name])}>
                            {TIER_ICONS[tier.name]}
                          </div>
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              <p className="text-sm font-semibold">{tier.display_name}</p>
                              {tier.name === 'pro' && (
                                <Badge className="text-[10px] bg-amber-500/20 text-amber-600 border-amber-500/30">Popular</Badge>
                              )}
                              {showDiscount && (
                                <Badge className="text-[10px] bg-emerald-500/20 text-emerald-600 border-emerald-500/30">
                                  <Sparkles size={9} className="mr-0.5" /> 50% off first month
                                </Badge>
                              )}
                            </div>
                            <p className="text-xs text-muted-foreground mt-0.5">
                              {tier.files_per_month.toLocaleString()} files/mo
                              {tier.max_pages_per_file && ` · ${tier.max_pages_per_file} pages/file`}
                              {tier.has_pipeline && ' · Pipeline access'}
                              {tier.overage_rate && ` · $${(tier.overage_rate / 100).toFixed(2)} overage`}
                            </p>
                          </div>
                        </div>
                        <div className="flex items-center gap-3 flex-shrink-0 ml-3">
                          <div className="text-right">
                            {showDiscount ? (
                              <>
                                <p className="text-sm font-bold">
                                  <span className="line-through text-muted-foreground font-normal">${(tier.price_monthly / 100).toFixed(0)}</span>
                                  {' '}${(tier.price_monthly / 200).toFixed(2)}
                                </p>
                                <p className="text-[10px] text-muted-foreground">first month</p>
                              </>
                            ) : tier.price_monthly > 0 ? (
                              <>
                                <p className="text-sm font-bold">${(tier.price_monthly / 100).toFixed(0)}</p>
                                <p className="text-[10px] text-muted-foreground">/month</p>
                              </>
                            ) : (
                              <p className="text-sm font-bold">Free</p>
                            )}
                          </div>
                          <Button
                            size="sm"
                            variant={isUpgrade ? 'default' : 'outline'}
                            disabled={subscribing === tier.name}
                            onClick={() => tier.name === 'free'
                              ? handleCancel()
                              : handleSubscribe(tier.name)
                            }
                            className="min-w-[90px]"
                          >
                            {subscribing === tier.name ? (
                              <div className="w-3.5 h-3.5 border-2 border-current/30 border-t-current rounded-full animate-spin" />
                            ) : tier.name === 'free' ? (
                              'Downgrade'
                            ) : isUpgrade ? (
                              <>Upgrade <ChevronRight size={12} /></>
                            ) : (
                              'Switch'
                            )}
                          </Button>
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>

            </>
          ) : null}
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
                      <p className="text-sm font-semibold">Files Processed</p>
                      <p className="text-xs text-muted-foreground">Current billing period</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="text-2xl font-bold tabular-nums">
                      {history.files_used_this_period}
                      <span className="text-sm font-normal text-muted-foreground"> / {history.files_limit}</span>
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
                    {Math.max(0, history.files_limit - history.files_used_this_period)} remaining
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
                  {sub.overage_files > 0 && sub.tier.overage_rate && (
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">Overage charges (est.)</span>
                      <span className="font-medium text-amber-600">
                        +${((sub.overage_files * sub.tier.overage_rate) / 100).toFixed(2)}
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

        {/* ── Default Fields ───────────────────────────────────────── */}
        <TabsContent value="defaults" className="space-y-4 mt-0">
          <p className="text-sm text-muted-foreground">Pre-selected fields when you open the extraction modal.</p>

          <div className="flex flex-wrap gap-2">
            {DEFAULT_FIELDS.map(field => {
              const selected = !!defaultFields.find(f => f.name === field)
              return (
                <button
                  key={field}
                  onClick={() => toggleDefault(field)}
                  className={cn(
                    'flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border transition-colors',
                    selected
                      ? 'bg-primary/15 text-primary border-primary/30'
                      : 'bg-secondary text-muted-foreground border-border hover:border-primary/30 hover:text-foreground'
                  )}
                >
                  {selected && <Check size={11} />}
                  {field}
                </button>
              )
            })}
          </div>

          <Card>
            <CardContent className="pt-4">
              <Label className="text-xs mb-2 block">Add Custom Field</Label>
              <div className="flex gap-2">
                <Input
                  placeholder="e.g. Contract Number"
                  value={customField}
                  onChange={e => setCustomField(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && addCustomDefault()}
                />
                <Button onClick={addCustomDefault} disabled={!customField.trim()} size="sm">Add</Button>
              </div>
            </CardContent>
          </Card>

          {defaultFields.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-xs font-medium text-muted-foreground">Selected ({defaultFields.length})</p>
              {defaultFields.map((field, i) => (
                <div key={i} className="rounded-lg border border-border overflow-hidden">
                  <div className="flex items-center justify-between px-3 py-2.5 bg-card">
                    <span className="text-sm flex-1 min-w-0 truncate">{field.name}</span>
                    <div className="flex items-center gap-1 ml-2 flex-shrink-0">
                      <button
                        onClick={() => setExpandedDesc(prev => prev === i ? null : i)}
                        title="Add description to improve accuracy"
                        className={cn(
                          'p-1 rounded transition-colors',
                          expandedDesc === i
                            ? 'text-primary bg-primary/10'
                            : field.description
                              ? 'text-primary/60 hover:text-primary'
                              : 'text-muted-foreground hover:text-primary'
                        )}
                      >
                        <StickyNote size={13} />
                      </button>
                      <button onClick={() => removeDefaultField(i)} className="p-1 rounded text-muted-foreground hover:text-red-400 transition-colors">
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </div>
                  {expandedDesc === i && (
                    <div className="px-3 py-2 bg-primary/5 border-t border-border">
                      <textarea
                        autoFocus
                        rows={2}
                        value={field.description}
                        onChange={e => updateDescription(i, e.target.value)}
                        placeholder="Describe what to look for, or how to calculate (e.g. 'Net Income ÷ Revenue × 100')…"
                        className="w-full text-xs bg-transparent resize-none outline-none text-foreground placeholder:text-muted-foreground/60 leading-relaxed"
                      />
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          <Button size="sm">Save Defaults</Button>
        </TabsContent>

        {/* ── Profile ──────────────────────────────────────────────── */}
        <TabsContent value="profile" className="mt-0">
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center gap-4">
                <div className="w-14 h-14 rounded-full overflow-hidden ring-1 ring-border flex-shrink-0">
                  {user?.picture ? (
                    <img src={user.picture} alt={user.name} className="w-14 h-14 rounded-full object-cover" />
                  ) : (
                    <div className="w-14 h-14 bg-primary/20 flex items-center justify-center">
                      <span className="text-primary text-lg font-semibold">{user ? getInitials(user.name) : 'U'}</span>
                    </div>
                  )}
                </div>
                <div>
                  <p className="font-semibold">{user?.name}</p>
                  <p className="text-sm text-muted-foreground">{user?.email}</p>
                  <div className="flex items-center gap-2 mt-1.5">
                    <Badge variant="outline" className="text-[10px]">
                      {user?.subscription_tier === 'free' ? 'Free Plan' : `${(sub?.tier.display_name || user?.subscription_tier || 'Free')} Plan`}
                    </Badge>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
