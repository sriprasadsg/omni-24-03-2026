import React, { useCallback, useEffect, useState } from 'react';
import { authFetch } from '../services/apiService';

/** One self-service sign-up waiting for a Super Admin (backend tenant_signup_endpoints.py). */
export interface PendingSignup {
  id: string;
  name: string;
  requestedAt?: string | null;
  adminEmail?: string | null;
  adminName?: string | null;
}

const when = (iso?: string | null) => {
  const t = Date.parse(String(iso ?? ''));
  return Number.isNaN(t) ? '' : new Date(t).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
};

/**
 * Sign-up requests at the top of Tenant Management: approve lets the new organization's admin
 * sign in (the tenant starts with Overview only); reject removes the request. Hidden when none wait.
 */
export function PendingSignupsPanel({ onChanged }: { onChanged?: () => void }) {
  const [signups, setSignups] = useState<PendingSignup[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ tone: 'ok' | 'error'; text: string } | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await authFetch('/api/tenants/signups/pending');
      if (res.ok) setSignups((await res.json()).signups ?? []);
    } catch { /* the panel stays hidden; Tenant Management still works */ }
  }, []);
  useEffect(() => { load(); }, [load]);

  const decide = async (signup: PendingSignup, action: 'approve' | 'reject') => {
    if (action === 'reject' && !window.confirm(`Reject the sign-up of "${signup.name}"? The request and its account are removed.`)) return;
    setBusy(signup.id);
    setMessage(null);
    try {
      const res = await authFetch(`/api/tenants/signups/${encodeURIComponent(signup.id)}/${action}`, { method: 'POST' });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Request failed (${res.status})`);
      }
      setSignups(list => list.filter(s => s.id !== signup.id));
      setMessage({ tone: 'ok', text: action === 'approve'
        ? `${signup.name} approved. Its admin can sign in now and sees Overview until you tick its screens in Manage Tenant.`
        : `${signup.name} rejected.` });
      onChanged?.();
    } catch (e) {
      setMessage({ tone: 'error', text: e instanceof Error ? e.message : 'Something went wrong' });
    } finally {
      setBusy(null);
    }
  };

  if (signups.length === 0 && !message) return null;
  return (
    <section aria-labelledby="pending-signups" className="mb-6 rounded-2xl border border-amber-500/30 bg-amber-500/5 p-4">
      <h2 id="pending-signups" className="text-base font-semibold text-gray-900 dark:text-white">
        Sign-up requests{signups.length > 0 && ` (${signups.length})`}
      </h2>
      <p className="mt-0.5 text-sm text-gray-600 dark:text-gray-300">
        Organizations that signed themselves up. Nobody from them can sign in until you approve.
      </p>
      {message && (
        <p role={message.tone === 'error' ? 'alert' : 'status'}
           className={`mt-3 rounded-xl px-3 py-2 text-sm ${message.tone === 'error' ? 'bg-red-500/10 text-red-700 dark:text-red-300' : 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'}`}>
          {message.text}
        </p>
      )}
      {signups.length > 0 && (
        <ul className="mt-3 divide-y divide-gray-200 dark:divide-white/[0.07]">
          {signups.map(s => (
            <li key={s.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
              <div className="min-w-0">
                <p className="font-medium text-gray-900 dark:text-white">{s.name}</p>
                <p className="text-sm text-gray-600 dark:text-gray-300">
                  {[s.adminName, s.adminEmail].filter(Boolean).join(' · ') || 'No admin recorded'}
                  {when(s.requestedAt) && ` · requested ${when(s.requestedAt)}`}
                </p>
              </div>
              <div className="flex gap-2">
                <button type="button" disabled={busy === s.id} onClick={() => decide(s, 'reject')}
                        className="h-10 rounded-xl px-4 text-sm font-medium text-red-600 hover:bg-red-500/10 disabled:opacity-50 dark:text-red-400">
                  Reject
                </button>
                <button type="button" disabled={busy === s.id} onClick={() => decide(s, 'approve')}
                        className="h-10 rounded-xl bg-primary-600 px-4 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50">
                  {busy === s.id ? 'Working…' : 'Approve'}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
