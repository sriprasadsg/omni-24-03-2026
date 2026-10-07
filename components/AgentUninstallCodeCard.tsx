import React, { useState } from 'react';
import { ShieldLockIcon, CopyIcon, RefreshCwIcon } from './icons';
import { API_BASE, authFetch } from '../services/apiService';
import { showToast } from '../utils/toast';

interface UninstallCode {
    code: string;
    version: number;
    createdAt: string;
}

/**
 * Uninstall protection: the code an administrator types into the agent's
 * uninstaller. Hidden until asked for (every reveal is audit-logged); each
 * code works once and is replaced after the agent reports its uninstall.
 */
export const AgentUninstallCodeCard: React.FC<{ agentId: string }> = ({ agentId }) => {
    const [code, setCode] = useState<UninstallCode | null>(null);
    const [busy, setBusy] = useState(false);

    const load = async (rotate: boolean) => {
        if (rotate && !window.confirm('Replace this agent\'s uninstall code? The current code stops working once the agent checks in.')) return;
        setBusy(true);
        try {
            const res = await authFetch(`${API_BASE}/agents/${agentId}/uninstall-code${rotate ? '/rotate' : ''}`,
                { method: rotate ? 'POST' : 'GET' });
            if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error || `HTTP ${res.status}`);
            setCode(await res.json());
            if (rotate) showToast('New uninstall code issued', 'success');
        } catch (e) {
            showToast(`Could not get the uninstall code: ${(e as Error).message}`, 'error');
        } finally {
            setBusy(false);
        }
    };

    const copy = () => {
        if (!code) return;
        navigator.clipboard?.writeText(code.code).then(() => showToast('Uninstall code copied', 'success'));
    };

    return (
        <div>
            <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2 flex items-center">
                <ShieldLockIcon size={16} className="mr-2" /> Uninstall protection
            </h3>
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
                The agent can only be uninstalled with this code. Each code works once; showing it is recorded in the audit log.
            </p>
            {code ? (
                <div className="flex items-center gap-2">
                    <span className="font-mono text-base tracking-widest px-3 py-1.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-gray-100 select-all">
                        {code.code}
                    </span>
                    <button onClick={copy} className="p-1.5 rounded hover:bg-gray-100 dark:hover:bg-gray-800" title="Copy code" aria-label="Copy uninstall code">
                        <CopyIcon size={16} />
                    </button>
                    <button onClick={() => load(true)} disabled={busy} className="flex items-center text-xs px-2 py-1 rounded border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-50">
                        <RefreshCwIcon size={14} className="mr-1" /> Replace
                    </button>
                </div>
            ) : (
                <button onClick={() => load(false)} disabled={busy} className="text-sm px-3 py-1.5 rounded bg-primary-600 hover:bg-primary-700 text-white disabled:opacity-50">
                    {busy ? 'Loading…' : 'Show uninstall code'}
                </button>
            )}
        </div>
    );
};
