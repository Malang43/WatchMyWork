import { StrictMode, useCallback, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import { API, api, post } from './api';
import type { Dataset, Demo, Workflow, Run, Dashboard, ExceptionItem, Plan } from './api';
import './styles.css';

type Page = 'Dashboard' | 'New Workflow' | 'Saved Workflows' | 'Runs' | 'Settings' | 'Research Metrics';
const icons: Record<string, string> = { Dashboard: 'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z', 'New Workflow': 'M12 5v14 M5 12h14', 'Saved Workflows': 'M5 3h14v18l-7-4-7 4z', Runs: 'M8 5l12 7-12 7z', Settings: 'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8 M12 2v3 M12 19v3 M2 12h3 M19 12h3 M5 5l2 2 M17 17l2 2 M5 19l2-2 M17 7l2-2', 'Research Metrics': 'M4 20V10 M12 20V4 M20 20v-7' };
function Icon({ name }: { name: string }) { return <svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={icons[name] || icons.Runs} /></svg>; }
const formatDate = (date: string) => new Date(date).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
const inputColumns = (plan: { input_columns?: string[]; input_column: string }) => plan.input_columns || [plan.input_column];
const label = (value: string) => value.replaceAll('_', ' ');
function Badge({ value }: { value: string }) { return <span className={`badge ${value}`}>{label(value)}</span>; }
function Empty({ title, children }: { title: string; children: ReactNode }) { return <div className="empty"><span className="empty-icon"><Icon name="Saved Workflows" /></span><h3>{title}</h3>{children}</div>; }
function ErrorBox({ text, retry }: { text: string; retry?: () => void }) { return <div className="error-box" role="alert"><span>{text}</span>{retry && <button className="small secondary" onClick={retry}>Retry</button>}</div>; }
function useResource<T>(path: string, interval = 0) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState('');
  const [version, setVersion] = useState(0);
  const refresh = useCallback(() => setVersion(v => v + 1), []);
  useEffect(() => {
    let active = true;
    let fetching = false;
    const controller = new AbortController();
    async function load() {
      if (fetching) return;
      fetching = true;
      try { const next = await api<T>(path, { signal: controller.signal }); if (active) { setData(next); setError(''); } }
      catch (e) { if (active) setError((e as Error).message); }
      finally { fetching = false; }
    }
    setData(null); void load();
    const timer = interval ? window.setInterval(load, interval) : undefined;
    return () => { active = false; controller.abort(); clearInterval(timer); };
  }, [path, interval, version]);
  return { data, error, refresh };
}
function App() {
  const [page, setPage] = useState<Page>('Dashboard');
  const [selectedRun, setSelectedRun] = useState<string | null>(null);
  const [reuse, setReuse] = useState<Workflow | null>(null);
  const [wizardKey, setWizardKey] = useState(0);
  const health = useResource<{ ok: boolean; api_key_configured: boolean }>('/health', 10000);
  function navigate(next: Page) { setPage(next); if (next === 'Runs') setSelectedRun(null); }
  function startNew(workflow: Workflow | null = null) {
    void api<{ id: string } | null>('/teach/current').then(active => {
      if (active) { setPage('New Workflow'); return; }
      sessionStorage.removeItem('watchmywork-wizard'); setReuse(workflow); setWizardKey(v => v + 1); setPage('New Workflow');
    }).catch(() => setPage('New Workflow'));
  }
  function viewRun(id: string) { setSelectedRun(id); setPage('Runs'); }
  return <div className="app-shell">
    <a className="skip-link" href="#main">Skip to content</a>
    <aside className="sidebar"><a className="brand" href="#" onClick={e => { e.preventDefault(); navigate('Dashboard'); }}><span className="brand-mark">w</span>WatchMyWork<span className="brand-period">.</span></a><div className="workspace-label">YOUR WORKSPACE <span>LOCAL</span></div>
      <nav aria-label="Main navigation">{(['Dashboard', 'New Workflow', 'Saved Workflows', 'Runs', 'Settings'] as Page[]).map(item => <button key={item} className={`nav-item ${page === item ? 'active' : ''}`} aria-current={page === item ? 'page' : undefined} onClick={() => navigate(item)}><Icon name={item} />{item}</button>)}</nav>
      <div className="sidebar-bottom"><div className="local-card"><span className={`connection-dot ${health.data ? '' : 'offline'}`} /><strong>{health.data ? 'Local workspace connected' : 'Backend not connected'}</strong><p>Your spreadsheet stays on this computer.</p></div><button className="nav-item" onClick={() => navigate('Research Metrics')}><Icon name="Research Metrics" />Research Metrics</button><div className="profile"><span>WM</span><div><strong>Demo workspace</strong><small>WatchMyWork MVP</small></div></div></div>
    </aside>
    <div className="content-shell"><header className="topbar"><span>Workspace <span className="slash">/</span> <strong>{page}</strong></span><span className="local-pill"><span /> LOCAL DEMO</span></header>
      <main id="main" className="main-content">
        {page === 'Dashboard' && <DashboardPage onNew={() => startNew()} onRun={viewRun} onSaved={() => navigate('Saved Workflows')} />}
        <div hidden={page !== 'New Workflow'}><Wizard key={wizardKey} reuse={reuse} onRun={id => { sessionStorage.removeItem('watchmywork-wizard'); setReuse(null); setWizardKey(v => v + 1); viewRun(id); }} /></div>
        {page === 'Saved Workflows' && <SavedPage onReuse={startNew} />}
        {page === 'Runs' && (selectedRun ? <RunPage id={selectedRun} onRun={viewRun} onBack={() => setSelectedRun(null)} /> : <RunsPage onRun={viewRun} />)}
        {page === 'Settings' && <SettingsPage configured={health.data?.api_key_configured ?? false} />}
        {page === 'Research Metrics' && <MetricsPage />}
      </main><footer className="app-footer">WatchMyWork <span>Developer workflow automation and automated web testing.</span></footer>
    </div>
  </div>;
}
function PageHeading({ eyebrow, title, description, action }: { eyebrow?: string; title: string; description: string; action?: ReactNode }) { return <div className="page-heading"><div>{eyebrow && <p className="eyebrow">{eyebrow}</p>}<h1>{title}</h1><p className="muted">{description}</p></div>{action}</div>; }
function DashboardPage({ onNew, onRun, onSaved }: { onNew: () => void; onRun: (id: string) => void; onSaved: () => void }) {
  const { data, error, refresh } = useResource<Dashboard>('/dashboard', 5000);
  return <><PageHeading eyebrow="OVERVIEW" title="Show one browser test. Generate and run the rest." description="WatchMyWork learns a developer’s browser testing workflow from demonstration, converts it into a reusable Playwright workflow, executes test cases automatically, and reports failures for debugging." action={<button onClick={onNew}><Icon name="New Workflow" />New Workflow</button>} />
    {error && <ErrorBox text={error} retry={refresh} />}
    <div className="stats-grid">{[['Workflows created', data?.workflows_created, 'Ready to repeat'], ['Records processed', data?.records_processed, 'Across all your runs'], ['Successful automations', data?.successful_automations, 'Verified and written back'], ['Manual-review items', data?.manual_review_items, 'Waiting for your judgment']].map(([name, count, caption]) => <div className="stat-card" key={String(name)}><span>{name}</span><strong>{count === undefined ? '—' : Number(count).toLocaleString()}</strong><small>{caption}</small></div>)}</div>
    <section className="hero-card"><div><span className="eyebrow">SHOW. CONFIRM. AUTOMATE.</span><h2>Teach one browser test.<br />Run the whole test suite.</h2><p>Turn one browser demonstration into a repeatable workflow.<br />You stay in control, from the first example to the final row.</p><button onClick={onNew}>Teach your first workflow <span aria-hidden="true">↗</span></button></div><div className="flow-illustration" aria-label="Spreadsheet to demonstration to automation"><div><span>01</span><strong>Your spreadsheet</strong><small>A clear starting point</small></div><i>↓</i><div><span>02</span><strong>One demonstration</strong><small>We learn the pattern</small></div><i>↓</i><div className="illustration-final"><span>✓</span><strong>Every row, handled</strong><small>Reviewed. Repeatable. Yours.</small></div></div></section>
    <div className="dashboard-bottom"><section className="panel"><div className="section-header"><h2>Recent workflows</h2><button className="text-button" onClick={onSaved}>View saved ↗</button></div>{data?.recent_workflows.length ? <div className="list">{data.recent_workflows.map(w => <div className="list-row" key={w.id}><span className="row-icon"><Icon name="Saved Workflows" /></span><div className="grow"><strong>{w.plan.workflow_name}</strong><small>{formatDate(w.created_at)} · {w.run_count} runs</small></div><Badge value={w.confirmed ? 'confirmed' : 'draft'} /></div>)}</div> : <Empty title="Your first workflow starts here"><p>Teach a task once, then make it repeatable.</p><button className="secondary small" onClick={onNew}>Create a workflow</button></Empty>}</section>
    <section className="panel"><div className="section-header"><h2>Recent activity</h2><span className="subtle-label">LIVE</span></div>{data?.recent_runs.length ? data.recent_runs.map(r => <button className="activity-row" key={r.id} onClick={() => onRun(r.id)}><div><strong>{r.plan.workflow_name}</strong><small>{r.processed} / {r.total} records</small></div><Badge value={r.state} /></button>) : <Empty title="A little quiet. For now."><p>Run activity and results will appear here.</p></Empty>}</section></div>
  </>;
}
function Wizard({ reuse, onRun }: { reuse: Workflow | null; onRun: (id: string) => void }) {
  const [step, setStep] = useState(1);
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [input, setInput] = useState(reuse ? inputColumns(reuse.plan)[0] : '');
  const [input2, setInput2] = useState(reuse ? inputColumns(reuse.plan)[1] || '' : '');
  const inputs = [input, input2].filter(Boolean);
  const [mode, setMode] = useState(reuse?.plan.mode || 'developer');
  const [expected, setExpected] = useState(reuse?.plan.expected_column || 'Expected Result');
  const [status, setStatus] = useState(reuse?.plan.status_column || 'Status');
  const [generated, setGenerated] = useState('');
  const mapping = { mode, expected_column: mode === 'developer' ? expected : null, status_column: mode === 'developer' ? status : null };
  const [output, setOutput] = useState(reuse?.plan.destination_column || '');
  const [workflow, setWorkflow] = useState<Workflow | null>(reuse);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  const [demos, setDemos] = useState<Demo[]>([]);
  const [rowIndex, setRowIndex] = useState(0);
  const [row, setRow] = useState<Record<string, string>>({});
  const [inferenceAttempt, setInferenceAttempt] = useState(1);
  useEffect(() => {
    if (!busy.includes('Nemotron') || !dataset) return;
    let live = true;
    const poll = async () => {
      try { const status = await api<{ attempt: number }>(`/inference/${dataset.id}/status`, { signal: AbortSignal.timeout(5000) }); if (live && status.attempt) setInferenceAttempt(status.attempt); } catch { /* The main request owns error handling. */ }
    };
    const timer = setInterval(poll, 750);
    return () => { live = false; clearInterval(timer); };
  }, [busy, dataset]);
  const [inferenceFailed, setInferenceFailed] = useState(false);
  const [editing, setEditing] = useState(false);
  const [json, setJson] = useState('');
  const [restored, setRestored] = useState(false);
  const active = demos.find(d => d.state === 'recording');
  const complete = demos.filter(d => d.state === 'complete' && JSON.stringify(inputColumns(d)) === JSON.stringify(inputs) && d.destination_column === output && (d.mode || 'lookup') === mode && (mode !== 'developer' || (d.expected_column === expected && d.status_column === status)));
  useEffect(() => {
    let live = true;
    async function restore() {
      try {
        const saved = JSON.parse(sessionStorage.getItem('watchmywork-wizard') || 'null');
        if (saved?.dataset_id && !reuse) {
          const d = await api<Dataset>(`/datasets/${saved.dataset_id}`);
          const w = saved.workflow_id ? await api<Workflow>(`/workflows/${saved.workflow_id}`) : null;
          if (live) { setDataset(d); setMode(saved.mode || 'lookup'); setExpected(saved.expected || 'Expected Result'); setStatus(saved.status || 'Status'); setInput(saved.input); setInput2(saved.input2 || ''); setOutput(saved.output); setRowIndex(saved.rowIndex || 0); setWorkflow(w); setStep(w ? 3 : saved.step === 2 ? 2 : 1); }
        }
      } catch { sessionStorage.removeItem('watchmywork-wizard'); }
      finally { if (live) setRestored(true); }
    }
    void restore(); return () => { live = false; };
  }, [reuse]);
  useEffect(() => {
    if (restored && dataset) sessionStorage.setItem('watchmywork-wizard', JSON.stringify({ dataset_id: dataset.id, workflow_id: workflow?.id, input, input2, output, rowIndex, step, mode, expected, status }));
  }, [restored, dataset, workflow, input, input2, output, rowIndex, step, mode, expected, status]);
  useEffect(() => {
    if (!dataset || step !== 2) return;
    let live = true;
    const poll = async () => { try { const d = await api<Demo[]>(`/demos?dataset_id=${dataset.id}`); if (live) setDemos(d); } catch (e) { if (live) setError((e as Error).message); } };
    void poll(); const timer = setInterval(poll, 800);
    return () => { live = false; clearInterval(timer); };
  }, [dataset, step]);
  useEffect(() => { if (!dataset) return; let live = true; void api<Record<string, string>>(`/datasets/${dataset.id}/rows/${rowIndex}`).then(r => { if (live) setRow(r); }).catch(e => { if (live) setError(e.message); }); return () => { live = false; }; }, [dataset, rowIndex]);
  async function task(name: string, fn: () => Promise<void>) { setError(''); setBusy(name); try { await fn(); } catch (e) { setError((e as Error).message); } finally { setBusy(''); } }
  async function upload(file: File) { await task('Uploading', async () => { const form = new FormData(); form.append('file', file); const d = await api<Dataset>('/datasets', { method: 'POST', body: form }); setDataset(d); setInput(reuse ? inputColumns(reuse.plan)[0] : d.columns.find(c => c === 'Email') || d.columns.find(c => c === 'Latitude') || d.columns[0]); setInput2(reuse ? inputColumns(reuse.plan)[1] || '' : d.columns.find(c => c === 'Password') || d.columns.find(c => c === 'Longitude') || ''); setMode(reuse?.plan.mode || (d.columns.includes('Email') ? 'developer' : 'lookup')); setOutput(reuse?.plan.destination_column || d.columns.find(c => c === 'Actual Result') || d.columns.find(c => c === 'Current Temperature (\u00b0C)') || d.columns.find(c => c.toLowerCase() === 'status') || d.columns[1] || ''); setRowIndex(0); setDemos([]); }); }
  async function record() { await task('Starting recording', async () => { if (!dataset) return; const d = await post<Demo>('/demos', { dataset_id: dataset.id, row_index: rowIndex, input_columns: inputs, destination_column: output, ...mapping }); setDemos(old => [d, ...old]); }); }
  async function stop() { if (!active) return; await task('Saving demonstration', async () => { const d = await post<Demo>(`/demos/${active.id}/stop`); setDemos(old => old.map(item => item.id === d.id ? d : item)); if (d.state !== 'complete') throw new Error('This example is incomplete. Wait for Recording, fill all shown inputs, perform the lookup, and wait for the result before stopping. Add a demonstration to try again.'); }); }
  async function analyze(manual = false) { setInferenceAttempt(1); await task(manual ? 'Preparing review' : 'Nemotron is analyzing', async () => { if (!dataset) return; try { const w = await api<Workflow>(manual ? '/workflows/manual' : '/workflows/infer', { method: 'POST', body: JSON.stringify({ dataset_id: dataset.id, input_columns: inputs, destination_column: output, ...mapping }), signal: AbortSignal.timeout(390000) }); setWorkflow(w); setStep(3); setInferenceFailed(false); } catch (e) { setInferenceFailed(true); throw e; } }); }
  async function run() { await task('Starting run', async () => { if (!workflow || !dataset) return; const r = await post<Run>('/runs', { workflow_id: workflow.id, dataset_id: dataset.id }); onRun(r.id); }); }
  return <><PageHeading eyebrow={reuse ? 'REUSE A WORKFLOW' : 'NEW WORKFLOW'} title={reuse ? 'Same workflow. Fresh data.' : 'Show us how you work.'} description="Start with your data. Teach a pattern. Approve every step." />
    <ol className="stepper">{['Upload Test Cases', 'Teach Test', 'Review Learned Test', 'Test Report'].map((s, i) => <li className={step === i + 1 ? 'current' : step > i + 1 ? 'done' : ''} key={s}><span>{step > i + 1 ? '✓' : `0${i + 1}`}</span>{s}</li>)}</ol>
    {error && <ErrorBox text={error} retry={inferenceFailed && !busy ? () => void analyze() : undefined} />}
    {busy && <div className="busy-banner" role="status"><span className="spinner" />{busy.includes('Nemotron') ? inferenceAttempt === 1 ? 'Analyzing demonstration with Nemotron...' : `Nemotron is taking longer than usual — retrying (${inferenceAttempt}/3)...` : `${busy}...`}{busy.includes('Nemotron') && <span>Your demonstration is saved. Each attempt can take up to 2 minutes.</span>}</div>}
    {step === 1 && <section className="panel wizard-panel"><div className="section-header"><div><h2>Upload Test Cases</h2><p className="muted">Configure test data, demonstrate once, then review and run.</p></div><span className="subtle-label">STEP 01</span></div>
      <label className="upload-zone"><span className="upload-symbol">↑</span><strong>{dataset ? dataset.filename : 'Choose your spreadsheet'}</strong><span>Excel (.xlsx) or UTF-8 CSV · Up to 10 MB</span><input aria-label="Upload spreadsheet" type="file" accept=".xlsx,.csv" disabled={Boolean(busy)} onChange={e => { const f = e.target.files?.[0]; if (f) void upload(f); }} /></label>
      <p className="sample-link">Just exploring? <a href={`${API}/samples/developer`}>Download developer test cases ↗</a></p>
      {dataset && <><div className="file-summary"><strong>{dataset.filename}</strong><Badge value={`${dataset.record_count} records`} /><span>{dataset.columns.length} detected columns</span></div><div className="fields"><label>Workflow mode<select aria-label="Workflow mode" value={mode} disabled={Boolean(reuse)} onChange={e => setMode(e.target.value)}><option value="developer">Developer testing</option><option value="lookup">Weather / lookup example</option></select></label><label>Input 1<select aria-label="Input 1" value={input} disabled={Boolean(reuse)} onChange={e => setInput(e.target.value)}><option value="">Select a column</option>{dataset.columns.map(c => <option key={c}>{c}</option>)}</select></label><label>Input 2 (optional)<select aria-label="Input 2 (optional)" value={input2} disabled={Boolean(reuse)} onChange={e => setInput2(e.target.value)}><option value="">None - single input</option>{dataset.columns.map(c => <option key={c}>{c}</option>)}</select></label><label>Destination / output column<select aria-label="Destination / output column" value={output} disabled={Boolean(reuse)} onChange={e => setOutput(e.target.value)}><option value="">Select a column</option>{dataset.columns.map(c => <option key={c}>{c}</option>)}</select></label></div>{mode === 'developer' && <div className="fields"><label>Expected output<select aria-label="Expected output" value={expected} disabled={Boolean(reuse)} onChange={e => setExpected(e.target.value)}>{dataset.columns.map(c => <option key={c}>{c}</option>)}</select></label><label>Test status<select aria-label="Test status" value={status} disabled={Boolean(reuse)} onChange={e => setStatus(e.target.value)}>{dataset.columns.map(c => <option key={c}>{c}</option>)}</select></label></div>}<div className="table-wrap"><table><caption>Preview · first {dataset.preview.length} records</caption><thead><tr>{dataset.columns.map(c => <th key={c}>{c}</th>)}</tr></thead><tbody>{dataset.preview.map((r, i) => <tr key={i}>{dataset.columns.map(c => <td key={c}>{r[c] || <span className="muted">—</span>}</td>)}</tr>)}</tbody></table></div></>}
      <div className="panel-actions"><span className="privacy-note">◈ Your spreadsheet stays local.</span><button disabled={(mode === 'developer' && (inputs.length !== 2 || new Set([...inputs, output, expected, status]).size !== 5 || !dataset?.columns.includes(expected) || !dataset?.columns.includes(status))) || !dataset || !input || !output || inputs.includes(output) || input === input2 || inputs.some(c => !dataset.columns.includes(c)) || !dataset.columns.includes(output) || Boolean(busy)} onClick={() => { setError(''); setStep(reuse ? 3 : 2); }}>{reuse ? 'Review Workflow' : 'Continue to Teach'} →</button></div>
    </section>}
    {step === 2 && dataset && <div className="teach-layout"><section className="panel wizard-panel"><div className="section-header"><div><h2>Teach WatchMyWork</h2><p className="muted">Perform the task normally. We’ll learn the pattern.</p></div><Badge value={active ? 'recording' : 'ready'} /></div>
      <div className="teach-instructions"><span className="step-number">1</span><div><h3>Use the demo row below</h3><p>Start recording, open the mock site, and enter the values below.</p></div></div><div className="demo-value"><label>Data row<input aria-label="Demonstration row" type="number" min="1" max={dataset.record_count} value={rowIndex + 1} disabled={Boolean(active) || Boolean(busy)} onChange={e => setRowIndex(Math.min(dataset.record_count - 1, Math.max(0, Number(e.target.value) - 1)))} /></label>{inputs.map(column => <div key={column}><span>READ {column}</span><strong>{row[column] || '(blank — select another row)'}</strong></div>)}</div>
      <div className="teach-instructions"><span className="step-number">2</span><div><h3>Perform the lookup in your browser</h3><p>{mode === 'developer' ? 'Wait for Recording. Fill Email and Password, click Login, and wait for Test demonstration captured.' : inputs.length === 2 ? 'Wait for Recording. Enter Latitude and Longitude, click Check Weather, and wait for Demonstration saved.' : 'Wait for Recording. Enter the input, perform the lookup, and save the result.'}</p><a href={mode === 'developer' ? "http://127.0.0.1:5173/developer" : "http://127.0.0.1:5173/"} target="_blank" rel="noreferrer">Open local test website ↗</a></div></div>
      <div className="teach-instructions"><span className="step-number">3</span><div><h3>{inputs.length === 2 ? 'Wait for automatic save, then analyze' : 'Stop recording, then analyze'}</h3><p>We’ll turn the example into steps you can review.</p></div></div>
      <div className="button-row"><button disabled={Boolean(active) || Boolean(busy) || inputs.some(column => !row[column]?.trim())} onClick={() => void record()}>● Start Recording</button><button className="secondary" disabled={!active || Boolean(busy)} onClick={() => void stop()}>■ Stop Recording</button><button className="secondary" disabled={Boolean(active) || Boolean(busy)} onClick={() => { setRowIndex(i => Math.min(i + 1, dataset.record_count - 1)); setError(''); }}>Add Demonstration</button></div>
      <div className="notice"><strong>Extension required</strong><p>Load the <code>extension</code> folder in Chrome’s Developer Mode, then refresh the mock-site tab. Full instructions are in README.md.</p></div>
      <div className="panel-actions"><button className="text-button" disabled={Boolean(active) || Boolean(busy)} onClick={() => setStep(1)}>← Upload Data</button><button disabled={!complete.length || Boolean(active) || Boolean(busy)} onClick={() => void analyze()}>Analyze Workflow →</button></div>
      {inferenceFailed && <button className="text-button manual-option" disabled={Boolean(busy)} onClick={() => void analyze(true)}>Review demonstrated steps manually (without AI)</button>}
    </section><section className="panel timeline-panel"><div className="section-header"><h2>Demonstration timeline</h2><span className="count-label">{complete.length} complete</span></div>{!demos.length ? <Empty title="Ready when you are"><p>Your semantic actions will appear here as you demonstrate.</p></Empty> : demos.map(d => <div className="demo-timeline" key={d.id}><div className="section-header"><strong>Example · row {d.row_index + 1}</strong><Badge value={d.state} /></div><ol>{inputColumns(d).map(column => <li key={column}><b>READ</b><span>{column}</span></li>)}{d.events.map((e, i) => <li key={i}><b>{e.action === 'extract' ? 'READ' : e.action.toUpperCase()}</b><span>{e.label || e.target}{e.text ? ` · ${e.text}` : ''}</span></li>)}{d.state === 'complete' && <li><b>WRITE</b><span>{d.destination_column} · {d.result}</span></li>}</ol></div>)}</section></div>}
    {step === 3 && workflow && <section className="panel wizard-panel"><div className="confirmation-heading"><span className="confirmation-check">✓</span><h2>Review Learned Test</h2><p className="muted">Review the pattern before any automation begins.</p><Badge value={workflow.source === 'nemotron' ? 'Nemotron inferred' : workflow.source === 'semantic_fallback' ? 'Generated from recorded actions' : 'Manually prepared'} /></div>
      {workflow.source === 'semantic_fallback' && <div className="notice" role="status">Nemotron temporarily unavailable. A workflow was generated from your recorded actions. Please review it before confirming.</div>}
      {editing ? <><label className="json-label">Workflow JSON<textarea rows={20} spellCheck={false} value={json} onChange={e => setJson(e.target.value)} /></label><div className="button-row"><button disabled={Boolean(busy)} onClick={() => void task('Validating edits', async () => { const plan = JSON.parse(json) as Plan; setWorkflow(await api<Workflow>(`/workflows/${workflow.id}`, { method: 'PUT', body: JSON.stringify(plan) })); setEditing(false); })}>Validate & Save Changes</button><button className="secondary" onClick={() => setEditing(false)}>Cancel</button></div></> : <><div className="plan-summary"><div><span>GOAL</span><h3>{workflow.plan.goal}</h3></div><div className="fields"><div><span>INPUT</span><strong>{inputColumns(workflow.plan).join(', ')}</strong></div><div><span>OUTPUT</span><strong>{workflow.plan.destination_column}</strong></div></div></div><ol className="plan-steps">{workflow.plan.steps.map((s, i) => <li key={i}><span>{i + 1}</span><div><strong>{({ fill: 'Fill input field', click: 'Click lookup button', wait: 'Wait for result', extract: 'Read the result', write_spreadsheet: 'Write to the spreadsheet' } as Record<string, string>)[s.action]}</strong><small>{s.action === 'fill' ? `${s.value} into ${s.target}` : s.action === 'write_spreadsheet' ? `Save result in ${s.column}` : s.target}</small></div></li>)}</ol><div className="plan-rules"><p><strong>Loop</strong> {mode === 'developer' ? 'Every test case is executed, including the demonstration, blanks and duplicates.' : 'Every populated row. Completed demonstration rows are preserved.'}</p><p><strong>Exceptions</strong> {mode === 'developer' ? 'Expected and actual results are compared after trimming and case folding. Assertion mismatches are FAIL; runtime errors are ERROR and retry once.' : 'Blank, duplicate, invalid, or missing results go to manual review. Browser failures retry once.'}</p></div><div className="button-row"><button className="secondary" onClick={() => { setJson(JSON.stringify(workflow.plan, null, 2)); setEditing(true); }}>Edit</button>{!reuse && <button className="secondary" onClick={() => { setStep(2); setWorkflow(null); setRowIndex(i => Math.min(i + 1, (dataset?.record_count || 1) - 1)); }}>Show Another Example</button>}</div><div className="panel-actions"><span className="privacy-note">{workflow.confirmed ? '✓ Confirmed by you. Ready to run.' : 'No automation starts without your confirmation.'}</span>{workflow.confirmed ? <button disabled={Boolean(busy)} onClick={() => void run()}>Run Test Suite →</button> : <button disabled={Boolean(busy)} onClick={() => void task('Confirming', async () => setWorkflow(await post<Workflow>(`/workflows/${workflow.id}/confirm`)))}>Confirm Workflow</button>}</div></>}
      {workflow.confirmed && mode === 'developer' && <section className="panel"><h2>Generated Test</h2><p>Framework: Playwright (Python) · Inputs: {inputs.join(', ')} · Assertion: {expected} vs {output} · Test cases: {dataset?.record_count}</p><button disabled={Boolean(busy)} onClick={() => void task('Generating test', async () => { const result = await api<{code: string}>(`/workflows/${workflow.id}/generated-test`); setGenerated(result.code); })}>Generate Playwright Test</button>{generated && <><pre style={{overflow: 'auto'}}>{generated}</pre><a className="button" href={`${API}/workflows/${workflow.id}/test-download?dataset_id=${dataset?.id}`}>Download Playwright test + data</a></>}</section>}
    </section>}
  </>;
}
function SavedPage({ onReuse }: { onReuse: (w: Workflow) => void }) {
  const { data, error, refresh } = useResource<Workflow[]>('/workflows');
  const saved = data?.filter(w => w.saved && w.confirmed) || [];
  return <><PageHeading eyebrow="YOUR LIBRARY" title="Saved workflows" description="A pattern you’ve taught. Ready for the next spreadsheet." />{error && <ErrorBox text={error} retry={refresh} />}{saved.length ? <div className="workflow-grid">{saved.map(w => <section className="panel workflow-card" key={w.id}><span className="row-icon"><Icon name="Saved Workflows" /></span><Badge value="confirmed" /><h2>{w.plan.workflow_name}</h2><p>{inputColumns(w.plan).join(', ')} → {w.plan.destination_column}</p><div className="workflow-facts"><span>Created <strong>{formatDate(w.created_at)}</strong></span><span>Runs <strong>{w.run_count}</strong></span><span>Last success <strong>{w.last_success_rate === null ? '—' : `${w.last_success_rate}%`}</strong></span></div><button className="secondary" onClick={() => onReuse(w)}>Use on another spreadsheet →</button></section>)}</div> : <section className="panel"><Empty title="Keep your best workflows close"><p>After a run, choose Save Workflow to reuse it without teaching again.</p></Empty></section>}</>;
}
function RunsPage({ onRun }: { onRun: (id: string) => void }) {
  const { data, error, refresh } = useResource<Run[]>('/runs', 2000);
  return <><PageHeading eyebrow="EXECUTION HISTORY" title="Runs" description="Follow every record, checkpoint, and result." />{error && <ErrorBox text={error} retry={refresh} />}<section className="panel">{data?.length ? <div className="table-wrap"><table><thead><tr><th>Workflow</th><th>Started</th><th>Progress</th><th>State</th><th>Results</th></tr></thead><tbody>{data.map(r => <tr key={r.id}><td><strong>{r.plan.workflow_name}</strong></td><td>{formatDate(r.created_at)}</td><td>{r.processed} / {r.total}</td><td><Badge value={r.state} /></td><td><button className="small secondary" onClick={() => onRun(r.id)}>View run</button></td></tr>)}</tbody></table></div> : <Empty title="Your run history starts here"><p>Confirmed workflows and their results will appear here.</p></Empty>}</section></>;
}
function RunPage({ id, onRun, onBack }: { id: string; onRun: (id: string) => void; onBack: () => void }) {
  const { data: run, error: loadError, refresh } = useResource<Run>(`/runs/${id}`, 800);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [review, setReview] = useState(false);
  const [exceptions, setExceptions] = useState<ExceptionItem[]>([]);
  const report = useResource<{test_case: number; expected: string; actual: string; status: string; reason: string}[]>(`/runs/${id}/test-report`, 1000);
  const [packagePath, setPackagePath] = useState('');
  const [resolutions, setResolutions] = useState<Record<number, string>>({});
  useEffect(() => { setSaved(false); setReview(false); setError(''); }, [id]);
  async function action(fn: () => Promise<void>) { setBusy(true); setError(''); try { await fn(); refresh(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); } }
  const ended = run?.state === 'completed' || run?.state === 'stopped';
  if (!run) return <>{loadError ? <ErrorBox text={loadError} retry={refresh} /> : <p role="status">Loading run…</p>}</>;
  return <><button className="text-button back-link" onClick={onBack}>← All runs</button><PageHeading eyebrow="WORKFLOW RUN" title={run.state === 'completed' ? 'Workflow Complete' : run.state === 'stopped' ? 'Workflow stopped' : run.state === 'paused' ? 'Workflow paused' : 'Your workflow is running.'} description={`${run.plan.workflow_name} · Every completed row is checkpointed locally.`} action={<Badge value={run.state} />} />{(error || loadError || run.error) && <ErrorBox text={error || loadError || run.error} />}
    <section className="panel progress-panel"><div className="section-header"><div><span className="eyebrow">RECORDS PROCESSED</span><h2 className="progress-count">{run.processed.toLocaleString()} <span>/ {run.total.toLocaleString()}</span></h2></div><div className="time-label"><strong>{run.seconds.toFixed(1)}s</strong><span>processing time</span></div></div><progress value={run.processed} max={run.total} aria-label="Records processed" /><div className="run-stats">{(run.plan.mode === 'developer' ? [['PASS', run.successful], ['FAIL', run.failed], ['ERROR', run.ERROR || 0], ['Pass rate', `${run.processed ? (100 * run.successful / run.processed).toFixed(1) : 0}%`]] : [['Successful', run.successful], ['Failed', run.failed], ['Manual Review', run.manual_review], ['Retrying', run.retrying ? 1 : 0]]).map(([name, value]) => <div key={String(name)}><span>{name}</span><strong>{value}</strong></div>)}</div><p className="muted">{run.retries} total retries · {run.total - run.processed} remaining</p>{!ended && <div className="button-row"><button className="secondary" disabled={busy || run.state !== 'running'} onClick={() => void action(async () => { await post(`/runs/${id}/pause`); })}>Pause</button><button disabled={busy || run.state !== 'paused'} onClick={() => void action(async () => { await post(`/runs/${id}/resume`); })}>Resume</button><button className="danger-outline" disabled={busy} onClick={() => void action(async () => { await post(`/runs/${id}/stop`); })}>Stop</button></div>}<p className="microcopy">Pause and stop take effect after the current browser action. Completed results are always preserved.</p></section>
    <section className="panel result-actions"><div><h2>{ended ? 'Your results are ready' : 'A checkpoint you can count on'}</h2><p className="muted">Download checkpointed results at any time. Developer tests include actual results and PASS / FAIL / ERROR status.</p></div><div className="button-row"><a className="button" href={`${API}/runs/${id}/download`}>Download Updated Excel ↓</a><button className="secondary" disabled={busy} onClick={() => void action(async () => { setExceptions(await api<ExceptionItem[]>(`/runs/${id}/exceptions`)); setReview(true); })}>Review Exceptions</button>{ended && <><button className="secondary" disabled={busy} onClick={() => void action(async () => { const r = await post<Run>('/runs', { workflow_id: run.workflow_id, dataset_id: run.dataset_id }); onRun(r.id); })}>Run Again</button><button className="secondary" disabled={busy || saved} onClick={() => void action(async () => { await post(`/workflows/${run.workflow_id}/save`); setSaved(true); })}>{saved ? '✓ Workflow Saved' : 'Save Workflow'}</button></>}</div></section>
    {run.plan.mode === 'developer' && <section className="panel"><h2>Test Report</h2><p>Total tests: {run.total} · Passed: {run.successful} · Failed: {run.failed} · Errors: {run.ERROR || 0} · Execution time: {run.seconds}s</p><table><thead><tr><th>Test Case</th><th>Status</th><th>Expected</th><th>Actual</th><th>Failure Reason</th></tr></thead><tbody>{report.data?.map(r => <tr key={r.test_case}><td>{r.test_case}</td><td><Badge value={r.status} /></td><td>{r.expected}</td><td>{r.actual}</td><td>{r.reason}</td></tr>)}</tbody></table>{ended && <><h2>Developer Impact</h2><p>Manual tests replaced: {run.successful + run.failed} · Automated tests executed: {run.processed} · Passed: {run.successful} · Failed: {run.failed} · Execution time: {run.seconds}s</p><button disabled={busy} onClick={() => void action(async () => { const result = await post<{path: string}>(`/runs/${id}/debug/package`); setPackagePath(result.path); })}>Prepare Bob Debug Package</button>{packagePath && <p role="status">Package ready: <code>{packagePath}</code>. Open this folder in IBM Bob IDE. No Bob API was called.</p>}</>}</section>}
    {review && <section className="panel"><div className="section-header"><h2>Exception Queue</h2><span className="count-label">{exceptions.length} records</span></div>{!ended && <p className="muted">Finish or stop the run before resolving exceptions.</p>}{exceptions.length ? <div className="table-wrap"><table><thead><tr><th>Spreadsheet row</th><th>Outcome</th><th>Reason</th><th>Reviewed status</th><th>Action</th></tr></thead><tbody>{exceptions.map(e => <tr key={e.row_index}><td>{e.row_index + 2}</td><td><Badge value={e.status} /></td><td>{e.reason}</td><td><input aria-label={`Reviewed status for row ${e.row_index + 2}`} placeholder="Enter verified status" value={resolutions[e.row_index] || ''} onChange={event => setResolutions(old => ({ ...old, [e.row_index]: event.target.value }))} /></td><td><button className="small secondary" disabled={!ended || busy || !resolutions[e.row_index]?.trim()} onClick={() => void action(async () => { await api(`/runs/${id}/exceptions/${e.row_index}`, { method: 'PUT', body: JSON.stringify({ value: resolutions[e.row_index] }) }); setExceptions(await api<ExceptionItem[]>(`/runs/${id}/exceptions`)); })}>Resolve</button></td></tr>)}</tbody></table></div> : <Empty title="All clear"><p>No unresolved exceptions in this run.</p></Empty>}</section>}
  </>;
}
function SettingsPage({ configured }: { configured: boolean }) {
  return <><PageHeading eyebrow="WORKSPACE" title="Settings" description="A local workspace, with clear boundaries." /><section className="panel settings-panel"><h2>Connections</h2><div className="setting-row"><div><strong>Nemotron / OpenRouter</strong><p>Used to infer a workflow once. Never called per row.</p><code>nvidia/nemotron-3.5-lightning:free</code></div><Badge value={configured ? 'configured' : 'not configured'} /></div><div className="setting-row"><div><strong>API key</strong><p>Managed in your root .env file. Restart the backend after changing it.</p></div><span className="muted">Never displayed</span></div><div className="setting-row"><div><strong>Browser execution</strong><p>Restricted to the local mock verification site.</p></div><a href="http://127.0.0.1:5173/" target="_blank" rel="noreferrer">Open mock site ↗</a></div><div className="setting-row"><div><strong>Local persistence</strong><p>Uploads, demonstrations, checkpoints, and results are stored in SQLite under backend/data.</p></div><Badge value="local only" /></div><div className="notice"><strong>What is sent to the model?</strong><p>Only selected column names, semantic action labels, selectors, and value placeholders. Full spreadsheets and record values are not sent. Research metrics contain counts and timings, not cell values.</p></div></section></>;
}
function MetricsPage() {
  const { data, error, refresh } = useResource<{ total_ai_calls: number; workflows: Record<string, string | number>[]; inference_attempts: { latency: number; success: number }[] }>('/metrics');
  return <><PageHeading eyebrow="LOCAL RESEARCH" title="Research metrics" description="Understand the work, without logging spreadsheet values." action={<a className="button" href={`${API}/metrics/download`}>Download JSON ↓</a>} />{error && <ErrorBox text={error} retry={refresh} />}<div className="stats-grid"><div className="stat-card"><span>AI calls</span><strong>{data?.total_ai_calls ?? '—'}</strong><small>Includes failed inference attempts</small></div><div className="stat-card"><span>Inference time</span><strong>{data ? `${data.inference_attempts.reduce((sum, c) => sum + c.latency, 0).toFixed(1)}s` : '—'}</strong><small>Total model latency</small></div></div><section className="panel">{data?.workflows.length ? <div className="table-wrap"><table><thead><tr><th>Workflow</th><th>Examples</th><th>Processed</th><th>Successes</th><th>Failures</th><th>Reviews</th><th>Retries</th><th>Avg / row</th></tr></thead><tbody>{data.workflows.map(w => <tr key={w.workflow_id}><td><code>{String(w.workflow_id).slice(0, 8)}</code></td><td>{w.number_of_demonstrations}</td><td>{w.records_processed}</td><td>{w.successes}</td><td>{w.failures}</td><td>{w.manual_reviews}</td><td>{w.retries}</td><td>{w.average_execution_time_per_record}s</td></tr>)}</tbody></table></div> : <Empty title="Evidence starts with a workflow"><p>Your first analysis and run will populate these metrics.</p></Empty>}</section></>;
}
createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>);
