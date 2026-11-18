import React, { useEffect, useState } from 'react';
import { authFetch } from '../services/apiService';

// Platform health, Wave 6: which optional integrations are configured (names and environment variables only, never
// a value) and a live test of each (backend/integration_status.py). Keys are set on the server, not here.

interface Integration { name: string; label: string; use: string; envVars: string[]; configured: boolean; missing: string[] }
interface TestResult { ok: boolean; detail: string }

const BASE = '/api/platform/autonomous-ops/health/integrations';

export const PlatformIntegrationsCard: React.FC = () => {
    const [items, setItems] = useState<Integration[] | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [results, setResults] = useState<Record<string, TestResult>>({});
    const [testing, setTesting] = useState<string | null>(null);

    useEffect(() => {
        let current = true;
        (async () => {
            try {
                const r = await authFetch(BASE);
                const body = await r.json().catch(() => ({}));
                if (!r.ok) throw new Error(typeof body?.detail === 'string' ? body.detail : `HTTP ${r.status}`);
                if (current) setItems(Array.isArray(body.items) ? body.items : []);
            } catch (e) {
                if (current) setError(e instanceof Error ? e.message : 'unknown error');
            }
        })();
        return () => { current = false; };
    }, []);

    const run = async (name: string) => {
        setTesting(name);
        try {
            const r = await authFetch(`${BASE}/${encodeURIComponent(name)}/test`, { method: 'POST' });
            const body = await r.json().catch(() => ({}));
            setResults(s => ({ ...s, [name]: r.ok ? body : { ok: false, detail: typeof body?.detail === 'string' ? body.detail : `HTTP ${r.status}` } }));
        } catch {
            setResults(s => ({ ...s, [name]: { ok: false, detail: 'The test request failed' } }));
        } finally {
            setTesting(null);
        }
    };

    const configured = items?.filter(i => i.configured).length ?? 0;

    return (
        <section aria-labelledby="platform-integrations-title" className="rounded-2xl border border-gray-200/80 dark:border-white/[0.07] bg-white dark:bg-gray-800 p-5 space-y-3">
            <div>
                <h3 id="platform-integrations-title" className="text-sm font-semibold text-gray-900 dark:text-white">Integrations</h3>
                <p className="text-xs text-gray-600 dark:text-gray-400 mt-1">
                    {items ? `${configured} of ${items.length} configured. ` : ''}Keys are set on the server (the backend's environment); this list never shows them.
                    A test makes one harmless call with the configured key; the email test goes to you.
                </p>
            </div>
            {/* A plain note, not an alert: the health page has its own alert for a failed load. */}
            {error && <p className="text-sm text-gray-600 dark:text-gray-400">The integration list could not be loaded ({error}).</p>}
            {items && (
                <ul className="divide-y divide-gray-100 dark:divide-white/[0.05]">
                    {items.map(i => {
                        const result = results[i.name];
                        return (
                            <li key={i.name} className="py-2.5 flex flex-wrap items-center gap-3 text-sm">
                                <span className={`h-2 w-2 rounded-full ${i.configured ? 'bg-emerald-500' : 'bg-gray-400'}`} aria-hidden="true" />
                                <span className="min-w-0 flex-1">
                                    <span className="font-medium text-gray-900 dark:text-white">{i.label}</span>
                                    <span className="ml-2 text-xs text-gray-500 dark:text-gray-400">{i.configured ? 'Configured' : `Not configured: set ${i.missing.join(', ')}`} · {i.use}</span>
                                    {result && (
                                        <span role="status" className={`block text-xs ${result.ok ? 'text-emerald-700 dark:text-emerald-300' : 'text-red-700 dark:text-red-300'}`}>
                                            {result.ok ? 'Test passed' : 'Test failed'}: {result.detail}
                                        </span>
                                    )}
                                </span>
                                {i.configured && (
                                    <button type="button" onClick={() => run(i.name)} disabled={testing !== null} aria-label={`Test ${i.label}`}
                                        className="text-xs font-semibold px-3 py-1.5 rounded-lg border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50">
                                        {testing === i.name ? 'Testing…' : 'Test'}
                                    </button>
                                )}
                            </li>
                        );
                    })}
                </ul>
            )}
        </section>
    );
};
