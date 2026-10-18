import { NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

interface ProjectNavItem {
  label: string
  to: string
}

interface SidebarProps {
  // When set, shows a project-scoped nav section below the global one,
  // matching the wireframe's per-project sidebar (Overview / Objects /
  // Project Brain) once a project is open.
  projectName?: string
  projectNav?: ProjectNavItem[]
}

const ROLE_LABEL: Record<string, string> = {
  admin: 'Admin',
  module_lead: 'Module Lead',
  solution_architect: 'Solution Architect',
  contributor: 'Contributor',
}

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  [
    'block rounded-lg px-3 py-2.5 text-sm no-underline transition-colors',
    isActive
      ? 'bg-accent font-semibold text-white'
      : 'text-sidebar-text hover:text-white',
  ].join(' ')

const projectNavLinkClass = ({ isActive }: { isActive: boolean }) =>
  [
    'block rounded-lg px-3 py-[9px] text-sm no-underline transition-colors',
    isActive
      ? 'bg-accent font-semibold text-white'
      : 'text-sidebar-text hover:text-white',
  ].join(' ')

export default function Sidebar({ projectName, projectNav }: SidebarProps) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  function handleLogout() {
    logout()
    navigate('/login', { replace: true })
  }

  const initial = user?.name?.trim()?.[0]?.toUpperCase() ?? '?'

  return (
    <div className="flex w-[240px] shrink-0 flex-col gap-7 bg-sidebar px-5 py-7 text-sidebar-text">
      <div className="font-heading text-xl font-extrabold tracking-tight text-white">
        CodeCanvas
      </div>

      <nav className="flex flex-col gap-1">
        <NavLink to="/" className={navLinkClass} end>
          Dashboard
        </NavLink>
        <NavLink to="/agent-observability" className={navLinkClass}>
          Agent Observability
        </NavLink>
        <NavLink to="/settings" className={navLinkClass}>
          Settings
        </NavLink>
      </nav>

      {projectName && projectNav && (
        <div className="mt-[6px] flex flex-col gap-1 border-t border-sidebar-border pt-[18px]">
          <div className="mb-1.5 px-3 text-[11px] font-bold uppercase tracking-wider text-sidebar-label">
            {projectName}
          </div>
          {projectNav.map((item) => (
            <NavLink key={item.to} to={item.to} className={projectNavLinkClass}>
              {item.label}
            </NavLink>
          ))}
        </div>
      )}

      <div className="mt-auto flex items-center gap-2.5 border-t border-sidebar-border pt-[18px]">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent text-[13px] font-bold text-white">
          {initial}
        </div>
        <div className="min-w-0 flex-1 text-[13px] leading-tight text-sidebar-text">
          <div className="truncate">{user?.name ?? 'Unknown user'}</div>
          <span className="text-sidebar-text-dim">{user ? ROLE_LABEL[user.role] ?? user.role : ''}</span>
        </div>
        <button
          type="button"
          onClick={handleLogout}
          title="Log out"
          className="shrink-0 rounded-md px-2 py-1 text-[11px] font-semibold text-sidebar-text-dim transition-colors hover:bg-sidebar-border hover:text-white"
        >
          Log out
        </button>
      </div>
    </div>
  )
}
