import type {
  ComplexityConfig,
  DocumentTemplate,
  DocumentTemplateSave,
  DocumentTemplateUploadResult,
  DocumentType,
  FsdDraftOut,
  FsdDraftSummary,
  ModuleConfig,
  ObjectCreate,
  ObjectType,
  ObjectTypeConfig,
  PipelineStage,
  Project,
  ProjectCreate,
  ProjectDocument,
  SourceDocumentIn,
  TokenResponse,
  TrackedObject,
  User,
} from './types'
import { getToken } from './authStorage'

// In dev, Vite's proxy (vite.config.ts) forwards '/api/*' to the FastAPI
// backend on :8000, so this stays relative and needs no env config.
const API_BASE = ''

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

// AuthProvider registers itself here so a 401 from any API call (token
// expired, server restarted and invalidated in-memory secrets, etc.) can
// clear the session and bounce to /login, without api.ts importing React
// context machinery.
let onUnauthorized: (() => void) | null = null
export function setUnauthorizedHandler(handler: (() => void) | null) {
  onUnauthorized = handler
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken()
  const headers: Record<string, string> = init?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }
  if (token) headers.Authorization = `Bearer ${token}`

  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { ...headers, ...init?.headers },
  })

  if (!res.ok) {
    let detail = `Request failed (${res.status})`
    try {
      const body = await res.json()
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      // response wasn't JSON -- fall back to the generic message
    }
    if (res.status === 401 && path !== '/api/auth/login') {
      onUnauthorized?.()
    }
    throw new ApiError(res.status, detail)
  }

  if (res.status === 204) return undefined as T
  return res.json()
}

// --- auth ---

export function login(email: string, password: string) {
  return request<TokenResponse>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
}

export function getMe() {
  return request<User>('/api/auth/me')
}

// --- health ---

export function checkHealth() {
  return request<{ status: string; agent_key_configured: boolean; template_sections: string[] }>('/api/health')
}

// --- projects ---

export function listProjects() {
  return request<Project[]>('/api/projects')
}

export function createProject(payload: ProjectCreate) {
  return request<Project>('/api/projects', { method: 'POST', body: JSON.stringify(payload) })
}

export function getProject(projectId: string) {
  return request<Project>(`/api/projects/${projectId}`)
}

export function deleteProject(projectId: string) {
  return request<void>(`/api/projects/${projectId}`, { method: 'DELETE' })
}

// --- objects ---

export function listObjects(projectId: string) {
  return request<TrackedObject[]>(`/api/projects/${projectId}/objects`)
}

export function createObject(projectId: string, payload: ObjectCreate) {
  return request<TrackedObject>(`/api/projects/${projectId}/objects`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function getObject(objectId: string) {
  return request<TrackedObject>(`/api/objects/${objectId}`)
}

export type PipelineStageKey = 'fsd' | 'feasibility' | 'tsd' | 'code_review' | 'unit_test' | 'code'

export function setObjectStageStatus(objectId: string, stage: PipelineStageKey, status: PipelineStage) {
  return request<TrackedObject>(`/api/objects/${objectId}/status`, {
    method: 'PATCH',
    body: JSON.stringify({ stage, status }),
  })
}

export function setObjectCancelled(objectId: string, cancelled: boolean) {
  return request<TrackedObject>(`/api/objects/${objectId}/cancel`, {
    method: 'PATCH',
    body: JSON.stringify({ cancelled }),
  })
}

// --- Project Brain ---

export function listObjectTypeConfigs(projectId: string) {
  return request<ObjectTypeConfig[]>(`/api/projects/${projectId}/brain/object-types`)
}

export function updateObjectTypeConfig(
  projectId: string,
  internalKey: ObjectType,
  patch: Partial<Pick<ObjectTypeConfig, 'display_label' | 'id_prefix' | 'enabled'>>,
) {
  return request<ObjectTypeConfig>(`/api/projects/${projectId}/brain/object-types/${internalKey}`, {
    method: 'PATCH',
    body: JSON.stringify(patch),
  })
}

export function listModuleConfigs(projectId: string) {
  return request<ModuleConfig[]>(`/api/projects/${projectId}/brain/modules`)
}

export function createModuleConfig(projectId: string, name: string, idCode?: string) {
  return request<ModuleConfig>(`/api/projects/${projectId}/brain/modules`, {
    method: 'POST',
    body: JSON.stringify({ name, id_code: idCode || undefined }),
  })
}

export function updateModuleConfig(
  projectId: string,
  moduleId: string,
  patch: Partial<Pick<ModuleConfig, 'name' | 'id_code' | 'enabled'>>,
) {
  return request<ModuleConfig>(`/api/projects/${projectId}/brain/modules/${moduleId}`, {
    method: 'PATCH',
    body: JSON.stringify(patch),
  })
}

export function deleteModuleConfig(projectId: string, moduleId: string) {
  return request<void>(`/api/projects/${projectId}/brain/modules/${moduleId}`, { method: 'DELETE' })
}

export function listComplexityConfigs(projectId: string) {
  return request<ComplexityConfig[]>(`/api/projects/${projectId}/brain/complexities`)
}

export function createComplexityConfig(projectId: string, name: string) {
  return request<ComplexityConfig>(`/api/projects/${projectId}/brain/complexities`, {
    method: 'POST',
    body: JSON.stringify({ name }),
  })
}

export function updateComplexityConfig(
  projectId: string,
  complexityId: string,
  patch: Partial<Pick<ComplexityConfig, 'name' | 'enabled'>>,
) {
  return request<ComplexityConfig>(`/api/projects/${projectId}/brain/complexities/${complexityId}`, {
    method: 'PATCH',
    body: JSON.stringify(patch),
  })
}

export function deleteComplexityConfig(projectId: string, complexityId: string) {
  return request<void>(`/api/projects/${projectId}/brain/complexities/${complexityId}`, { method: 'DELETE' })
}

export function listDocumentTemplates(projectId: string) {
  return request<DocumentTemplate[]>(`/api/projects/${projectId}/brain/document-templates`)
}

export function uploadDocumentTemplate(projectId: string, file: File) {
  const form = new FormData()
  form.append('file', file)
  return request<DocumentTemplateUploadResult>(`/api/projects/${projectId}/brain/document-templates/upload`, {
    method: 'POST',
    body: form,
  })
}

export function saveDocumentTemplate(
  projectId: string,
  documentType: DocumentType,
  objectTypeKey: ObjectType,
  payload: DocumentTemplateSave,
) {
  return request<DocumentTemplate>(
    `/api/projects/${projectId}/brain/document-templates/${encodeURIComponent(documentType)}/${objectTypeKey}`,
    { method: 'PUT', body: JSON.stringify(payload) },
  )
}

// --- FSD drafts ---

export function listFsdDrafts(objectId: string) {
  return request<FsdDraftSummary[]>(`/api/objects/${objectId}/fsd-drafts`)
}

export function getLatestFsdDraft(objectId: string) {
  return request<FsdDraftOut>(`/api/objects/${objectId}/fsd-drafts/latest`)
}

export function getFsdDraft(draftId: string) {
  return request<FsdDraftOut>(`/api/fsd-drafts/${draftId}`)
}

export function generateFsdDraft(objectId: string, sources: SourceDocumentIn[], note = '') {
  return request<FsdDraftOut>(`/api/objects/${objectId}/fsd-drafts`, {
    method: 'POST',
    body: JSON.stringify({ sources, note }),
  })
}

export function setApproval(draftId: string, role: 'module_lead' | 'solution_architect', approved: boolean) {
  return request<FsdDraftOut>(`/api/fsd-drafts/${draftId}/approval`, {
    method: 'PATCH',
    body: JSON.stringify({ role, approved }),
  })
}

export function rerunIntakeValidation(draftId: string) {
  return request<FsdDraftOut>(`/api/fsd-drafts/${draftId}/intake-validation/rerun`, { method: 'POST' })
}

// --- export / push ---

export type ExportFormat = 'markdown' | 'docx' | 'pdf'

// Downloads need the raw response (filename + binary blob), not the
// JSON-shaped `request<T>()` helper above, so this talks to fetch directly
// -- but still attaches the same auth header and 401 handling.
export async function downloadFsdExport(draftId: string, format: ExportFormat): Promise<void> {
  const token = getToken()
  const headers: Record<string, string> = {}
  if (token) headers.Authorization = `Bearer ${token}`

  const res = await fetch(`${API_BASE}/api/fsd-drafts/${draftId}/export/${format}`, { headers })
  if (!res.ok) {
    if (res.status === 401) onUnauthorized?.()
    let detail = `Export failed (${res.status})`
    try {
      const body = await res.json()
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      // not JSON -- keep the generic message
    }
    throw new ApiError(res.status, detail)
  }

  const disposition = res.headers.get('Content-Disposition') || ''
  const match = disposition.match(/filename="([^"]+)"/)
  const filename = match ? match[1] : `fsd-export.${format === 'markdown' ? 'md' : format}`

  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

// Same pattern as downloadFsdExport above, but for the Intake Validation
// assessment -- a separate report from the FSD content itself.
export async function downloadIntakeValidationPdf(draftId: string): Promise<void> {
  const token = getToken()
  const headers: Record<string, string> = {}
  if (token) headers.Authorization = `Bearer ${token}`

  const res = await fetch(`${API_BASE}/api/fsd-drafts/${draftId}/export/intake-validation-pdf`, { headers })
  if (!res.ok) {
    if (res.status === 401) onUnauthorized?.()
    let detail = `Download failed (${res.status})`
    try {
      const body = await res.json()
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      // not JSON -- keep the generic message
    }
    throw new ApiError(res.status, detail)
  }

  const disposition = res.headers.get('Content-Disposition') || ''
  const match = disposition.match(/filename="([^"]+)"/)
  const filename = match ? match[1] : 'intake-validation.pdf'

  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export interface PushResult {
  url: string
  detail: string
}

export function pushFsdToGithub(draftId: string) {
  return request<PushResult>(`/api/fsd-drafts/${draftId}/push/github`, { method: 'POST' })
}

export function pushFsdToGoogleDrive(draftId: string) {
  return request<PushResult>(`/api/fsd-drafts/${draftId}/push/google-drive`, { method: 'POST' })
}

// --- documents ---

export async function extractDocument(file: File) {
  const form = new FormData()
  form.append('file', file)
  return request<{ filename: string; text: string; char_count: number }>('/api/documents/extract', {
    method: 'POST',
    body: form,
  })
}

export function fetchDocumentLink(url: string) {
  return request<{ label: string; text: string; char_count: number }>('/api/documents/fetch-link', {
    method: 'POST',
    body: JSON.stringify({ url }),
  })
}

// --- Project Repository ---

export function listProjectDocuments(projectId: string, category?: string) {
  const qs = category ? `?category=${encodeURIComponent(category)}` : ''
  return request<ProjectDocument[]>(`/api/projects/${projectId}/documents${qs}`)
}

export function uploadProjectDocument(projectId: string, file: File, category: string, notes = '') {
  const form = new FormData()
  form.append('file', file)
  const qs = `?category=${encodeURIComponent(category)}&notes=${encodeURIComponent(notes)}`
  return request<ProjectDocument>(`/api/projects/${projectId}/documents${qs}`, {
    method: 'POST',
    body: form,
  })
}

export function deleteProjectDocument(documentId: string) {
  return request<void>(`/api/project-documents/${documentId}`, { method: 'DELETE' })
}

// Same blob-download pattern as downloadFsdExport above.
export async function downloadProjectDocument(documentId: string, fallbackFilename: string): Promise<void> {
  const token = getToken()
  const headers: Record<string, string> = {}
  if (token) headers.Authorization = `Bearer ${token}`

  const res = await fetch(`${API_BASE}/api/project-documents/${documentId}/download`, { headers })
  if (!res.ok) {
    if (res.status === 401) onUnauthorized?.()
    let detail = `Download failed (${res.status})`
    try {
      const body = await res.json()
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      // not JSON -- keep the generic message
    }
    throw new ApiError(res.status, detail)
  }

  const disposition = res.headers.get('Content-Disposition') || ''
  const match = disposition.match(/filename="([^"]+)"/)
  const filename = match ? match[1] : fallbackFilename

  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
