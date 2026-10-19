import { useEffect, useState } from 'react'
import { useNavigate, useParams, Link } from 'react-router-dom'
import AppShell from '../components/AppShell'
import { ApiError, extractDocument, fetchDocumentLink, getObject, getProject } from '../lib/api'
import type { Project, SourceDocumentIn, TrackedObject } from '../lib/types'

const DOC_TYPES = [
  'Business Requirement Document (BRD)',
  'Process Design Document (PDD)',
  'Process Flow Diagram',
  'Existing Business Functionality Doc',
  'Other',
]

const PROJECT_NAV = (projectId: string) => [
  { label: 'Overview', to: `/projects/${projectId}/overview` },
  { label: 'Custom Objects', to: `/projects/${projectId}` },
  { label: 'Project Brain', to: `/projects/${projectId}/brain` },
  { label: 'Repository', to: `/projects/${projectId}/repository` },
]

interface AddedDoc extends SourceDocumentIn {
  id: string
}

let docCounter = 0

type LoadState =
  | { phase: 'loading' }
  | { phase: 'error'; message: string }
  | { phase: 'done'; project: Project; object: TrackedObject }

export default function FsdIntake() {
  const { projectId, objectId } = useParams<{ projectId: string; objectId: string }>()
  const navigate = useNavigate()

  const [load, setLoad] = useState<LoadState>({ phase: 'loading' })

  const [docs, setDocs] = useState<AddedDoc[]>([])
  const [typedContext, setTypedContext] = useState('')

  // "add a document" mini-form state
  const [draftDocType, setDraftDocType] = useState(DOC_TYPES[0])
  const [draftLabel, setDraftLabel] = useState('')
  const [draftText, setDraftText] = useState('')
  const [draftMode, setDraftMode] = useState<'pasted' | 'uploaded' | 'linked'>('pasted')
  const [fileError, setFileError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [linkUrl, setLinkUrl] = useState('')
  const [linkFetching, setLinkFetching] = useState(false)
  const [linkError, setLinkError] = useState<string | null>(null)

  useEffect(() => {
    if (!projectId || !objectId) return
    Promise.all([getProject(projectId), getObject(objectId)])
      .then(([project, object]) => setLoad({ phase: 'done', project, object }))
      .catch((err) =>
        setLoad({ phase: 'error', message: err instanceof ApiError ? err.message : 'Could not load this object.' }),
      )
  }, [projectId, objectId])

  if (load.phase === 'loading') {
    return (
      <AppShell>
        <div className="text-sm text-muted">Loading…</div>
      </AppShell>
    )
  }
  if (load.phase === 'error') {
    return (
      <AppShell>
        <div className="rounded-xl border border-red-border bg-red-soft px-5 py-4 text-sm text-red-text">
          {load.message}
        </div>
      </AppShell>
    )
  }

  const { project, object } = load

  async function handleFile(file: File) {
    setFileError(null)
    setUploading(true)
    try {
      const { text } = await extractDocument(file)
      setDraftText(text)
      if (!draftLabel) setDraftLabel(file.name)
    } catch (err) {
      setFileError(err instanceof ApiError ? err.message : `Couldn't read "${file.name}".`)
    } finally {
      setUploading(false)
    }
  }

  async function handleLink() {
    const url = linkUrl.trim()
    if (!url) return
    setLinkError(null)
    setLinkFetching(true)
    try {
      const { label, text } = await fetchDocumentLink(url)
      setDraftText(text)
      if (!draftLabel) setDraftLabel(label)
    } catch (err) {
      setLinkError(err instanceof ApiError ? err.message : `Couldn't fetch that link.`)
    } finally {
      setLinkFetching(false)
    }
  }

  function addDocument() {
    if (!draftText.trim()) return
    docCounter += 1
    const doc: AddedDoc = {
      id: `doc-${docCounter}`,
      source_id: `source_${docCounter}`,
      label: draftLabel.trim() || `Document ${docCounter}`,
      doc_type: draftDocType,
      text: draftText.trim(),
    }
    setDocs((prev) => [...prev, doc])
    setDraftLabel('')
    setDraftText('')
    setFileError(null)
    setLinkError(null)
    setLinkUrl('')
  }

  function removeDocument(id: string) {
    setDocs((prev) => prev.filter((d) => d.id !== id))
  }

  const trimmedTypedContext = typedContext.trim()
  const sources: SourceDocumentIn[] = [
    ...docs.map((d): SourceDocumentIn => ({
      source_id: d.source_id,
      label: d.label,
      doc_type: d.doc_type,
      text: d.text,
    })),
    ...(trimmedTypedContext
      ? [{ source_id: 'typed_context', label: 'Typed Context', doc_type: 'Typed Context', text: trimmedTypedContext }]
      : []),
  ]
  const canGenerate = sources.length > 0

  function handleGenerate() {
    navigate(`/projects/${project.id}/objects/${object.id}/fsd/review`, { state: { sources } })
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

      <div className="mb-5 flex flex-wrap items-center justify-between gap-2.5">
        <div className="flex items-center gap-2.5">
          <h1 className="m-0 font-heading text-2xl font-extrabold">{object.name}</h1>
          <span className="rounded-full bg-slate-pill-bg px-2.5 py-1 text-xs font-bold text-slate-pill-text">
            {object.type}
          </span>
        </div>
        <Link
          to={`/projects/${project.id}/objects/${object.id}`}
          className="whitespace-nowrap rounded-lg border border-input-border bg-white px-4 py-2.5 text-[13px] font-semibold text-slate-pill-text no-underline"
        >
          ← Object Dashboard
        </Link>
      </div>

      <PipelineSteps current="FSD Creation" />

      <div className="mt-6">
        <div className="font-heading text-[19px] font-extrabold">Create Functional Specification</div>
        <div className="mt-1 text-[13.5px] text-muted">
          Combine any inputs below — all optional, used together. A section with nothing behind it is flagged, not
          invented.
        </div>
      </div>

      {/* Reference documents */}
      <div className="mt-5 flex flex-col gap-3 rounded-2xl border border-card-border bg-white p-5">
        <div className="font-semibold text-sm">Reference Documents</div>

        <div className="flex flex-wrap items-center gap-2">
          <select
            value={draftDocType}
            onChange={(e) => setDraftDocType(e.target.value)}
            className="rounded-md border border-input-border bg-white px-2.5 py-1.5 text-[12.5px]"
          >
            {DOC_TYPES.map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>

          <div className="flex overflow-hidden rounded-md border border-input-border">
            <button
              type="button"
              onClick={() => setDraftMode('uploaded')}
              className={`px-3 py-1.5 text-[12.5px] font-semibold ${
                draftMode === 'uploaded' ? 'bg-accent text-white' : 'bg-white text-slate-pill-text'
              }`}
            >
              Upload file
            </button>
            <button
              type="button"
              onClick={() => setDraftMode('pasted')}
              className={`border-l border-input-border px-3 py-1.5 text-[12.5px] font-semibold ${
                draftMode === 'pasted' ? 'bg-accent text-white' : 'bg-white text-slate-pill-text'
              }`}
            >
              Paste text
            </button>
            <button
              type="button"
              onClick={() => setDraftMode('linked')}
              className={`border-l border-input-border px-3 py-1.5 text-[12.5px] font-semibold ${
                draftMode === 'linked' ? 'bg-accent text-white' : 'bg-white text-slate-pill-text'
              }`}
            >
              Link to repo
            </button>
          </div>
        </div>

        {draftMode === 'linked' ? (
          <div className="flex flex-col gap-2 rounded-lg border border-dashed border-input-border bg-app-bg/60 p-4">
            <div className="flex flex-wrap items-center gap-2">
              <input
                value={linkUrl}
                onChange={(e) => setLinkUrl(e.target.value)}
                placeholder="https://github.com/org/repo/blob/main/docs/BRD.docx"
                className="min-w-[280px] flex-1 rounded-md border border-input-border px-2.5 py-1.5 text-[13px]"
              />
              <button
                type="button"
                onClick={handleLink}
                disabled={!linkUrl.trim() || linkFetching}
                className="whitespace-nowrap rounded-md bg-accent px-3.5 py-1.5 text-[12.5px] font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
              >
                {linkFetching ? 'Fetching…' : 'Fetch'}
              </button>
            </div>
            <div className="text-[11.5px] text-muted">
              A link to one file in a GitHub repo (or any other plain URL) — fetched and parsed on the server, same
              as an upload. Point at the file itself, not the repo's homepage.
            </div>
          </div>
        ) : null}
        {linkError && <div className="text-[11.5px] text-red-text">{linkError}</div>}

        {draftMode === 'uploaded' ? (
          <label className="flex cursor-pointer flex-wrap items-center justify-between gap-3 rounded-lg border border-dashed border-input-border bg-app-bg/60 p-4">
            <span className="text-[13px] text-muted">
              {uploading
                ? 'Reading file…'
                : draftText
                  ? 'File loaded — edit below if needed, then add it.'
                  : '.txt, .md, .docx, or .pdf — parsed on the server, not just this browser'}
            </span>
            <span className="rounded-md bg-accent px-3.5 py-1.5 text-[12.5px] font-semibold text-white">
              Browse files
            </span>
            <input
              type="file"
              accept=".txt,.md,.docx,.pdf"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) handleFile(f)
              }}
            />
          </label>
        ) : null}

        {fileError && <div className="text-[11.5px] text-red-text">{fileError}</div>}

        <textarea
          value={draftText}
          onChange={(e) => setDraftText(e.target.value)}
          placeholder="Paste (or review loaded) document text here..."
          className="min-h-[100px] w-full resize-y rounded-lg border border-input-border p-2.5 text-[13.5px]"
        />

        <div className="flex items-center gap-2">
          <input
            value={draftLabel}
            onChange={(e) => setDraftLabel(e.target.value)}
            placeholder="Label, e.g. BRD_CustomerMaster_v2.docx"
            className="flex-1 rounded-md border border-input-border px-2.5 py-1.5 text-[13px]"
          />
          <button
            type="button"
            onClick={addDocument}
            disabled={!draftText.trim()}
            className="whitespace-nowrap rounded-md bg-accent px-3.5 py-2 text-[12.5px] font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
          >
            + Add document
          </button>
        </div>

        {docs.length > 0 && (
          <div className="mt-1 flex flex-col gap-2">
            <div className="text-xs font-semibold text-slate-pill-text">Added documents</div>
            {docs.map((d) => (
              <div
                key={d.id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-divider bg-app-bg/60 px-3.5 py-2.5"
              >
                <div className="flex items-center gap-2.5">
                  <span className="rounded-full bg-slate-pill-bg px-2 py-0.5 text-[10.5px] font-bold text-slate-pill-text">
                    {d.doc_type.split(' ')[0]}
                  </span>
                  <span className="text-[13px] font-semibold">{d.label}</span>
                  <span className="text-[11.5px] text-faint">({d.text.length.toLocaleString()} chars)</span>
                </div>
                <button
                  type="button"
                  onClick={() => removeDocument(d.id)}
                  className="text-[12px] font-semibold text-red-text"
                >
                  Remove
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Typed context */}
      <div className="mt-[18px] flex flex-col gap-2.5 rounded-2xl border border-card-border bg-white p-5">
        <div className="font-semibold text-sm">Typed Context</div>
        <textarea
          value={typedContext}
          onChange={(e) => setTypedContext(e.target.value)}
          placeholder="Add instructions, scope notes, or anything not already captured above..."
          className="min-h-[110px] w-full resize-y rounded-lg border border-input-border p-[11px] text-[13.5px]"
        />
      </div>

      <div className="mt-[18px] flex items-center justify-between rounded-2xl border border-card-border bg-white px-[22px] py-[18px]">
        <div className="max-w-[520px] text-[12.5px] text-muted">
          Nothing drafts until every input above is combined into one grounded brief. You'll see exactly which
          sections are grounded, which need input, and which conflict.
        </div>
        <button
          type="button"
          onClick={handleGenerate}
          disabled={!canGenerate}
          className="whitespace-nowrap rounded-lg bg-accent px-[26px] py-[13px] text-sm font-bold text-white disabled:cursor-not-allowed disabled:opacity-40"
        >
          Generate FSD →
        </button>
      </div>
      {!canGenerate && (
        <div className="mt-2 text-[12px] text-faint">Add at least one document or some typed context to continue.</div>
      )}
      {object.latest_fsd_version && (
        <div className="mt-2 text-[12px] text-faint">
          This object already has {object.latest_fsd_version} generated version
          {object.latest_fsd_version > 1 ? 's' : ''} — generating again creates a new one.
        </div>
      )}
    </AppShell>
  )
}

function PipelineSteps({ current }: { current: string }) {
  const steps = ['FSD Creation', 'Feasibility', 'TSD', 'Code', 'Review', 'Test']
  return (
    <div className="flex items-center overflow-x-auto rounded-xl border border-card-border bg-white px-5 py-4">
      {steps.map((step, i) => {
        const active = step === current
        return (
          <div key={step} className="flex items-center">
            <div className="flex items-center gap-2 whitespace-nowrap">
              <span className={`h-2.5 w-2.5 rounded-full ${active ? 'bg-accent' : 'bg-input-border'}`} />
              <span className={`text-[13px] font-semibold ${active ? 'text-accent' : 'text-faint'}`}>{step}</span>
            </div>
            {i < steps.length - 1 && <div className="mx-2.5 h-px w-9 bg-card-border" />}
          </div>
        )
      })}
    </div>
  )
}
