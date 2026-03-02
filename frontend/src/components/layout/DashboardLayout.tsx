import { useState, ReactNode } from 'react'
import Sidebar, { SidebarExpandButton } from './Sidebar'

interface DashboardLayoutProps {
  children: ReactNode
}

export default function DashboardLayout({ children }: DashboardLayoutProps) {
  const [collapsed, setCollapsed] = useState(false)

  return (
    <div className="flex h-screen bg-background overflow-hidden">
      <Sidebar collapsed={collapsed} onCollapse={() => setCollapsed(true)} />
      {collapsed && <SidebarExpandButton onClick={() => setCollapsed(false)} />}
      <main className="flex-1 overflow-y-auto scrollbar-thin bg-background">
        {children}
      </main>
    </div>
  )
}
