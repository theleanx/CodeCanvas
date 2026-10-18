# CodeCanvas

An agentic AI platform that turns SAP functional requirements into grounded Functional Specification Documents (FSDs) — and, as agents are added, carries that through TSD, code generation, code review, and unit tests.

The core principle: every section of a generated document is either **grounded** in a cited source fact, flagged **needs input**, or flagged **conflict**. Nothing is invented to fill a gap.

## What's built so far

- **FSD Creation agent**: extracts a fact ledger from pasted/uploaded source documents, drafts each FSD section against that ledger, and scores intake quality (grounded / needs-input / conflict %).
- **FastAPI backend** with real persistence (SQLite dev DB) for projects, tracked objects, and versioned FSD drafts.
- **Document parsing**: real server-side text extraction from `.docx` and `.pdf` (not just `.txt`/pasted text).
- **Auth**: JWT-based login, bcrypt password hashing, role-based access (`admin`, `module_lead`, `solution_architect`, `contributor`).
- **Role-gated dual approval**: an FSD draft needs Module Lead + Solution Architect approval when its quality score is below 80%; the UI only lets a user approve the slot matching their own role (or admin).
- **React + TypeScript + Tailwind frontend**: Dashboard → Project → Object → FSD Intake → FSD Review, wired end-to-end to the live backend.

## Not built yet

Feasibility, TSD, Code, Code Review, and Unit Test agents; GitHub integration for generated code; Project Overview/KPI dashboards and Agent Observability (deliberately not faked — they need real agent-run telemetry that doesn't exist yet); Settings; Project Brain document store.

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
