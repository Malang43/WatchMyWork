# WatchMyWork

**Don't explain the software you need. Show us how you work.**

A Windows-local MVP: spreadsheet - browser demonstration - semantic recording - Nemotron inference - human confirmation - deterministic Playwright execution - updated Excel.

## Local addresses

| Component | URL |
| --- | --- |
| Main WatchMyWork app | http://127.0.0.1:5174/ |
| Open-Meteo weather demo | http://127.0.0.1:5173/ |
| Backend health | http://127.0.0.1:8000/health |
| API documentation | http://127.0.0.1:8000/docs |

Use **127.0.0.1**, not localhost, in browser tabs. The extension and browser executor intentionally match the exact local mock origin.

## Weather demo

The `mock-site` page now looks up real current temperature from [Open-Meteo](https://open-meteo.com/en/docs), replacing its hard-coded tracking records. It runs independently of the main app and backend, with no API key, signup, or authentication.

```powershell
npm.cmd --prefix mock-site run dev
```

Open **http://127.0.0.1:5173/**. Enter latitude **33.6844** and longitude **73.0479** (Islamabad), then click **Check Weather** or press Enter. The result displays the temperature returned by the API in °C; no fixed weather values are used.

The browser sends only the entered coordinates to:

```text
https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}&current=temperature_2m
```

Latitude must be between -90 and 90, and longitude between -180 and 180. Empty/invalid inputs, network failures, a 10-second request timeout, HTTP failures, and malformed responses display friendly errors. Changing either coordinate clears the old result and cancels any outstanding lookup.

Stable automation targets:

| Element | Selector | Accessible label / name |
| --- | --- | --- |
| Latitude | `#latitude-input` | Latitude / `latitude` |
| Longitude | `#longitude-input` | Longitude / `longitude` |
| Submit | `#check-weather-button` | Check Weather / `checkWeather` |
| Temperature only | `#temperature-result` | Current temperature in Celsius / `temperature` |
| Result state | `#weather-result` | `data-state`: idle, loading, success, error |

On success, `#temperature-result` contains text such as `24.7 °C` and exposes the numeric value in `data-temperature`. It is empty before success or after an error.

**Integration boundary:** the main frontend, backend, extension, workflow schema, and executor are unchanged and still use tracking-specific fields/selectors. The weather page has semantic targets ready for future integration, but the existing tracking automation and its old end-to-end tests cannot operate on this replacement page. The original tracking instructions below are retained as reference, not as the current weather workflow.

## Windows setup

Requirements: Python 3.13, Node.js 24, npm, and desktop Google Chrome. Run commands in PowerShell from the WatchMyWork project folder. Use `npm.cmd` to avoid PowerShell npm.ps1 execution-policy issues. No virtual-environment activation is needed.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-lock.txt
.\.venv\Scripts\python.exe -m playwright install chromium
npm.cmd --prefix mock-site ci
npm.cmd --prefix frontend ci
```

The existing root `.env` must contain `OPENROUTER_API_KEY`. **Keep the existing file; do not overwrite it.** `.env.example` is an empty template only for new installations. Never paste the key into frontend code or give it a `VITE_` prefix. The mock site does not need the key. Settings shows whether the backend has a key without displaying it.

The included sample files are ready to use. To regenerate them:

```powershell
.\.venv\Scripts\python.exe scripts/generate_sample.py
```

## Start the three local servers

Open three PowerShell terminals in this project folder. Leave all three running.

**Terminal 1 - backend**

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

Use a single backend process. Do not add `--workers` or `--reload` during an execution run. If you restart the backend, interrupted runs become paused and can resume from saved checkpoints.

**Terminal 2 - mock site** (keep an existing server if it is already running)

```powershell
npm.cmd --prefix mock-site run dev
```

**Terminal 3 - main app**

```powershell
npm.cmd --prefix frontend run dev
```

Open http://127.0.0.1:5174/. Stop each server with Ctrl+C in its terminal. Vite uses strict ports: if a port is occupied, reuse the existing WatchMyWork server or stop that server before restarting it.

## Load the Chrome extension

1. Open `chrome://extensions` in desktop Chrome.
2. Turn on **Developer Mode**.
3. Click **Load unpacked**.
4. Select this project's **extension** folder (the folder containing `manifest.json`).
5. Optionally pin WatchMyWork to the toolbar.
6. Open or refresh http://127.0.0.1:5173/. The lower-right recorder panel should say WatchMyWork is ready.

The extension is plain Manifest V3 JavaScript, with no build step. After updating it, click Reload on its extension card and refresh the mock-site tab. It records only the bundled mock site, only while you have started Teach Mode. It never records passwords, arbitrary pages, or mouse movements.

## Hackathon Demo — 2 Minute Flow

**Original tracking flow:** these steps require the former tracking page and do not apply to the weather replacement. For the current standalone demo, use the latitude/longitude walkthrough above. No weather integration changes were made to the workflow engine or extension.

Before presenting: start all servers, load the extension, open the main app and mock site in adjacent Chrome tabs, and have `sample-data/tracking-demo.xlsx` ready. Check that Settings says Nemotron is configured. Free-model latency varies; rehearse once before presenting.

1. **0:00-0:15 - Show the problem.** On Dashboard, say: "Don't explain the software you need. Show us how you work." Choose **New Workflow**, upload `tracking-demo.xlsx`, and keep input **Tracking ID** and output **Status**. Show the 20 records and preview. Continue to Teach.
2. **0:15-0:35 - Teach one example.** Click **Start Recording**. Switch to the mock-site tab and wait until the extension says **Recording**. Type `PK100001`, click **Check Status**, and see **Delivered**. Wait for the panel to start with **Result saved**. Return to the main app and click **Stop Recording**. Point out READ, FILL, CLICK, READ, WRITE in the timeline.
3. **0:35-1:10 - Infer and approve.** Click **Analyze Workflow**. Explain that Nemotron generalizes the example once, rather than being called on every row. Review the goal and four steps. Click **Confirm Workflow**, then **Run Workflow**. Nothing runs before confirmation.
4. **1:10-1:40 - Repeat safely.** Show live counts and the progress bar. Pause/resume if there is time. The demonstrated first row is already saved; Playwright executes the remaining unique populated valid IDs. The sample intentionally produces **4 successful, 16 manual-review, 0 failed** before any human resolutions.
5. **1:40-2:00 - Show the outcome.** Click **Download Updated Excel**. The first four rows contain Delivered, Pending, In Transit, Returned. The Exceptions worksheet explains unknown, duplicate, blank, and invalid records. Choose **Review Exceptions**, then **Save Workflow**. In Saved Workflows, show that a new spreadsheet can reuse the confirmed pattern without teaching again. Research Metrics shows inference calls and execution counts.

If the free model times out or is busy, use **Retry**. Demonstrations remain saved. For a service outage, **Review demonstrated steps manually (without AI)** is an explicitly labeled human-review path, or reuse a previously confirmed saved workflow. Neither path claims a live model inference occurred. Do not present the manual path as a Nemotron result.

## What the original tracking sample contains (unchanged)

Both `sample-data/tracking-demo.xlsx` and `.csv` contain 20 fake rows: all five known mock IDs, unknown IDs, duplicates (including case/whitespace variants), one blank, and one invalid string. Only the first occurrence of an ID is automatically processed. Duplicates are sent to review, not silently copied or dropped.

| ID | Mock response | Automation outcome |
| --- | --- | --- |
| PK100001 | Delivered | Successful |
| PK100002 | Pending | Successful |
| PK100003 | In Transit | Successful |
| PK100004 | Returned | Successful |
| PK100005 | Not Found | Manual review |

Unknown IDs return Not Found. Blank/invalid/duplicate records enter the exception queue. A website or selector failure retries once, then fails safely. A missing/unrecognized result goes to manual review. Each completed outcome is committed to SQLite before the next row. Pause/stop take effect at the next row/retry boundary; an in-flight lookup may finish.

## Results, reuse, and local storage

- Downloads are available during and after runs. They contain the latest checkpoint, not only a final file.
- Unprocessed/unresolved output cells retain their original values. The Exceptions worksheet lists unresolved completed records.
- Finish or stop a run before resolving an exception with a reviewed value. Download again to include corrections.
- Saved Workflows accepts a new spreadsheet with the same input/output header names, without another model call. Renaming mappings requires another demonstration.
- Runs survive page refreshes and browser closure. After a backend restart they resume from the Runs page; already-completed rows are skipped.
- Working data is in `backend/data/watchmywork.sqlite3` (SQLite WAL). Keep this folder private. It contains local spreadsheets and demonstrations; it is ignored by Git.
- Metrics JSON is downloadable from Research Metrics and contains IDs, counts, timings, and corrections, not spreadsheet values.
- Only selected column names, known semantic labels, selectors, and template placeholders leave the machine for OpenRouter. Record values, extracted result text, and full spreadsheets do not.

The uploader reads the first XLSX worksheet or a UTF-8 CSV. Files must be under 10 MB with 1-10,000 records, at most 100 columns, and unique nonblank headers. The input and destination columns must both exist and differ. The exported workbook preserves cell values as text; it does not preserve original formatting, formulas, macros, or other worksheets. This MVP intentionally supports the demonstrated local tracking pattern only.

## Quality checks

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q
npm.cmd --prefix frontend run typecheck
npm.cmd --prefix frontend run build
npm.cmd --prefix mock-site test
npm.cmd --prefix mock-site run build
node extension/validate.mjs
```

With the weather demo running on port 5173, run its browser checks using the existing Python environment:

```powershell
.\.venv\Scripts\python.exe mock-site/tests/browser_weather.py
```

To also verify a real Open-Meteo request and compare the rendered temperature with its response:

```powershell
.\.venv\Scripts\python.exe mock-site/tests/browser_weather.py --live
```

Weather unit tests use controlled responses for reliable coverage. Browser checks verify accessible selectors, validation, keyboard submission, temperature display, network/HTTP/malformed response errors, timeout recovery, cancellation of stale requests, and mobile layout. `--live` additionally requires internet access and a reachable Open-Meteo service. It does not use Nemotron, the backend, or the extension.

The legacy tracking integration scripts remain unchanged for reference and require the former tracking page; they are not weather tests:

```powershell
# scripts/e2e.py, scripts/e2e.py --manual, scripts/browser_checks.py
```

Backend tests use temporary databases and mocked model responses. They include malformed response/API timeout, unsafe plan rejection, approval gates, interrupted run recovery, retries/browser failures, spreadsheet export, and privacy checks. Browser-test artifacts are written to ignored `test-results/`, including screenshots, the exported workbook, and a JSON summary. The pre-existing `test_nemotron.py` is unchanged and can still be run separately; it is not the deterministic backend test suite.

## Troubleshooting

- **Backend not connected:** start Terminal 1 and visit `/health`. Ensure ports 8000, 5173, and 5174 are available.
- **No recording events:** load/reload the extension and refresh the mock tab. Use the exact 127.0.0.1 URL. Start Recording in the app before doing the lookup, and wait for the recorder panel to say Recording.
- **Incomplete demonstration:** use the exact displayed example ID, click Check Status, and wait for the panel's **Result saved** message before stopping. Add Demonstration selects another row; click Start Recording to begin it.
- **Nemotron unavailable:** check network access, key configuration, and free-model availability. Retry preserves your examples. The API never exposes provider response bodies or keys.
- **Browser unavailable:** run the Playwright Chromium install command again. Resume an interrupted run after fixing the browser setup.
- **Paused run blocks a new run:** resume or stop the existing run from Runs. The MVP intentionally executes one job at a time.
- **API explorer mutations rejected:** custom clients must send `X-WatchMyWork: local-demo`; the app/extension already do so.

## Project files

- `frontend/` - main React + TypeScript workspace.
- `backend/` - FastAPI, strict workflow schema, SQLite persistence, inference, spreadsheet handling, executor, tests.
- `extension/` - Manifest V3 semantic recorder and validator.
- `mock-site/` - independent React weather lookup demo powered by Open-Meteo.
- `sample-data/` - fake XLSX and CSV demo inputs.
- `scripts/` - sample generation and browser integration test.
- `PROJECT_SPEC.md` - supported behavior and acceptance criteria.
- `ARCHITECTURE.md` - boundaries, data flow, checkpoint lifecycle, API map.
- `AGENTS.md` - contributor safety and validation instructions.
- `.env.example` - empty backend configuration template.

`.gitignore` excludes `.env`, `.env.*`, local databases, dependencies, builds, and test artifacts, while allowing `.env.example`. The scaffold does not initialize a Git repository; those rules apply once you initialize one. Never force-add secrets or local working data.

## Implementation references

[FastAPI file uploads](https://fastapi.tiangolo.com/tutorial/request-files/), [Chrome extension messaging](https://developer.chrome.com/docs/extensions/develop/concepts/messaging), [Playwright browser contexts](https://playwright.dev/python/docs/api/class-browsercontext), and [OpenRouter API](https://openrouter.ai/docs/api_reference/overview).

## Developer testing demo (primary)

Open http://127.0.0.1:5174 and upload `sample-data/developer-tests.csv`.
Choose Developer testing, Email + Password inputs, Expected Result, Actual Result,
and Status. Start recording, open http://127.0.0.1:5173/developer, enter the
first row, and click Login. Wait for “Test demonstration captured,” then analyze,
review and confirm. Generate Playwright Test exports a ZIP with a reusable
`generated_test.spec.py` and local `test_cases.json`. Python matches the existing
Playwright backend and requires no new dependencies.

Run Test Suite executes every row, including blanks and duplicates. Actual
results remain unchanged; assertions trim and case-fold both sides. PASS and
FAIL are assertions; ERROR indicates an automation failure, retried once.
Download Updated Excel includes actual results and the selected status column.
Prepare Bob Debug Package writes `bob_debug_package/<run-id>/` locally. Open it
in IBM Bob IDE; no Bob API is called. Packages contain local test data and are
ignored by Git. Add authentic Bob task summary screenshots to `bob_sessions/`;
PNG files there are not ignored.

Run the three servers in separate PowerShell terminals from the repository root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
npm.cmd --prefix frontend run dev -- --host 127.0.0.1 --port 5174
npm.cmd --prefix mock-site run dev -- --host 127.0.0.1 --port 5173
```

Load unpacked `extension/` in Chrome, then refresh the portal after extension
updates. The weather example remains at http://127.0.0.1:5173/.

Full browser validation (no overlapping sessions):

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/developer_e2e.py
```

This uses the real extension and inference endpoint and creates synthetic data,
including one intentional FAIL to verify reporting. It reports whether Nemotron
or the semantic fallback produced the workflow. Inference may take up to three
120-second attempts; fallback does not prove live model availability. To run the
export independently, extract both files together and invoke the generated Python
file using this repository's `.venv\Scripts\python.exe`. A failed assertion
returns exit code 1 after executing all cases.
