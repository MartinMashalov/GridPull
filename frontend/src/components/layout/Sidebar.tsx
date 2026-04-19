import { useNavigate, useLocation } from 'react-router-dom'
import { Settings, LogOut, FileSpreadsheet, ChevronsLeft, Workflow, Clipboard, Table2, Inbox, FileText, Lock } from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import { getInitials, cn } from '@/lib/utils'
import { isToolLocked, type ToolKey } from '@/lib/toolAccess'
import toast from 'react-hot-toast'
import { Tooltip, TooltipContent, TooltipTrigger, TooltipProvider } from '@/components/ui/tooltip'
import { Separator } from '@/components/ui/separator'
import { Button } from '@/components/ui/button'

interface SidebarProps {
  collapsed: boolean
  onToggle: () => void
}

type NavItem = {
  icon: typeof Clipboard
  label: string
  path: string
  toolKey?: ToolKey
}

const NAV: NavItem[] = [
  { icon: Clipboard,  label: 'Fill Applications', path: '/form-filling', toolKey: 'form-filling' },
  { icon: Table2,     label: 'Schedules',        path: '/schedules',    toolKey: 'schedules' },
  { icon: Inbox,      label: 'Document Inbox',   path: '/inbox',        toolKey: 'inbox' },
  { icon: FileText,   label: 'Proposals',        path: '/proposals',    toolKey: 'proposals' },
  { icon: Workflow,   label: 'Pipelines',        path: '/pipelines',    toolKey: 'pipelines' },
  { icon: Settings,   label: 'Settings',         path: '/settings'  },
]

export default function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const navigate  = useNavigate()
  const location  = useLocation()
  const { user, logout } = useAuthStore()

  const handleLogout = () => {
    logout()
    window.location.replace('/')
  }

  const handleLogoClick = () => {
    logout()
    window.location.replace('/')
  }

  return (
    <TooltipProvider delayDuration={200}>
      <aside
        className={cn(
          'relative flex flex-col h-full bg-white border-r border-border transition-[width] duration-200 ease-in-out flex-shrink-0',
          collapsed ? 'w-16' : 'w-60'
        )}
      >
        {/* ── Logo + toggle ──────────────────────────────────────── */}
        <div className={cn(
          'flex items-center h-14 border-b border-border flex-shrink-0 px-3',
          collapsed ? 'justify-center' : 'justify-between px-4'
        )}>
          <button
            type="button"
            onClick={handleLogoClick}
            title="Log out and return to home"
            className={cn(
              'flex items-center gap-2.5 rounded-md outline-none focus-visible:ring-2 focus-visible:ring-ring',
              collapsed ? 'justify-center' : ''
            )}
          >
            <div className="w-7 h-7 bg-primary rounded-md flex items-center justify-center flex-shrink-0">
              <FileSpreadsheet size={14} className="text-white" />
            </div>
            {!collapsed && <span className="font-semibold text-sm tracking-tight">GridPull</span>}
          </button>
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
        <nav className="flex-1 min-h-0 overflow-y-auto px-2 py-3 space-y-0.5">
          {NAV.map(item => {
            const isActive = location.pathname === item.path
            const locked = item.toolKey ? isToolLocked(user?.subscription_tier, item.toolKey) : false

            const btn = (
              <button
                key={item.path}
                onClick={(e) => {
                  e.stopPropagation()
                  if (locked) {
                    toast('Upgrade your plan to unlock this tool.', { icon: '🔒' })
                    navigate('/settings')
                    return
                  }
                  navigate(item.path)
                }}
                className={cn(
                  'w-full flex items-center rounded-lg text-sm font-medium transition-all duration-150',
                  collapsed ? 'justify-center p-2.5' : 'gap-3 px-3 py-2',
                  isActive
                    ? 'bg-primary/10 text-primary'
                    : locked
                      ? 'text-muted-foreground/50 hover:bg-accent/50'
                      : 'text-muted-foreground hover:bg-accent hover:text-foreground'
                )}
                aria-disabled={locked}
              >
                <item.icon size={17} className="flex-shrink-0" />
                {!collapsed && <span className="flex-1 text-left">{item.label}</span>}
                {!collapsed && locked && <Lock size={12} className="flex-shrink-0" />}
              </button>
            )

            if (collapsed) {
              return (
                <Tooltip key={item.path}>
                  <TooltipTrigger asChild>{btn}</TooltipTrigger>
                  <TooltipContent side="right">
                    {item.label}{locked ? ' — upgrade required' : ''}
                  </TooltipContent>
                </Tooltip>
              )
            }
            return btn
          })}
        </nav>


        {/* ── User ──────────────────────────────────────────────── */}
        <div className="px-2 pb-3">
          <Separator className="mb-2" />

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
            <div className="space-y-1">
              <div className="flex items-center gap-2.5 px-2 py-1.5 rounded-lg">
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
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={handleLogout}
                className="w-full justify-start gap-3 px-3 text-muted-foreground hover:bg-red-50 hover:text-red-500"
              >
                <LogOut size={15} />
                Log out
              </Button>
            </div>
          )}
        </div>
      </aside>
    </TooltipProvider>
  )
}
