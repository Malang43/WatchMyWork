# Working on WatchMyWork

## Scope and safety

- Preserve the independently working `mock-site` app on 127.0.0.1:5173.
- Automate only the bundled local mock verification site. Do not add third-party targets, authentication bypasses, CAPTCHA handling, or government-site automation.
- Never read aloud, print, overwrite, expose, or commit the root .env/API key. Backend configuration loads it privately. Never put a secret in a VITE_ environment variable.
- Spreadsheet values stay local. Strip record values from inference requests and metrics. Do not log full HTTP model responses or request authorization headers.
- Nemotron infers workflows; Playwright executes validated confirmed plans. No per-row model calls.
- Keep strict workflow schema/selector/origin validation and explicit confirmation before execution.
- Commit row checkpoints before advancing; do not reset or delete local datasets/results to conceal failures.

## Project map

- `backend`: Python FastAPI, SQLite, Pydantic, openpyxl, Playwright.
- `frontend`: primary React/TypeScript app on port 5174.
- `extension`: Manifest V3 semantic recorder; no build step.
- `mock-site`: standalone fake package verification app on port 5173.
- `sample-data`: synthetic CSV/XLSX inputs.
- `scripts`: sample generation and full browser test.

## Validation

From the repository root in Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q
npm.cmd --prefix frontend run build
npm.cmd --prefix mock-site test
npm.cmd --prefix mock-site run build
node extension/validate.mjs
```

With all three servers running, use `.\.venv\Scripts\python.exe scripts/e2e.py` for the real extension, live model, approval, executor, and export flow. It creates synthetic test data in the local database and writes ignored artifacts under `test-results`. Do not run overlapping end-to-end sessions or edit the frontend during the test: Vite reloads can interrupt browser assertions.

`scripts/e2e.py --manual` tests the explicitly labeled manual inference-outage path. It does not prove live Nemotron availability. Backend tests use isolated temporary databases and mock model responses; never point them at the user's working database.

Use `npm.cmd` if PowerShell blocks npm.ps1. Use `.venv\Scripts\python.exe` directly; activation is not required. Keep dependency locks current after intentional dependency changes.
