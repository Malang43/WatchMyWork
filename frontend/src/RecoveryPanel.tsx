import { useEffect, useState } from 'react';
import { api, post } from './api';

interface Recovery {
  id: string; row_index: number; state: string; confidence: number; method: string; reason: string;
  original: { name: string; selector: string }; candidate?: { name: string; role: string };
  navigation?: string;
}

export function RecoveryPanel({ runId, ended }: { runId: string; ended: boolean }) {
  const [items, setItems] = useState<Recovery[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let live = true;
    async function load() {
      try { const data = await api<Recovery[]>(`/runs/${runId}/recoveries`); if (live) setItems(data); }
      catch (e) { if (live) setError((e as Error).message); }
    }
    void load(); const timer = setInterval(load, 1000);
    return () => { live = false; clearInterval(timer); };
  }, [runId]);
  async function decide(item: Recovery, decision: string) {
    setBusy(true); setError('');
    try {
      await post(decision === 'stop' ? `/runs/${runId}/stop` : `/runs/${runId}/recoveries/${item.id}/${decision}`);
      setItems(await api<Recovery[]>(`/runs/${runId}/recoveries`));
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  return <section className="panel recovery-panel" aria-label="Adaptive Recovery Agent">
    <h2>Adaptive Recovery Agent</h2>
    {error && <p role="alert">{error}</p>}
    {!items.length && <p className="muted">{ended ? 'No recovery was needed.' : 'Monitoring for website changes.'}</p>}
    {items.map(item => <article key={item.id} className="notice">
      <h3>{item.state === 'pending' && !ended ? 'Website change detected' : item.state === 'recovered' ? 'Recovered' : `Recovery: ${item.state}`}</h3>
      <p>Test {item.row_index + 1}: <strong>{item.original.name}</strong> → <strong>{item.candidate?.name || item.navigation || 'No equivalent action found'}</strong></p>
      <p>{item.reason}</p><p>{item.method} · Confidence: {Math.round(item.confidence * 100)}%</p>
      {item.state === 'pending' && !ended && <div className="button-row">
        <button disabled={busy} onClick={() => void decide(item, 'approve')}>Approve &amp; Continue</button>
        <button className="secondary" disabled={busy} onClick={() => void decide(item, 'reject')}>Reject</button>
        <button className="danger-outline" disabled={busy} onClick={() => void decide(item, 'stop')}>Stop Run</button>
      </div>}
    </article>)}
  </section>;
}
