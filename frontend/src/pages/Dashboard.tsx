import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import AppShell from '../components/AppShell'
import { ApiError, listProjects } from '../lib/api'
import type { Project } from '../lib/types'

type LoadState = { phase: 'loading' } | { phase: 'error'; message: string } | { phase: 'done'; projects: Project[] }

export default function Dashboard() {
  const [state, setState] = useState<LoadState>({ phase: 'loading' })

  useEffect(() => {
    let cancelled = false
    listProjects()
      .then((projects) => {
        if (!cancelled) setState({ phase: 'done', projects })
      })
      .catch((err) => {
        if (!cancelled) {
          setState({
            phase: 'error',
            message: err instanceof ApiError ? err.message : 'Could not reach the backend.',
          })
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  const projects = state.phase === 'done' ? state.projects : []
  const totalObjects = projects.reduce((sum, p) => sum + p.object_count, 0)

  return (
    <AppShell>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="m-0 font-heading text-[28px] font-extrabold">Projects</h1>
          <div className="mt-1 text-sm text-muted">
            Each project is a closed context — its own Objects, Project Brain, and approval history.
          </div>
        </div>
        <Link
          to="/projects/new"
          className="whitespace-nowrap rounded-lg bg-accent px-[22px] py-3 text-sm font-semibold text-white no-underline"
        >
          + New Project
        </Link>
      </div>

      {state.phase === 'loading' && <div className="mt-8 text-sm text-muted">Loading projects…</div>}
      {state.phase === 'error' && (
        <div className="mt-8 rounded-xl border border-red-border bg-red-soft px-5 py-4 text-sm text-red-text">
          Couldn't load projects: {state.message}
        </div>
      )}

      {state.phase === 'done' && (
        <>
          <div className="mt-7 grid grid-cols-4 gap-4">
            <StatCard label="Active Projects" value={projects.length} />
            <StatCard label="Total Objects" value={totalObjects} />
            <StatCard label="Pending Approvals" value={0} tone="amber" />
            <StatCard label="Agent Runs (7d)" value={0} />
          </div>

          <div className="mt-7 grid grid-cols-[repeat(auto-fill,minmax(300px,1fr))] gap-5">
            {projects.map((p) => (
              <Link
                key={p.id}
                to={`/projects/${p.id}`}
                className="flex flex-col gap-3.5 rounded-2xl border border-card-border bg-white p-[22px] text-inherit no-underline"
              >
                <div className="flex items-start justify-between gap-2.5">
                  <div className="font-heading text-base font-bold">{p.name}</div>
                  <span
                    className={`whitespace-nowrap rounded-full px-2.5 py-1 text-[11px] font-bold ${
                      p.kind === 'Greenfield' ? 'bg-accent-soft text-accent' : 'bg-slate-pill-bg text-slate-pill-text'
                    }`}
                  >
                    {p.kind}
                  </span>
                </div>
                <div className="flex flex-col gap-1 text-[13px] text-muted">
                  <div>{p.system_description || '—'}</div>
                  <div>
                    {p.industry || '—'} · {p.geography || '—'}
                  </div>
                </div>
                <div className="mt-0.5 flex items-center justify-between border-t border-divider pt-3.5 text-xs text-muted">
                  <span>{p.object_count} objects</span>
                  <span>Updated {new Date(p.updated_at).toLocaleDateString()}</span>
                </div>
              </Link>
            ))}

            {projects.length === 0 && (
              <div className="col-span-full rounded-2xl border border-dashed border-input-border bg-white p-10 text-center text-sm text-muted">
                No projects yet. Create one to get started.
              </div>
            )}
          </div>
        </>
      )}
    </AppShell>
  )
}

function StatCard({ label, value, tone }: { label: string; value: number; tone?: 'amber' }) {
  return (
    <div className="rounded-xl border border-card-border bg-white px-5 py-[18px]">
      <div className="text-xs font-semibold uppercase tracking-wide text-muted">{label}</div>
      <div className={`mt-2 font-heading text-[28px] font-extrabold ${tone === 'amber' ? 'text-amber' : ''}`}>
        {value}
      </div>
    </div>
  )
}
