import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import AppShell from '../components/AppShell'
import {
  ApiError,
  deleteProjectDocument,
  downloadProjectDocument,
  getProject,
  listProjectDocuments,
  uploadProjectDocument,
} from '../lib/api'
import type { Project, ProjectDocument, ProjectDocumentCategory } from '../lib/types'
import { PROJECT_DOCUMENT_CATEGORIES } from '../lib/types'

const PROJECT_NAV = (projectId: string) => [
  { label: 'Overview', to: `/projects/${projectId}/overview` },
  { label: 'Custom Objects', to: `/projects/${projectId}` },
  { label: 'Project Brain', to: `/projects/${projectId}/brain` },
  { label: 'Repository', to: `/projects/${projectId}/repository` },
]

const CATEGORY_BLURB: Record<ProjectDocumentCategory, string> = {
  SOW: 'Statement of Work',
  BPML: 'Business Process Master List',
  PDD: 'Process Design Document',
  FDD: 'Functional Design Document',
  'Big Rocks': 'Major milestones / roadmap',
  Skills: 'Project-specific skill / playbook files',
  Other: 'Anything else worth keeping with this project',
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
  } catch {
    return iso
  }
}

export default function ProjectRepository() {
  const { projectId } = useParams<{ projectId: string }>()
  const [project, setProject] = useState<Project | null>(null)
  const [documents, setDocuments] = useState<ProjectDocument[]>([])
  const [activeCategory, setActiveCategory] = useState<ProjectDocumentCategory | 'All'>('All')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  async function reload() {
    if (!projectId) return
    try {
      const [p, docs] = await Promise.all([getProject(projectId), listProjectDocuments(projectId)])
      setProject(p)
      setDocuments(docs)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not load the project repository.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    reload()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId])

  if (!projectId) return null

  const counts: Record<string, number> = {}
  for (const d of documents) counts[d.category] = (counts[d.category] ?? 0) + 1

  const visible = activeCategory === 'All' ? documents : documents.filter((d) => d.category === activeCategory)

  return (
    <AppShell projectName={project?.name} projectNav={project ? PROJECT_NAV(project.id) : undefined} maxWidth="1100px">
      <div className="mb-4 text-[13px] text-muted">
        <Link to="/" className="text-muted no-underline">
          Projects
        </Link>{' '}
        /{' '}
        {project && (
          <>
            <Link to={`/projects/${project.id}`} className="text-muted no-underline">
              {project.name}
            </Link>{' '}
            /{' '}
          </>
        )}
        <span className="text-ink">Repository</span>
      </div>

      <div className="mb-2">
        <h1 className="m-0 font-heading text-2xl font-extrabold">Repository</h1>
        <div className="mt-1 text-sm text-muted">
          Reference documents for this engagement -- SOW, BPML, PDD, FDD, Big Rocks, project-specific Skill files, and
          anything else worth keeping alongside the project. Stored as-is; uploading here doesn't feed FSD generation.
        </div>
      </div>

      {error && <div className="my-4 rounded-xl border border-red-border bg-red-soft px-5 py-4 text-sm text-red-text">{error}</div>}

      <UploadPanel projectId={projectId} onUploaded={reload} />

      <div className="my-5 flex items-center gap-1 overflow-x-auto rounded-xl border border-card-border bg-white p-1.5">
        <button
          type="button"
          onClick={() => setActiveCategory('All')}
          className={`shrink-0 whitespace-nowrap rounded-lg px-4 py-2.5 text-[13px] font-semibold ${
            activeCategory === 'All' ? 'bg-accent text-white' : 'text-slate-pill-text hover:bg-app-bg'
          }`}
        >
          All ({documents.length})
        </button>
        {PROJECT_DOCUMENT_CATEGORIES.map((c) => (
          <button
            key={c}
            type="button"
            onClick={() => setActiveCategory(c)}
            className={`shrink-0 whitespace-nowrap rounded-lg px-4 py-2.5 text-[13px] font-semibold ${
              activeCategory === c ? 'bg-accent text-white' : 'text-slate-pill-text hover:bg-app-bg'
            }`}
          >
            {c} ({counts[c] ?? 0})
          </button>
        ))}
      </div>

      {loading ? (
        <div className="rounded-2xl border border-card-border bg-white p-8 text-center text-sm text-muted">Loading…</div>
      ) : visible.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-card-border bg-white p-8 text-center text-sm text-muted">
          {activeCategory === 'All'
            ? 'No documents uploaded yet.'
            : `No ${activeCategory} documents yet.`}
        </div>
      ) : (
        <div className="overflow-hidden rounded-2xl border border-card-border bg-white">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-card-border text-left text-xs font-semibold uppercase tracking-wide text-muted">
                <th className="px-4 py-2.5">File</th>
                <th className="px-4 py-2.5">Category</th>
                <th className="px-4 py-2.5">Notes</th>
                <th className="px-4 py-2.5">Uploaded</th>
                <th className="px-4 py-2.5">Size</th>
                <th className="px-4 py-2.5" />
              </tr>
            </thead>
            <tbody>
              {visible.map((doc) => (
                <DocumentRow key={doc.id} doc={doc} onChanged={reload} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </AppShell>
  )
}

function UploadPanel({ projectId, onUploaded }: { projectId: string; onUploaded: () => void }) {
  const [category, setCategory] = useState<ProjectDocumentCategory>('SOW')
  const [notes, setNotes] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  async function handleFile(file: File) {
    setBusy(true)
    setError(null)
    try {
      await uploadProjectDocument(projectId, file, category, notes.trim())
      setNotes('')
      if (fileInputRef.current) fileInputRef.current.value = ''
      onUploaded()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Upload failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="rounded-2xl border border-card-border bg-white p-6">
      <div className="mb-3 font-heading text-[15px] font-extrabold">Upload a document</div>
      {error && <div className="mb-3 rounded-lg border border-red-border bg-red-soft px-4 py-2.5 text-[12.5px] text-red-text">{error}</div>}
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-semibold text-slate-pill-text">Category</span>
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value as ProjectDocumentCategory)}
            className="w-48 rounded-md border border-input-border px-3 py-2 text-sm"
          >
            {PROJECT_DOCUMENT_CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {c} — {CATEGORY_BLURB[c]}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-semibold text-slate-pill-text">Notes (optional)</span>
          <input
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="e.g. signed v2, 2026-10-01"
            className="w-64 rounded-md border border-input-border px-3 py-2 text-sm"
          />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-semibold text-slate-pill-text">File</span>
          <input
            ref={fileInputRef}
            type="file"
            disabled={busy}
            onChange={(e) => {
              const file = e.target.files?.[0]
              if (file) handleFile(file)
            }}
            className="w-64 text-sm disabled:opacity-40"
          />
        </label>
        {busy && <span className="pb-2 text-[12.5px] text-muted">Uploading…</span>}
      </div>
    </div>
  )
}

function DocumentRow({ doc, onChanged }: { doc: ProjectDocument; onChanged: () => void }) {
  const [busy, setBusy] = useState(false)

  async function handleDownload() {
    try {
      await downloadProjectDocument(doc.id, doc.filename)
    } catch {
      // the download helper already surfaces failures via a thrown ApiError;
      // a failed download isn't worth a page-level error banner here.
    }
  }

  async function handleDelete() {
    if (!window.confirm(`Delete "${doc.filename}"? This can't be undone.`)) return
    setBusy(true)
    try {
      await deleteProjectDocument(doc.id)
      onChanged()
    } catch (err) {
      window.alert(err instanceof ApiError ? err.message : 'Could not delete this document.')
      setBusy(false)
    }
  }

  return (
    <tr className="border-b border-divider last:border-0">
      <td className="px-4 py-2.5 font-medium">{doc.filename}</td>
      <td className="px-4 py-2.5">
        <span className="rounded-full bg-app-bg px-2.5 py-0.5 text-[11px] font-bold text-slate-pill-text">{doc.category}</span>
      </td>
      <td className="px-4 py-2.5 text-muted">{doc.notes || '—'}</td>
      <td className="px-4 py-2.5 text-muted">
        {formatDate(doc.uploaded_at)}
        {doc.uploaded_by && <div className="text-[11px] text-faint">{doc.uploaded_by}</div>}
      </td>
      <td className="px-4 py-2.5 text-muted">{formatSize(doc.size_bytes)}</td>
      <td className="px-4 py-2.5 whitespace-nowrap">
        <button type="button" onClick={handleDownload} className="mr-3 text-xs font-semibold text-accent">
          Download
        </button>
        <button type="button" onClick={handleDelete} disabled={busy} className="text-xs font-semibold text-red-text disabled:opacity-40">
          Delete
        </button>
      </td>
    </tr>
  )
}
