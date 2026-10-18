import { useEffect, useState } from 'react'
import { Route, Routes, useParams } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import NewProject from './pages/NewProject'
import ObjectDashboard from './pages/ObjectDashboard'
import ProjectBrain from './pages/ProjectBrain'
import ProjectWorkspace from './pages/ProjectWorkspace'
import FsdIntake from './pages/FsdIntake'
import FsdReview from './pages/FsdReview'
import Login from './pages/Login'
import Placeholder from './pages/Placeholder'
import RequireAuth from './components/RequireAuth'
import { getProject } from './lib/api'
import type { Project } from './lib/types'

const PROJECT_NAV = (projectId: string) => [
  { label: 'Overview', to: `/projects/${projectId}/overview` },
  { label: 'Custom Objects', to: `/projects/${projectId}` },
  { label: 'Project Brain', to: `/projects/${projectId}/brain` },
]

function ProjectScopedPlaceholder({ title, note }: { title: string; note?: string }) {
  const { projectId } = useParams<{ projectId: string }>()
  const [project, setProject] = useState<Project | null>(null)

  useEffect(() => {
    if (!projectId) return
    getProject(projectId)
      .then(setProject)
      .catch(() => setProject(null))
  }, [projectId])

  return (
    <Placeholder
      title={title}
      note={note}
      projectName={project?.name}
      projectNav={project ? PROJECT_NAV(project.id) : undefined}
    />
  )
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/*"
        element={
          <RequireAuth>
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/agent-observability" element={<Placeholder title="Agent Observability" />} />
              <Route path="/settings" element={<Placeholder title="Settings" />} />
              <Route path="/projects/new" element={<NewProject />} />
              <Route path="/projects/:projectId" element={<ProjectWorkspace />} />
              <Route
                path="/projects/:projectId/overview"
                element={
                  <ProjectScopedPlaceholder
                    title="Project Overview"
                    note="Project Dashboard (KPIs, burndown, status distribution) isn't wired up in this app yet — see the wireframe for the intended design. Building it honestly needs real agent-run telemetry to chart, which doesn't exist yet either."
                  />
                }
              />
              <Route path="/projects/:projectId/brain" element={<ProjectBrain />} />
              <Route path="/projects/:projectId/objects/:objectId" element={<ObjectDashboard />} />
              <Route path="/projects/:projectId/objects/:objectId/fsd/intake" element={<FsdIntake />} />
              <Route path="/projects/:projectId/objects/:objectId/fsd/review" element={<FsdReview />} />
              <Route path="*" element={<Placeholder title="Not found" note="That page doesn't exist." />} />
            </Routes>
          </RequireAuth>
        }
      />
    </Routes>
  )
}
