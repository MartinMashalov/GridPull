import { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { Settings, LogOut, FileSpreadsheet, ChevronsLeft, Workflow, Clipboard, Table2, Inbox, FileText } from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import { getInitials, cn } from '@/lib/utils'
import toast from 'react-hot-toast'
import { Tooltip, TooltipContent, TooltipTrigger, TooltipProvider } from '@/components/ui/tooltip'
import { Separator } from '@/components/ui/separator'

interface SidebarProps {
  collapsed: boolean
  onToggle: () => void
}

const NAV = [
  { icon: Clipboard,  label: 'Form Filling',    path: '/form-filling' },
  { icon: Table2,     label: 'Schedules',        path: '/schedules' },
  { icon: Inbox,      label: 'Document Inbox',   path: '/inbox' },
  { icon: FileText,   label: 'Proposals',        path: '/proposals' },
  { icon: Workflow,   label: 'Pipelines',        path: '/pipelines' },
  { icon: Settings,   label: 'Settings',         path: '/settings'  },
]

export default function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const navigate  = useNavigate()
  const location  = useLocation()
  const { user, logout } = useAuthStore()
  const [userOpen, setUserOpen] = useState(false)

  const handleLogout = () => {
    logout()
    toast.success('Logged out')
    navigate('/')
  }

  return (
    <TooltipProvider delayDuration={200}>
      <aside
        className={cn(
          'relative flex flex-col h-screen bg-white border-r border-border transition-[width] duration-200 ease-in-out flex-shrink-0',
          collapsed ? 'w-16 cursor-pointer' : 'w-60'
        )}
        onClick={collapsed ? onToggle : undefined}
      >
        {/* ── Logo + toggle ──────────────────────────────────────── */}
        <div className={cn(
          'flex items-center h-14 border-b border-border flex-shrink-0 px-3',
          collapsed ? 'justify-center' : 'justify-between px-4'
        )}>
          {!collapsed && (
            <div className="flex items-center gap-2.5">
              <div className="w-7 h-7 bg-primary rounded-md flex items-center justify-center flex-shrink-0">
                <FileSpreadsheet size={14} className="text-white" />
              </div>
              <span className="font-semibold text-sm tracking-tight">GridPull</span>
            </div>
          )}
          {collapsed && (
            <div className="w-7 h-7 bg-primary rounded-md flex items-center justify-center">
              <FileSpreadsheet size={14} className="text-white" />
            </div>
          )}
          <button
            onClick={onToggle}
            className={cn(
              'w-7 h-7 flex items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-accent transition-colors',
              collapsed && 'hidden'
            )}
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            <ChevronsLeft size={15} />
          </button>
        </div>

        {/* ── Nav ───────────────────────────────────────────────── */}
        <nav className="flex-1 px-2 py-3 space-y-0.5">
          {NAV.map(item => {
            const isActive = location.pathname === item.path
            const btn = (
              <button
                key={item.path}
                onClick={(e) => { e.stopPropagation(); navigate(item.path) }}
                className={cn(
                  'w-full flex items-center rounded-lg text-sm font-medium transition-all duration-150',
                  collapsed ? 'justify-center p-2.5' : 'gap-3 px-3 py-2',
                  isActive
                    ? 'bg-primary/10 text-primary'
                    : 'text-muted-foreground hover:bg-accent hover:text-foreground'
                )}
              >
                <item.icon size={17} className="flex-shrink-0" />
                {!collapsed && <span>{item.label}</span>}
              </button>
            )

            if (collapsed) {
              return (
                <Tooltip key={item.path}>
                  <TooltipTrigger asChild>{btn}</TooltipTrigger>
                  <TooltipContent side="right">{item.label}</TooltipContent>
                </Tooltip>
              )
            }
            return btn
          })}
        </nav>


        {/* ── User ──────────────────────────────────────────────── */}
        <div className="px-2 pb-3">
          <Separator className="mb-2" />

          {/* Accordion: name + logout — only visible when userOpen */}
          {!collapsed && userOpen && (
            <div className="mb-1">
              <button
                onClick={(e) => { e.stopPropagation(); handleLogout() }}
                className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-muted-foreground hover:bg-red-50 hover:text-red-500 transition-colors"
              >
                <LogOut size={15} />
                Log out
              </button>
            </div>
          )}

          {/* Avatar — always visible, click to toggle */}
          {collapsed ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  onClick={(e) => { e.stopPropagation(); handleLogout() }}
                  className="w-full flex items-center justify-center p-1.5 rounded-lg hover:bg-accent transition-colors"
                >
                  <div className="w-7 h-7 rounded-full overflow-hidden ring-1 ring-border flex-shrink-0">
                    {user?.picture ? (
                      <img src={user.picture} alt={user?.name} className="w-7 h-7 object-cover" />
                    ) : (
                      <div className="w-7 h-7 bg-primary/20 flex items-center justify-center">
                        <span className="text-primary text-xs font-semibold">{user ? getInitials(user.name) : 'U'}</span>
                      </div>
                    )}
                  </div>
                </button>
              </TooltipTrigger>
              <TooltipContent side="right">Log out</TooltipContent>
            </Tooltip>
          ) : (
            <button
              onClick={(e) => { e.stopPropagation(); setUserOpen(o => !o) }}
              className={cn(
                "w-full flex items-center gap-2.5 px-2 py-1.5 rounded-lg transition-all duration-150 outline-none focus:outline-none focus-visible:outline-none [&:focus-visible]:bg-transparent [-webkit-tap-highlight-color:transparent]",
                userOpen ? "bg-muted/80 text-foreground" : "hover:bg-muted/70"
              )}
            >
              <div className="w-7 h-7 rounded-full overflow-hidden ring-1 ring-border flex-shrink-0">
                {user?.picture ? (
                  <img src={user.picture} alt={user?.name} className="w-7 h-7 object-cover" />
                ) : (
                  <div className="w-7 h-7 bg-primary/20 flex items-center justify-center">
                    <span className="text-primary text-xs font-semibold">{user ? getInitials(user.name) : 'U'}</span>
                  </div>
                )}
              </div>
              <span className="text-xs font-medium truncate flex-1 text-left">{user?.name}</span>
            </button>
          )}
        </div>
      </aside>
    </TooltipProvider>
  )
}
