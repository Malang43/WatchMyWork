# WatchMyWork MVP

> Don’t explain the software you need. Show us how you work.

## Product contract

A Windows-local demonstration of spreadsheet upload, semantic browser teaching, Nemotron workflow inference, explicit human approval, deterministic browser execution, and an updated Excel export. Development and execution are limited to the bundled tracking mock site.

## User journey

1. Upload a UTF-8 CSV or .xlsx. See filename, record count, detected headers, and a five-row preview. Choose distinct existing input/output columns.
2. Select a populated example row. Start recording in the app, demonstrate its lookup in Chrome with the unpacked extension, wait for the extension to confirm the result was saved, then stop recording.
3. Optionally select another row and add a demonstration. Analyze the completed examples with Nemotron.
4. Review the inferred goal, columns, selectors, loop, steps, and exception behavior. Edit within the supported schema or show another example. Confirm explicitly.
5. Run the workflow. Previously demonstrated rows are preserved only for the exact original dataset. Remaining records are executed with Playwright, without per-row AI calls.
6. Pause/resume/stop, monitor progress, download the Excel checkpoint, review exceptions, save the confirmed workflow, or run again.
7. Reuse a saved workflow on a new upload with matching column names. No new teaching or inference is needed. Review before starting the new run.

## Supported scope

- Dashboard, New Workflow, Saved Workflows, Runs, Settings, and Research Metrics.
- Exactly the local mock site's fill → submit → read result → write spreadsheet pattern.
- Input headers are configurable; supported browser targets are not arbitrary websites.
- XLSX first worksheet or UTF-8 CSV; 1–10,000 records, 100 columns, 10 MB upload, 50 MB expanded XLSX limit. Headers must be unique/nonblank.
- All columns must already exist, including the destination column.
- Values are preserved in a new workbook; source formatting, macros, formulas, and additional worksheets are not preserved. Formula-like content is exported as literal text, never executable formulas.
- At most one active recording and one active/paused execution job in this local workspace.
- Blank/invalid/duplicate IDs and Not Found/uncertain results require manual review. Browser failures retry once, then fail safely. A missing result goes to manual review after retry.
- A human may resolve an exception with an explicitly reviewed value. The original dataset remains immutable.
- Free-model timeout/outage/invalid JSON produces a friendly Retry error. An explicit, labeled manual-review path can prepare the demonstrated supported steps without pretending AI succeeded.

## Confirmation and data safety

Workflow validation happens before storage/approval/execution. Any edit revokes approval. Each run stores an immutable plan snapshot. The executor has no LLM client and accepts no arbitrary code, URLs, or selectors. Browser network traffic is limited to 127.0.0.1:5173.

The root .env is backend-only. No key appears in API responses or frontend bundles. Spreadsheet values and extracted results stay local. Only column names, known action labels, supported CSS selectors, and templated values are sent to OpenRouter. SQLite contains local working data; metrics exports contain identifiers, counts, and timings only.

## Definition of done

- Original five-record mock site still passes tests and build.
- Backend tests cover uploads, schema restrictions, confirmation, checkpoints, retries, malformed AI output, timeouts, exports, and recovery.
- Frontend TypeScript/build and extension validation pass.
- The actual loaded extension records a browser example.
- Live Nemotron returns a valid workflow which the user confirms.
- Playwright processes sample data and export matches expected statuses.
- Pause/resume/stop, exception review, saved reuse, mobile layout, and no per-row AI calls are verified.
