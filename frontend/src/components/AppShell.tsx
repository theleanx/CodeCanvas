import type { ReactNode } from 'react'
import Sidebar from './Sidebar'

interface ProjectNavItem {
  label: string
  to: string
}

interface AppShellProps {
  children: ReactNode
  projectName?: string
  projectNav?: ProjectNavItem[]
  maxWidth?: string
}

export default function AppShell({ children, projectName, projectNav, maxWidth }: AppShellProps) {
  return (
    <div className="flex min-h-screen bg-app-bg font-sans text-ink">
      <Sidebar projectName={projectName} projectNav={projectNav} />
      <div
        className="min-w-0 flex-1 px-12 py-10"
        style={maxWidth ? { maxWidth } : undefined}
      >
        {children}
      </div>
    </div>
  )
}
