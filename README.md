# CodeCanvas

An agentic AI platform that turns SAP functional requirements into grounded Functional Specification Documents (FSDs) — and, as agents are added, carries that through TSD, code generation, code review, and unit tests.

The core principle: every section of a generated document is either **grounded** in a cited source fact, flagged **needs input**, or flagged **conflict**. Nothing is invented to fill a gap.

## What's built so far

- **FSD Creation agent**: extracts a fact ledger from pasted/uploaded source documents, drafts each FSD section against that ledger, and scores intake quality (grounded / needs-input / conflict %).
- **Enhancement-specific FSD template**: objects of type "Enhancement" get a different, more detailed 12-section template (Requirements, Solution Options, Current/Future Functionality, Functional Design & Process Logic, Process Flow, Performance Criteria, Error Handling, Dependencies & Config, Assumptions & Constraints, Security and Roles, Test Scenarios), plus a computed Document Identification block, a Review & Sign-off table, and a 9-point Validation table — all included in the on-screen review and every export. The Process Flow section also gets two rendered diagrams (a flowchart and, where relevant, a screen wireframe) drawn server-side from the agent's structured output, not invented pixels. Every other object type still uses the original generic nine-section template.
- **Reference Documents by link**: besides uploading a file or pasting text, a reference document can be a link to one file in a GitHub repo (or any other plain URL) — fetched and parsed on the server.
- **FastAPI backend** with real persistence (SQLite dev DB) for projects, tracked objects, and versioned FSD drafts.
- **Document parsing**: real server-side text extraction from `.docx` and `.pdf` (not just `.txt`/pasted text).
- **Auth**: JWT-based login, bcrypt password hashing, role-based access (`admin`, `module_lead`, `solution_architect`, `contributor`).
- **Role-gated dual approval**: an FSD draft needs Module Lead + Solution Architect approval when its quality score is below 80%; the UI only lets a user approve the slot matching their own role (or admin).
- **Add-context regeneration**: any Needs Input / Conflict section can take typed clarification, which is added as a new source and regenerates the whole draft as a new version — so any other section grounded in the same facts gets re-drafted too, not just the one flagged.
- **Export**: download an FSD as Markdown, Word (.docx), or PDF; optionally push it to a GitHub repo or a Google Drive folder (see below — both need their own env vars, downloads need none).
- **React + TypeScript + Tailwind frontend**: Dashboard → Project → Object → FSD Intake → FSD Review, wired end-to-end to the live backend.

## Not built yet

Feasibility, TSD, Code, Code Review, and Unit Test agents; GitHub integration for *generated SAP code* (the export push above is for the FSD document itself, a separate thing); Project Overview/KPI dashboards and Agent Observability (deliberately not faked — they need real agent-run telemetry that doesn't exist yet); Settings; Project Brain document store.

## Running it locally

### Backend

```bash
cd backend
python3 -m pip install -r ../requirements.txt
cp ../.env.example ../.env   # then fill in ANTHROPIC_API_KEY
python3 -m uvicorn backend.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server proxies `/api/*` to `http://127.0.0.1:8000`.

### Demo accounts

Password for all: `codecanvas123`

| Email | Role |
|---|---|
| `admin@codecanvas.demo` | Admin |
| `priya.nair@codecanvas.demo` | Module Lead |
| `ankit.buffalo@gmail.com` | Solution Architect |

On first run, the backend seeds these accounts plus a handful of demo projects/objects (Westlake Chemicals, Meijer AP Modernization, Tennant, CSL OneERP) so there's real data to click through immediately.

### Optional: export push targets

The three downloads (Markdown/Word/PDF) work with zero setup. The two push buttons on FSD Review are each gated by their own env vars — unset, they fail with a clear "not configured" message instead of crashing:

- **GitHub** — `GITHUB_EXPORT_TOKEN` (a PAT with `Contents: write` on the target repo) + `GITHUB_EXPORT_REPO` (`owner/repo`). Commits the FSD as Markdown to `fsd-exports/<project>/<object>/...` in that repo.
- **Google Drive** — `GOOGLE_SERVICE_ACCOUNT_JSON` (a service account key's full JSON) + `GOOGLE_DRIVE_FOLDER_ID` (a Drive folder shared with that service account's `client_email` as Editor). Uploads the FSD as a native Google Doc.

See `.env.example` for the full list.
