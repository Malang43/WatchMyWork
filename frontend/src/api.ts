export const API = import.meta.env.PROD ? '' : 'http://127.0.0.1:8000';
export const DEMO = import.meta.env.PROD ? '/weather' : 'http://127.0.0.1:5173/';
export const DEVELOPER = import.meta.env.PROD ? '/developer' : 'http://127.0.0.1:5173/developer';
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(API + path, { ...init, headers: { 'X-WatchMyWork': 'local-demo', ...(init.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }), ...init.headers }, signal: init.signal ?? AbortSignal.timeout(135000) });
  } catch { throw new Error('The backend is not responding. Try again shortly. Your saved work is safe.'); }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === 'string' ? body.detail : 'Please check the selected columns and workflow fields, then try again.');
  }
  return response.json() as Promise<T>;
}
export const post = <T>(path: string, body?: unknown) => api<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) });
export interface Dataset { id: string; filename: string; record_count: number; columns: string[]; preview: Record<string, string>[] }
export interface Event { action: string; target: string; label: string; role: string; value: string; text: string }
export interface Demo { mode?: string; expected_column?: string; status_column?: string; id: string; state: string; row_index: number; input_column: string; input_columns?: string[]; destination_column: string; events: Event[]; result: string }
export interface Step { action: string; target?: string | null; value?: string | null; save_as?: string | null; column?: string | null }
export interface Plan { mode?: string; expected_column?: string; status_column?: string; workflow_name: string; goal: string; input_column: string; input_columns?: string[]; destination_column: string; url: string; loop: string; steps: Step[]; exceptions: { no_result: string } }
export interface Workflow { id: string; plan: Plan; confirmed: boolean; saved: boolean; source: string; created_at: string; run_count?: number; last_success_rate?: number | null }
export interface Run { ERROR?: number; id: string; workflow_id: string; dataset_id: string; plan: Plan; state: string; total: number; processed: number; successful: number; failed: number; manual_review: number; retries: number; retrying: boolean; seconds: number; error: string; created_at: string }
export interface ExceptionItem { row_index: number; status: string; reason: string; value: string }
export interface Dashboard { workflows_created: number; records_processed: number; successful_automations: number; manual_review_items: number; recent_workflows: Workflow[]; recent_runs: Run[] }
