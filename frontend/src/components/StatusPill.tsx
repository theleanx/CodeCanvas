import type { PipelineStage, ObjectComplexity } from '../lib/types'

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

const COMPLEXITY_STYLES: Record<ObjectComplexity, string> = {
  Low: 'bg-green-soft text-green',
  Medium: 'bg-amber-soft text-amber',
  High: 'bg-red-soft text-red-text',
}

export function ComplexityPill({ level }: { level: ObjectComplexity }) {
  return (
    <span
      className={`inline-block whitespace-nowrap rounded-full px-2.5 py-1 text-[11px] font-bold ${COMPLEXITY_STYLES[level]}`}
    >
      {level}
    </span>
  )
}
