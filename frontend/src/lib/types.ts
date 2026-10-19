// Mirrors backend/schemas.py and backend/api_schemas.py. Keep these in
// sync by hand -- there are only a handful of shapes and a shared-schema
// generator would be overkill at this stage.

export type FSDSectionStatus = 'grounded' | 'needs_input' | 'conflict' | 'ai_inferred'

export interface SourceDocumentIn {
  source_id: string
  label: string
  doc_type: string
  text: string
}

export interface LedgerEntry {
  entry_id: string
  fact: string
  source_id: string
  source_quote: string
  topic_hint: string | null
}

export interface FieldMappingRow {
  field: string
  source: string
  target: string
  rule_type: 'Direct Copy' | 'Conditional' | 'Derived' | string
  rule_detail: string
}

export interface ErrorHandlingRow {
  failure_point: string
  detection: string
  handling_rule: string
  user_notification: string
  remediation: string
}

export interface TestScriptRow {
  test_id: string
  scenario: string
  steps: string
  expected_result: string
}

export interface FSDSection {
  key: string
  title: string
  status: FSDSectionStatus
  content: string
  grounded_in: string[]
  needs_input_detail: string | null
  conflict_detail: string | null
  ai_inferred_note: string | null
  images: Record<string, string>
  // Structured tables -- only ever populated on one section key each (see
  // backend/schemas.py FSDSection), rendered as literal tables rather than
  // left as prose.
  field_mapping: FieldMappingRow[]
  error_rows: ErrorHandlingRow[]
  test_rows: TestScriptRow[]
}

// Only present on drafts for "Enhancement" objects -- the custom
// development-ready FSD template. Generic-template drafts leave all three
// of these null/undefined.
export interface DocumentIdentification {
  object_id: string
  title: string
  object_type: string
  development_type: string
  module: string
  project: string
  version: string
  status: string
  generated_on: string
  author: string
  sap_release: string
  transport_path: string
}

export interface ReviewSignoffRow {
  role: string
  name: string
  status: string
  date: string
}

export interface ValidationRow {
  point: string
  how_satisfied: string
  section: string
  pass: boolean
}

export type QualityTier = 'pass' | 'pass_with_condition' | 'not_advisable'

export interface QualityScore {
  green_pct: number
  yellow_pct: number
  red_pct: number
  overall_pct: number
  tier: QualityTier
  requires_dual_approval: boolean
  red_items: string[]
  yellow_items: string[]
}

// --- Auth -------------------------------------------------------------------

export type UserRole = 'admin' | 'module_lead' | 'solution_architect' | 'contributor'

export interface User {
  id: string
  email: string
  name: string
  role: UserRole
}

export interface TokenResponse {
  access_token: string
  token_type: 'bearer'
  user: User
}

// --- Real persisted domain data (backed by the API, not mock data) --------

export type ProjectKind = 'Greenfield' | 'Brownfield'

export interface Project {
  id: string
  name: string
  kind: ProjectKind
  system_description: string
  industry: string
  geography: string
  object_count: number
  updated_at: string
}

export interface ProjectCreate {
  name: string
  kind: ProjectKind
  system_description: string
  industry: string
  geography: string
}

// The six behavioral categories are fixed in code (they select an FSD
// template + Intake Validation checklist) -- a project can only relabel
// them for display (ProjectBrain's "object types" config), never add a
// genuinely new one, so this stays a closed union.
export type ObjectType = 'Report' | 'Interface' | 'Conversion' | 'Enhancement' | 'Form' | 'Workflow'
// Module and Complexity are each a free, per-project vocabulary configured
// in Project Brain -- no fixed set of values, so these are just `string`.
export type PipelineStage = 'Not Started' | 'In Progress' | 'Blocked' | 'On Hold' | 'Complete'

export interface TrackedObject {
  id: string
  project_id: string
  name: string
  object_code: string | null
  type: ObjectType
  module: string
  complexity: string
  cancelled: boolean
  fsd_status: PipelineStage
  feasibility_status: PipelineStage
  tsd_status: PipelineStage
  code_review_status: PipelineStage
  unit_test_status: PipelineStage
  code_status: PipelineStage
  // Computed server-side (backend/project_brain.py) -- never independently
  // editable, so it can't drift from the per-stage statuses it's built from.
  overall_status: string
  latest_fsd_version: number | null
}

export interface ObjectCreate {
  name: string
  type: ObjectType
  module: string
  complexity: string
}

// --- Project Brain --------------------------------------------------------

export const OBJECT_TYPE_INTERNAL_KEYS: ObjectType[] = ['Report', 'Interface', 'Conversion', 'Enhancement', 'Form', 'Workflow']
export const DOCUMENT_TYPES = ['FSD', 'TSD', 'Code Review', 'Test Script'] as const
export type DocumentType = (typeof DOCUMENT_TYPES)[number]

export interface ObjectTypeConfig {
  internal_key: ObjectType
  display_label: string
  id_prefix: string
  enabled: boolean
  sort_order: number
}

export interface ModuleConfig {
  id: string
  name: string
  id_code: string
  enabled: boolean
  sort_order: number
}

export interface ComplexityConfig {
  id: string
  name: string
  enabled: boolean
  sort_order: number
}

export interface DocumentTemplateSection {
  key: string
  title: string
}

export interface DocumentTemplate {
  document_type: DocumentType
  object_type_key: ObjectType
  source: 'in_built' | 'client_specific'
  uploaded_filename: string | null
  sections: DocumentTemplateSection[] | null
  diagram_section_key: string | null
  allow_ai_inferred: boolean
  updated_at: string | null
  updated_by: string | null
  in_built_sections: DocumentTemplateSection[] | null
  generation_available: boolean
}

export interface DocumentTemplateUploadResult {
  filename: string
  sections: DocumentTemplateSection[]
  raw_text: string
  char_count: number
}

export interface DocumentTemplateSave {
  source: 'in_built' | 'client_specific'
  uploaded_filename?: string | null
  sections?: DocumentTemplateSection[] | null
  diagram_section_key?: string | null
  allow_ai_inferred?: boolean
  raw_text?: string | null
}

export interface ApprovalState {
  module_lead_approved: boolean
  module_lead_approved_by: string | null
  module_lead_approved_at: string | null
  solution_architect_approved: boolean
  solution_architect_approved_by: string | null
  solution_architect_approved_at: string | null
}

export interface FsdDraftSummary {
  id: string
  version: number
  created_at: string
  request_id: string
  duration_ms: number
  overall_pct: number
  tier: QualityTier
  note: string
}

// --- Intake Validation --------------------------------------------------
// A second, independent assessment of a finished FSD draft -- an SAP
// delivery-readiness audit, distinct from the grounding-focused
// QualityScore above. Runs automatically with every generate/regenerate.

export type IntakeVerdict = 'ready' | 'needs_correction' | 'not_ready'
export type IntakeCheckStatus = 'pass' | 'warn' | 'fail' | 'cannot_verify'
export type IntakeSeverity = 'critical' | 'high' | 'medium' | 'low'

export interface IntakeRadarScores {
  clarity: number
  completeness: number
  feasibility: number
  technical_detail: number
  business_value: number
  security: number
  performance: number
  compliance: number
}

export interface IntakeQualityCheck {
  key: string
  title: string
  status: IntakeCheckStatus
  finding: string
  suggestion: string | null
}

export interface IntakeCorrection {
  severity: IntakeSeverity
  text: string
}

export interface IntakeChecklistItem {
  item_id: string
  category: string
  severity: IntakeSeverity
  check: string
  status: IntakeCheckStatus
  finding: string
}

export interface IntakeValidationResult {
  verdict: IntakeVerdict
  overall_pct: number
  radar: IntakeRadarScores
  assessment: string
  quality_checks: IntakeQualityCheck[]
  corrections: IntakeCorrection[]
  checklist: IntakeChecklistItem[]
}

export type IntakeValidationStatus = 'pending' | 'complete' | 'failed'

// Real token counts off the Anthropic response, plus a dollar estimate --
// null when the model that produced this draft isn't in the pricing table
// in backend/token_usage.py, rather than a guessed figure.
export interface TokenUsageOut {
  input_tokens: number
  output_tokens: number
  cost_usd: number | null
}

export interface FsdDraftOut {
  id: string
  object_id: string
  version: number
  created_at: string
  request_id: string
  duration_ms: number
  sources: SourceDocumentIn[]
  ledger: LedgerEntry[]
  sections: FSDSection[]
  quality_score: QualityScore
  approvals: ApprovalState
  note: string
  document_identification: DocumentIdentification | null
  review_signoff: ReviewSignoffRow[] | null
  validation_table: ValidationRow[] | null
  intake_validation_status: IntakeValidationStatus
  intake_validation: IntakeValidationResult | null
  intake_validation_error: string | null
  model_used: string | null
  token_usage_breakdown: Record<string, TokenUsageOut> | null
  token_usage_total: TokenUsageOut | null
  template_source: 'in_built' | 'client_specific' | null
  template_name: string | null
  generated_by: string | null
}
