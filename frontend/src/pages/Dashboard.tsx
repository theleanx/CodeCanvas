import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import AppShell from '../components/AppShell'
import { useAuth } from '../context/AuthContext'
import { ApiError, deleteProject, listProjects } from '../lib/api'
import type { Project } from '../lib/types'

type LoadState = { phase: 'loading' } | { phase: 'error'; message: string } | { phase: 'done'; projects: Project[] }

export default function Dashboard() {
  const { user } = useAuth()
  const [state, setState] = useState<LoadState>({ phase: 'loading' })
  const [confirmingId, setConfirmingId] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  function reload() {
    listProjects()
      .then((projects) => setState({ phase: 'done', projects }))
      .catch((err) =>
        setState({
          phase: 'error',
          message: err instanceof ApiError ? err.message : 'Could not reach the backend.',
        }),
      )
  }

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

  async function handleDelete(projectId: string) {
    setDeleteError(null)
    setDeletingId(projectId)
    try {
      await deleteProject(projectId)
      setConfirmingId(null)
      reload()
    } catch (err) {
      setDeleteError(err instanceof ApiError ? err.message : 'Could not delete this project.')
    } finally {
      setDeletingId(null)
    }
  }

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

          {deleteError && (
            <div className="mt-5 rounded-xl border border-red-border bg-red-soft px-5 py-3 text-sm text-red-text">
              {deleteError}
            </div>
          )}

          <div className="mt-7 grid grid-cols-[repeat(auto-fill,minmax(300px,1fr))] gap-5">
            {projects.map((p) => (
              <div key={p.id} className="relative flex flex-col gap-3.5 rounded-2xl border border-card-border bg-white p-[22px]">
                {(user?.role === 'admin' || user?.role === 'solution_architect') && (
                  <div className="absolute right-3.5 top-3.5">
                    {confirmingId === p.id ? (
                      <div className="flex gap-1.5">
                        <button
                          type="button"
                          onClick={() => handleDelete(p.id)}
                          disabled={deletingId === p.id}
                          className="whitespace-nowrap rounded-md bg-red-text px-2.5 py-1 text-[11px] font-bold text-white disabled:opacity-50"
                        >
                          {deletingId === p.id ? 'Deleting…' : 'Confirm delete'}
                        </button>
                        <button
                          type="button"
                          onClick={() => setConfirmingId(null)}
                          className="whitespace-nowrap rounded-md border border-input-border bg-white px-2.5 py-1 text-[11px] font-semibold text-slate-pill-text"
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <button
                        type="button"
                        onClick={() => setConfirmingId(p.id)}
                        title="Delete project"
                        className="rounded-md border border-input-border bg-white px-2 py-1 text-[11px] font-semibold text-faint hover:border-red-border hover:text-red-text"
                      >
                        Delete
                      </button>
                    )}
                  </div>
                )}
                <Link to={`/projects/${p.id}`} className="flex flex-col gap-3.5 text-inherit no-underline">
                  <div className="flex items-start justify-between gap-2.5 pr-14">
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
              </div>
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
