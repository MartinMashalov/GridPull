import { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { Home, Settings, LogOut, FileSpreadsheet, ChevronUp, ChevronDown, PanelLeftClose, PanelLeftOpen } from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import { getInitials } from '@/lib/utils'
import * as Accordion from '@radix-ui/react-accordion'
import toast from 'react-hot-toast'

export default function Sidebar() {
  const navigate = useNavigate()
  const location = useLocation()
  const { user, logout } = useAuthStore()
  const [collapsed, setCollapsed] = useState(false)
  const [userPanelOpen, setUserPanelOpen] = useState(false)

  const handleLogout = () => {
    logout()
    toast.success('Logged out successfully')
    navigate('/')
  }

  const navItems = [
    { icon: Home, label: 'Home', path: '/dashboard' },
    { icon: Settings, label: 'Settings', path: '/settings' },
  ]

  return (
    <aside
      className={`relative flex flex-col bg-white border-r border-blue-100 transition-all duration-300 ${collapsed ? 'w-16' : 'w-64'}`}
      style={{ minHeight: '100vh' }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 h-16 border-b border-blue-100">
        {!collapsed && (
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 bg-blue-600 rounded-md flex items-center justify-center flex-shrink-0">
              <FileSpreadsheet size={15} className="text-white" />
            </div>
            <span className="font-semibold text-slate-800 text-sm tracking-tight">GridPull</span>
          </div>
        )}
        {collapsed && (
          <div className="w-7 h-7 bg-blue-600 rounded-md flex items-center justify-center mx-auto">
            <FileSpreadsheet size={15} className="text-white" />
          </div>
        )}
        {!collapsed && (
          <button
            onClick={() => setCollapsed(true)}
            className="text-slate-400 hover:text-slate-600 transition-colors p-1 rounded"
          >
            <PanelLeftClose size={16} />
          </button>
        )}
      </div>

      {collapsed && (
        <button
          onClick={() => setCollapsed(false)}
          className="absolute -right-3 top-16 w-6 h-6 bg-white border border-blue-100 rounded-full flex items-center justify-center text-slate-400 hover:text-blue-600 transition-colors z-10"
        >
          <PanelLeftOpen size={12} />
        </button>
      )}

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-1">
        {navItems.map((item) => {
          const isActive = location.pathname === item.path
          return (
            <button
              key={item.path}
              onClick={() => navigate(item.path)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150 ${
                isActive
                  ? 'bg-blue-600 text-white shadow-sm shadow-blue-200'
                  : 'text-slate-500 hover:bg-blue-50 hover:text-blue-700'
              } ${collapsed ? 'justify-center' : ''}`}
              title={collapsed ? item.label : undefined}
            >
              <item.icon size={18} className="flex-shrink-0" />
              {!collapsed && <span>{item.label}</span>}
            </button>
          )
        })}
      </nav>

      {/* User Panel - Bottom */}
      <div className="border-t border-blue-100 px-3 py-3">
        {!collapsed ? (
          <Accordion.Root
            type="single"
            collapsible
            value={userPanelOpen ? 'user' : ''}
            onValueChange={(v) => setUserPanelOpen(v === 'user')}
          >
            <Accordion.Item value="user" className="rounded-lg overflow-hidden">
              <Accordion.Trigger className="w-full flex items-center gap-3 px-3 py-2.5 hover:bg-blue-50 rounded-lg transition-colors group">
                {/* Avatar */}
                <div className="w-8 h-8 bg-blue-100 rounded-full flex items-center justify-center flex-shrink-0">
                  {user?.picture ? (
                    <img src={user.picture} alt={user.name} className="w-8 h-8 rounded-full object-cover" />
                  ) : (
                    <span className="text-blue-700 text-xs font-semibold">
                      {user ? getInitials(user.name) : 'U'}
                    </span>
                  )}
                </div>
                <div className="flex-1 text-left min-w-0">
                  <div className="text-sm text-slate-700 font-medium truncate">{user?.name}</div>
                </div>
                {userPanelOpen ? (
                  <ChevronDown size={14} className="text-slate-400 flex-shrink-0" />
                ) : (
                  <ChevronUp size={14} className="text-slate-400 flex-shrink-0" />
                )}
              </Accordion.Trigger>

              <Accordion.Content className="data-[state=open]:animate-accordion-down data-[state=closed]:animate-accordion-up overflow-hidden">
                <div className="mt-1 space-y-0.5">
                  <button
                    onClick={() => { navigate('/settings'); setUserPanelOpen(false) }}
                    className="w-full flex items-center gap-3 px-3 py-2.5 text-sm text-slate-500 hover:bg-blue-50 hover:text-blue-700 rounded-lg transition-colors"
                  >
                    <Settings size={16} />
                    Settings
                  </button>
                  <button
                    onClick={handleLogout}
                    className="w-full flex items-center gap-3 px-3 py-2.5 text-sm text-slate-500 hover:bg-red-50 hover:text-red-500 rounded-lg transition-colors"
                  >
                    <LogOut size={16} />
                    Log Out
                  </button>
                </div>
              </Accordion.Content>
            </Accordion.Item>
          </Accordion.Root>
        ) : (
          <div className="flex justify-center">
            <div
              className="w-8 h-8 bg-blue-100 rounded-full flex items-center justify-center cursor-pointer hover:ring-2 hover:ring-blue-300 transition-all"
              onClick={() => setCollapsed(false)}
            >
              {user?.picture ? (
                <img src={user.picture} alt={user.name} className="w-8 h-8 rounded-full object-cover" />
              ) : (
                <span className="text-blue-700 text-xs font-semibold">
                  {user ? getInitials(user.name) : 'U'}
                </span>
              )}
            </div>
          </div>
        )}
      </div>
    </aside>
  )
}
