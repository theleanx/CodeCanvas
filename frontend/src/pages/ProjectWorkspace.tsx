import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import AppShell from '../components/AppShell'
import { ComplexityPill, OverallStatusPill, PipelinePill } from '../components/StatusPill'
import {
  ApiError,
  createObject,
  getProject,
  listComplexityConfigs,
  listModuleConfigs,
  listObjectTypeConfigs,
  listObjects,
} from '../lib/api'
import type { ComplexityConfig, ModuleConfig, ObjectType, ObjectTypeConfig, PipelineStage, Project, TrackedObject } from '../lib/types'

const PROJECT_NAV = (projectId: string) => [
  { label: 'Overview', to: `/projects/${projectId}/overview` },
  { label: 'Custom Objects', to: `/projects/${projectId}` },
  { label: 'Project Brain', to: `/projects/${projectId}/brain` },
  { label: 'Repository', to: `/projects/${projectId}/repository` },
]

type LoadState =
  | { phase: 'loading' }
  | { phase: 'error'; message: string }
  | {
      phase: 'done'
      project: Project
      objects: TrackedObject[]
      objectTypes: ObjectTypeConfig[]
      modules: ModuleConfig[]
      complexities: ComplexityConfig[]
    }

export default function ProjectWorkspace() {
  const { projectId } = useParams<{ projectId: string }>()
  const [state, setState] = useState<LoadState>({ phase: 'loading' })
  const [showAddForm, setShowAddForm] = useState(false)

  async function reload() {
    if (!projectId) return
    try {
      const [project, objects, objectTypes, modules, complexities] = await Promise.all([
        getProject(projectId),
        listObjects(projectId),
        listObjectTypeConfigs(projectId),
        listModuleConfigs(projectId),
        listComplexityConfigs(projectId),
      ])
      setState({ phase: 'done', project, objects, objectTypes, modules, complexities })
    } catch (err) {
      setState({ phase: 'error', message: err instanceof ApiError ? err.message : 'Could not load this project.' })
    }
  }

  useEffect(() => {
    setState({ phase: 'loading' })
    reload()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId])

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
        <div className="rounded-xl border border-red-border bg-red-soft px-5 py-4 text-sm text-red-text">
          {state.message}
        </div>
      </AppShell>
    )
  }

  const { project, objects, objectTypes, modules, complexities } = state
  const typeLabel = (key: ObjectType) => objectTypes.find((t) => t.internal_key === key)?.display_label ?? key

  return (
    <AppShell projectName={project.name} projectNav={PROJECT_NAV(project.id)} maxWidth="100%">
      <div className="mb-4 text-[13px] text-muted">
        <Link to="/" className="text-muted no-underline">
          Projects
        </Link>{' '}
        / <span className="text-ink">{project.name}</span>
      </div>

      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="m-0 font-heading text-[26px] font-extrabold">{project.name}</h1>
          <div className="mt-1 text-sm text-muted">
            {project.system_description || '—'} · {project.industry || '—'} · {project.geography || '—'}
          </div>
        </div>
        <button
          type="button"
          onClick={() => setShowAddForm((v) => !v)}
          className="whitespace-nowrap rounded-lg bg-accent px-5 py-3 text-sm font-semibold text-white"
        >
          {showAddForm ? 'Cancel' : '+ New Custom Object'}
        </button>
      </div>

      {showAddForm && (
        <AddObjectForm
          projectId={project.id}
          objectTypes={objectTypes}
          modules={modules}
          complexities={complexities}
          onCreated={() => {
            setShowAddForm(false)
            reload()
          }}
        />
      )}

      <div className="overflow-x-auto rounded-2xl border border-card-border bg-white">
        <table className="w-full min-w-[1250px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-card-border text-left text-xs font-semibold uppercase tracking-wide text-muted">
              <Th>Object ID</Th>
              <Th>Object</Th>
              <Th>Type</Th>
              <Th>Module</Th>
              <Th>Complexity</Th>
              <Th>Overall Status</Th>
              <Th>FSD</Th>
              <Th>Feasibility</Th>
              <Th>TSD</Th>
              <Th>Code Review</Th>
              <Th>Unit Test</Th>
              <Th>Code</Th>
            </tr>
          </thead>
          <tbody>
            {objects.map((obj) => (
              <tr key={obj.id} className="border-b border-divider last:border-0 hover:bg-app-bg/60">
                <td className="px-4 py-3 font-mono text-[12.5px] text-muted">{obj.object_code ?? '—'}</td>
                <td className="px-4 py-3 font-medium">
                  <Link
                    to={`/projects/${project.id}/objects/${obj.id}`}
                    className="font-semibold text-ink no-underline hover:text-accent"
                  >
                    {obj.name}
                  </Link>
                </td>
                <td className="px-4 py-3 text-muted">{typeLabel(obj.type)}</td>
                <td className="px-4 py-3 text-muted">{obj.module}</td>
                <td className="px-4 py-3">
                  <ComplexityPill level={obj.complexity} />
                </td>
                <td className="px-4 py-3">
                  <OverallStatusPill status={obj.overall_status} />
                </td>
                <td className="px-4 py-3">
                  <StagePillLink projectId={project.id} objectId={obj.id} tab="fsd" stage={obj.fsd_status} />
                </td>
                <td className="px-4 py-3">
                  <StagePillLink projectId={project.id} objectId={obj.id} tab="feasibility" stage={obj.feasibility_status} />
                </td>
                <td className="px-4 py-3">
                  <StagePillLink projectId={project.id} objectId={obj.id} tab="tsd" stage={obj.tsd_status} />
                </td>
                <td className="px-4 py-3">
                  <StagePillLink projectId={project.id} objectId={obj.id} tab="code_review" stage={obj.code_review_status} />
                </td>
                <td className="px-4 py-3">
                  <StagePillLink projectId={project.id} objectId={obj.id} tab="unit_test" stage={obj.unit_test_status} />
                </td>
                <td className="px-4 py-3">
                  <StagePillLink projectId={project.id} objectId={obj.id} tab="code" stage={obj.code_status} />
                </td>
              </tr>
            ))}

            {objects.length === 0 && (
              <tr>
                <td colSpan={12} className="px-4 py-8 text-center text-sm text-muted">
                  No custom objects yet. Add one to start an FSD.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </AppShell>
  )
}

function AddObjectForm({
  projectId,
  objectTypes,
  modules,
  complexities,
  onCreated,
}: {
  projectId: string
  objectTypes: ObjectTypeConfig[]
  modules: ModuleConfig[]
  complexities: ComplexityConfig[]
  onCreated: () => void
}) {
  const enabledTypes = objectTypes.filter((t) => t.enabled)
  const enabledModules = modules.filter((m) => m.enabled)
  const enabledComplexities = complexities.filter((c) => c.enabled)

  const [name, setName] = useState('')
  const [type, setType] = useState<ObjectType | ''>(enabledTypes[0]?.internal_key ?? '')
  const [module, setModule] = useState(enabledModules[0]?.name ?? '')
  const [complexity, setComplexity] = useState(enabledComplexities[0]?.name ?? '')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit() {
    if (!name.trim() || !type || !module || !complexity) return
    setSubmitting(true)
    setError(null)
    try {
      await createObject(projectId, { name: name.trim(), type, module, complexity })
      onCreated()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not create the object.')
      setSubmitting(false)
    }
  }

  const blockedReason =
    enabledTypes.length === 0
      ? 'No object types are enabled in Project Brain yet.'
      : enabledModules.length === 0
        ? 'No modules are enabled in Project Brain yet.'
        : enabledComplexities.length === 0
          ? 'No complexity levels are enabled in Project Brain yet.'
          : null

  if (blockedReason) {
    return (
      <div className="mb-5 rounded-2xl border border-amber-border bg-amber-soft p-5 text-sm text-amber-text">
        {blockedReason} Configure it in{' '}
        <Link to={`/projects/${projectId}/brain`} className="font-semibold underline">
          Project Brain
        </Link>{' '}
        before adding a custom object.
      </div>
    )
  }

  return (
    <div className="mb-5 flex flex-wrap items-end gap-3 rounded-2xl border border-card-border bg-white p-5">
      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-semibold text-slate-pill-text">Name</span>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Sales Order Enhancement"
          className="w-64 rounded-md border border-input-border px-3 py-2 text-sm"
        />
      </label>
      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-semibold text-slate-pill-text">Type</span>
        <select value={type} onChange={(e) => setType(e.target.value as ObjectType)} className="rounded-md border border-input-border px-3 py-2 text-sm">
          {enabledTypes.map((t) => (
            <option key={t.internal_key} value={t.internal_key}>
              {t.display_label}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-semibold text-slate-pill-text">Module</span>
        <select value={module} onChange={(e) => setModule(e.target.value)} className="rounded-md border border-input-border px-3 py-2 text-sm">
          {enabledModules.map((m) => (
            <option key={m.id} value={m.name}>
              {m.name}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-semibold text-slate-pill-text">Complexity</span>
        <select value={complexity} onChange={(e) => setComplexity(e.target.value)} className="rounded-md border border-input-border px-3 py-2 text-sm">
          {enabledComplexities.map((c) => (
            <option key={c.id} value={c.name}>
              {c.name}
            </option>
          ))}
        </select>
      </label>
      <button
        type="button"
        onClick={handleSubmit}
        disabled={!name.trim() || submitting}
        className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
      >
        {submitting ? 'Adding…' : 'Add'}
      </button>
      {error && <div className="w-full text-sm text-red-text">{error}</div>}
    </div>
  )
}

function Th({ children }: { children: ReactNode }) {
  return <th className="px-4 py-3 font-semibold">{children}</th>
}

// Each pipeline-stage pill jumps straight to that stage's tab on the
// object's dashboard, instead of only the object name going anywhere.
function StagePillLink({
  projectId,
  objectId,
  tab,
  stage,
}: {
  projectId: string
  objectId: string
  tab: string
  stage: PipelineStage
}) {
  return (
    <Link to={`/projects/${projectId}/objects/${objectId}?tab=${tab}`} className="no-underline">
      <PipelinePill stage={stage} />
    </Link>
  )
}
