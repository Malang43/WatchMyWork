"""Local, data-driven Playwright export and honest IBM Bob handoff."""
import json
import os
from pathlib import Path
from .schema import Workflow, developer

ROOT = Path(__file__).resolve().parents[1]

def generate(plan):
    plan = Workflow.model_validate(plan)
    if not developer(plan):
        raise ValueError('Select developer testing mode')
    lines = ["# Generated from the confirmed WatchMyWork workflow.", "# Run: .venv\\Scripts\\python.exe generated_test.spec.py", 'import json', 'from pathlib import Path', 'from playwright.sync_api import sync_playwright', '', "cases = json.loads(Path(__file__).with_name('test_cases.json').read_text(encoding='utf-8'))", 'failed = 0', 'with sync_playwright() as pw:', '    browser = pw.chromium.launch()', '    try:', '        for index, row in enumerate(cases, 1):', '            page = browser.new_page()', '            try:', f'                page.goto({plan.url!r})']
    for step, column in zip(plan.steps, plan.input_columns):
        lines.append(f'                page.locator({step.target!r}).fill(row[{column!r}])')
    lines += [f'                page.locator({plan.steps[2].target!r}).click()', f'                result = page.locator({plan.steps[-2].target!r})', "                result.wait_for(state='visible')", '                actual = result.inner_text()', f'                assert actual.strip().casefold() == row[{plan.expected_column!r}].strip().casefold(), "Expected and actual results differ"', "                print(f'Test {index}: PASS')", '            except Exception as exc:', '                failed += 1', "                print(f'Test {index}: FAIL/ERROR ({type(exc).__name__})')", '            finally:', '                page.close()', '    finally:', '        browser.close()', 'raise SystemExit(1 if failed else 0)', '']
    return '\n'.join(lines)

def report(run, dataset, results):
    plan = run['plan']
    return [{**r, 'test_case': r['row_index'] + 1, 'expected': dataset['rows'][r['row_index']][plan['expected_column']], 'actual': r['value']} for r in results]

def package(run, dataset, results):
    directory = Path(os.getenv('BOB_DEBUG_DIR', str(ROOT / 'bob_debug_package'))) / run['id']
    directory.mkdir(parents=True, exist_ok=True)
    rows = report(run, dataset, results)
    files = {'generated_test.spec.py': generate(run['plan']), 'test_cases.json': json.dumps(dataset['rows'], indent=2), 'failed_tests.json': json.dumps([r for r in rows if r['status'] in ('FAIL', 'ERROR')], indent=2), 'workflow.json': json.dumps(run['plan'], indent=2), 'runtime_logs.json': json.dumps([{'test_case': r['test_case'], 'status': r['status'], 'reason': r['reason'], 'retries': r['retries'], 'seconds': r['seconds']} for r in rows], indent=2), 'selectors.json': json.dumps([s['target'] for s in run['plan']['steps'] if s.get('target')], indent=2), 'failure_summary.md': '# IBM Bob debugging task\n\nAnalyze these failing Playwright tests. Determine whether the failure is caused by the test, selector, or application behavior. Suggest the smallest safe fix and rerun the affected tests.\n\nNo IBM Bob API was called. This package contains local test data; review it before sharing.\n\nStart the local mock site, then run the generated Python file with the project virtual environment. It loads test_cases.json from this directory and runs all cases, including blanks and duplicates.\n\n' + f"Run: {run['id']}\nState: {run['state']}\nFailures: {sum(r['status'] == 'FAIL' for r in rows)}\nRuntime errors: {sum(r['status'] == 'ERROR' for r in rows)}\n"}
    for name, content in files.items():
        (directory / name).write_text(content, encoding='utf-8')
    return str(directory)
