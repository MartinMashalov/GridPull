import { useState } from 'react'
import { CreditCard, Plus, Check, Zap, User, Trash2 } from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import { getInitials } from '@/lib/utils'
import api from '@/lib/api'
import toast from 'react-hot-toast'

const CREDIT_PACKAGES = [
  { credits: 10, price: 500, label: '$5', priceId: 'price_10credits' },
  { credits: 50, price: 2000, label: '$20', priceId: 'price_50credits', popular: true },
  { credits: 200, price: 6000, label: '$60', priceId: 'price_200credits' },
]

const DEFAULT_FIELDS = [
  'Invoice Number', 'Date', 'Total Amount', 'Vendor Name',
  'Customer Name', 'Description', 'Tax Amount', 'Due Date',
]

export default function SettingsPage() {
  const { user } = useAuthStore()
  const [activeTab, setActiveTab] = useState<'profile' | 'credits' | 'defaults'>('credits')
  const [loadingPriceId, setLoadingPriceId] = useState<string | null>(null)
  const [defaultFields, setDefaultFields] = useState<string[]>(['Invoice Number', 'Date', 'Total Amount'])
  const [customField, setCustomField] = useState('')

  const handlePurchase = async (pkg: typeof CREDIT_PACKAGES[0]) => {
    setLoadingPriceId(pkg.priceId)
    try {
      const res = await api.post('/payments/create-checkout', {
        price_id: pkg.priceId,
        credits: pkg.credits,
      })
      window.location.href = res.data.checkout_url
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Payment failed')
    } finally {
      setLoadingPriceId(null)
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
    { key: 'credits', label: 'Credits', icon: CreditCard },
    { key: 'defaults', label: 'Default Fields', icon: Zap },
    { key: 'profile', label: 'Profile', icon: User },
  ] as const

  return (
    <div className="p-8 max-w-3xl mx-auto">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-slate-900">Settings</h1>
        <p className="text-slate-500 mt-1">Manage your account, credits, and extraction defaults</p>
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

      {/* Credits Tab */}
      {activeTab === 'credits' && (
        <div>
          {/* Current balance */}
          <div className="bg-gradient-to-br from-blue-600 to-blue-700 rounded-2xl p-6 text-white mb-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-blue-200 text-sm mb-1">Available Credits</p>
                <p className="text-4xl font-bold">{user?.credits ?? 0}</p>
                <p className="text-blue-200 text-sm mt-1">1 credit = 1 PDF page extracted</p>
              </div>
              <div className="w-16 h-16 bg-white/20 rounded-2xl flex items-center justify-center">
                <CreditCard size={28} className="text-white" />
              </div>
            </div>
          </div>

          {/* Packages */}
          <h3 className="text-base font-semibold text-slate-900 mb-4">Add Credits</h3>
          <div className="grid grid-cols-3 gap-4">
            {CREDIT_PACKAGES.map(pkg => (
              <div
                key={pkg.priceId}
                className={`relative rounded-2xl border p-5 ${pkg.popular ? 'border-blue-300 ring-2 ring-blue-200 bg-blue-50' : 'border-blue-100 bg-white'}`}
              >
                {pkg.popular && (
                  <div className="absolute -top-2.5 left-1/2 -translate-x-1/2">
                    <span className="bg-blue-600 text-white text-[10px] font-semibold px-2.5 py-1 rounded-full">
                      BEST VALUE
                    </span>
                  </div>
                )}
                <div className="text-2xl font-bold text-slate-900">{pkg.label}</div>
                <div className="text-sm text-slate-500 mb-4">{pkg.credits} credits</div>
                <button
                  onClick={() => handlePurchase(pkg)}
                  disabled={loadingPriceId === pkg.priceId}
                  className={`w-full py-2 rounded-lg text-sm font-medium transition-colors ${
                    pkg.popular
                      ? 'bg-blue-600 text-white hover:bg-blue-700'
                      : 'bg-slate-900 text-white hover:bg-slate-800'
                  } disabled:opacity-60`}
                >
                  {loadingPriceId === pkg.priceId ? (
                    <span className="flex items-center justify-center gap-2">
                      <div className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                      Loading...
                    </span>
                  ) : (
                    <span className="flex items-center justify-center gap-1.5">
                      <Plus size={14} />
                      Purchase
                    </span>
                  )}
                </button>
              </div>
            ))}
          </div>

          <p className="text-xs text-slate-400 mt-4 text-center">
            Secure payment via Stripe. Credits never expire.
          </p>
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
