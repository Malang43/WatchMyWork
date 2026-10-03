# Adaptive Recovery Agent delivery report

## Files changed

| Area | Files |
|---|---|
| Recovery and execution | `backend/recovery.py` (new), `backend/executor.py`, `backend/main.py`, `backend/schema.py`, `backend/storage.py`, `backend/config.py` |
| Reporting | `backend/developer.py`, `backend/sheets.py` |
| UI | `frontend/src/RecoveryPanel.tsx` (new), `frontend/src/main.tsx` |
| Recorder | `extension/recorder.js` |
| Bundled fixture | `mock-site/src/DeveloperPortal.tsx`, `mock-site/src/main.tsx` |
| Tests | `backend/tests/test_recovery.py` (new), `backend/tests/test_deployment.py`, `scripts/recovery_e2e.py` (new), `scripts/developer_e2e.py`, `scripts/weather_e2e.py` |
| Documentation/configuration | `.env.example`, `README.md`, `ARCHITECTURE.md`, this report |

The existing Dockerfile, Railway configuration and dependency locks need no changes. No new dependencies were required; installed Python requirements passed `pip check`. The root `.env` was not inspected or changed. Pre-existing changes involving `.pytest_tmp` were left untouched.

## Architecture and behavior

The existing confirmed workflow and Playwright worker remain authoritative. A failed action invokes local semantic discovery and ranking. Nemotron can choose only a discovered compatible candidate through a strict Pydantic result. An unavailable or malformed response falls back to local ranking. New repairs require explicit approval; Playwright rechecks the candidate, performs the original action, observes the row result, checkpoints it, and only then saves successful memory. Ordinary execution and memory reuse do not call the model per row.

SQLite's existing `objects` table stores `recovery` and `recovery_memory` entities without destructive migrations. The UI adds approval/rejection/stop controls and recovery history; Excel adds a Recoveries worksheet; Bob's existing runtime log includes recovery audit records. The original PASS/FAIL/ERROR fields and standalone generated test remain compatible. Standalone test exports do not include the interactive recovery agent.

## API and environment

```text
GET  /runs/{id}/recoveries
POST /runs/{id}/recoveries/{recovery_id}/approve
POST /runs/{id}/recoveries/{recovery_id}/reject
```

Existing stop/resume controls are reused. `POST /runs` accepts optional `recovery_demo: true` for a developer workflow. This changes Login to Sign In with a different ID only in that run's private browser.

The only new environment variable is optional backend-only `TAVILY_API_KEY`. On Railway, add **`TAVILY_API_KEY=<your Tavily key>`** only if external fallback is desired. Preserve `OPENROUTER_API_KEY`, `DATABASE_PATH`, `BOB_DEBUG_DIR`, origin and other existing deployment settings.

Tavily runs only after local recovery is inconclusive and uses the original domain filter. Loopback sites and absent credentials skip it. Returned URLs must match the configured origin and an explicitly bundled page. The developer alias `/developer/sign-in` supports the navigation recovery flow; arbitrary same-domain paths and third-party sites remain blocked. Navigation needs approval and is followed by fresh local discovery. Public search results for the Railway demo are not guaranteed.

## Validation evidence

- Backend suite: 93 passed; one existing Starlette/httpx deprecation warning.
- Frontend TypeScript and production build: passed. No standalone frontend unit-test script exists.
- Mock site: 23 tests passed; normal and Railway `/demo-static/` builds passed.
- Extension manifest, host restrictions, worker routing and JavaScript validation: passed.
- Developer E2E: real extension and live Nemotron inference passed; six cases, five PASS, one deliberate assertion FAIL, zero runtime errors; export and Bob package verified.
- Recovery E2E: real browser Login → Sign In repair, UI approval, resumed execution, later-row and next-run memory reuse, no additional AI calls on reuse, Excel and Bob recovery audit passed. This observed recovery used the deterministic local fallback; the AI recovery selection path also passes mocked structured-response tests.
- Weather E2E: real Open-Meteo results, real extension, three coordinate rows, Excel export and zero per-row calls passed. Workflow inference used the explicitly labeled manual outage path.
- Security checks: no API-key patterns found in the source scan; row-value redaction, arbitrary selector rejection, stale/ambiguous candidates, cross-domain URLs, wrong-run approvals and missing/unavailable providers tested.
- Production configuration tests: passed, including the bundled recovery alias. Railway itself was not deployed; live Tavily was not exercised.

The first recovery browser attempt exposed nested event-loop use. It paused without losing checkpoints; provider I/O was moved into its own bounded thread, and the preserved run resumed successfully. Existing E2E assertions for renamed UI labels/Bob downloads were corrected. No datasets or failure records were deleted to reset validation.

Browser validation used an isolated database under ignored `test-results/recovery-validation-*.sqlite3`. Screenshots are `test-results/recovery-approval.png` and `test-results/recovery-complete.png`; packages are under `test-results/recovery-bob/`. Working user data was not used for these sessions.

## Local commands

Run each server in its own PowerShell terminal from the repository root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

```powershell
npm.cmd --prefix frontend run dev -- --host 127.0.0.1 --port 5174
```

```powershell
npm.cmd --prefix mock-site run dev -- --host 127.0.0.1 --port 5173
```

Validation commands:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q
npm.cmd --prefix frontend run build
npm.cmd --prefix mock-site test
npm.cmd --prefix mock-site run build
node extension/validate.mjs
```

For isolated E2E testing, set a new database and debug directory in the backend terminal **before** starting the backend. Never remove working datasets to reset a demo:

```powershell
$env:DATABASE_PATH = Join-Path (Get-Location) ('test-results/e2e-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.sqlite3')
$env:BOB_DEBUG_DIR = Join-Path (Get-Location) 'test-results/e2e-bob'
```

With all three servers running, execute these sequentially, without editing the frontend during a session:

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/developer_e2e.py
.\.venv\Scripts\python.exe -X utf8 scripts/recovery_e2e.py
.\.venv\Scripts\python.exe -X utf8 scripts/weather_e2e.py --manual
```

The recovery script expects no previous approved mapping, or it can resume its interrupted paused fixture run. Normal app runs reuse existing memory by design.

## Remaining manual steps

1. Reload the unpacked Chrome extension and refresh demo tabs. GitHub ZIP installation is documented in README and linked from Settings.
2. Finish a normal developer run, then choose **Run Recovery Demo** and approve the first repair. Later runs show memory reuse.
3. Optionally configure the backend/Railway Tavily key and redeploy through your existing Railway workflow. No key is needed for local recovery.
4. Verify the deployed UI and extension against your actual Railway domain after deployment.
