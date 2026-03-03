import { useState } from 'react'
import { Wallet, Plus, Zap, User, Trash2, Check } from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import { getInitials } from '@/lib/utils'
import api from '@/lib/api'
import toast from 'react-hot-toast'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { cn } from '@/lib/utils'

const DEFAULT_FIELDS = [
  'Invoice Number', 'Date', 'Total Amount', 'Vendor Name',
  'Customer Name', 'Description', 'Tax Amount', 'Due Date',
]

export default function SettingsPage() {
  const { user } = useAuthStore()
  const [addAmount, setAddAmount] = useState('')
  const [loadingAdd, setLoadingAdd] = useState(false)
  const [autoRenewEnabled, setAutoRenewEnabled] = useState(() => user?.auto_renewal_enabled ?? false)
  const [threshold, setThreshold] = useState(() => String(user?.auto_renewal_threshold ?? 5))
  const [refillAmount, setRefillAmount] = useState(() => String(user?.auto_renewal_refill ?? 20))
  const [savingRenewal, setSavingRenewal] = useState(false)
  const [defaultFields, setDefaultFields] = useState<string[]>(['Invoice Number', 'Date', 'Total Amount'])
  const [customField, setCustomField] = useState('')

  const handleAddFunds = async () => {
    const dollars = parseFloat(addAmount)
    if (!dollars || dollars < 1) { toast.error('Minimum top-up is $1.00'); return }
    setLoadingAdd(true)
    try {
      const res = await api.post('/payments/create-checkout', { amount: dollars })
      window.location.href = res.data.checkout_url
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Payment failed')
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

  const toggleDefault = (field: string) =>
    setDefaultFields(prev => prev.includes(field) ? prev.filter(f => f !== field) : [...prev, field])

  const addCustomDefault = () => {
    if (customField.trim() && !defaultFields.includes(customField.trim())) {
      setDefaultFields(prev => [...prev, customField.trim()])
      setCustomField('')
    }
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
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground text-sm font-medium">$</span>
                  <Input
                    type="number" min="1" step="1" placeholder="0.00"
                    value={addAmount}
                    onChange={e => setAddAmount(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && handleAddFunds()}
                    className="pl-7"
                  />
                </div>
                <Button onClick={handleAddFunds} disabled={loadingAdd || !addAmount} size="sm">
                  {loadingAdd
                    ? <div className="w-3.5 h-3.5 border-2 border-primary-foreground/30 border-t-white rounded-full animate-spin" />
                    : <><Plus size={14} />Add Funds</>}
                </Button>
              </div>
              <p className="text-[11px] text-muted-foreground mt-2.5">Secure payment via Stripe. Balance never expires.</p>
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
              const selected = defaultFields.includes(field)
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
              {defaultFields.map(field => (
                <div key={field} className="flex items-center justify-between px-3 py-2.5 bg-card border border-border rounded-lg">
                  <span className="text-sm">{field}</span>
                  <button onClick={() => setDefaultFields(prev => prev.filter(f => f !== field))} className="text-muted-foreground hover:text-red-400 transition-colors">
                    <Trash2 size={13} />
                  </button>
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
