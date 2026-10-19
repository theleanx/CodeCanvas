import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import AppShell from '../components/AppShell'
import {
  ApiError,
  createComplexityConfig,
  createModuleConfig,
  deleteComplexityConfig,
  deleteModuleConfig,
  getProject,
  listComplexityConfigs,
  listDocumentTemplates,
  listModuleConfigs,
  listObjectTypeConfigs,
  saveDocumentTemplate,
  updateComplexityConfig,
  updateModuleConfig,
  updateObjectTypeConfig,
  uploadDocumentTemplate,
} from '../lib/api'
import type {
  ComplexityConfig,
  DocumentTemplate,
  DocumentTemplateSection,
  DocumentType,
  ModuleConfig,
  ObjectType,
  ObjectTypeConfig,
  Project,
} from '../lib/types'
import { DOCUMENT_TYPES, OBJECT_TYPE_INTERNAL_KEYS } from '../lib/types'

const PROJECT_NAV = (projectId: string) => [
  { label: 'Overview', to: `/projects/${projectId}/overview` },
  { label: 'Custom Objects', to: `/projects/${projectId}` },
  { label: 'Project Brain', to: `/projects/${projectId}/brain` },
  { label: 'Repository', to: `/projects/${projectId}/repository` },
]

type Tab = 'types' | 'modules' | 'complexity' | 'templates'
const TABS: { key: Tab; label: string }[] = [
  { key: 'types', label: 'Object Types' },
  { key: 'modules', label: 'Modules' },
  { key: 'complexity', label: 'Complexity' },
  { key: 'templates', label: 'Document Templates' },
]

export default function ProjectBrain() {
  const { projectId } = useParams<{ projectId: string }>()
  const [project, setProject] = useState<Project | null>(null)
  const [tab, setTab] = useState<Tab>('types')

  const [types, setTypes] = useState<ObjectTypeConfig[]>([])
  const [modules, setModules] = useState<ModuleConfig[]>([])
  const [complexities, setComplexities] = useState<ComplexityConfig[]>([])
  const [templates, setTemplates] = useState<DocumentTemplate[]>([])
  const [error, setError] = useState<string | null>(null)

  async function reloadAll() {
    if (!projectId) return
    try {
      const [p, t, m, c, dt] = await Promise.all([
        getProject(projectId),
        listObjectTypeConfigs(projectId),
        listModuleConfigs(projectId),
        listComplexityConfigs(projectId),
        listDocumentTemplates(projectId),
      ])
      setProject(p)
      setTypes(t)
      setModules(m)
      setComplexities(c)
      setTemplates(dt)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not load Project Brain configuration.')
    }
  }

  useEffect(() => {
    reloadAll()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId])

  if (!projectId) return null

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
        <span className="text-ink">Project Brain</span>
      </div>

      <div className="mb-2">
        <h1 className="m-0 font-heading text-2xl font-extrabold">Project Brain</h1>
        <div className="mt-1 text-sm text-muted">
          Terminology and document templates for this project -- what appears in "New Custom Object" dropdowns, how
          Object IDs are generated, and which FSD template drafts against each object type.
        </div>
      </div>

      {error && <div className="my-4 rounded-xl border border-red-border bg-red-soft px-5 py-4 text-sm text-red-text">{error}</div>}

      <div className="my-5 flex items-center gap-1 overflow-x-auto rounded-xl border border-card-border bg-white p-1.5">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            className={`shrink-0 whitespace-nowrap rounded-lg px-4 py-2.5 text-[13px] font-semibold ${
              tab === t.key ? 'bg-accent text-white' : 'text-slate-pill-text hover:bg-app-bg'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'types' && <ObjectTypesTab projectId={projectId} types={types} onReload={reloadAll} />}
      {tab === 'modules' && <ModulesTab projectId={projectId} modules={modules} onReload={reloadAll} />}
      {tab === 'complexity' && <ComplexityTab projectId={projectId} complexities={complexities} onReload={reloadAll} />}
      {tab === 'templates' && <TemplatesTab projectId={projectId} templates={templates} onReload={reloadAll} />}
    </AppShell>
  )
}

// --- Object Types -----------------------------------------------------------
// Rename-only: the six categories are fixed (they select an FSD template and
// an Intake Validation checklist), but a project can relabel each one and
// change its Object ID prefix, or hide it from "New Custom Object".

function ObjectTypesTab({ projectId, types, onReload }: { projectId: string; types: ObjectTypeConfig[]; onReload: () => void }) {
  const [drafts, setDrafts] = useState<Record<string, { display_label: string; id_prefix: string }>>({})
  const [savingKey, setSavingKey] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  function draftFor(t: ObjectTypeConfig) {
    return drafts[t.internal_key] ?? { display_label: t.display_label, id_prefix: t.id_prefix }
  }

  async function save(t: ObjectTypeConfig) {
    const d = draftFor(t)
    setSavingKey(t.internal_key)
    setError(null)
    try {
      await updateObjectTypeConfig(projectId, t.internal_key, { display_label: d.display_label, id_prefix: d.id_prefix })
      onReload()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not save.')
    } finally {
      setSavingKey(null)
    }
  }

  async function toggleEnabled(t: ObjectTypeConfig) {
    try {
      await updateObjectTypeConfig(projectId, t.internal_key, { enabled: !t.enabled })
      onReload()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not update.')
    }
  }

  return (
    <div className="rounded-2xl border border-card-border bg-white p-6">
      <p className="mb-4 text-[13px] text-muted">
        These six categories are fixed -- each one drives which FSD template and Intake Validation checklist get
        used. You can relabel them for this client (e.g. rename "Enhancement" to whatever your client calls it) and
        set the Object ID prefix each one generates (e.g. "F" for Form → PP_F001). Disabling one hides it from "New
        Custom Object" without touching any object that already used it.
      </p>
      {error && <div className="mb-4 rounded-lg border border-red-border bg-red-soft px-4 py-2.5 text-[12.5px] text-red-text">{error}</div>}
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-card-border text-left text-xs font-semibold uppercase tracking-wide text-muted">
            <th className="px-3 py-2">Internal Category</th>
            <th className="px-3 py-2">Display Label</th>
            <th className="px-3 py-2">Object ID Prefix</th>
            <th className="px-3 py-2">Enabled</th>
            <th className="px-3 py-2" />
          </tr>
        </thead>
        <tbody>
          {types.map((t) => {
            const d = draftFor(t)
            const dirty = d.display_label !== t.display_label || d.id_prefix !== t.id_prefix
            return (
              <tr key={t.internal_key} className="border-b border-divider last:border-0">
                <td className="px-3 py-2.5 font-mono text-[12.5px] text-muted">{t.internal_key}</td>
                <td className="px-3 py-2.5">
                  <input
                    value={d.display_label}
                    onChange={(e) => setDrafts((prev) => ({ ...prev, [t.internal_key]: { ...d, display_label: e.target.value } }))}
                    className="w-56 rounded-md border border-input-border px-2.5 py-1.5 text-sm"
                  />
                </td>
                <td className="px-3 py-2.5">
                  <input
                    value={d.id_prefix}
                    onChange={(e) =>
                      setDrafts((prev) => ({ ...prev, [t.internal_key]: { ...d, id_prefix: e.target.value.toUpperCase() } }))
                    }
                    maxLength={10}
                    className="w-20 rounded-md border border-input-border px-2.5 py-1.5 text-sm"
                  />
                </td>
                <td className="px-3 py-2.5">
                  <input type="checkbox" checked={t.enabled} onChange={() => toggleEnabled(t)} className="h-4 w-4" />
                </td>
                <td className="px-3 py-2.5">
                  {dirty && (
                    <button
                      type="button"
                      onClick={() => save(t)}
                      disabled={savingKey === t.internal_key}
                      className="rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-40"
                    >
                      {savingKey === t.internal_key ? 'Saving…' : 'Save'}
                    </button>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// --- Modules / Complexity: shared list-editor shape -------------------------

function ModulesTab({ projectId, modules, onReload }: { projectId: string; modules: ModuleConfig[]; onReload: () => void }) {
  const [name, setName] = useState('')
  const [idCode, setIdCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function add() {
    if (!name.trim()) return
    setBusy(true)
    setError(null)
    try {
      await createModuleConfig(projectId, name.trim(), idCode.trim() || undefined)
      setName('')
      setIdCode('')
      onReload()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not add module.')
    } finally {
      setBusy(false)
    }
  }

  async function toggle(m: ModuleConfig) {
    try {
      await updateModuleConfig(projectId, m.id, { enabled: !m.enabled })
      onReload()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not update.')
    }
  }

  async function remove(m: ModuleConfig) {
    try {
      await deleteModuleConfig(projectId, m.id)
      onReload()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not delete.')
    }
  }

  return (
    <div className="rounded-2xl border border-card-border bg-white p-6">
      <p className="mb-4 text-[13px] text-muted">
        Your project's own module vocabulary -- add whatever this client calls their modules. The ID Code is a short,
        unique tag used only for Object IDs (e.g. "WM/EWM" → "WMEWM" → PP-style codes like WMEWM_F001).
      </p>
      {error && <div className="mb-4 rounded-lg border border-red-border bg-red-soft px-4 py-2.5 text-[12.5px] text-red-text">{error}</div>}

      <div className="mb-4 flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-semibold text-slate-pill-text">Name</span>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Sales" className="w-48 rounded-md border border-input-border px-3 py-2 text-sm" />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-semibold text-slate-pill-text">ID Code (optional)</span>
          <input
            value={idCode}
            onChange={(e) => setIdCode(e.target.value.toUpperCase())}
            placeholder="auto"
            maxLength={10}
            className="w-28 rounded-md border border-input-border px-3 py-2 text-sm"
          />
        </label>
        <button type="button" onClick={add} disabled={!name.trim() || busy} className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white disabled:opacity-40">
          {busy ? 'Adding…' : '+ Add Module'}
        </button>
      </div>

      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-card-border text-left text-xs font-semibold uppercase tracking-wide text-muted">
            <th className="px-3 py-2">Name</th>
            <th className="px-3 py-2">ID Code</th>
            <th className="px-3 py-2">Enabled</th>
            <th className="px-3 py-2" />
          </tr>
        </thead>
        <tbody>
          {modules.map((m) => (
            <tr key={m.id} className="border-b border-divider last:border-0">
              <td className="px-3 py-2.5 font-medium">{m.name}</td>
              <td className="px-3 py-2.5 font-mono text-[12.5px] text-muted">{m.id_code}</td>
              <td className="px-3 py-2.5">
                <input type="checkbox" checked={m.enabled} onChange={() => toggle(m)} className="h-4 w-4" />
              </td>
              <td className="px-3 py-2.5">
                <button type="button" onClick={() => remove(m)} className="text-xs font-semibold text-red-text">
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ComplexityTab({
  projectId,
  complexities,
  onReload,
}: {
  projectId: string
  complexities: ComplexityConfig[]
  onReload: () => void
}) {
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function add() {
    if (!name.trim()) return
    setBusy(true)
    setError(null)
    try {
      await createComplexityConfig(projectId, name.trim())
      setName('')
      onReload()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not add complexity level.')
    } finally {
      setBusy(false)
    }
  }

  async function toggle(c: ComplexityConfig) {
    try {
      await updateComplexityConfig(projectId, c.id, { enabled: !c.enabled })
      onReload()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not update.')
    }
  }

  async function remove(c: ComplexityConfig) {
    try {
      await deleteComplexityConfig(projectId, c.id)
      onReload()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not delete.')
    }
  }

  return (
    <div className="rounded-2xl border border-card-border bg-white p-6">
      <p className="mb-4 text-[13px] text-muted">Complexity levels shown on the "New Custom Object" form and the object list.</p>
      {error && <div className="mb-4 rounded-lg border border-red-border bg-red-soft px-4 py-2.5 text-[12.5px] text-red-text">{error}</div>}

      <div className="mb-4 flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-semibold text-slate-pill-text">Name</span>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Critical" className="w-48 rounded-md border border-input-border px-3 py-2 text-sm" />
        </label>
        <button type="button" onClick={add} disabled={!name.trim() || busy} className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white disabled:opacity-40">
          {busy ? 'Adding…' : '+ Add Level'}
        </button>
      </div>

      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-card-border text-left text-xs font-semibold uppercase tracking-wide text-muted">
            <th className="px-3 py-2">Name</th>
            <th className="px-3 py-2">Enabled</th>
            <th className="px-3 py-2" />
          </tr>
        </thead>
        <tbody>
          {complexities.map((c) => (
            <tr key={c.id} className="border-b border-divider last:border-0">
              <td className="px-3 py-2.5 font-medium">{c.name}</td>
              <td className="px-3 py-2.5">
                <input type="checkbox" checked={c.enabled} onChange={() => toggle(c)} className="h-4 w-4" />
              </td>
              <td className="px-3 py-2.5">
                <button type="button" onClick={() => remove(c)} className="text-xs font-semibold text-red-text">
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// --- Document Templates -------------------------------------------------
// A 6 (object type) x 4 (document type) grid. Only FSD is actually consumed
// by a generation step today -- the others can still be configured ahead of
// time, labeled honestly as not yet used.

function TemplatesTab({ projectId, templates, onReload }: { projectId: string; templates: DocumentTemplate[]; onReload: () => void }) {
  const [selected, setSelected] = useState<{ documentType: DocumentType; objectTypeKey: ObjectType } | null>(null)

  const byKey = new Map(templates.map((t) => [`${t.document_type}::${t.object_type_key}`, t]))
  const selectedTemplate = selected ? byKey.get(`${selected.documentType}::${selected.objectTypeKey}`) : null

  return (
    <div className="flex flex-col gap-5">
      <div className="rounded-2xl border border-card-border bg-white p-6">
        <p className="mb-4 text-[13px] text-muted">
          Each cell is one (document type × object type) template. "In-Built" uses CodeCanvas's own default section
          list; "Client-Specific" replaces it entirely with sections from an uploaded template. Click a cell to view
          or change it.
        </p>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-card-border text-left text-xs font-semibold uppercase tracking-wide text-muted">
                <th className="px-3 py-2">Object Type</th>
                {DOCUMENT_TYPES.map((dt) => (
                  <th key={dt} className="px-3 py-2">
                    {dt}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {OBJECT_TYPE_INTERNAL_KEYS.map((ot) => (
                <tr key={ot} className="border-b border-divider last:border-0">
                  <td className="px-3 py-2.5 font-medium">{ot}</td>
                  {DOCUMENT_TYPES.map((dt) => {
                    const t = byKey.get(`${dt}::${ot}`)
                    const isSelected = selected?.documentType === dt && selected?.objectTypeKey === ot
                    const clientSpecific = t?.source === 'client_specific'
                    return (
                      <td key={dt} className="px-3 py-2.5">
                        <button
                          type="button"
                          onClick={() => setSelected({ documentType: dt, objectTypeKey: ot })}
                          className={`w-full rounded-lg border px-2.5 py-2 text-left text-[12px] font-semibold ${
                            isSelected
                              ? 'border-accent bg-accent-soft text-accent'
                              : clientSpecific
                                ? 'border-green-border bg-green-soft text-green'
                                : 'border-input-border bg-app-bg/60 text-slate-pill-text'
                          }`}
                        >
                          {clientSpecific ? 'Client-Specific' : 'In-Built'}
                        </button>
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {selected && (
        <TemplateEditor
          projectId={projectId}
          documentType={selected.documentType}
          objectTypeKey={selected.objectTypeKey}
          template={selectedTemplate ?? null}
          onSaved={() => {
            onReload()
          }}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  )
}

function TemplateEditor({
  projectId,
  documentType,
  objectTypeKey,
  template,
  onSaved,
  onClose,
}: {
  projectId: string
  documentType: DocumentType
  objectTypeKey: ObjectType
  template: DocumentTemplate | null
  onSaved: () => void
  onClose: () => void
}) {
  const [source, setSource] = useState<'in_built' | 'client_specific'>(template?.source ?? 'in_built')
  const [filename, setFilename] = useState(template?.uploaded_filename ?? '')
  const [sections, setSections] = useState<DocumentTemplateSection[]>(template?.sections ?? [])
  const [rawText, setRawText] = useState('')
  const [diagramSectionKey, setDiagramSectionKey] = useState<string>(template?.diagram_section_key ?? '')
  const [allowAiInferred, setAllowAiInferred] = useState(template?.allow_ai_inferred ?? false)
  const [uploading, setUploading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setSource(template?.source ?? 'in_built')
    setFilename(template?.uploaded_filename ?? '')
    setSections(template?.sections ?? [])
    setDiagramSectionKey(template?.diagram_section_key ?? '')
    setAllowAiInferred(template?.allow_ai_inferred ?? false)
    setRawText('')
    setError(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [documentType, objectTypeKey])

  async function handleUpload(file: File) {
    setUploading(true)
    setError(null)
    try {
      const result = await uploadDocumentTemplate(projectId, file)
      setFilename(result.filename)
      setSections(result.sections)
      setRawText(result.raw_text)
      setSource('client_specific')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not read that file.')
    } finally {
      setUploading(false)
    }
  }

  function updateSectionTitle(index: number, title: string) {
    setSections((prev) => prev.map((s, i) => (i === index ? { ...s, title } : s)))
  }

  function removeSection(index: number) {
    setSections((prev) => prev.filter((_, i) => i !== index))
  }

  function addSection() {
    const n = sections.length + 1
    let key = `section_${n}`
    const existing = new Set(sections.map((s) => s.key))
    let i = n
    while (existing.has(key)) {
      i += 1
      key = `section_${i}`
    }
    setSections((prev) => [...prev, { key, title: 'New Section' }])
  }

  function moveSection(index: number, dir: -1 | 1) {
    setSections((prev) => {
      const next = [...prev]
      const target = index + dir
      if (target < 0 || target >= next.length) return prev
      ;[next[index], next[target]] = [next[target], next[index]]
      return next
    })
  }

  async function save() {
    setSaving(true)
    setError(null)
    try {
      if (source === 'in_built') {
        await saveDocumentTemplate(projectId, documentType, objectTypeKey, { source: 'in_built' })
      } else {
        if (sections.length === 0) {
          setError('Add at least one section before saving.')
          setSaving(false)
          return
        }
        await saveDocumentTemplate(projectId, documentType, objectTypeKey, {
          source: 'client_specific',
          uploaded_filename: filename || 'Untitled template',
          sections,
          diagram_section_key: diagramSectionKey || null,
          allow_ai_inferred: allowAiInferred,
          // Only sent when this save follows a fresh upload in this session
          // -- raw_text isn't echoed back by the list endpoint, so an
          // edit-only save (no re-upload) has nothing to resend here. It's
          // provenance only (generation reads `sections`, not this), so
          // that's an acceptable gap rather than a functional one.
          raw_text: rawText || undefined,
        })
      }
      onSaved()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not save this template.')
    } finally {
      setSaving(false)
    }
  }

  const generationAvailable = template?.generation_available ?? documentType === 'FSD'
  const inBuiltSections = template?.in_built_sections ?? null

  return (
    <div className="rounded-2xl border border-card-border bg-white p-6">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <div className="font-heading text-base font-bold">
            {documentType} · {objectTypeKey}
          </div>
          {!generationAvailable && (
            <div className="mt-1 text-[12.5px] text-amber-text">
              {documentType} doesn't have a generation step built in CodeCanvas yet -- this config is saved for when
              it does, and won't change anything in the meantime.
            </div>
          )}
        </div>
        <button type="button" onClick={onClose} className="text-xs font-semibold text-muted">
          Close
        </button>
      </div>

      {error && <div className="mb-4 rounded-lg border border-red-border bg-red-soft px-4 py-2.5 text-[12.5px] text-red-text">{error}</div>}

      <div className="mb-4 flex gap-4 text-sm">
        <label className="flex items-center gap-2">
          <input type="radio" checked={source === 'in_built'} onChange={() => setSource('in_built')} />
          In-Built template
        </label>
        <label className="flex items-center gap-2">
          <input type="radio" checked={source === 'client_specific'} onChange={() => setSource('client_specific')} />
          Client-specific template
        </label>
      </div>

      {source === 'in_built' &&
        (inBuiltSections ? (
          <div className="rounded-xl border border-dashed border-input-border bg-app-bg/60 p-4">
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">In-built sections</div>
            <ol className="list-decimal pl-5 text-sm text-ink">
              {inBuiltSections.map((s) => (
                <li key={s.key}>{s.title}</li>
              ))}
            </ol>
          </div>
        ) : (
          <div className="rounded-xl border border-dashed border-input-border bg-app-bg/60 p-4 text-sm text-muted">
            No in-built template exists for {documentType} yet.
          </div>
        ))}

      {source === 'client_specific' && (
        <div className="flex flex-col gap-4">
          <div>
            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-semibold text-slate-pill-text">
                Upload a template (.docx with Heading styles works best; .pdf/.txt/.md also supported)
              </span>
              <input
                type="file"
                accept=".docx,.pdf,.txt,.md"
                onChange={(e) => {
                  const f = e.target.files?.[0]
                  if (f) handleUpload(f)
                }}
                className="text-sm"
              />
            </label>
            {uploading && <div className="mt-1 text-xs text-muted">Reading file…</div>}
            {filename && <div className="mt-1 text-xs text-muted">Current file: {filename}</div>}
          </div>

          <div>
            <div className="mb-2 flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-pill-text">Sections (this replaces the in-built section list entirely)</span>
              <button type="button" onClick={addSection} className="text-xs font-semibold text-accent">
                + Add section
              </button>
            </div>
            {sections.length === 0 && <div className="rounded-lg border border-dashed border-input-border p-4 text-sm text-muted">No sections yet -- upload a file above or add one manually.</div>}
            <div className="flex flex-col gap-2">
              {sections.map((s, i) => (
                <div key={s.key} className="flex items-center gap-2">
                  <span className="w-6 text-right text-xs text-muted">{i + 1}.</span>
                  <input
                    value={s.title}
                    onChange={(e) => updateSectionTitle(i, e.target.value)}
                    className="flex-1 rounded-md border border-input-border px-2.5 py-1.5 text-sm"
                  />
                  <button type="button" onClick={() => moveSection(i, -1)} disabled={i === 0} className="text-xs text-muted disabled:opacity-30">
                    ↑
                  </button>
                  <button type="button" onClick={() => moveSection(i, 1)} disabled={i === sections.length - 1} className="text-xs text-muted disabled:opacity-30">
                    ↓
                  </button>
                  <button type="button" onClick={() => removeSection(i)} className="text-xs font-semibold text-red-text">
                    Remove
                  </button>
                </div>
              ))}
            </div>
          </div>

          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={allowAiInferred} onChange={(e) => setAllowAiInferred(e.target.checked)} />
            Allow the AI to infer content from general SAP knowledge when a section has nothing grounding it (flagged
            clearly either way) -- otherwise it always stops at "needs input".
          </label>

          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-semibold text-slate-pill-text">Diagram section (optional)</span>
            <select
              value={diagramSectionKey}
              onChange={(e) => setDiagramSectionKey(e.target.value)}
              className="w-72 rounded-md border border-input-border px-2.5 py-1.5 text-sm"
            >
              <option value="">None</option>
              {sections.map((s) => (
                <option key={s.key} value={s.key}>
                  {s.title}
                </option>
              ))}
            </select>
            <span className="text-[11.5px] text-muted">
              That section will get a rendered process-flow diagram (and a screen wireframe, when relevant).
            </span>
          </label>
        </div>
      )}

      <div className="mt-5 flex gap-2.5">
        <button type="button" onClick={save} disabled={saving} className="rounded-lg bg-accent px-5 py-2.5 text-sm font-semibold text-white disabled:opacity-40">
          {saving ? 'Saving…' : 'Save'}
        </button>
      </div>
    </div>
  )
}
