import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import AppShell from '../components/AppShell'
import { useAuth } from '../context/AuthContext'
import {
  ApiError,
  downloadFsdExport,
  downloadIntakeValidationPdf,
  generateFsdDraft,
  getFsdDraft,
  getLatestFsdDraft,
  getObject,
  getProject,
  listFsdDrafts,
  pushFsdToGithub,
  pushFsdToGoogleDrive,
  rerunIntakeValidation,
  setApproval,
} from '../lib/api'
import type { ExportFormat } from '../lib/api'
import type {
  DocumentIdentification,
  FsdDraftOut,
  FsdDraftSummary,
  FSDSection,
  IntakeCheckStatus,
  IntakeChecklistItem,
  IntakeSeverity,
  Project,
  ReviewSignoffRow,
  SourceDocumentIn,
  TrackedObject,
  ValidationRow,
} from '../lib/types'

const PROJECT_NAV = (projectId: string) => [
  { label: 'Overview', to: `/projects/${projectId}/overview` },
  { label: 'Custom Objects', to: `/projects/${projectId}` },
  { label: 'Project Brain', to: `/projects/${projectId}/brain` },
]

interface LocationState {
  sources?: SourceDocumentIn[]
}

type RunState =
  | { phase: 'loading' }
  | { phase: 'empty' } // no draft exists yet and nothing to generate
  | { phase: 'error'; message: string }
  | { phase: 'done'; draft: FsdDraftOut }

export default function FsdReview() {
  const { projectId, objectId } = useParams<{ projectId: string; objectId: string }>()
  const location = useLocation()
  const navigate = useNavigate()
  const { user } = useAuth()
  const navSources = (location.state as LocationState | null)?.sources

  const [meta, setMeta] = useState<{ project: Project; object: TrackedObject } | null>(null)
  const [metaError, setMetaError] = useState<string | null>(null)
  const [run, setRun] = useState<RunState>({ phase: 'loading' })
  const [versions, setVersions] = useState<FsdDraftSummary[]>([])
  const [approvalError, setApprovalError] = useState<string | null>(null)
  const [contextQueue, setContextQueue] = useState<Record<string, { title: string; text: string }>>({})

  const refreshVersions = useCallback(() => {
    if (!objectId) return
    listFsdDrafts(objectId).then(setVersions).catch(() => {})
  }, [objectId])

  const runGenerate = useCallback(
    async (sources: SourceDocumentIn[], note = '') => {
      if (!objectId) return
      setRun({ phase: 'loading' })
      try {
        const draft = await generateFsdDraft(objectId, sources, note)
        setRun({ phase: 'done', draft })
        refreshVersions()
      } catch (err) {
        setRun({ phase: 'error', message: err instanceof ApiError ? err.message : 'Agent run failed.' })
      }
    },
    [objectId, refreshVersions],
  )

  // load project/object metadata once
  useEffect(() => {
    if (!projectId || !objectId) return
    Promise.all([getProject(projectId), getObject(objectId)])
      .then(([project, object]) => setMeta({ project, object }))
      .catch((err) => setMetaError(err instanceof ApiError ? err.message : 'Could not load this object.'))
  }, [projectId, objectId])

  // Guards the generate-on-mount call below against firing twice. React's
  // StrictMode intentionally double-invokes effects in dev (mount, cleanup,
  // mount again) to surface missing-cleanup bugs -- without this, that
  // double-invoke fires two concurrent POSTs and creates two draft rows
  // that both land on "version 1" (caught via an actual test run).
  const generateFiredRef = useRef(false)

  // decide what to show: generate fresh (came from Intake) or load latest existing draft
  useEffect(() => {
    if (!objectId) return
    refreshVersions()
    if (navSources && navSources.length > 0) {
      if (generateFiredRef.current) return
      generateFiredRef.current = true
      // The browser's own History API keeps navigate()'s `state` attached
      // to this history entry -- it survives a hard reload, not just
      // React's in-memory router state. Left alone, refreshing this page
      // would silently replay "generate" and mint a new version every
      // time. Scrub it from the entry immediately so a reload instead
      // falls through to loading the latest saved draft below.
      navigate(location.pathname, { replace: true, state: null })
      runGenerate(navSources)
      return
    }
    getLatestFsdDraft(objectId)
      .then((draft) => setRun({ phase: 'done', draft }))
      .catch((err) => {
        if (err instanceof ApiError && err.status === 404) {
          setRun({ phase: 'empty' })
        } else {
          setRun({ phase: 'error', message: err instanceof ApiError ? err.message : 'Could not load this object.' })
        }
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [objectId])

  // Adding context to a flagged section doesn't patch that section alone --
  // the agent drafts the whole FSD holistically from one fact ledger, so
  // there's no per-section dependency graph to walk, which means there's
  // no reliable way to predict "only section Y will change" either. So
  // instead of regenerating on every single add, context added to any
  // number of flagged sections is queued here, and one regenerate call at
  // the end turns all of it into new source documents and redrafts the
  // whole FSD as one new version -- any other section grounded in the same
  // facts gets re-drafted too, not just the ones that were queued.
  const queueContext = useCallback((sectionKey: string, sectionTitle: string, text: string) => {
    setContextQueue((prev) => ({ ...prev, [sectionKey]: { title: sectionTitle, text } }))
  }, [])

  const removeQueuedContext = useCallback((sectionKey: string) => {
    setContextQueue((prev) => {
      const next = { ...prev }
      delete next[sectionKey]
      return next
    })
  }, [])

  const regenerateQueued = useCallback(() => {
    if (run.phase !== 'done') return
    const entries = Object.entries(contextQueue)
    if (entries.length === 0) return
    const newSources: SourceDocumentIn[] = entries.map(([sectionKey, { title, text }]) => ({
      source_id: `clarification_${sectionKey}_${Date.now()}`,
      label: `Added context — ${title}`,
      doc_type: 'Clarification',
      text,
    }))
    const note =
      entries.length === 1
        ? `Added context for "${entries[0][1].title}"`
        : `Added context for ${entries.length} sections (${entries.map(([, v]) => v.title).join(', ')})`
    setContextQueue({})
    runGenerate([...run.draft.sources, ...newSources], note)
  }, [run, runGenerate, contextQueue])

  async function viewVersion(draftId: string) {
    setRun({ phase: 'loading' })
    try {
      const draft = await getFsdDraft(draftId)
      setRun({ phase: 'done', draft })
    } catch (err) {
      setRun({ phase: 'error', message: err instanceof ApiError ? err.message : 'Could not load that version.' })
    }
  }

  async function handleApprovalToggle(draft: FsdDraftOut, role: 'module_lead' | 'solution_architect') {
    const currentlyApproved = role === 'module_lead' ? draft.approvals.module_lead_approved : draft.approvals.solution_architect_approved
    setApprovalError(null)
    try {
      const updated = await setApproval(draft.id, role, !currentlyApproved)
      setRun({ phase: 'done', draft: updated })
      if (meta) {
        const object = await getObject(meta.object.id)
        setMeta({ ...meta, object })
      }
    } catch (err) {
      setApprovalError(err instanceof ApiError ? err.message : 'Could not update approval.')
    }
  }

  if (metaError) {
    return (
      <AppShell>
        <div className="rounded-xl border border-red-border bg-red-soft px-5 py-4 text-sm text-red-text">{metaError}</div>
      </AppShell>
    )
  }
  if (!meta) {
    return (
      <AppShell>
        <div className="text-sm text-muted">Loading…</div>
      </AppShell>
    )
  }

  const { project, object } = meta

  return (
    <AppShell projectName={project.name} projectNav={PROJECT_NAV(project.id)} maxWidth="100%">
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

      <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="m-0 font-heading text-2xl font-extrabold">{object.name} — FSD</h1>
            <span className="rounded-full bg-slate-pill-bg px-2.5 py-1 text-xs font-bold text-slate-pill-text">
              {object.type}
            </span>
          </div>
          {run.phase === 'done' && (
            <div className="mt-2.5 flex items-center gap-2.5">
              <span className="rounded-md border border-input-border bg-white px-2.5 py-1.5 text-[13px]">
                Version {run.draft.version}
                {run.draft.version === versions[0]?.version ? ' (current)' : ''}
              </span>
              <span
                className={`rounded-full px-2.5 py-1 text-xs font-bold ${
                  object.fsd_status === 'Complete' ? 'bg-green-soft text-green' : 'bg-amber-soft text-amber'
                }`}
              >
                {object.fsd_status === 'Complete' ? 'Approved' : 'Draft · pending approval'}
              </span>
            </div>
          )}
        </div>
        <div className="flex gap-2.5">
          <Link
            to={`/projects/${project.id}/objects/${object.id}`}
            className="whitespace-nowrap rounded-lg border border-input-border bg-white px-4 py-2.5 text-[13px] font-semibold text-slate-pill-text no-underline"
          >
            ← Object Dashboard
          </Link>
          <Link
            to={`/projects/${project.id}/objects/${object.id}/fsd/intake`}
            className="whitespace-nowrap rounded-lg border border-input-border bg-white px-4 py-2.5 text-[13px] font-semibold text-slate-pill-text no-underline"
          >
            Edit inputs
          </Link>
          {run.phase === 'done' && (
            <button
              type="button"
              onClick={() => runGenerate(run.draft.sources, 'Regenerated')}
              className="whitespace-nowrap rounded-lg border border-input-border bg-white px-4 py-2.5 text-[13px] font-semibold text-slate-pill-text"
            >
              Regenerate
            </button>
          )}
        </div>
      </div>

      {run.phase === 'loading' && <LoadingCard />}
      {run.phase === 'error' && (
        <ErrorCard message={run.message} onRetry={() => navSources && runGenerate(navSources)} />
      )}
      {run.phase === 'empty' && (
        <div className="rounded-2xl border border-card-border bg-white p-8 text-center">
          <div className="font-heading text-lg font-bold">No FSD has been generated yet</div>
          <div className="mt-2 text-sm text-muted">Add inputs and generate the first draft for this object.</div>
          <Link
            to={`/projects/${project.id}/objects/${object.id}/fsd/intake`}
            className="mt-4 inline-block rounded-lg bg-accent px-5 py-2.5 text-sm font-semibold text-white no-underline"
          >
            Go to FSD Creation
          </Link>
        </div>
      )}

      {run.phase === 'done' && (
        <>
          <IntakeValidationCard draft={run.draft} onUpdated={(updated) => setRun({ phase: 'done', draft: updated })} />

          {Object.keys(contextQueue).length > 0 && (
            <div className="sticky top-3 z-10 mb-6 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-accent bg-accent-soft px-5 py-3.5">
              <div className="text-[13px] font-semibold text-accent">
                {Object.keys(contextQueue).length} section{Object.keys(contextQueue).length > 1 ? 's' : ''} queued for
                context — regenerating redrafts the whole FSD, so any other section grounded in the same facts gets
                updated too, not just these.
              </div>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setContextQueue({})}
                  className="whitespace-nowrap rounded-md border border-accent bg-white px-3.5 py-2 text-[12.5px] font-semibold text-accent"
                >
                  Clear queue
                </button>
                <button
                  type="button"
                  onClick={regenerateQueued}
                  className="whitespace-nowrap rounded-md bg-accent px-4 py-2 text-[12.5px] font-bold text-white"
                >
                  Regenerate {Object.keys(contextQueue).length === 1 ? 'this section' : 'all queued sections'}
                </button>
              </div>
            </div>
          )}

          <div className="flex flex-wrap items-start gap-6">
            <div className="flex min-w-0 flex-[2_1_580px] flex-col gap-5 rounded-2xl border border-card-border bg-white p-9">
              {run.draft.document_identification && <DocumentIdentificationBlock info={run.draft.document_identification} />}
              {run.draft.validation_table && <ValidationTableBlock rows={run.draft.validation_table} />}
              {run.draft.review_signoff && <ReviewSignoffBlock rows={run.draft.review_signoff} />}
              {run.draft.sections.map((s, i) => (
                <SectionBlock
                  key={s.key}
                  index={i + 1}
                  section={s}
                  queuedText={contextQueue[s.key]?.text ?? null}
                  onQueueContext={(text) => queueContext(s.key, s.title, text)}
                  onRemoveQueuedContext={() => removeQueuedContext(s.key)}
                />
              ))}
            </div>

            <div className="flex min-w-[280px] flex-[1_1_300px] flex-col gap-4.5">
              <CoverageCard draft={run.draft} />
              <ApprovalCard
                draft={run.draft}
                currentUserRole={user?.role ?? null}
                error={approvalError}
                onToggle={(role) => handleApprovalToggle(run.draft, role)}
              />
              <ExportCard draftId={run.draft.id} />
              <VersionHistoryCard versions={versions} activeVersion={run.draft.version} onSelect={viewVersion} />
              <LedgerCard draft={run.draft} />
              <div className="rounded-2xl border border-card-border bg-white p-4 text-[11px] text-faint">
                request_id {run.draft.request_id.slice(0, 8)} · {(run.draft.duration_ms / 1000).toFixed(1)}s
              </div>
            </div>
          </div>
        </>
      )}
    </AppShell>
  )
}

function LoadingCard() {
  return (
    <div className="flex flex-col items-center gap-3 rounded-2xl border border-card-border bg-white px-8 py-14 text-center">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-accent-soft border-t-accent" />
      <div className="font-heading text-base font-bold">Generating FSD…</div>
      <div className="max-w-md text-sm text-muted">
        The agent is extracting a grounded fact ledger from your inputs, then drafting each section against it. This
        is a real model call and typically takes 15–30 seconds.
      </div>
    </div>
  )
}

function ErrorCard({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-2xl border border-red-border bg-red-soft px-8 py-10 text-center">
      <div className="font-heading text-base font-bold text-red-text">Generation failed</div>
      <div className="max-w-md text-sm text-red-text">{message}</div>
      <button type="button" onClick={onRetry} className="mt-1 rounded-lg bg-white px-4 py-2 text-sm font-semibold text-red-text">
        Try again
      </button>
    </div>
  )
}

const VERDICT_LABEL: Record<string, string> = { ready: 'Ready', needs_correction: 'Needs Correction', not_ready: 'Not Ready' }

function verdictClasses(verdict: string) {
  if (verdict === 'ready') return { text: 'text-green', pill: 'bg-green-soft text-green' }
  if (verdict === 'not_ready') return { text: 'text-red', pill: 'bg-red-soft text-red-text' }
  return { text: 'text-amber', pill: 'bg-amber-soft text-amber' }
}

function checkStatusClasses(status: IntakeCheckStatus) {
  if (status === 'pass') return { border: 'border-green-border', bg: 'bg-green-soft', pill: 'bg-green text-white' }
  if (status === 'fail') return { border: 'border-red-border', bg: 'bg-red-soft', pill: 'bg-red text-white' }
  if (status === 'cannot_verify') return { border: 'border-input-border', bg: 'bg-app-bg/60', pill: 'bg-slate-pill-text text-white' }
  return { border: 'border-amber-border', bg: 'bg-amber-soft-2', pill: 'bg-amber-dark text-white' }
}

const CHECK_STATUS_LABEL: Record<IntakeCheckStatus, string> = {
  pass: 'Pass',
  warn: 'Warn',
  fail: 'Fail',
  cannot_verify: 'Cannot Verify',
}

function severityPillClasses(severity: IntakeSeverity) {
  if (severity === 'critical') return 'bg-red text-white'
  if (severity === 'high') return 'bg-red-soft text-red-text'
  if (severity === 'medium') return 'bg-amber-soft text-amber-text'
  return 'bg-slate-pill-bg text-slate-pill-text'
}

function radarBarColor(score: number) {
  if (score >= 75) return 'bg-green'
  if (score >= 50) return 'bg-amber-dark'
  return 'bg-red'
}

function IntakeValidationCard({ draft, onUpdated }: { draft: FsdDraftOut; onUpdated: (draft: FsdDraftOut) => void }) {
  const [groundingOpen, setGroundingOpen] = useState(false)
  const [checksOpen, setChecksOpen] = useState(false)
  const [correctionsOpen, setCorrectionsOpen] = useState(true)
  const [checklistOpen, setChecklistOpen] = useState(false)
  const [busy, setBusy] = useState<'rerun' | 'download' | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function handleRerun() {
    setError(null)
    setBusy('rerun')
    try {
      const updated = await rerunIntakeValidation(draft.id)
      onUpdated(updated)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not re-run Intake Validation.')
    } finally {
      setBusy(null)
    }
  }

  async function handleDownload() {
    setError(null)
    setBusy('download')
    try {
      await downloadIntakeValidationPdf(draft.id)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not download the PDF.')
    } finally {
      setBusy(null)
    }
  }

  const actions = (
    <div className="flex flex-wrap gap-2">
      <button
        type="button"
        onClick={handleRerun}
        disabled={busy !== null}
        className="whitespace-nowrap rounded-md border border-input-border bg-white px-3 py-1.5 text-[12px] font-semibold text-slate-pill-text disabled:opacity-50"
      >
        {busy === 'rerun' ? 'Running…' : draft.intake_validation_status === 'pending' ? 'Run Intake Validation' : 'Re-run assessment'}
      </button>
      {draft.intake_validation && (
        <button
          type="button"
          onClick={handleDownload}
          disabled={busy !== null}
          className="whitespace-nowrap rounded-md border border-input-border bg-white px-3 py-1.5 text-[12px] font-semibold text-slate-pill-text disabled:opacity-50"
        >
          {busy === 'download' ? 'Preparing…' : 'Download PDF'}
        </button>
      )}
    </div>
  )

  // "pending" only ever means "never assessed" here -- Intake Validation
  // runs synchronously as part of generate/regenerate and always resolves
  // to complete/failed by the time that request returns, so a draft only
  // shows pending on *first load* if it's a draft from before this feature
  // existed (its column is simply unset). Opening or viewing this page
  // never itself triggers an assessment -- that only happens on an
  // explicit "Run Intake Validation" click here, or on generate/regenerate.
  if (draft.intake_validation_status === 'pending') {
    return (
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-card-border bg-white p-[22px_30px]">
        <div className="text-[13px] text-muted">
          This draft hasn't been through Intake Validation yet (it was generated before this check existed, or it
          hasn't been run manually).
        </div>
        {actions}
      </div>
    )
  }

  if (draft.intake_validation_status === 'failed' || !draft.intake_validation) {
    return (
      <div className="mb-6 flex flex-col gap-3 rounded-2xl border border-red-border bg-red-soft p-[22px_30px]">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="font-heading text-[15px] font-bold text-red-text">Intake Validation failed</div>
            <div className="mt-1 text-[12.5px] text-red-text">
              {draft.intake_validation_error || 'The assessment could not be completed.'}
            </div>
          </div>
          {actions}
        </div>
        {error && <div className="text-[12px] text-red-text">{error}</div>}
      </div>
    )
  }

  const iv = draft.intake_validation
  const q = draft.quality_score
  const groundingIssueCount = q.red_items.length + q.yellow_items.length
  const verdict = verdictClasses(iv.verdict)
  const flaggedChecks = iv.quality_checks.filter((c) => c.status !== 'pass').length
  const checklistPass = iv.checklist.filter((c) => c.status === 'pass').length

  const byCategory = new Map<string, IntakeChecklistItem[]>()
  for (const item of iv.checklist) {
    const list = byCategory.get(item.category) ?? []
    list.push(item)
    byCategory.set(item.category, list)
  }

  return (
    <div className="mb-6 flex flex-col gap-5 rounded-2xl border border-card-border bg-white p-[26px_30px]">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="font-heading text-[17px] font-extrabold">Intake Validation</div>
          <div className="mt-0.5 text-[12.5px] text-muted">
            SAP delivery-readiness audit — structure, specificity, and testability, graded against a fixed
            checklist.
          </div>
        </div>
        <div className="flex flex-wrap items-start gap-4">
          <div className="text-right">
            <div className={`font-heading text-[26px] font-extrabold leading-none ${verdict.text}`}>
              {iv.overall_pct.toFixed(0)}%
            </div>
            <span className={`mt-1 inline-block whitespace-nowrap rounded-full px-2.5 py-1 text-[11px] font-bold ${verdict.pill}`}>
              {VERDICT_LABEL[iv.verdict] ?? iv.verdict}
            </span>
          </div>
          {actions}
        </div>
      </div>

      {error && <div className="rounded-md border border-red-border bg-red-soft px-3 py-2 text-[12px] text-red-text">{error}</div>}

      <div className="text-[13.5px] leading-relaxed text-[#333d4d]">{iv.assessment}</div>

      <div className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4">
        {Object.entries(iv.radar).map(([dim, score]) => (
          <div key={dim}>
            <div className="mb-1 flex items-center justify-between text-[11px] font-semibold text-muted">
              <span className="capitalize">{dim.replace(/_/g, ' ')}</span>
              <span>{score}</span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-app-bg">
              <div className={`h-full rounded-full ${radarBarColor(score)}`} style={{ width: `${score}%` }} />
            </div>
          </div>
        ))}
      </div>

      {groundingIssueCount > 0 && (
        <div className="border-t border-divider pt-4">
          <button
            type="button"
            onClick={() => setGroundingOpen((v) => !v)}
            className="flex w-full items-center justify-between bg-transparent p-0 text-left"
          >
            <div className="font-heading text-[14px] font-bold">
              Grounding Issues <span className="font-normal text-muted">({groundingIssueCount})</span>
            </div>
            <span className="text-[12px] font-semibold text-accent">{groundingOpen ? 'Hide' : 'Show'}</span>
          </button>
          {groundingOpen && (
            <div className="mt-3 flex flex-col gap-2">
              <div className="text-[11.5px] text-faint">
                Content the draft couldn't trace back to your source inputs — mechanically checked, separate from
                the SAP-readiness checks below.
              </div>
              {q.red_items.map((item) => (
                <div
                  key={item}
                  className="flex items-start gap-2.5 rounded-lg border border-red-border bg-red-soft px-3.5 py-2.5 text-[12.5px]"
                >
                  <span className="mt-0.5 shrink-0 rounded-full bg-red px-2 py-0.5 text-[10px] font-bold text-white">
                    MUST FIX
                  </span>
                  <span className="text-red-text">{item}</span>
                </div>
              ))}
              {q.yellow_items.map((item) => (
                <div
                  key={item}
                  className="flex items-start gap-2.5 rounded-lg border border-amber-border bg-amber-soft-2 px-3.5 py-2.5 text-[12.5px]"
                >
                  <span className="mt-0.5 shrink-0 rounded-full bg-amber-dark px-2 py-0.5 text-[10px] font-bold text-white">
                    SHOULD FIX
                  </span>
                  <span className="text-amber-text">{item}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="border-t border-divider pt-4">
        <button
          type="button"
          onClick={() => setChecksOpen((v) => !v)}
          className="flex w-full items-center justify-between bg-transparent p-0 text-left"
        >
          <div className="font-heading text-[14px] font-bold">
            Quality Checks{' '}
            <span className="font-normal text-muted">
              ({flaggedChecks} flagged of {iv.quality_checks.length})
            </span>
          </div>
          <span className="text-[12px] font-semibold text-accent">{checksOpen ? 'Hide' : 'Show'}</span>
        </button>
        {checksOpen && (
          <div className="mt-3 flex flex-col gap-2">
            {iv.quality_checks.map((qc) => {
              const sc = checkStatusClasses(qc.status)
              return (
                <div key={qc.key} className={`rounded-lg border ${sc.border} ${sc.bg} px-3.5 py-2.5 text-[12.5px]`}>
                  <div className="flex items-center justify-between gap-2">
                    <div className="font-semibold">{qc.title}</div>
                    <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10.5px] font-bold ${sc.pill}`}>
                      {CHECK_STATUS_LABEL[qc.status]}
                    </span>
                  </div>
                  <div className="mt-1 text-[#333d4d]">{qc.finding}</div>
                  {qc.suggestion && <div className="mt-1 text-faint">→ {qc.suggestion}</div>}
                </div>
              )
            })}
          </div>
        )}
      </div>

      {iv.corrections.length > 0 && (
        <div className="border-t border-divider pt-4">
          <button
            type="button"
            onClick={() => setCorrectionsOpen((v) => !v)}
            className="flex w-full items-center justify-between bg-transparent p-0 text-left"
          >
            <div className="font-heading text-[14px] font-bold">
              Corrections Required <span className="font-normal text-muted">({iv.corrections.length})</span>
            </div>
            <span className="text-[12px] font-semibold text-accent">{correctionsOpen ? 'Hide' : 'Show'}</span>
          </button>
          {correctionsOpen && (
            <ul className="m-0 mt-3 flex list-none flex-col gap-2 p-0">
              {iv.corrections.map((c, i) => (
                <li
                  key={i}
                  className="flex items-start gap-2.5 rounded-lg border border-input-border bg-app-bg/50 px-3.5 py-2.5 text-[12.5px]"
                >
                  <span className={`mt-0.5 shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold ${severityPillClasses(c.severity)}`}>
                    {c.severity.toUpperCase()}
                  </span>
                  <span className="text-[#333d4d]">{c.text}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="border-t border-divider pt-4">
        <button
          type="button"
          onClick={() => setChecklistOpen((v) => !v)}
          className="flex w-full items-center justify-between bg-transparent p-0 text-left"
        >
          <div className="font-heading text-[14px] font-bold">
            Intake Checklist{' '}
            <span className="font-normal text-muted">
              ({checklistPass}/{iv.checklist.length} pass)
            </span>
          </div>
          <span className="text-[12px] font-semibold text-accent">{checklistOpen ? 'Hide' : 'Show'}</span>
        </button>
        {checklistOpen && (
          <div className="mt-3 flex flex-col gap-4">
            {Array.from(byCategory.entries()).map(([category, items]) => (
              <div key={category}>
                <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-faint">{category}</div>
                <div className="overflow-hidden rounded-lg border border-card-border">
                  {items.map((item) => {
                    const sc = checkStatusClasses(item.status)
                    return (
                      <div
                        key={item.item_id}
                        className="flex items-start gap-3 border-b border-divider px-3.5 py-2.5 text-[12px] last:border-0"
                      >
                        <span className={`mt-0.5 shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold ${sc.pill}`}>
                          {CHECK_STATUS_LABEL[item.status]}
                        </span>
                        <div>
                          <div className="font-semibold text-[#333d4d]">{item.check}</div>
                          <div className="mt-0.5 text-muted">{item.finding}</div>
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="border-t border-divider pt-2.5 text-[11.5px] text-faint">
        Checklist items marked "Cannot Verify" would require a live SAP system connection this tool doesn't have —
        they describe what's named in the document, not whether it exists in any real system.
      </div>
    </div>
  )
}

function DocumentIdentificationBlock({ info }: { info: DocumentIdentification }) {
  const rows: [string, string][] = [
    ['Object ID', info.object_id],
    ['Type', info.object_type],
    ['Module', info.module],
    ['Project', info.project],
    ['Version', info.version],
    ['Status', info.status],
    ['Generated', info.generated_on],
    ['Author', info.author],
    ['SAP Release', info.sap_release],
    ['Transport Path', info.transport_path],
  ]
  return (
    <div className="rounded-xl border border-card-border bg-app-bg/50 p-4.5">
      <div className="mb-2.5 font-heading text-[15px] font-extrabold">Document Identification</div>
      <div className="grid grid-cols-2 gap-x-6 gap-y-1.5 sm:grid-cols-3">
        {rows.map(([label, value]) => (
          <div key={label} className="text-[12.5px]">
            <div className="text-faint">{label}</div>
            <div className="font-semibold text-ink">{value}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

function ValidationTableBlock({ rows }: { rows: ValidationRow[] }) {
  return (
    <div className="rounded-xl border border-card-border bg-white">
      <div className="border-b border-card-border p-4.5 pb-2.5 font-heading text-[15px] font-extrabold">
        Validation
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[560px] border-collapse text-[12.5px]">
          <thead>
            <tr className="border-b border-divider text-left text-[11px] font-semibold uppercase tracking-wide text-muted">
              <th className="px-4.5 py-2">Validation Point</th>
              <th className="px-4.5 py-2">How It's Satisfied</th>
              <th className="px-4.5 py-2">Section</th>
              <th className="px-4.5 py-2">Pass/Fail</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.point} className="border-b border-divider last:border-0">
                <td className="px-4.5 py-2.5 font-semibold">{row.point}</td>
                <td className="px-4.5 py-2.5 text-muted">{row.how_satisfied}</td>
                <td className="px-4.5 py-2.5 text-muted">{row.section}</td>
                <td className="px-4.5 py-2.5">
                  <span
                    className={`rounded-full px-2.5 py-0.5 text-[11px] font-bold ${
                      row.pass ? 'bg-green-soft text-green' : 'bg-red-soft text-red-text'
                    }`}
                  >
                    {row.pass ? 'Pass' : 'Fail'}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function ReviewSignoffBlock({ rows }: { rows: ReviewSignoffRow[] }) {
  return (
    <div className="rounded-xl border border-card-border bg-white p-4.5">
      <div className="mb-2.5 font-heading text-[15px] font-extrabold">Review and Sign-off</div>
      <div className="flex flex-col gap-2">
        {rows.map((row) => (
          <div
            key={row.role}
            className={`flex items-center justify-between rounded-lg border px-3.5 py-2.5 text-[12.5px] ${
              row.status === 'Signed off' ? 'border-green-border bg-green-soft' : 'border-input-border bg-app-bg/50'
            }`}
          >
            <div>
              <div className="font-semibold">{row.role}</div>
              <div className="text-faint">{row.name}</div>
            </div>
            <div className="text-right">
              <div className={`font-semibold ${row.status === 'Signed off' ? 'text-green' : 'text-muted'}`}>
                {row.status}
              </div>
              <div className="text-faint">{row.date}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function SectionImages({ images }: { images: Record<string, string> }) {
  return (
    <>
      {Object.entries(images ?? {}).map(([label, b64]) => (
        <figure key={label} className="mt-3 rounded-lg border border-card-border bg-app-bg/60 p-3">
          <img src={`data:image/png;base64,${b64}`} alt={label} className="mx-auto block max-w-full rounded-md" />
          <figcaption className="mt-2 text-center text-[11.5px] font-semibold text-muted">{label}</figcaption>
        </figure>
      ))}
    </>
  )
}

// The three structured tables a section can carry (see FieldMappingRow /
// ErrorHandlingRow / TestScriptRow in lib/types.ts) -- rendered as a real
// table rather than left as prose, matching what the exported document
// shows. Keyed by section key so SectionBlock can look up the right shape.
const SECTION_TABLE_CONFIG: Record<
  string,
  { field: 'field_mapping' | 'error_rows' | 'test_rows'; heading: string; columns: [string, string][] }
> = {
  functional_design_logic: {
    field: 'field_mapping',
    heading: 'Field Mapping',
    columns: [
      ['field', 'Field'],
      ['source', 'Source'],
      ['target', 'Target'],
      ['rule_type', 'Rule Type'],
      ['rule_detail', 'Rule Detail'],
    ],
  },
  error_handling: {
    field: 'error_rows',
    heading: 'Error Handling Table',
    columns: [
      ['failure_point', 'Failure Point'],
      ['detection', 'Detection'],
      ['handling_rule', 'Handling Rule'],
      ['user_notification', 'User Notification'],
      ['remediation', 'Remediation'],
    ],
  },
  test_scenarios: {
    field: 'test_rows',
    heading: 'Test Script',
    columns: [
      ['test_id', 'Test ID'],
      ['scenario', 'Scenario'],
      ['steps', 'Steps'],
      ['expected_result', 'Expected Result'],
    ],
  },
}

function SectionTable({ section }: { section: FSDSection }) {
  const config = SECTION_TABLE_CONFIG[section.key]
  if (!config) return null
  const rows = (section[config.field] ?? []) as unknown as Record<string, string>[]
  if (rows.length === 0) return null
  return (
    <div className="mt-3 overflow-x-auto rounded-lg border border-card-border bg-white">
      <div className="border-b border-card-border px-3.5 py-2 text-[12.5px] font-semibold text-ink">
        {config.heading}
      </div>
      <table className="w-full min-w-[560px] border-collapse text-[12px]">
        <thead>
          <tr className="border-b border-divider text-left text-[10.5px] font-semibold uppercase tracking-wide text-muted">
            {config.columns.map(([key, label]) => (
              <th key={key} className="px-3.5 py-1.5">
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-b border-divider last:border-0 align-top">
              {config.columns.map(([key]) => (
                <td key={key} className="px-3.5 py-2 text-[#333d4d]">
                  {row[key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SectionBlock({
  index,
  section,
  queuedText,
  onQueueContext,
  onRemoveQueuedContext,
}: {
  index: number
  section: FSDSection
  queuedText: string | null
  onQueueContext: (text: string) => void
  onRemoveQueuedContext: () => void
}) {
  const [open, setOpen] = useState(false)
  const [text, setText] = useState(queuedText ?? '')

  if (section.status === 'grounded') {
    return (
      <div>
        <div className="mb-1.5 font-heading text-[15px] font-extrabold">
          {index}. {section.title}
        </div>
        <div className="text-[13.5px] leading-relaxed text-[#333d4d]">{section.content}</div>
        <SectionTable section={section} />
        <SectionImages images={section.images} />
      </div>
    )
  }

  if (section.status === 'ai_inferred') {
    return (
      <div className="rounded-r-lg border-l-[3px] border-l-accent bg-accent-soft/60 px-4.5 py-3.5">
        <div className="mb-1.5 flex items-center justify-between">
          <div className="font-heading text-[15px] font-extrabold">
            {index}. {section.title}
          </div>
          <span className="whitespace-nowrap rounded-full bg-accent-soft px-2.5 py-0.5 text-[11px] font-bold text-accent">
            AI-inferred — not grounded
          </span>
        </div>
        <div className="text-[13.5px] leading-relaxed text-[#333d4d]">{section.content}</div>
        <SectionTable section={section} />
        <SectionImages images={section.images} />
        <div className="mt-2.5 rounded-md bg-white/70 px-3 py-2 text-[12px] text-accent">
          Based on general SAP knowledge, not your project's own documents — {section.ai_inferred_note || 'confirm or correct this before relying on it.'}
        </div>
        <QueuedContextControl
          section={section}
          queuedText={queuedText}
          open={open}
          setOpen={setOpen}
          text={text}
          setText={setText}
          onQueueContext={onQueueContext}
          onRemoveQueuedContext={onRemoveQueuedContext}
          toneClass="border-accent bg-white text-accent"
          placeholder="Confirm this is correct, or supply the real project-specific detail..."
        />
      </div>
    )
  }

  const isConflict = section.status === 'conflict'
  const tone = isConflict
    ? { border: 'border-l-red', bg: 'bg-red-soft', badgeBg: 'bg-red-soft', badgeText: 'text-red-text', text: 'text-red-text' }
    : { border: 'border-l-amber-dark', bg: 'bg-amber-soft-2', badgeBg: 'bg-amber-soft', badgeText: 'text-amber', text: 'text-amber-text' }

  return (
    <div className={`rounded-r-lg border-l-[3px] ${tone.border} ${tone.bg} px-4.5 py-3.5`}>
      <div className="mb-1.5 flex items-center justify-between">
        <div className="font-heading text-[15px] font-extrabold">
          {index}. {section.title}
        </div>
        <span className={`whitespace-nowrap rounded-full px-2.5 py-0.5 text-[11px] font-bold ${tone.badgeBg} ${tone.badgeText}`}>
          {isConflict ? 'Conflict flagged' : 'Needs Input'}
        </span>
      </div>
      <div className={`text-[13.5px] leading-relaxed ${tone.text}`}>
        {isConflict ? section.conflict_detail : section.needs_input_detail}
      </div>

      <QueuedContextControl
        section={section}
        queuedText={queuedText}
        open={open}
        setOpen={setOpen}
        text={text}
        setText={setText}
        onQueueContext={onQueueContext}
        onRemoveQueuedContext={onRemoveQueuedContext}
        toneClass={isConflict ? 'border-red-border bg-white text-red-text' : 'border-amber-border bg-white text-amber-text'}
        placeholder={
          isConflict
            ? 'Resolve the conflict — which input is correct, or what should override it?'
            : 'Add the missing detail this section needs...'
        }
      />
    </div>
  )
}

// Shared by the needs_input/conflict/ai_inferred branches: queues context
// for this one section (doesn't regenerate by itself — the sticky bar
// above the section list regenerates everything queued across the whole
// document in one call, see FsdReview's regenerateQueued).
function QueuedContextControl({
  queuedText,
  open,
  setOpen,
  text,
  setText,
  onQueueContext,
  onRemoveQueuedContext,
  toneClass,
  placeholder,
}: {
  section: FSDSection
  queuedText: string | null
  open: boolean
  setOpen: (v: boolean) => void
  text: string
  setText: (v: string) => void
  onQueueContext: (text: string) => void
  onRemoveQueuedContext: () => void
  toneClass: string
  placeholder: string
}) {
  function submit() {
    const trimmed = text.trim()
    if (!trimmed) return
    onQueueContext(trimmed)
    setOpen(false)
  }

  if (queuedText && !open) {
    return (
      <div className="mt-2.5 flex items-center gap-2">
        <span className="rounded-full bg-white px-2.5 py-1 text-[11px] font-bold text-accent">✓ Context queued</span>
        <button type="button" onClick={() => setOpen(true)} className="text-[12px] font-semibold text-slate-pill-text underline">
          Edit
        </button>
        <button type="button" onClick={onRemoveQueuedContext} className="text-[12px] font-semibold text-red-text underline">
          Remove
        </button>
      </div>
    )
  }

  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)} className={`mt-2.5 rounded-md border px-3 py-1.5 text-[12px] font-bold ${toneClass}`}>
        + Add context
      </button>
    )
  }

  return (
    <div className="mt-3 flex flex-col gap-2 border-t border-dashed border-divider pt-3">
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        autoFocus
        placeholder={placeholder}
        className="min-h-[80px] w-full resize-y rounded-lg border border-input-border bg-white p-2.5 text-[13px]"
      />
      <div className="text-[11.5px] text-faint">
        Queued, not regenerated yet — add context to as many sections as you like, then use "Regenerate" in the bar
        above to redraft the whole FSD once, against all of it together.
      </div>
      <div className="flex gap-2">
        <button
          type="button"
          onClick={submit}
          disabled={!text.trim()}
          className="rounded-md bg-accent px-3.5 py-1.5 text-[12.5px] font-bold text-white disabled:cursor-not-allowed disabled:opacity-40"
        >
          {queuedText ? 'Update queued context' : 'Queue this context'}
        </button>
        <button
          type="button"
          onClick={() => {
            setOpen(false)
            setText(queuedText ?? '')
          }}
          className="rounded-md border border-input-border bg-white px-3.5 py-1.5 text-[12.5px] font-semibold text-slate-pill-text"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}

function CoverageCard({ draft }: { draft: FsdDraftOut }) {
  const total = draft.sections.length
  const grounded = draft.sections.filter((s) => s.status === 'grounded').length
  const flagged = draft.sections.filter((s) => s.status !== 'grounded')
  const pct = total > 0 ? Math.round((grounded / total) * 100) : 0

  return (
    <div className="flex flex-col gap-3 rounded-2xl border border-card-border bg-white p-5">
      <div className="font-heading text-[15px] font-bold">Coverage</div>
      <div className="flex items-center gap-2.5">
        <div className="h-2 flex-1 overflow-hidden rounded-full bg-divider">
          <div className="h-full bg-green" style={{ width: `${pct}%` }} />
        </div>
        <div className="whitespace-nowrap text-[13px] font-bold">
          {grounded} / {total}
        </div>
      </div>
      <div className="text-[12.5px] text-muted">
        sections fully grounded.{flagged.length > 0 ? ` ${flagged.length} flagged below.` : ''}
      </div>
      {flagged.length > 0 && (
        <div className="mt-1 flex flex-col gap-1.5 text-[12.5px]">
          {flagged.map((s) => (
            <div key={s.key} className="flex items-start gap-1.5">
              <span
                className={
                  s.status === 'conflict' ? 'text-red-text' : s.status === 'ai_inferred' ? 'text-accent' : 'text-amber'
                }
              >
                ●
              </span>
              {s.title} —{' '}
              {s.status === 'conflict' ? 'conflicting inputs' : s.status === 'ai_inferred' ? 'AI-inferred, not grounded' : 'no input provided'}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function ApprovalCard({
  draft,
  currentUserRole,
  error,
  onToggle,
}: {
  draft: FsdDraftOut
  currentUserRole: string | null
  error: string | null
  onToggle: (role: 'module_lead' | 'solution_architect') => void
}) {
  const { approvals, quality_score } = draft
  const requiresDual = quality_score.requires_dual_approval
  const approvalsCount = (approvals.module_lead_approved ? 1 : 0) + (approvals.solution_architect_approved ? 1 : 0)
  const needed = requiresDual ? 2 : 1
  const satisfied = approvalsCount >= needed
  const isAdmin = currentUserRole === 'admin'

  return (
    <div className="flex flex-col gap-2.5 rounded-2xl border border-card-border bg-white p-5">
      <div className="font-heading text-[15px] font-bold">Approval</div>
      <div className="-mt-0.5 text-[12.5px] text-muted">
        {requiresDual
          ? `${quality_score.green_pct.toFixed(0)}% grounded in the source inputs, below the 80% threshold — two approvers are required.`
          : `${quality_score.green_pct.toFixed(0)}% grounded in the source inputs, meeting the single-approver threshold.`}
      </div>

      {error && <div className="rounded-md border border-red-border bg-red-soft px-2.5 py-2 text-[12px] text-red-text">{error}</div>}

      <ApproverRow
        testId="approve-module-lead"
        label="Module Lead"
        approvedBy={approvals.module_lead_approved_by}
        approvedAt={approvals.module_lead_approved_at}
        approved={approvals.module_lead_approved}
        canAct={isAdmin || currentUserRole === 'module_lead'}
        onToggle={() => onToggle('module_lead')}
      />
      <ApproverRow
        testId="approve-solution-architect"
        label="Solution Architect"
        approvedBy={approvals.solution_architect_approved_by}
        approvedAt={approvals.solution_architect_approved_at}
        approved={approvals.solution_architect_approved}
        canAct={isAdmin || currentUserRole === 'solution_architect'}
        onToggle={() => onToggle('solution_architect')}
      />

      <div className="text-center text-xs text-muted">
        {approvalsCount} of {needed} approval{needed > 1 ? 's' : ''}
      </div>

      <div
        className={`rounded-lg py-2.5 text-center text-[13.5px] font-bold text-white ${
          satisfied ? 'bg-green' : 'bg-[#c6ccda]'
        }`}
      >
        {satisfied ? 'Version approved ✓' : 'Approve this version'}
      </div>
    </div>
  )
}

function ApproverRow({
  testId,
  label,
  approvedBy,
  approvedAt,
  approved,
  canAct,
  onToggle,
}: {
  testId: string
  label: string
  approvedBy: string | null
  approvedAt: string | null
  approved: boolean
  canAct: boolean
  onToggle: () => void
}) {
  const subtitle = approved
    ? `${approvedBy ?? 'Someone'} · ${approvedAt ? new Date(approvedAt).toLocaleString() : ''}`
    : canAct
      ? 'Awaiting your approval'
      : 'Awaiting approval'

  return (
    <div
      className={`flex items-center justify-between gap-2.5 rounded-lg border px-3 py-2.5 ${
        approved ? 'border-green-border bg-green-soft' : 'border-input-border bg-white'
      }`}
    >
      <div>
        <div className={`text-[13px] font-semibold ${approved ? 'text-green' : 'text-slate-pill-text'}`}>{label}</div>
        <div className="text-[11.5px] text-muted">{subtitle}</div>
      </div>
      <button
        type="button"
        data-testid={testId}
        onClick={onToggle}
        disabled={!canAct}
        title={!canAct ? `Only ${label} (or admin) can set this approval` : undefined}
        className={`whitespace-nowrap rounded-md border px-3.5 py-2 text-[12.5px] font-bold disabled:cursor-not-allowed disabled:opacity-50 ${
          approved ? 'border-green-border bg-green-soft text-green' : 'border-input-border bg-white text-slate-pill-text'
        }`}
      >
        {approved ? 'Approved ✓' : 'Approve'}
      </button>
    </div>
  )
}

const EXPORT_FORMATS: { format: ExportFormat; label: string }[] = [
  { format: 'markdown', label: 'Markdown (.md)' },
  { format: 'docx', label: 'Word (.docx)' },
  { format: 'pdf', label: 'PDF' },
]

function ExportCard({ draftId }: { draftId: string }) {
  const [downloading, setDownloading] = useState<ExportFormat | null>(null)
  const [pushing, setPushing] = useState<'github' | 'google-drive' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pushResult, setPushResult] = useState<{ target: string; url: string } | null>(null)

  async function handleDownload(format: ExportFormat) {
    setError(null)
    setDownloading(format)
    try {
      await downloadFsdExport(draftId, format)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : `Could not download as ${format}.`)
    } finally {
      setDownloading(null)
    }
  }

  async function handlePush(target: 'github' | 'google-drive') {
    setError(null)
    setPushResult(null)
    setPushing(target)
    try {
      const result = target === 'github' ? await pushFsdToGithub(draftId) : await pushFsdToGoogleDrive(draftId)
      setPushResult({ target: target === 'github' ? 'GitHub' : 'Google Drive', url: result.url })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : `Could not push to ${target}.`)
    } finally {
      setPushing(null)
    }
  }

  return (
    <div className="flex flex-col gap-2.5 rounded-2xl border border-card-border bg-white p-5">
      <div className="font-heading text-[15px] font-bold">Export</div>

      <div className="flex flex-col gap-1.5">
        <div className="text-[11.5px] font-semibold uppercase tracking-wide text-faint">Download</div>
        <div className="flex flex-wrap gap-1.5">
          {EXPORT_FORMATS.map(({ format, label }) => (
            <button
              key={format}
              type="button"
              onClick={() => handleDownload(format)}
              disabled={downloading !== null}
              className="rounded-md border border-input-border bg-white px-3 py-1.5 text-[12.5px] font-semibold text-slate-pill-text disabled:cursor-not-allowed disabled:opacity-50"
            >
              {downloading === format ? 'Downloading…' : label}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-1.5 flex flex-col gap-1.5">
        <div className="text-[11.5px] font-semibold uppercase tracking-wide text-faint">Push to</div>
        <div className="flex flex-wrap gap-1.5">
          <button
            type="button"
            onClick={() => handlePush('github')}
            disabled={pushing !== null}
            className="rounded-md border border-input-border bg-white px-3 py-1.5 text-[12.5px] font-semibold text-slate-pill-text disabled:cursor-not-allowed disabled:opacity-50"
          >
            {pushing === 'github' ? 'Pushing…' : 'GitHub'}
          </button>
          <button
            type="button"
            onClick={() => handlePush('google-drive')}
            disabled={pushing !== null}
            className="rounded-md border border-input-border bg-white px-3 py-1.5 text-[12.5px] font-semibold text-slate-pill-text disabled:cursor-not-allowed disabled:opacity-50"
          >
            {pushing === 'google-drive' ? 'Pushing…' : 'Google Drive'}
          </button>
        </div>
      </div>

      {pushResult && (
        <div className="rounded-md border border-green-border bg-green-soft px-2.5 py-2 text-[12px] text-green">
          Pushed to {pushResult.target} —{' '}
          <a href={pushResult.url} target="_blank" rel="noreferrer" className="font-semibold underline">
            open it
          </a>
        </div>
      )}
      {error && <div className="rounded-md border border-red-border bg-red-soft px-2.5 py-2 text-[12px] text-red-text">{error}</div>}
    </div>
  )
}

function VersionHistoryCard({
  versions,
  activeVersion,
  onSelect,
}: {
  versions: FsdDraftSummary[]
  activeVersion: number
  onSelect: (draftId: string) => void
}) {
  return (
    <div className="flex flex-col gap-2.5 rounded-2xl border border-card-border bg-white p-5">
      <div className="font-heading text-[15px] font-bold">Version History</div>
      {versions.map((v) => (
        <button
          key={v.id}
          type="button"
          onClick={() => onSelect(v.id)}
          className="flex items-start gap-2.5 bg-transparent p-0 text-left"
        >
          <span
            className={`mt-[5px] h-2 w-2 shrink-0 rounded-full ${v.version === activeVersion ? 'bg-accent' : 'bg-input-border'}`}
          />
          <div>
            <div className={`text-[13px] font-semibold ${v.version === activeVersion ? '' : 'text-muted'}`}>
              Version {v.version}
              {v.version === versions[0]?.version ? ' — current' : ''}
            </div>
            <div className="text-xs text-faint">
              {v.note || 'Generated'} · {v.overall_pct.toFixed(0)}% · {new Date(v.created_at).toLocaleString()}
            </div>
          </div>
        </button>
      ))}
    </div>
  )
}

function LedgerCard({ draft }: { draft: FsdDraftOut }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="flex flex-col gap-2.5 rounded-2xl border border-card-border bg-white p-5">
      <button type="button" onClick={() => setOpen((v) => !v)} className="flex items-center justify-between gap-2 bg-transparent p-0 text-left">
        <div className="font-heading text-[15px] font-bold">Extraction Ledger</div>
        <span className="text-xs font-semibold text-accent">{open ? 'Hide' : 'Show'} ({draft.ledger.length})</span>
      </button>
      <div className="text-[12px] text-muted">
        Every atomic fact the agent pulled from your inputs, each cited back to its source — this is what every
        section above is grounded in (or not).
      </div>
      {open && (
        <div className="flex max-h-80 flex-col gap-2.5 overflow-y-auto border-t border-divider pt-2.5">
          {draft.ledger.map((entry) => (
            <div key={entry.entry_id} className="text-[12px]">
              <div className="font-semibold text-ink">{entry.fact}</div>
              <div className="mt-0.5 text-faint">
                [{entry.source_id}
                {entry.topic_hint ? ` · ${entry.topic_hint}` : ''}] “{entry.source_quote}”
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
