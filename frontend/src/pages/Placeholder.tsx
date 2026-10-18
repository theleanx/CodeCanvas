import { Link } from 'react-router-dom'
import AppShell from '../components/AppShell'

interface PlaceholderProps {
  title: string
  note?: string
  projectName?: string
  projectNav?: { label: string; to: string }[]
}

export default function Placeholder({ title, note, projectName, projectNav }: PlaceholderProps) {
  return (
    <AppShell projectName={projectName} projectNav={projectNav}>
      <h1 className="m-0 font-heading text-2xl font-extrabold">{title}</h1>
      <div className="mt-6 rounded-2xl border border-dashed border-input-border bg-white p-10 text-center">
        <div className="text-sm text-muted">
          {note ?? 'Not built yet — this screen exists in the approved wireframe but the real implementation is still ahead of this one.'}
        </div>
        <Link to="/" className="mt-4 inline-block text-sm font-semibold text-accent no-underline">
          ← Back to Dashboard
        </Link>
      </div>
    </AppShell>
  )
}
