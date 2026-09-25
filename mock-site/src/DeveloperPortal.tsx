import { useState } from 'react';

export function DeveloperPortal() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [result, setResult] = useState('');
  const [busy, setBusy] = useState(false);
  return <main className="developer-portal"><header><span>ACME / DEVELOPER TOOLS</span><h1>Acme Developer Portal</h1><p>A deterministic local application for browser testing.</p></header>
    <section className="card"><h2>Sign in to your workspace</h2><form noValidate onSubmit={event => {
      event.preventDefault(); setResult(''); setBusy(true);
      const users: Record<string, string> = { 'dev@example.com': 'test123', 'admin@example.com': 'admin123' };
      const message = !email.trim() || !password ? 'Email and password are required' : !Object.hasOwn(users, email.trim()) ? 'User not found' : users[email.trim()] !== password ? 'Invalid credentials' : 'Login successful';
      setTimeout(() => { setResult(message); setBusy(false); }, 200);
    }}><label htmlFor="email-input">Email</label><input id="email-input" autoComplete="off" value={email} disabled={busy} onChange={e => { setEmail(e.target.value); setResult(''); }} />
      <label htmlFor="password-input">Password</label><input id="password-input" type="password" autoComplete="off" value={password} disabled={busy} onChange={e => { setPassword(e.target.value); setResult(''); }} />
      <button id="login-button" disabled={busy}>{busy ? 'Checking…' : 'Login'}</button>
      <output id="login-result" role="status" hidden={!result}>{result}</output></form>
      <p>Synthetic test accounts only. No external authentication service.</p><a href="/">Weather example</a>
    </section></main>;
}
