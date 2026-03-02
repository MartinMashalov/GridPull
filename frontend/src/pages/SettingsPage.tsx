import { useState } from 'react'
import { Wallet, Plus, Zap, User, Trash2, Check, ToggleLeft, ToggleRight } from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import { getInitials } from '@/lib/utils'
import api from '@/lib/api'
import toast from 'react-hot-toast'

const DEFAULT_FIELDS = [
  'Invoice Number', 'Date', 'Total Amount', 'Vendor Name',
  'Customer Name', 'Description', 'Tax Amount', 'Due Date',
]

export default function SettingsPage() {
  const { user } = useAuthStore()
  const [activeTab, setActiveTab] = useState<'balance' | 'defaults' | 'profile'>('balance')

  // Add funds
  const [addAmount, setAddAmount] = useState('')
  const [loadingAdd, setLoadingAdd] = useState(false)

  // Auto-renewal
  const [autoRenewEnabled, setAutoRenewEnabled] = useState(false)
  const [threshold, setThreshold] = useState('5')
  const [refillAmount, setRefillAmount] = useState('20')
  const [savingRenewal, setSavingRenewal] = useState(false)

  // Default fields
  const [defaultFields, setDefaultFields] = useState<string[]>(['Invoice Number', 'Date', 'Total Amount'])
  const [customField, setCustomField] = useState('')

  const handleAddFunds = async () => {
    const dollars = parseFloat(addAmount)
    if (!dollars || dollars < 1) {
      toast.error('Minimum top-up is $1.00')
      return
    }
    setLoadingAdd(true)
    try {
      const res = await api.post('/payments/create-checkout', {
        price_id: 'price_custom',
        credits: Math.round(dollars * 100),
        amount: Math.round(dollars * 100),
      })
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
      toast.success('Auto-renewal settings saved')
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to save')
    } finally {
      setSavingRenewal(false)
    }
  }

  const toggleDefault = (field: string) => {
    setDefaultFields(prev =>
      prev.includes(field) ? prev.filter(f => f !== field) : [...prev, field]
    )
  }

  const addCustomDefault = () => {
    if (customField.trim() && !defaultFields.includes(customField.trim())) {
      setDefaultFields(prev => [...prev, customField.trim()])
      setCustomField('')
    }
  }

  const tabs = [
    { key: 'balance', label: 'Balance', icon: Wallet },
    { key: 'defaults', label: 'Default Fields', icon: Zap },
    { key: 'profile', label: 'Profile', icon: User },
  ] as const

  return (
    <div className="p-8 max-w-3xl mx-auto">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-slate-900">Settings</h1>
        <p className="text-slate-500 mt-1">Manage your account, balance, and extraction defaults</p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-blue-50 border border-blue-100 p-1 rounded-xl mb-8 w-fit">
        {tabs.map(tab => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
              activeTab === tab.key
                ? 'bg-white text-slate-900 shadow-sm'
                : 'text-slate-500 hover:text-slate-700'
            }`}
          >
            <tab.icon size={15} />
            {tab.label}
          </button>
        ))}
      </div>

      {/* Balance Tab */}
      {activeTab === 'balance' && (
        <div className="space-y-6">
          {/* Current balance card */}
          <div className="bg-gradient-to-br from-blue-600 to-blue-700 rounded-2xl p-6 text-white">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-blue-200 text-sm mb-1">Account Balance</p>
                <p className="text-4xl font-bold">${(user?.credits ?? 0).toFixed(2)}</p>
                <p className="text-blue-200 text-sm mt-1">Depletes per extraction operation</p>
              </div>
              <div className="w-16 h-16 bg-white/20 rounded-2xl flex items-center justify-center">
                <Wallet size={28} className="text-white" />
              </div>
            </div>
          </div>

          {/* Add funds */}
          <div className="bg-white border border-blue-100 rounded-2xl p-6">
            <h3 className="text-base font-semibold text-slate-900 mb-4">Add Funds</h3>
            <div className="flex gap-3">
              <div className="relative flex-1">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 font-medium">$</span>
                <input
                  type="number"
                  min="1"
                  step="1"
                  placeholder="0.00"
                  value={addAmount}
                  onChange={e => setAddAmount(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleAddFunds()}
                  className="w-full pl-7 pr-4 py-2.5 border border-blue-200 rounded-xl text-sm focus:outline-none focus:border-blue-400"
                />
              </div>
              <button
                onClick={handleAddFunds}
                disabled={loadingAdd || !addAmount}
                className="flex items-center gap-2 px-5 py-2.5 bg-blue-600 text-white rounded-xl text-sm font-medium hover:bg-blue-700 disabled:opacity-60 transition-colors"
              >
                {loadingAdd ? (
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                ) : (
                  <Plus size={15} />
                )}
                Add Funds
              </button>
            </div>
            <p className="text-xs text-slate-400 mt-3">Secure payment via Stripe. Balance never expires.</p>
          </div>

          {/* Auto-renewal */}
          <div className="bg-white border border-blue-100 rounded-2xl p-6">
            <div className="flex items-center justify-between mb-5">
              <div>
                <h3 className="text-base font-semibold text-slate-900">Auto-Renewal</h3>
                <p className="text-sm text-slate-500 mt-0.5">Automatically top up when balance runs low</p>
              </div>
              <button
                onClick={() => setAutoRenewEnabled(!autoRenewEnabled)}
                className="flex-shrink-0"
              >
                {autoRenewEnabled ? (
                  <ToggleRight size={36} className="text-blue-600" />
                ) : (
                  <ToggleLeft size={36} className="text-slate-300" />
                )}
              </button>
            </div>

            {autoRenewEnabled && (
              <div className="space-y-4 pt-4 border-t border-blue-50">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-sm font-medium text-slate-700 mb-1.5 block">
                      When balance drops below
                    </label>
                    <div className="relative">
                      <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 font-medium">$</span>
                      <input
                        type="number"
                        min="1"
                        step="1"
                        value={threshold}
                        onChange={e => setThreshold(e.target.value)}
                        className="w-full pl-7 pr-4 py-2.5 border border-blue-200 rounded-xl text-sm focus:outline-none focus:border-blue-400"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="text-sm font-medium text-slate-700 mb-1.5 block">
                      Automatically add
                    </label>
                    <div className="relative">
                      <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 font-medium">$</span>
                      <input
                        type="number"
                        min="1"
                        step="1"
                        value={refillAmount}
                        onChange={e => setRefillAmount(e.target.value)}
                        className="w-full pl-7 pr-4 py-2.5 border border-blue-200 rounded-xl text-sm focus:outline-none focus:border-blue-400"
                      />
                    </div>
                  </div>
                </div>
                <p className="text-xs text-slate-400">
                  When your balance drops below ${threshold || '0'}, we'll automatically charge your saved card and add ${refillAmount || '0'} to your account.
                </p>
              </div>
            )}

            <button
              onClick={handleSaveAutoRenewal}
              disabled={savingRenewal}
              className="mt-5 flex items-center gap-2 px-5 py-2.5 bg-blue-600 text-white rounded-xl text-sm font-medium hover:bg-blue-700 disabled:opacity-60 transition-colors"
            >
              {savingRenewal ? (
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                <Check size={15} />
              )}
              Save Settings
            </button>
          </div>
        </div>
      )}

      {/* Default Fields Tab */}
      {activeTab === 'defaults' && (
        <div>
          <p className="text-sm text-slate-500 mb-6">
            These fields will be pre-selected when you open the extraction modal.
          </p>
          <div className="flex flex-wrap gap-2 mb-6">
            {DEFAULT_FIELDS.map(field => {
              const selected = defaultFields.includes(field)
              return (
                <button
                  key={field}
                  onClick={() => toggleDefault(field)}
                  className={`flex items-center gap-1.5 px-4 py-2 rounded-full text-sm font-medium border transition-colors ${
                    selected
                      ? 'bg-blue-600 text-white border-blue-600'
                      : 'bg-white text-slate-600 border-blue-200 hover:border-blue-400 hover:bg-blue-50'
                  }`}
                >
                  {selected && <Check size={13} />}
                  {field}
                </button>
              )
            })}
          </div>

          <div className="bg-blue-50 border border-blue-100 rounded-xl p-4 mb-4">
            <label className="text-sm font-medium text-slate-700 mb-2 block">Add Custom Default Field</label>
            <div className="flex gap-2">
              <input
                type="text"
                placeholder="e.g. Contract Number"
                value={customField}
                onChange={e => setCustomField(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && addCustomDefault()}
                className="flex-1 px-3 py-2 text-sm border border-blue-200 rounded-lg focus:outline-none focus:border-blue-400 bg-white"
              />
              <button
                onClick={addCustomDefault}
                disabled={!customField.trim()}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm font-medium transition-colors"
              >
                Add
              </button>
            </div>
          </div>

          <div className="mt-6">
            <p className="text-sm font-medium text-slate-700 mb-2">Selected defaults ({defaultFields.length})</p>
            <div className="space-y-1.5">
              {defaultFields.map(field => (
                <div key={field} className="flex items-center justify-between p-3 bg-white border border-blue-100 rounded-lg">
                  <span className="text-sm text-slate-700">{field}</span>
                  <button
                    onClick={() => setDefaultFields(prev => prev.filter(f => f !== field))}
                    className="text-slate-300 hover:text-red-500 transition-colors"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
            </div>
          </div>

          <button className="mt-6 px-6 py-2.5 bg-blue-600 text-white rounded-xl text-sm font-medium hover:bg-blue-700 transition-colors">
            Save Defaults
          </button>
        </div>
      )}

      {/* Profile Tab */}
      {activeTab === 'profile' && (
        <div className="space-y-6">
          <div className="flex items-center gap-4 p-6 bg-white border border-blue-100 rounded-2xl">
            <div className="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center flex-shrink-0">
              {user?.picture ? (
                <img src={user.picture} alt={user.name} className="w-16 h-16 rounded-full object-cover" />
              ) : (
                <span className="text-blue-700 text-xl font-semibold">
                  {user ? getInitials(user.name) : 'U'}
                </span>
              )}
            </div>
            <div>
              <h3 className="font-semibold text-slate-900">{user?.name}</h3>
              <p className="text-sm text-slate-500">{user?.email}</p>
              <p className="text-xs text-slate-400 mt-1">Signed in with Google</p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
