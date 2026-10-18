import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import AppShell from '../components/AppShell'
import { useAuth } from '../context/AuthContext'
import {
  ApiError,
  downloadFsdExport,
  generateFsdDraft,
  getFsdDraft,
  getLatestFsdDraft,
  getObject,
  getProject,
  listFsdDrafts,
  pushFsdToGithub,
  pushFsdToGoogleDrive,
  setApproval,
} from '../lib/api'
import type { ExportFormat } from '../lib/api'
import type {
  DocumentIdentification,
  FsdDraftOut,
  FsdDraftSummary,
  FSDSection,
  Project,
  ReviewSignoffRow,
  SourceDocumentIn,
  TrackedObject,
  ValidationRow,
} from '../lib/types'

const PROJECT_NAV = (projectId: string) => [
  { label: 'Overview', to: `/projects/${projectId}/overview` },
  { label: 'Objects', to: `/projects/${projectId}` },
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
  const [yellowOpen, setYellowOpen] = useState(false)
  const [redOpen, setRedOpen] = useState(false)
  const [approvalError, setApprovalError] = useState<string | null>(null)

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
  // there's no per-section dependency graph to walk. Instead, the typed
  // context becomes a new source document and the full draft is
  // regenerated against the enriched ledger as a new version. That's what
  // correctly "cascades": any other section whose grounding touches the
  // same fact gets re-drafted too, not just the one the user clicked.
  const regenerateWithContext = useCallback(
    (sectionKey: string, sectionTitle: string, contextText: string) => {
      if (run.phase !== 'done') return
      const newSource: SourceDocumentIn = {
        source_id: `clarification_${sectionKey}_${Date.now()}`,
        label: `Added context — ${sectionTitle}`,
        doc_type: 'Clarification',
        text: contextText,
      }
      runGenerate([...run.draft.sources, newSource], `Added context for "${sectionTitle}"`)
    },
    [run, runGenerate],
  )

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
            to={`/projects/${project.id}/objects/${object.id}/fsd/intake`}
            className="whitespace-nowrap rounded-lg border border-input-border bg-white px-4 py-2.5 text-[13px] font-semibold text-slate-pill-text no-underline"
          >
            ← Edit inputs
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
          <QualityScoreCard
            draft={run.draft}
            yellowOpen={yellowOpen}
            redOpen={redOpen}
            onToggleYellow={() => setYellowOpen((v) => !v)}
            onToggleRed={() => setRedOpen((v) => !v)}
          />

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
                  onAddContext={(text) => regenerateWithContext(s.key, s.title, text)}
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

function tierLabel(tier: string) {
  if (tier === 'pass') return 'Pass'
  if (tier === 'pass_with_condition') return 'Pass with condition'
  return 'Below threshold'
}

function QualityScoreCard({
  draft,
  yellowOpen,
  redOpen,
  onToggleYellow,
  onToggleRed,
}: {
  draft: FsdDraftOut
  yellowOpen: boolean
  redOpen: boolean
  onToggleYellow: () => void
  onToggleRed: () => void
}) {
  const q = draft.quality_score
  const scoreColor = q.tier === 'pass' ? 'text-green' : q.tier === 'pass_with_condition' ? 'text-amber' : 'text-red'
  return (
    <div className="mb-6 flex flex-col gap-4 rounded-2xl border border-card-border bg-white p-[26px_30px]">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="font-heading text-[17px] font-extrabold">FSD Intake Quality Score</div>
          <div className="mt-0.5 text-[12.5px] text-muted">
            How fully this draft is grounded in the provided inputs, plus review-readiness checks.
          </div>
        </div>
        <div className="text-right">
          <div className={`font-heading text-[26px] font-extrabold leading-none ${scoreColor}`}>
            {q.overall_pct.toFixed(0)}%
          </div>
          <span
            className={`mt-1 inline-block whitespace-nowrap rounded-full px-2.5 py-1 text-[11px] font-bold ${
              q.tier === 'pass'
                ? 'bg-green-soft text-green'
                : q.tier === 'pass_with_condition'
                  ? 'bg-amber-soft text-amber'
                  : 'bg-red-soft text-red-text'
            }`}
          >
            {tierLabel(q.tier)}
          </span>
        </div>
      </div>

      <div
        role="img"
        aria-label={`Quality breakdown: ${q.green_pct}% green, ${q.yellow_pct}% yellow, ${q.red_pct}% red`}
        className="flex h-3.5 w-full overflow-hidden rounded-full"
      >
        <div className="h-full bg-green" style={{ width: `${q.green_pct}%` }} />
        <div className="h-full bg-amber-dark" style={{ width: `${q.yellow_pct}%` }} />
        <div className="h-full bg-red" style={{ width: `${q.red_pct}%` }} />
      </div>

      <div className="flex flex-wrap items-center gap-4.5 text-[12.5px]">
        <span className="flex items-center gap-1.5 font-semibold text-green">
          <span className="h-[9px] w-[9px] rounded-full bg-green" /> {q.green_pct.toFixed(0)}% grounded
        </span>
        {q.yellow_items.length > 0 && (
          <button
            type="button"
            onClick={onToggleYellow}
            className="flex items-center gap-1.5 bg-transparent p-0 text-[12.5px] font-semibold text-amber-text underline"
          >
            <span className="h-[9px] w-[9px] rounded-full bg-amber-dark" /> {q.yellow_pct.toFixed(0)}% should fix —
            click to view
          </button>
        )}
        {q.red_items.length > 0 && (
          <button
            type="button"
            onClick={onToggleRed}
            className="flex items-center gap-1.5 bg-transparent p-0 text-[12.5px] font-semibold text-red-text underline"
          >
            <span className="h-[9px] w-[9px] rounded-full bg-red" /> {q.red_pct.toFixed(0)}% must fix — click to view
          </button>
        )}
      </div>

      {yellowOpen && q.yellow_items.length > 0 && (
        <div className="flex flex-col gap-2 rounded-lg border border-amber-border bg-amber-soft-2 px-4 py-3.5">
          <div className="text-[12.5px] font-bold text-amber-text">Should-fix items</div>
          <ul className="m-0 flex flex-col gap-1.5 pl-[18px] text-[12.5px] leading-relaxed text-amber-text">
            {q.yellow_items.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      )}

      {redOpen && q.red_items.length > 0 && (
        <div className="flex flex-col gap-2 rounded-lg border border-red-border bg-red-soft px-4 py-3.5">
          <div className="text-[12.5px] font-bold text-red-text">Must-fix items</div>
          <ul className="m-0 flex flex-col gap-1.5 pl-[18px] text-[12.5px] leading-relaxed text-red-text">
            {q.red_items.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="border-t border-divider pt-2.5 text-[11.5px] text-faint">
        Above 90% — pass, single approver. 80–90% — pass with condition. Below 80% — not advisable to approve; if
        approved anyway, requires one Module Lead and one Solution Architect.
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

function SectionBlock({
  index,
  section,
  onAddContext,
}: {
  index: number
  section: FSDSection
  onAddContext: (text: string) => void
}) {
  const [open, setOpen] = useState(false)
  const [text, setText] = useState('')

  if (section.status === 'grounded') {
    return (
      <div>
        <div className="mb-1.5 font-heading text-[15px] font-extrabold">
          {index}. {section.title}
        </div>
        <div className="text-[13.5px] leading-relaxed text-[#333d4d]">{section.content}</div>
        {Object.entries(section.images ?? {}).map(([label, b64]) => (
          <figure key={label} className="mt-3 rounded-lg border border-card-border bg-app-bg/60 p-3">
            <img src={`data:image/png;base64,${b64}`} alt={label} className="mx-auto block max-w-full rounded-md" />
            <figcaption className="mt-2 text-center text-[11.5px] font-semibold text-muted">{label}</figcaption>
          </figure>
        ))}
      </div>
    )
  }

  const isConflict = section.status === 'conflict'
  const tone = isConflict
    ? { border: 'border-l-red', bg: 'bg-red-soft', badgeBg: 'bg-red-soft', badgeText: 'text-red-text', text: 'text-red-text' }
    : { border: 'border-l-amber-dark', bg: 'bg-amber-soft-2', badgeBg: 'bg-amber-soft', badgeText: 'text-amber', text: 'text-amber-text' }

  function submit() {
    const trimmed = text.trim()
    if (!trimmed) return
    onAddContext(trimmed)
    setOpen(false)
    setText('')
  }

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

      {!open && (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className={`mt-2.5 rounded-md border px-3 py-1.5 text-[12px] font-bold ${
            isConflict ? 'border-red-border bg-white text-red-text' : 'border-amber-border bg-white text-amber-text'
          }`}
        >
          + Add context
        </button>
      )}

      {open && (
        <div className="mt-3 flex flex-col gap-2 border-t border-dashed border-divider pt-3">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            autoFocus
            placeholder={
              isConflict
                ? 'Resolve the conflict — which input is correct, or what should override it?'
                : 'Add the missing detail this section needs...'
            }
            className="min-h-[80px] w-full resize-y rounded-lg border border-input-border bg-white p-2.5 text-[13px]"
          />
          <div className="text-[11.5px] text-faint">
            This becomes a new source and regenerates the full draft as a new version — any other section grounded in
            the same facts gets re-drafted too, not just this one.
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={submit}
              disabled={!text.trim()}
              className="rounded-md bg-accent px-3.5 py-1.5 text-[12.5px] font-bold text-white disabled:cursor-not-allowed disabled:opacity-40"
            >
              Regenerate with this context
            </button>
            <button
              type="button"
              onClick={() => {
                setOpen(false)
                setText('')
              }}
              className="rounded-md border border-input-border bg-white px-3.5 py-1.5 text-[12.5px] font-semibold text-slate-pill-text"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
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
              <span className={s.status === 'conflict' ? 'text-red-text' : 'text-amber'}>●</span>
              {s.title} — {s.status === 'conflict' ? 'conflicting inputs' : 'no input provided'}
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
        {requiresDual ? 'Score is below 80% — two approvers are required.' : 'Score meets the single-approver threshold.'}
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
