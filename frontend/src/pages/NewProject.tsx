import { useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import AppShell from '../components/AppShell'
import { ApiError, createProject } from '../lib/api'
import type { ProjectKind } from '../lib/types'

export default function NewProject() {
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [kind, setKind] = useState<ProjectKind>('Greenfield')
  const [systemDescription, setSystemDescription] = useState('')
  const [industry, setIndustry] = useState('')
  const [geography, setGeography] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!name.trim()) return
    setSubmitting(true)
    setError(null)
    try {
      const project = await createProject({
        name: name.trim(),
        kind,
        system_description: systemDescription.trim(),
        industry: industry.trim(),
        geography: geography.trim(),
      })
      navigate(`/projects/${project.id}`)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not create the project.')
      setSubmitting(false)
    }
  }

  return (
    <AppShell maxWidth="620px">
      <h1 className="m-0 font-heading text-2xl font-extrabold">New Project</h1>
      <div className="mt-1 text-sm text-muted">
        A project is a closed context — its own Objects, Project Brain, and approval history.
      </div>

      <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-4 rounded-2xl border border-card-border bg-white p-6">
        <Field label="Project name">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Westlake Chemicals"
            className="w-full rounded-md border border-input-border px-3 py-2 text-sm"
            required
          />
        </Field>

        <Field label="Project kind">
          <div className="flex gap-2">
            {(['Greenfield', 'Brownfield'] as ProjectKind[]).map((k) => (
              <button
                key={k}
                type="button"
                onClick={() => setKind(k)}
                className={`rounded-md border px-4 py-2 text-sm font-semibold ${
                  kind === k ? 'border-accent bg-accent-soft text-accent' : 'border-input-border bg-white text-slate-pill-text'
                }`}
              >
                {k}
              </button>
            ))}
          </div>
        </Field>

        <Field label="System">
          <input
            value={systemDescription}
            onChange={(e) => setSystemDescription(e.target.value)}
            placeholder="e.g. SAP S/4HANA Private Edition · 2023"
            className="w-full rounded-md border border-input-border px-3 py-2 text-sm"
          />
        </Field>

        <div className="grid grid-cols-2 gap-4">
          <Field label="Industry">
            <input
              value={industry}
              onChange={(e) => setIndustry(e.target.value)}
              placeholder="e.g. Chemical"
              className="w-full rounded-md border border-input-border px-3 py-2 text-sm"
            />
          </Field>
          <Field label="Geography">
            <input
              value={geography}
              onChange={(e) => setGeography(e.target.value)}
              placeholder="e.g. US, Germany"
              className="w-full rounded-md border border-input-border px-3 py-2 text-sm"
            />
          </Field>
        </div>

        {error && <div className="text-sm text-red-text">{error}</div>}

        <button
          type="submit"
          disabled={!name.trim() || submitting}
          className="mt-2 rounded-lg bg-accent py-3 text-sm font-bold text-white disabled:cursor-not-allowed disabled:opacity-40"
        >
          {submitting ? 'Creating…' : 'Create Project'}
        </button>
      </form>
    </AppShell>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-[13px] font-semibold text-slate-pill-text">{label}</span>
      {children}
    </label>
  )
}
