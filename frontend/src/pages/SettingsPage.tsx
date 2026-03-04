import { useState, useEffect } from 'react'
import { Wallet, Plus, Zap, User, Trash2, Check, StickyNote, CreditCard, X } from 'lucide-react'
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
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { cn } from '@/lib/utils'

interface DefaultField {
  name: string
  description: string
}

const DEFAULT_FIELDS = [
  'Date', 'Total Amount', 'Company Name', 'Invoice Number',
  'Revenue', 'Net Income', 'Contract Value', 'Effective Date',
  'Address', 'Signatory', 'Description', 'Tax Amount',
]

export default function SettingsPage() {
  const { user, updateBalance } = useAuthStore()
  const [searchParams, setSearchParams] = useSearchParams()
  const [addAmount, setAddAmount] = useState('')
  const [loadingAdd, setLoadingAdd] = useState(false)
  const [autoRenewEnabled, setAutoRenewEnabled] = useState(() => user?.auto_renewal_enabled ?? false)
  const [threshold, setThreshold] = useState(() => String(user?.auto_renewal_threshold ?? 5))
  const [refillAmount, setRefillAmount] = useState(() => String(user?.auto_renewal_refill ?? 20))
  const [savingRenewal, setSavingRenewal] = useState(false)
  const [savedCard, setSavedCard] = useState<{ brand: string; last4: string } | null | undefined>(undefined)
  const [loadingCard, setLoadingCard] = useState(false)
  const [addingCard, setAddingCard] = useState(false)
  const [checkoutUrl, setCheckoutUrl] = useState<string | null>(null)
  const [defaultFields, setDefaultFields] = useState<DefaultField[]>([
    { name: 'Invoice Number', description: '' },
    { name: 'Date', description: '' },
    { name: 'Total Amount', description: '' },
  ])
  const [customField, setCustomField] = useState('')
  const [expandedDesc, setExpandedDesc] = useState<number | null>(null)

  // Fetch fresh balance + saved card on mount
  useEffect(() => {
    api.get('/payments/me').then(r => updateBalance(r.data.balance)).catch(() => {})
    api.get('/payments/saved-card').then(r => setSavedCard(r.data.card)).catch(() => setSavedCard(null))
  }, [])

  // Reset loading state if browser restores page from bfcache (user pressed Back from Stripe)
  useEffect(() => {
    const handlePageShow = (e: PageTransitionEvent) => {
      if (e.persisted) {
        setLoadingAdd(false)
        setAddingCard(false)
        setCheckoutUrl(null)
      }
    }
    window.addEventListener('pageshow', handlePageShow)
    return () => window.removeEventListener('pageshow', handlePageShow)
  }, [])

  // Handle return from Stripe (payment success or card saved)
  useEffect(() => {
    const payment = searchParams.get('payment')
    const sessionId = searchParams.get('session_id')
    const card = searchParams.get('card')

    if (payment === 'success' && sessionId) {
      setSearchParams({})
      // Verify directly with Stripe and credit balance immediately
      api.post(`/payments/verify-session/${sessionId}`)
        .then(r => {
          const { balance, credited, amount } = r.data
          if (credited) {
            updateBalance(balance)
            toast.success(`$${amount.toFixed(2)} added to your balance!`)
          }
          api.get('/payments/saved-card').then(r2 => setSavedCard(r2.data.card)).catch(() => {})
        })
        .catch(() => toast.error('Payment verified by Stripe but balance update failed — refresh the page'))
    }

    if (card === 'saved') {
      toast.success('Card saved successfully!')
      api.get('/payments/saved-card').then(r => setSavedCard(r.data.card)).catch(() => {})
      setSearchParams({})
    }
  }, [])

  const handleAddFunds = async () => {
    const dollars = parseFloat(addAmount)
    if (!addAmount) { toast.error('Enter an amount to add'); return }
    if (!dollars || dollars < 1) { toast.error('Minimum top-up is $1.00'); return }
    setLoadingAdd(true)
    setCheckoutUrl(null)
    try {
      const res = await api.post('/payments/create-checkout', { amount: dollars })
      const url = res.data?.checkout_url
      if (!url) { toast.error('No checkout URL returned — contact support'); return }
      // Store URL so user can click it manually if auto-redirect fails
      setCheckoutUrl(url)
      // Try redirect
      window.location.href = url
    } catch (err: any) {
      console.error('create-checkout error:', err)
      const msg = err.response?.data?.detail || err.message || 'Payment service error — please try again'
      toast.error(msg, { duration: 8000 })
    } finally {
      setLoadingAdd(false)
    }
  }

  const handleSaveAutoRenewal = async () => {
    setSavingRenewal(true)
    try {
      await api.post('/users/auto-renewal', {
        enabled: autoRenewEnabled,
        threshold: parseFloat(threshold),
        refill_amount: parseFloat(refillAmount),
      })
      toast.success('Saved')
    } catch {
      toast.error('Failed to save')
    } finally {
      setSavingRenewal(false)
    }
  }

  const handleAddCard = async () => {
    setAddingCard(true)
    try {
      const res = await api.post('/payments/setup-card')
      window.location.href = res.data.setup_url
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to open card setup')
      setAddingCard(false)
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

  return (
    <div className="p-8 max-w-2xl mx-auto">
      <div className="mb-7">
        <h1 className="text-xl font-semibold">Settings</h1>
        <p className="text-muted-foreground text-sm mt-0.5">Manage your account, balance, and extraction defaults</p>
      </div>

      <Tabs defaultValue="balance">
        <TabsList className="mb-6">
          <TabsTrigger value="balance"><Wallet size={13} />Balance</TabsTrigger>
          <TabsTrigger value="defaults"><Zap size={13} />Default Fields</TabsTrigger>
          <TabsTrigger value="profile"><User size={13} />Profile</TabsTrigger>
        </TabsList>

        {/* ── Balance ─────────────────────────────────────────────── */}
        <TabsContent value="balance" className="space-y-4 mt-0">
          {/* Balance card */}
          <div className="relative overflow-hidden rounded-xl border border-primary/20 bg-gradient-to-br from-primary/10 to-primary/5 p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-muted-foreground mb-1 uppercase tracking-widest font-medium">Account Balance</p>
                <p className="text-4xl font-bold font-mono">${(user?.balance ?? 0).toFixed(2)}</p>
                <p className="text-xs text-muted-foreground mt-2">Depletes per extraction operation</p>
              </div>
              <div className="w-14 h-14 bg-primary/20 rounded-xl flex items-center justify-center">
                <Wallet size={24} className="text-primary" />
              </div>
            </div>
            <div className="absolute -bottom-6 -right-6 w-24 h-24 bg-primary/10 rounded-full blur-2xl pointer-events-none" />
          </div>

          {/* Add funds */}
          <Card>
            <CardHeader className="pb-4">
              <CardTitle className="text-sm">Add Funds</CardTitle>
              <CardDescription className="text-xs">Funds are added instantly via Stripe</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex gap-1.5 mb-3">
                {[5, 10, 20, 50].map(amt => (
                  <button
                    key={amt}
                    onClick={() => setAddAmount(String(amt))}
                    className={cn(
                      'flex-1 py-1.5 rounded-lg text-xs font-medium border transition-colors',
                      addAmount === String(amt)
                        ? 'bg-primary text-primary-foreground border-primary'
                        : 'bg-secondary text-muted-foreground border-border hover:border-primary/40 hover:text-foreground'
                    )}
                  >
                    ${amt}
                  </button>
                ))}
              </div>
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground text-sm font-medium">$</span>
                  <Input
                    type="number" min="1" step="1" placeholder="Custom amount"
                    value={addAmount}
                    onChange={e => setAddAmount(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && handleAddFunds()}
                    className="pl-7"
                  />
                </div>
                <Button onClick={handleAddFunds} disabled={loadingAdd} size="sm">
                  {loadingAdd
                    ? <div className="w-3.5 h-3.5 border-2 border-primary-foreground/30 border-t-white rounded-full animate-spin" />
                    : <><Plus size={14} />Add Funds</>}
                </Button>
              </div>
              {checkoutUrl && (
                <div className="mt-3 p-3 rounded-lg bg-primary/5 border border-primary/20">
                  <p className="text-xs text-muted-foreground mb-1.5">Redirect didn't open automatically?</p>
                  <a href={checkoutUrl} className="text-sm font-semibold text-primary underline">
                    → Click here to open Stripe Checkout
                  </a>
                </div>
              )}
              <p className="text-[11px] text-muted-foreground mt-2.5">Secure payment via Stripe. Balance never expires.</p>
            </CardContent>
          </Card>

          {/* Payment Method */}
          <Card>
            <CardHeader className="pb-4">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-sm">Payment Method</CardTitle>
                  <CardDescription className="text-xs">Saved card used for top-ups and auto-renewal</CardDescription>
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
                  <p className="text-xs text-muted-foreground">No card saved yet</p>
                  <Button onClick={handleAddCard} disabled={addingCard} size="sm" variant="outline">
                    {addingCard
                      ? <div className="w-3.5 h-3.5 border-2 border-border border-t-foreground rounded-full animate-spin" />
                      : <><Plus size={13} />Add Card</>}
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Auto-renewal */}
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-sm">Auto-Renewal</CardTitle>
                  <CardDescription className="text-xs mt-0.5">Top up automatically when balance is low</CardDescription>
                </div>
                <Switch checked={autoRenewEnabled} onCheckedChange={setAutoRenewEnabled} />
              </div>
            </CardHeader>

            {autoRenewEnabled && (
              <CardContent className="border-t border-border pt-4">
                <div className="grid grid-cols-2 gap-3 mb-4">
                  <div className="space-y-1.5">
                    <Label className="text-xs">When balance drops below</Label>
                    <div className="relative">
                      <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground text-sm">$</span>
                      <Input type="number" min="1" value={threshold} onChange={e => setThreshold(e.target.value)} className="pl-7" />
                    </div>
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">Automatically add</Label>
                    <div className="relative">
                      <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground text-sm">$</span>
                      <Input type="number" min="1" value={refillAmount} onChange={e => setRefillAmount(e.target.value)} className="pl-7" />
                    </div>
                  </div>
                </div>
                <p className="text-[11px] text-muted-foreground">
                  When balance drops below ${threshold || '0'}, we'll charge your saved card and add ${refillAmount || '0'}.
                </p>
              </CardContent>
            )}

            <div className="px-6 pb-4 pt-3 border-t border-border">
              <Button onClick={handleSaveAutoRenewal} disabled={savingRenewal} size="sm" variant="outline">
                {savingRenewal
                  ? <div className="w-3.5 h-3.5 border-2 border-border border-t-foreground rounded-full animate-spin" />
                  : <><Check size={13} />Save</>}
              </Button>
            </div>
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
                  <Badge variant="outline" className="mt-1.5 text-[10px]">Google Account</Badge>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
