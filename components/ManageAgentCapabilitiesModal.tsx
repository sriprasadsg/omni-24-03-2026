import React, { useState, useEffect } from 'react';
import { Agent, AgentCapability } from '../types';
import { XIcon, CogIcon, BarChart3Icon, ShieldSearchIcon, FileTextIcon, FileShieldIcon, ShieldCheckIcon, ShieldZapIcon, SaveIcon, LightbulbIcon, UsersIcon, ComponentIcon, GitMergeIcon } from './icons';

interface ManageAgentCapabilitiesModalProps {
    isOpen: boolean;
    onClose: () => void;
    agent: Agent | null;
    onSave: (updatedAgent: Agent) => void;
}

const allCapabilities: { id: AgentCapability; icon: React.ReactNode; label: string; description: string }[] = [
    { id: 'metrics_collection', icon: <BarChart3Icon />, label: 'Metric Collection', description: 'Collects CPU, memory, disk, and network metrics.' },
    { id: 'log_collection', icon: <FileTextIcon />, label: 'Log Collection', description: 'Gathers and forwards logs from the host system.' },
    { id: 'vulnerability_scanning', icon: <ShieldSearchIcon />, label: 'Vulnerability Scanning', description: 'Scans for known vulnerabilities in installed packages.' },
    { id: 'fim', icon: <FileShieldIcon />, label: 'File Integrity Monitoring', description: 'Monitors critical system files for unauthorized changes.' },
    { id: 'compliance_enforcement', icon: <ShieldCheckIcon />, label: 'Compliance Enforcement', description: 'Enforces security policies and compliance baselines.' },
    { id: 'runtime_security', icon: <ShieldZapIcon />, label: 'Runtime Security', description: 'Detects and blocks malicious runtime behavior.' },
    { id: 'predictive_health', icon: <LightbulbIcon />, label: 'Predictive Health', description: 'Uses AI to predict potential agent or host issues.' },
    { id: 'ueba', icon: <UsersIcon />, label: 'Behavior Analytics (UEBA)', description: 'Monitors user and entity behavior for anomalies.' },
    { id: 'sbom_analysis', icon: <ComponentIcon />, label: 'SBOM Analysis', description: 'Analyzes Software Bill of Materials for vulnerabilities.' },
    { id: 'ebpf_tracing', icon: <GitMergeIcon />, label: 'eBPF Tracing', description: 'Provides deep kernel-level visibility and tracing.' },
];

export const ManageAgentCapabilitiesModal: React.FC<ManageAgentCapabilitiesModalProps> = ({ isOpen, onClose, agent, onSave }) => {
    const [enabledCapabilities, setEnabledCapabilities] = useState<Set<AgentCapability>>(new Set());

    useEffect(() => {
        if (agent) {
            setEnabledCapabilities(new Set(agent.agentCapabilities || []));
        }
    }, [agent]);

    const handleToggle = (capability: AgentCapability) => {
        setEnabledCapabilities(prev => {
            const newSet = new Set(prev);
            if (newSet.has(capability)) {
                newSet.delete(capability);
            } else {
                newSet.add(capability);
            }
            return newSet;
        });
    };

    const handleSave = () => {
        if (agent) {
            onSave({ ...agent, agentCapabilities: Array.from(enabledCapabilities) });
        }
    };

    if (!isOpen || !agent) return null;

    return (
        <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex justify-center items-center" onClick={onClose}>
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-2xl p-6 m-4 max-h-[90vh] flex flex-col" onClick={e => e.stopPropagation()}>
                <div className="flex-shrink-0 flex justify-between items-start mb-4">
                    <div>
                        <h2 className="text-xl font-bold text-gray-900 dark:text-white flex items-center">
                            <CogIcon className="mr-3 text-primary-500" />
                            Manage Agent Capabilities
                        </h2>
                        <p className="text-sm text-gray-500 dark:text-gray-400 font-mono">{agent.hostname}</p>
                    </div>
                    <button onClick={onClose} className="p-1 rounded-full text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700">
                        <XIcon size={20} />
                    </button>
                </div>

                <div className="flex-grow space-y-4 overflow-y-auto pr-2">
                    {allCapabilities.map(cap => (
                        <div key={cap.id} className="p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg border border-gray-200 dark:border-gray-600 flex items-center justify-between">
                            <div className="flex items-center">
                                <div className="flex-shrink-0 w-8 h-8 flex items-center justify-center rounded-full bg-gray-100 dark:bg-gray-700 text-primary-500 dark:text-primary-400 mr-4">
                                    {cap.icon}
                                </div>
                                <div>
                                    <p className="font-semibold text-gray-800 dark:text-gray-200">{cap.label}</p>
                                    <p className="text-xs text-gray-500 dark:text-gray-400">{cap.description}</p>
                                </div>
                            </div>
                            <button
                                type="button"
                                className={`${enabledCapabilities.has(cap.id) ? 'bg-primary-600' : 'bg-gray-200 dark:bg-gray-600'} relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 dark:ring-offset-gray-800`}
                                role="switch"
                                aria-checked={enabledCapabilities.has(cap.id)}
                                onClick={() => handleToggle(cap.id)}
                            >
                                <span
                                    aria-hidden="true"
                                    className={`${enabledCapabilities.has(cap.id) ? 'translate-x-5' : 'translate-x-0'} pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out`}
                                />
                            </button>
                        </div>
                    ))}
                </div>

                <div className="flex-shrink-0 mt-6 flex justify-end space-x-3 pt-4 border-t border-gray-200 dark:border-gray-700">
                    <button onClick={onClose} className="px-4 py-2 text-sm font-medium text-gray-700 bg-white dark:bg-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-md">Cancel</button>
                    <button onClick={handleSave} className="flex items-center px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700">
                        <SaveIcon size={16} className="mr-2" />
                        Save Capabilities
                    </button>
                </div>
            </div>
        </div>
    );
};
