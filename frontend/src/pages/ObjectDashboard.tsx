import { useCallback, useEffect, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import AppShell from '../components/AppShell'
import { PipelinePill } from '../components/StatusPill'
import { ApiError, getLatestFsdDraft, getObject, getProject, setObjectStageStatus } from '../lib/api'
import type { PipelineStageKey } from '../lib/api'
import type { FsdDraftOut, PipelineStage, Project, TrackedObject } from '../lib/types'

const PROJECT_NAV = (projectId: string) => [
  { label: 'Overview', to: `/projects/${projectId}/overview` },
  { label: 'Custom Objects', to: `/projects/${projectId}` },
  { label: 'Project Brain', to: `/projects/${projectId}/brain` },
]

const PIPELINE_STATUSES: PipelineStage[] = ['Not Started', 'In Progress', 'Blocked', 'On Hold', 'Complete']

interface StageDef {
  key: PipelineStageKey
  label: string
  statusField: keyof TrackedObject
  built: boolean
}

const STAGES: StageDef[] = [
  { key: 'fsd', label: 'FSD', statusField: 'fsd_status', built: true },
  { key: 'feasibility', label: 'Feasibility', statusField: 'feasibility_status', built: false },
  { key: 'tsd', label: 'TSD', statusField: 'tsd_status', built: false },
  { key: 'code_review', label: 'Code Review', statusField: 'code_review_status', built: false },
  { key: 'unit_test', label: 'Unit Test', statusField: 'unit_test_status', built: false },
  { key: 'code', label: 'Code', statusField: 'code_status', built: false },
]

type LoadState =
  | { phase: 'loading' }
  | { phase: 'error'; message: string }
  | { phase: 'done'; project: Project; object: TrackedObject }

export default function ObjectDashboard() {
  const { projectId, objectId } = useParams<{ projectId: string; objectId: string }>()
  const [searchParams, setSearchParams] = useSearchParams()
  const [state, setState] = useState<LoadState>({ phase: 'loading' })

  const requestedTab = searchParams.get('tab')
  const activeTab: PipelineStageKey = (STAGES.find((s) => s.key === requestedTab)?.key ?? 'fsd') as PipelineStageKey

  const reload = useCallback(() => {
    if (!projectId || !objectId) return
    Promise.all([getProject(projectId), getObject(objectId)])
      .then(([project, object]) => setState({ phase: 'done', project, object }))
      .catch((err) => setState({ phase: 'error', message: err instanceof ApiError ? err.message : 'Could not load this object.' }))
  }, [projectId, objectId])

  useEffect(() => {
    setState({ phase: 'loading' })
    reload()
  }, [reload])

  if (state.phase === 'loading') {
    return (
      <AppShell>
        <div className="text-sm text-muted">Loading…</div>
      </AppShell>
    )
  }
  if (state.phase === 'error') {
    return (
      <AppShell>
        <div className="rounded-xl border border-red-border bg-red-soft px-5 py-4 text-sm text-red-text">{state.message}</div>
      </AppShell>
    )
  }

  const { project, object } = state
  const activeStage = STAGES.find((s) => s.key === activeTab)!

  async function handleStatusChange(stage: StageDef, status: PipelineStage) {
    if (!objectId) return
    try {
      const updated = await setObjectStageStatus(objectId, stage.key, status)
      setState({ phase: 'done', project, object: updated })
    } catch {
      // best-effort -- a failed status change just leaves the dropdown as it was
    }
  }

  return (
    <AppShell projectName={project.name} projectNav={PROJECT_NAV(project.id)} maxWidth="1100px">
      <div className="mb-4 text-[13px] text-muted">
        <Link to="/" className="text-muted no-underline">
          Projects
        </Link>{' '}
        /{' '}
        <Link to={`/projects/${project.id}`} className="text-muted no-underline">
          {project.name}
        </Link>{' '}
        / <span className="text-ink">{object.name}</span>
      </div>

      <div className="mb-6 flex items-center gap-2.5">
        <h1 className="m-0 font-heading text-2xl font-extrabold">{object.name}</h1>
        <span className="rounded-full bg-slate-pill-bg px-2.5 py-1 text-xs font-bold text-slate-pill-text">{object.type}</span>
        <span className="rounded-full bg-slate-pill-bg px-2.5 py-1 text-xs font-bold text-slate-pill-text">{object.module}</span>
      </div>

      <div className="mb-6 flex items-center gap-1 overflow-x-auto rounded-xl border border-card-border bg-white p-1.5">
        {STAGES.map((stage) => (
          <button
            key={stage.key}
            type="button"
            onClick={() => setSearchParams({ tab: stage.key })}
            className={`flex shrink-0 items-center gap-2 whitespace-nowrap rounded-lg px-4 py-2.5 text-[13px] font-semibold ${
              activeTab === stage.key ? 'bg-accent text-white' : 'text-slate-pill-text hover:bg-app-bg'
            }`}
          >
            {stage.label}
            <PipelinePill stage={object[stage.statusField] as PipelineStage} />
          </button>
        ))}
      </div>

      <div className="rounded-2xl border border-card-border bg-white p-7">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <div className="font-heading text-lg font-bold">{activeStage.label}</div>
          <label className="flex items-center gap-2 text-[12.5px] text-muted">
            Status
            <select
              value={object[activeStage.statusField] as string}
              onChange={(e) => handleStatusChange(activeStage, e.target.value as PipelineStage)}
              className="rounded-md border border-input-border px-2.5 py-1.5 text-[12.5px] font-semibold text-ink"
            >
              {PIPELINE_STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
        </div>

        {activeStage.key === 'fsd' ? (
          <FsdStagePanel projectId={project.id} objectId={object.id} object={object} />
        ) : (
          <div className="rounded-xl border border-dashed border-input-border bg-app-bg/60 p-8 text-center text-sm text-muted">
            {activeStage.label} isn't built yet in this app — the status above is a manual marker you can set and
            change yourself in the meantime.
          </div>
        )}
      </div>
    </AppShell>
  )
}

function FsdStagePanel({ projectId, objectId, object }: { projectId: string; objectId: string; object: TrackedObject }) {
  const [draft, setDraft] = useState<FsdDraftOut | null>(null)
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    let cancelled = false
    getLatestFsdDraft(objectId)
      .then((d) => {
        if (!cancelled) setDraft(d)
      })
      .catch(() => {
        if (!cancelled) setDraft(null)
      })
      .finally(() => {
        if (!cancelled) setLoaded(true)
      })
    return () => {
      cancelled = true
    }
  }, [objectId])

  if (!loaded) {
    return <div className="text-sm text-muted">Loading…</div>
  }

  if (!draft) {
    return (
      <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-input-border bg-app-bg/60 p-8 text-center">
        <div className="text-sm text-muted">No FSD has been generated yet for this object.</div>
        <Link
          to={`/projects/${projectId}/objects/${objectId}/fsd/intake`}
          className="rounded-lg bg-accent px-5 py-2.5 text-sm font-semibold text-white no-underline"
        >
          Go to FSD Creation
        </Link>
      </div>
    )
  }

  const q = draft.quality_score

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-4 rounded-xl border border-card-border bg-app-bg/60 p-5">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-wide text-muted">Latest version</div>
          <div className="font-heading text-lg font-bold">v{draft.version}</div>
        </div>
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-wide text-muted">Quality score</div>
          <div className="font-heading text-lg font-bold">{q.overall_pct.toFixed(0)}%</div>
        </div>
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-wide text-muted">Approvals</div>
          <div className="text-[13px] font-semibold">
            {(draft.approvals.module_lead_approved ? 1 : 0) + (draft.approvals.solution_architect_approved ? 1 : 0)} of{' '}
            {q.requires_dual_approval ? 2 : 1}
          </div>
        </div>
      </div>
      <div className="flex gap-2.5">
        <Link
          to={`/projects/${projectId}/objects/${objectId}/fsd/review`}
          className="rounded-lg bg-accent px-5 py-2.5 text-sm font-semibold text-white no-underline"
        >
          Open FSD Review
        </Link>
        <Link
          to={`/projects/${projectId}/objects/${objectId}/fsd/intake`}
          className="rounded-lg border border-input-border bg-white px-5 py-2.5 text-sm font-semibold text-slate-pill-text no-underline"
        >
          Edit inputs / regenerate
        </Link>
      </div>
      {object.fsd_status === 'On Hold' && (
        <div className="rounded-lg border border-amber-border bg-amber-soft-2 px-4 py-2.5 text-[12.5px] text-amber-text">
          This stage is manually marked On Hold — generating a new version, or an approval withdrawal, won't move it
          off On Hold on its own (a full approval still will, since that's a real completion). Switch the status
          above when you're ready to resume.
        </div>
      )}
    </div>
  )
}
