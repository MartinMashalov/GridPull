import { useState, useEffect, ReactNode } from 'react'
import Sidebar from './Sidebar'

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

  // Auto-collapse when switching to mobile
  useEffect(() => {
    if (isMobile) setCollapsed(true)
  }, [isMobile])

  return (
    <div className="flex h-screen bg-background overflow-hidden">
      <Sidebar collapsed={collapsed} onToggle={() => setCollapsed(c => !c)} />
      <main className="flex-1 overflow-y-auto bg-background min-w-0">
        {children}
      </main>
    </div>
  )
}
