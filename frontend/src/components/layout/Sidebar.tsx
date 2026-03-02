import { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { Home, Settings, LogOut, FileSpreadsheet, ChevronUp, ChevronDown, PanelLeftClose, PanelLeftOpen } from 'lucide-react' // Settings used in user panel dropdown
import { useAuthStore } from '@/store/authStore'
import { getInitials } from '@/lib/utils'
import { cn } from '@/lib/utils'
import toast from 'react-hot-toast'

export default function Sidebar() {
  const navigate = useNavigate()
  const location = useLocation()
  const { user, logout } = useAuthStore()
  const [collapsed, setCollapsed] = useState(false)
  const [userPanelOpen, setUserPanelOpen] = useState(false)

  const handleLogout = () => {
    logout()
    toast.success('Logged out')
    navigate('/')
  }

  const navItems = [
    { icon: Home, label: 'Home', path: '/dashboard' },
  ]

  return (
    <aside
      className={cn(
        'relative flex flex-col border-r border-border transition-all duration-300',
        'bg-[#0c0c0f]',
        collapsed ? 'w-16' : 'w-60'
      )}
      style={{ minHeight: '100vh' }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 h-14 border-b border-border">
        {!collapsed && (
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 bg-primary rounded-md flex items-center justify-center flex-shrink-0">
              <FileSpreadsheet size={14} className="text-white" />
            </div>
            <span className="font-semibold text-foreground text-sm tracking-tight">PDF to Excel</span>
          </div>
        )}
        {collapsed && (
          <div className="w-7 h-7 bg-primary rounded-md flex items-center justify-center mx-auto">
            <FileSpreadsheet size={14} className="text-white" />
          </div>
        )}
        {!collapsed && (
          <button
            onClick={() => setCollapsed(true)}
            className="text-muted-foreground hover:text-foreground transition-colors p-1 rounded-md hover:bg-accent"
          >
            <PanelLeftClose size={15} />
          </button>
        )}
      </div>

      {collapsed && (
        <button
          onClick={() => setCollapsed(false)}
          className="absolute -right-3 top-14 w-6 h-6 bg-card border border-border rounded-full flex items-center justify-center text-muted-foreground hover:text-primary transition-colors z-10"
        >
          <PanelLeftOpen size={11} />
        </button>
      )}

      {/* Navigation */}
      <nav className="flex-1 px-2 py-3 space-y-0.5">
        {navItems.map((item) => {
          const isActive = location.pathname === item.path
          return (
            <button
              key={item.path}
              onClick={() => navigate(item.path)}
              className={cn(
                'w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-all duration-150',
                isActive
                  ? 'bg-primary/15 text-primary border border-primary/20'
                  : 'text-muted-foreground hover:bg-accent hover:text-foreground',
                collapsed && 'justify-center'
              )}
              title={collapsed ? item.label : undefined}
            >
              <item.icon size={17} className="flex-shrink-0" />
              {!collapsed && <span>{item.label}</span>}
            </button>
          )
        })}
      </nav>

      {/* User Panel - Bottom */}
      <div className="border-t border-border px-2 py-2">
        {!collapsed ? (
          <div>
            {/* Menu expands upward */}
            {userPanelOpen && (
              <div className="mb-1 p-1 bg-card border border-border rounded-lg space-y-0.5">
                <button
                  onClick={() => { navigate('/settings'); setUserPanelOpen(false) }}
                  className="w-full flex items-center gap-3 px-3 py-2 text-sm text-muted-foreground hover:bg-accent hover:text-foreground rounded-md transition-colors"
                >
                  <Settings size={15} />
                  Settings
                </button>
                <button
                  onClick={handleLogout}
                  className="w-full flex items-center gap-3 px-3 py-2 text-sm text-muted-foreground hover:bg-destructive/10 hover:text-red-400 rounded-md transition-colors"
                >
                  <LogOut size={15} />
                  Log Out
                </button>
              </div>
            )}

            {/* User trigger */}
            <button
              onClick={() => setUserPanelOpen(!userPanelOpen)}
              className="w-full flex items-center gap-2.5 px-3 py-2 hover:bg-accent rounded-lg transition-colors group"
            >
              <div className="w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 overflow-hidden ring-1 ring-border">
                {user?.picture ? (
                  <img src={user.picture} alt={user.name} className="w-7 h-7 rounded-full object-cover" />
                ) : (
                  <div className="w-7 h-7 bg-primary/20 flex items-center justify-center">
                    <span className="text-primary text-xs font-semibold">
                      {user ? getInitials(user.name) : 'U'}
                    </span>
                  </div>
                )}
              </div>
              <div className="flex-1 text-left min-w-0">
                <div className="text-xs text-foreground font-medium truncate">{user?.name}</div>
              </div>
              {userPanelOpen
                ? <ChevronDown size={13} className="text-muted-foreground flex-shrink-0" />
                : <ChevronUp size={13} className="text-muted-foreground flex-shrink-0" />
              }
            </button>
          </div>
        ) : (
          <div className="flex justify-center">
            <div
              className="w-7 h-7 rounded-full overflow-hidden cursor-pointer ring-1 ring-border hover:ring-primary transition-all"
              onClick={() => setCollapsed(false)}
            >
              {user?.picture ? (
                <img src={user.picture} alt={user.name} className="w-7 h-7 rounded-full object-cover" />
              ) : (
                <div className="w-7 h-7 bg-primary/20 flex items-center justify-center">
                  <span className="text-primary text-xs font-semibold">
                    {user ? getInitials(user.name) : 'U'}
                  </span>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </aside>
  )
}
