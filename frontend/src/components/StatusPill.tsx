import type { PipelineStage } from '../lib/types'

const PIPELINE_STYLES: Record<PipelineStage, string> = {
  'Not Started': 'bg-slate-pill-bg text-slate-pill-text',
  'In Progress': 'bg-accent-soft text-accent',
  Blocked: 'bg-red-soft text-red-text',
  'On Hold': 'bg-amber-soft text-amber',
  Complete: 'bg-green-soft text-green',
}

export function PipelinePill({ stage }: { stage: PipelineStage }) {
  return (
    <span
      className={`inline-block whitespace-nowrap rounded-full px-2.5 py-1 text-[11px] font-bold ${PIPELINE_STYLES[stage]}`}
    >
      {stage}
    </span>
  )
}

// Complexity is a free, per-project vocabulary (Project Brain) rather than a
// fixed Low/Medium/High union, so this colors the common default labels
// while still rendering any client-defined level neutrally.
const COMPLEXITY_STYLES: Record<string, string> = {
  low: 'bg-green-soft text-green',
  medium: 'bg-amber-soft text-amber',
  high: 'bg-red-soft text-red-text',
}

export function ComplexityPill({ level }: { level: string }) {
  const style = COMPLEXITY_STYLES[level.toLowerCase()] ?? 'bg-slate-pill-bg text-slate-pill-text'
  return <span className={`inline-block whitespace-nowrap rounded-full px-2.5 py-1 text-[11px] font-bold ${style}`}>{level}</span>
}

// The computed object-level roll-up (backend/project_brain.py's
// compute_overall_status) -- never independently stored, so this just
// colors whatever string comes back rather than enumerating every stage x
// status combination.
export function OverallStatusPill({ status }: { status: string }) {
  const lower = status.toLowerCase()
  let style = 'bg-slate-pill-bg text-slate-pill-text'
  if (lower === 'cancelled') style = 'bg-red-soft text-red-text'
  else if (lower === 'complete') style = 'bg-green-soft text-green'
  else if (lower === 'not started') style = 'bg-slate-pill-bg text-slate-pill-text'
  else if (lower.includes('on hold')) style = 'bg-amber-soft text-amber'
  else if (lower.includes('in progress')) style = 'bg-accent-soft text-accent'
  return <span className={`inline-block whitespace-nowrap rounded-full px-2.5 py-1 text-[11px] font-bold ${style}`}>{status}</span>
}
