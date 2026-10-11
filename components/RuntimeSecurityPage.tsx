import React, { useMemo, useState } from 'react';
import { Agent } from '../types';
import { RuntimeSecurityTab } from './RuntimeSecurityTab';

// Runtime security data is reported per agent (agent.meta.runtime_security), so
// the sidebar page lets the user pick an agent and reuses the agent-detail tab.
const runtimeData = (agent?: Agent) => (agent?.meta as any)?.runtime_security;

export const RuntimeSecurityPage: React.FC<{ agents: Agent[] }> = ({ agents }) => {
    const withData = useMemo(() => agents.filter(a => runtimeData(a)), [agents]);
    const [agentId, setAgentId] = useState<string>('');
    const selected = agents.find(a => a.id === agentId) || withData[0] || agents[0];

    return (
        <div className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Runtime Security</h1>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                        Live processes, network connections and suspicious activity reported by each agent
                    </p>
                </div>
                {agents.length > 0 && (
                    <select
                        aria-label="Agent"
                        value={selected?.id || ''}
                        onChange={e => setAgentId(e.target.value)}
                        className="px-3 py-2 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                    >
                        {agents.map(a => (
                            <option key={a.id} value={a.id}>
                                {a.hostname}{runtimeData(a) ? '' : ' (no runtime data yet)'}
                            </option>
                        ))}
                    </select>
                )}
            </div>
            {agents.length === 0 ? (
                <div className="p-8 text-center text-gray-500 dark:text-gray-400">
                    No agents are enrolled yet. Install an agent to see runtime security data.
                </div>
            ) : (
                <RuntimeSecurityTab data={runtimeData(selected)} />
            )}
        </div>
    );
};

export default RuntimeSecurityPage;
