import { useCallback, useEffect, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import AppShell from '../components/AppShell'
import { OverallStatusPill, PipelinePill } from '../components/StatusPill'
import { ApiError, getLatestFsdDraft, getObject, getProject, setObjectCancelled, setObjectStageStatus } from '../lib/api'
import type { PipelineStageKey } from '../lib/api'
import type { FsdDraftOut, PipelineStage, Project, TrackedObject } from '../lib/types'

const PROJECT_NAV = (projectId: string) => [
  { label: 'Overview', to: `/projects/${projectId}/overview` },
  { label: 'Custom Objects', to: `/projects/${projectId}` },
  { label: 'Project Brain', to: `/projects/${projectId}/brain` },
  { label: 'Repository', to: `/projects/${projectId}/repository` },
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
  // Lifted up here (rather than fetched inside the FSD tab panel) so the
  // stat-card row above the stepper has real numbers regardless of which
  // stage tab is active -- a draft may not exist yet, which is a normal
  // state (a brand-new object), not an error.
  const [draft, setDraft] = useState<FsdDraftOut | null>(null)
  const [draftLoaded, setDraftLoaded] = useState(false)

  const requestedTab = searchParams.get('tab')
  const activeTab: PipelineStageKey = (STAGES.find((s) => s.key === requestedTab)?.key ?? 'fsd') as PipelineStageKey

  const reload = useCallback(() => {
    if (!projectId || !objectId) return
    Promise.all([getProject(projectId), getObject(objectId)])
      .then(([project, object]) => setState({ phase: 'done', project, object }))
      .catch((err) => setState({ phase: 'error', message: err instanceof ApiError ? err.message : 'Could not load this object.' }))
    setDraftLoaded(false)
    getLatestFsdDraft(objectId)
      .then((d) => setDraft(d))
      .catch(() => setDraft(null))
      .finally(() => setDraftLoaded(true))
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

  async function handleToggleCancelled() {
    if (!objectId) return
    try {
      const updated = await setObjectCancelled(objectId, !object.cancelled)
      setState({ phase: 'done', project, object: updated })
    } catch {
      // best-effort -- a failed toggle just leaves the button as it was
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

      <div className="mb-6 flex flex-wrap items-center gap-2.5">
        <h1 className="m-0 font-heading text-2xl font-extrabold">{object.name}</h1>
        {object.object_code && (
          <span className="rounded-full bg-slate-pill-bg px-2.5 py-1 font-mono text-xs font-bold text-slate-pill-text">
            {object.object_code}
          </span>
        )}
        <span className="rounded-full bg-slate-pill-bg px-2.5 py-1 text-xs font-bold text-slate-pill-text">{object.type}</span>
        <span className="rounded-full bg-slate-pill-bg px-2.5 py-1 text-xs font-bold text-slate-pill-text">{object.module}</span>
        <OverallStatusPill status={object.overall_status} />
        <button
          type="button"
          onClick={handleToggleCancelled}
          className={`ml-auto rounded-lg border px-4 py-2 text-xs font-semibold ${
            object.cancelled ? 'border-input-border bg-white text-slate-pill-text' : 'border-red-border bg-red-soft text-red-text'
          }`}
        >
          {object.cancelled ? 'Reactivate Object' : 'Cancel Object'}
        </button>
      </div>

      <StatCardRow stages={STAGES} object={object} draft={draft} draftLoaded={draftLoaded} />

      <PipelineStepper stages={STAGES} object={object} activeKey={activeTab} onSelect={(key) => setSearchParams({ tab: key })} />

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
          <FsdStagePanel projectId={project.id} objectId={object.id} object={object} draft={draft} draftLoaded={draftLoaded} />
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

// --- Pipeline stepper ------------------------------------------------------
// A visual read on the object's whole pipeline at a glance -- inspired by
// (not a copy of) the Capgemini Atlas Forge dashboard's stage stepper.
// Still backed by the same manually-set per-stage status fields as the old
// tab row (nothing here is a real multi-agent run beyond the FSD stage),
// it just makes "where is this object, overall" visible without clicking
// through every tab.

const NODE_STYLES: Record<PipelineStage, string> = {
  'Not Started': 'border-input-border bg-white text-faint',
  'In Progress': 'border-accent bg-accent text-white',
  Blocked: 'border-red bg-red text-white',
  'On Hold': 'border-amber bg-amber text-white',
  Complete: 'border-green bg-green text-white',
}

function PipelineStepper({
  stages,
  object,
  activeKey,
  onSelect,
}: {
  stages: StageDef[]
  object: TrackedObject
  activeKey: PipelineStageKey
  onSelect: (key: PipelineStageKey) => void
}) {
  return (
    <div className="mb-6 overflow-x-auto rounded-2xl border border-card-border bg-white px-6 py-7">
      <div className="flex min-w-max items-start">
        {stages.map((stage, idx) => {
          const status = object[stage.statusField] as PipelineStage
          const prevStatus = idx > 0 ? (object[stages[idx - 1].statusField] as PipelineStage) : null
          const isActive = stage.key === activeKey
          return (
            <div key={stage.key} className="flex items-start">
              {idx > 0 && (
                <div className={`mt-5 h-[2px] w-9 shrink-0 sm:w-14 ${prevStatus === 'Complete' ? 'bg-green' : 'bg-card-border'}`} />
              )}
              <button
                type="button"
                onClick={() => onSelect(stage.key)}
                className="flex w-[88px] shrink-0 flex-col items-center gap-2 bg-transparent text-center"
              >
                <span
                  className={`flex h-10 w-10 items-center justify-center rounded-full border-2 text-[13px] font-bold ${NODE_STYLES[status]} ${
                    isActive ? 'ring-[3px] ring-accent-soft' : ''
                  }`}
                >
                  {status === 'Complete' ? '✓' : idx + 1}
                </span>
                <span className={`text-[12.5px] font-semibold ${isActive ? 'text-ink' : 'text-muted'}`}>{stage.label}</span>
                <PipelinePill stage={status} />
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// --- Stat cards --------------------------------------------------------
// Current Step / Next Step / Tokens & Cost / Execution Time -- the same
// four-card idea as the Capgemini Manager Agent dashboard's stat row,
// adapted to what CodeCanvas actually tracks: Current/Next Step read the
// per-stage statuses above, Tokens & Cost and Execution Time come from the
// latest FSD draft's real recorded usage and duration (null/"—" rather
// than a guess when a draft predates this tracking, or doesn't exist yet).

function StatCard({ label, value, sublabel }: { label: string; value: string; sublabel?: string }) {
  return (
    <div className="rounded-xl border border-card-border bg-white p-5">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-muted">{label}</div>
      <div className="mt-1.5 font-heading text-lg font-bold text-ink">{value}</div>
      {sublabel && <div className="mt-0.5 text-[12px] text-muted">{sublabel}</div>}
    </div>
  )
}

function StatCardRow({
  stages,
  object,
  draft,
  draftLoaded,
}: {
  stages: StageDef[]
  object: TrackedObject
  draft: FsdDraftOut | null
  draftLoaded: boolean
}) {
  const firstIncompleteIdx = stages.findIndex((s) => object[s.statusField] !== 'Complete')
  const currentStepLabel = firstIncompleteIdx === -1 ? 'All stages complete' : stages[firstIncompleteIdx].label
  const nextStepLabel =
    firstIncompleteIdx === -1 || firstIncompleteIdx === stages.length - 1 ? '—' : stages[firstIncompleteIdx + 1].label

  let tokensValue = '—'
  let tokensSublabel: string | undefined = 'No FSD run yet'
  if (draftLoaded && draft) {
    const total = draft.token_usage_total
    if (total) {
      tokensValue = `${(total.input_tokens + total.output_tokens).toLocaleString()} tok`
      tokensSublabel = total.cost_usd != null ? `~$${total.cost_usd.toFixed(3)} est.` : 'Cost n/a for this model'
    } else {
      tokensValue = 'Not tracked'
      tokensSublabel = 'Generated before usage tracking existed'
    }
  }

  const executionTimeValue = draftLoaded && draft ? `${(draft.duration_ms / 1000).toFixed(1)}s` : '—'
  const executionTimeSublabel = draftLoaded && draft ? `Latest FSD generation (v${draft.version})` : undefined

  return (
    <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
      <StatCard label="Current Step" value={currentStepLabel} />
      <StatCard label="Next Step" value={nextStepLabel} />
      <StatCard label="Tokens & Cost" value={tokensValue} sublabel={tokensSublabel} />
      <StatCard label="Execution Time" value={executionTimeValue} sublabel={executionTimeSublabel} />
    </div>
  )
}

function FsdStagePanel({
  projectId,
  objectId,
  object,
  draft,
  draftLoaded,
}: {
  projectId: string
  objectId: string
  object: TrackedObject
  draft: FsdDraftOut | null
  draftLoaded: boolean
}) {
  if (!draftLoaded) {
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
