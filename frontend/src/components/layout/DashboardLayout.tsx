import { useState, useEffect, ReactNode } from 'react'
import Sidebar from './Sidebar'
import { Menu } from 'lucide-react'

function useIsMobile(breakpoint = 768) {
  const [isMobile, setIsMobile] = useState(() =>
    typeof window !== 'undefined' ? window.innerWidth < breakpoint : false
  )
  useEffect(() => {
    const onResize = () => setIsMobile(window.innerWidth < breakpoint)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [breakpoint])
  return isMobile
}

export default function DashboardLayout({ children }: { children: ReactNode }) {
  const isMobile = useIsMobile()
  const [collapsed, setCollapsed] = useState(isMobile)
  const [mobileOpen, setMobileOpen] = useState(false)

  // Auto-collapse when switching to mobile
  useEffect(() => {
    if (isMobile) setCollapsed(true)
  }, [isMobile])

  // Close mobile drawer on route change (children change)
  useEffect(() => {
    if (mobileOpen) setMobileOpen(false)
  }, [children])

  return (
    <div className="flex h-screen bg-background overflow-hidden">
      {/* Mobile: overlay sidebar */}
      {isMobile ? (
        <>
          {/* Hamburger bar */}
          <div className="fixed top-0 left-0 right-0 z-40 h-12 bg-white border-b border-border flex items-center px-3 gap-3">
            <button
              onClick={() => setMobileOpen(true)}
              className="w-8 h-8 flex items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
            >
              <Menu size={18} />
            </button>
          </div>

          {/* Drawer overlay */}
          {mobileOpen && (
            <div className="fixed inset-0 z-50 flex">
              <div
                className="absolute inset-0 bg-black/40"
                onClick={() => setMobileOpen(false)}
              />
              <div className="relative z-10 w-60 max-w-[80vw]">
                <Sidebar collapsed={false} onToggle={() => setMobileOpen(false)} />
              </div>
            </div>
          )}

          <main className="flex-1 overflow-y-auto bg-background min-w-0 pt-12">
            {children}
          </main>
        </>
      ) : (
        <>
          <Sidebar collapsed={collapsed} onToggle={() => setCollapsed(c => !c)} />
          <main className="flex-1 overflow-y-auto bg-background min-w-0">
            {children}
          </main>
        </>
      )}
    </div>
  )
}
