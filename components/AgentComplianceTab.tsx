import React from 'react';
import { CheckIcon, XIcon, AlertTriangleIcon, ShieldCheckIcon } from './icons';
import { showToast } from '../utils/toast';

export interface ComplianceRule {
    id: string;
    title: string;
    status: 'passed' | 'failed' | 'warning';
    category: string;
    description?: string;
    remediation?: string;
    evidence?: string;
    checkName?: string;
}

export interface ComplianceData {
    score: number;
    total_rules: number;
    total_controls?: number;
    passed: number;
    failed: number;
    warnings: number;
    rules?: ComplianceRule[];
    compliance_checks?: any[];
    framework: string;
}

interface AgentComplianceTabProps {
    data?: ComplianceData;
    agentId: string;
    onRefresh?: () => void;
    onCollect?: () => Promise<void>;
}

const REMEDIATION_TIPS: Record<string, { summary: string; steps: string[]; powershell?: string }> = {
    'autorun': {
        summary: 'Disable AutoRun/AutoPlay via Group Policy to prevent malware from running automatically on removable media.',
        steps: [
            'Open Group Policy Editor: press Win+R, type gpedit.msc',
            'Navigate to Computer Configuration > Administrative Templates > Windows Components > AutoPlay Policies',
            'Double-click "Turn off AutoPlay", set to Enabled for "All drives"',
            'Run "gpupdate /force" in an elevated Command Prompt to apply immediately',
        ],
        powershell: 'Set-ItemProperty -Path "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\Explorer" -Name "NoDriveTypeAutoRun" -Value 255 -Force',
    },
    'bitlocker': {
        summary: 'Enable BitLocker full-disk encryption on the system drive to protect data at rest.',
        steps: [
            'Open Control Panel > System and Security > BitLocker Drive Encryption',
            'Click "Turn on BitLocker" next to the C: drive',
            'Choose unlock method: TPM (recommended), PIN, or USB startup key',
            'Save or print your recovery key and store it securely offline',
            'Select "Encrypt entire drive" and start encryption',
        ],
        powershell: 'Enable-BitLocker -MountPoint "C:" -EncryptionMethod Aes256 -TpmProtector',
    },
    'firewall': {
        summary: 'Enable Windows Defender Firewall on all network profiles.',
        steps: [
            'Open Windows Defender Firewall: search "firewall" in Start Menu',
            'Click "Turn Windows Defender Firewall on or off"',
            'Enable firewall for Domain, Private, and Public network profiles',
            'Click OK to save',
        ],
        powershell: 'Set-NetFirewallProfile -Profile Domain,Public,Private -Enabled True',
    },
    'defender': {
        summary: 'Enable Windows Defender real-time protection.',
        steps: [
            'Open Windows Security from the Start Menu',
            'Go to Virus & threat protection',
            'Under Virus & threat protection settings, click Manage settings',
            'Toggle Real-time protection to On',
        ],
        powershell: 'Set-MpPreference -DisableRealtimeMonitoring $false',
    },
    'uac': {
        summary: 'Enable User Account Control to prompt for privilege elevation on system changes.',
        steps: [
            'Open Control Panel > User Accounts > Change User Account Control settings',
            'Move the slider to at least "Notify me only when apps try to make changes"',
            'Click OK and restart your computer',
        ],
        powershell: 'Set-ItemProperty -Path "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\System" -Name "EnableLUA" -Value 1',
    },
    'screen lock': {
        summary: 'Configure automatic screen lock after inactivity to prevent unauthorized access.',
        steps: [
            'Open Settings > Accounts > Sign-in options',
            'Under "Require sign-in", select "When PC wakes up from sleep"',
            'Open Settings > System > Power & Sleep',
            'Set screen to turn off after 5-10 minutes on both battery and plugged in',
        ],
        powershell: 'powercfg /setdcvalueindex SCHEME_CURRENT SUB_VIDEO VIDEOIDLE 300; powercfg /setacvalueindex SCHEME_CURRENT SUB_VIDEO VIDEOIDLE 300',
    },
    'remote registry': {
        summary: 'Disable the Remote Registry service to prevent remote modification of the registry.',
        steps: [
            'Open Services: press Win+R, type services.msc',
            'Find "Remote Registry" in the list',
            'Right-click > Properties, set Startup type to "Disabled"',
            'Click Stop if running, then OK',
        ],
        powershell: 'Stop-Service -Name RemoteRegistry -Force -ErrorAction SilentlyContinue; Set-Service -Name RemoteRegistry -StartupType Disabled',
    },
    'windows update': {
        summary: 'Configure Windows Update to automatically download and install security patches.',
        steps: [
            'Open Settings > Update & Security > Windows Update',
            'Click Advanced options',
            'Ensure automatic updates are enabled',
            'Click "Check for updates" to apply any pending patches now',
        ],
        powershell: 'Set-ItemProperty -Path "HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsUpdate\\AU" -Name "AUOptions" -Value 4 -Force',
    },
    'password': {
        summary: 'Enforce a strong password policy via Local Security Policy.',
        steps: [
            'Open Local Security Policy: press Win+R, type secpol.msc',
            'Navigate to Account Policies > Password Policy',
            'Set Minimum password length to 12 or more characters',
            'Enable "Password must meet complexity requirements"',
            'Set Maximum password age to 90 days',
        ],
        powershell: 'net accounts /minpwlen:12 /maxpwage:90 /uniquepw:5',
    },
    'smb': {
        summary: 'Disable SMBv1 and require SMB signing to prevent lateral movement attacks.',
        steps: [
            'Open PowerShell as Administrator',
            'Run the command below to disable SMBv1 and enforce signing',
            'Reboot for the change to take full effect',
        ],
        powershell: 'Set-SmbServerConfiguration -EnableSMB1Protocol $false -RequireSecuritySignature $true -Force',
    },
    'rdp': {
        summary: 'Restrict Remote Desktop Protocol if not required, or enforce Network Level Authentication.',
        steps: [
            'Open System Properties: Win+R, type sysdm.cpl',
            'Go to the Remote tab',
            'Select "Don\'t allow remote connections" if RDP is not needed',
            'If RDP is required, enable "Allow connections only from computers running Remote Desktop with NLA"',
        ],
        powershell: 'Set-ItemProperty -Path "HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server" -Name "fDenyTSConnections" -Value 1',
    },
};

function getRemediationTip(checkName: string): { summary: string; steps: string[]; powershell?: string } | null {
    const lower = checkName.toLowerCase();
    for (const [key, tip] of Object.entries(REMEDIATION_TIPS)) {
        if (lower.includes(key)) return tip;
    }
    return null;
}

export const AgentComplianceTab: React.FC<AgentComplianceTabProps> = ({ data, agentId, onRefresh, onCollect }) => {
    const [isRefreshing, setIsRefreshing] = React.useState(false);
    const [isCollecting, setIsCollecting] = React.useState(false);
    const [expandedTips, setExpandedTips] = React.useState<Set<string>>(new Set());
    const [copiedId, setCopiedId] = React.useState<string | null>(null);

    const handleRefresh = async () => {
        if (onRefresh) {
            setIsRefreshing(true);
            try { await onRefresh(); } finally { setTimeout(() => setIsRefreshing(false), 1000); }
        }
    };

    const handleCollect = async () => {
        if (onCollect) {
            setIsCollecting(true);
            try { await onCollect(); } finally { setTimeout(() => setIsCollecting(false), 6000); }
        }
    };

    const toggleTips = (ruleId: string) => {
        setExpandedTips(prev => {
            const next = new Set(prev);
            if (next.has(ruleId)) next.delete(ruleId); else next.add(ruleId);
            return next;
        });
    };

    const copyPowershell = (ruleId: string, cmd: string) => {
        navigator.clipboard.writeText(cmd).then(() => {
            setCopiedId(ruleId);
            setTimeout(() => setCopiedId(null), 2000);
        });
    };

    const rules: ComplianceRule[] = React.useMemo(() => {
        if (data?.rules) return data.rules;
        if (data?.compliance_checks) {
            return data.compliance_checks.map((check: any) => ({
                id: check.check,
                title: check.check,
                checkName: check.check,
                status: (check.status?.toLowerCase() === 'pass' || check.status?.toLowerCase() === 'compliant') ? 'passed' :
                    (check.status?.toLowerCase() === 'fail' || check.status?.toLowerCase() === 'non-compliant') ? 'failed' : 'warning',
                category: 'System',
                description: check.details,
                evidence: check.evidence_content,
                remediation: check.remediation,
            }));
        }
        return [];
    }, [data]);

    const stats = React.useMemo(() => {
        if (data?.rules && data.score !== undefined) {
            return { score: data.score, passed: data.passed, failed: data.failed, warnings: data.warnings, total: data.total_rules };
        }
        const passed = rules.filter(r => r.status === 'passed').length;
        const failed = rules.filter(r => r.status === 'failed').length;
        const warnings = rules.filter(r => r.status === 'warning').length;
        const total = rules.length;
        return { score: total > 0 ? Math.round((passed + warnings * 0.5) / total * 100) : 0, passed, failed, warnings, total };
    }, [data, rules]);

    if (!data || (!data.rules && !data.compliance_checks)) {
        return (
            <div className="text-center py-8 text-gray-500 dark:text-gray-400">
                <ShieldCheckIcon size={48} className="mx-auto mb-3 opacity-50" />
                <p>No compliance data available</p>
                <p className="text-xs mt-1 text-gray-400 dark:text-gray-500">
                    Click "Collect Evidence Now" to dispatch evidence collection to this agent.
                </p>
                <div className="mt-4 flex items-center gap-3 justify-center">
                    {onCollect && (
                        <button onClick={handleCollect} disabled={isCollecting}
                            className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-md text-sm font-medium transition-colors disabled:opacity-50 flex items-center">
                            <svg className={`w-4 h-4 mr-2 ${isCollecting ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                            </svg>
                            {isCollecting ? 'Collecting…' : 'Collect Evidence Now'}
                        </button>
                    )}
                    <button onClick={handleRefresh} disabled={isRefreshing}
                        className="px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white rounded-md text-sm font-medium transition-colors disabled:opacity-50 flex items-center">
                        <svg className={`w-4 h-4 mr-2 ${isRefreshing ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                        </svg>
                        {isRefreshing ? 'Refreshing...' : 'Refresh Data'}
                    </button>
                </div>
            </div>
        );
    }

    const getStatusIcon = (status: string) => {
        switch (status) {
            case 'passed': return <CheckIcon size={16} className="text-green-600 dark:text-green-400" />;
            case 'failed': return <XIcon size={16} className="text-red-600 dark:text-red-400" />;
            case 'warning': return <AlertTriangleIcon size={16} className="text-yellow-600 dark:text-yellow-400" />;
            default: return null;
        }
    };

    const getStatusColor = (status: string) => {
        switch (status) {
            case 'passed': return 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300';
            case 'failed': return 'bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-300';
            case 'warning': return 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-300';
            default: return 'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-300';
        }
    };

    const categories = [...new Set(rules.map(r => r.category))];

    const handleFix = async (rule: ComplianceRule) => {
        const fixTarget = rule.checkName || rule.title;
        if (!agentId) { showToast("Agent ID is missing, cannot trigger fix.", 'error'); return; }
        try {
            const formData = new FormData();
            formData.append('check_name', fixTarget);
            const response = await fetch(`/api/agents/${agentId}/compliance/fix`, { method: 'POST', body: formData });
            const result = await response.json();
            if (result.success) {
                showToast(`Fix instruction sent for: ${fixTarget}. The agent will apply it on next check-in.`, 'success');
            } else {
                showToast(`Failed to trigger fix: ${result.message}`, 'error');
            }
        } catch (error) {
            showToast(`Error connecting to backend: ${error}`, 'error');
        }
    };

    return (
        <div className="space-y-6">
            <div className="bg-gradient-to-br from-primary-50 to-primary-100 dark:from-primary-900/20 dark:to-primary-800/20 rounded-lg p-6 border border-primary-200 dark:border-primary-700">
                <div className="flex items-center justify-between">
                    <div>
                        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
                            {data.framework || 'System'} Compliance Score
                        </h3>
                        <div className="flex items-baseline space-x-3">
                            <div className="text-5xl font-bold text-primary-600 dark:text-primary-400">{stats.score}%</div>
                            <div className="text-sm text-gray-600 dark:text-gray-400">
                                {stats.passed} passed · {stats.warnings} warnings · {stats.failed} failed
                                <span className="ml-2 text-xs text-gray-400 dark:text-gray-500">(warnings = ½ credit)</span>
                                {data?.total_controls && data.total_controls > stats.total && (
                                    <span className="ml-2 text-xs text-primary-500 dark:text-primary-400">
                                        · {stats.total} checks · {data.total_controls} control IDs
                                    </span>
                                )}
                            </div>
                        </div>
                    </div>
                    <div className="flex items-center space-x-2">
                        {onCollect && (
                            <button onClick={handleCollect} disabled={isCollecting}
                                className="px-3 py-2 bg-green-600 hover:bg-green-700 text-white rounded-md text-sm font-medium shadow-sm transition-colors disabled:opacity-50 flex items-center"
                                title="Dispatch evidence collection to this agent now">
                                <svg className={`w-4 h-4 mr-2 ${isCollecting ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                                </svg>
                                {isCollecting ? 'Collecting…' : 'Collect Now'}
                            </button>
                        )}
                        {onRefresh && (
                            <button onClick={handleRefresh} disabled={isRefreshing}
                                className="px-3 py-2 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-200 rounded-md text-sm font-medium border border-gray-200 dark:border-gray-600 shadow-sm transition-colors disabled:opacity-50 flex items-center"
                                title="Refresh compliance data from last scan">
                                <svg className={`w-4 h-4 mr-2 ${isRefreshing ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                                </svg>
                                {isRefreshing ? 'Refreshing...' : 'Refresh'}
                            </button>
                        )}
                        <ShieldCheckIcon size={64} className="text-primary-500 opacity-20" />
                    </div>
                </div>
                <div className="mt-4">
                    <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-3">
                        <div className="bg-primary-600 h-3 rounded-full transition-all duration-500" style={{ width: `${stats.score}%` }} />
                    </div>
                </div>
            </div>

            <div className="grid grid-cols-3 gap-4">
                <div className="bg-white border border-gray-200 dark:bg-gray-800 dark:border-gray-700 rounded-xl p-6 shadow-sm">
                    <div className="flex items-center justify-between">
                        <div>
                            <p className="text-sm font-semibold text-green-600 dark:text-green-400 mb-1">Passed</p>
                            <p className="text-3xl font-bold text-gray-900 dark:text-white">{stats.passed}</p>
                        </div>
                        <div className="p-3 bg-green-50 dark:bg-green-900/20 rounded-lg"><CheckIcon size={24} className="text-green-500" /></div>
                    </div>
                </div>
                <div className="bg-white border border-gray-200 dark:bg-gray-800 dark:border-gray-700 rounded-xl p-6 shadow-sm">
                    <div className="flex items-center justify-between">
                        <div>
                            <p className="text-sm font-semibold text-red-600 dark:text-red-400 mb-1">Failed</p>
                            <p className="text-3xl font-bold text-gray-900 dark:text-white">{stats.failed}</p>
                        </div>
                        <div className="p-3 bg-red-50 dark:bg-red-900/20 rounded-lg"><XIcon size={24} className="text-red-500" /></div>
                    </div>
                </div>
                <div className="bg-white border border-gray-200 dark:bg-gray-800 dark:border-gray-700 rounded-xl p-6 shadow-sm">
                    <div className="flex items-center justify-between">
                        <div>
                            <p className="text-sm font-semibold text-amber-600 dark:text-amber-400 mb-1">Warnings</p>
                            <p className="text-3xl font-bold text-gray-900 dark:text-white">{stats.warnings}</p>
                        </div>
                        <div className="p-3 bg-amber-50 dark:bg-amber-900/20 rounded-lg"><AlertTriangleIcon size={24} className="text-amber-500" /></div>
                    </div>
                </div>
            </div>

            <div>
                <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">Compliance Rules</h4>
                <div className="space-y-4">
                    {categories.map(category => {
                        const categoryRules = rules.filter(r => r.category === category);
                        const failedRules = categoryRules.filter(r => r.status === 'failed');
                        return (
                            <div key={category} className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
                                <div className="bg-gray-50 dark:bg-gray-700/50 px-4 py-3 border-b border-gray-200 dark:border-gray-700">
                                    <div className="flex items-center justify-between">
                                        <h5 className="font-medium text-gray-900 dark:text-white">{category}</h5>
                                        <span className="text-sm text-gray-500 dark:text-gray-400">
                                            {categoryRules.length} rules
                                            {failedRules.length > 0 && (
                                                <span className="ml-2 text-red-600 dark:text-red-400">({failedRules.length} failed)</span>
                                            )}
                                        </span>
                                    </div>
                                </div>

                                <div className="divide-y divide-gray-200 dark:divide-gray-700">
                                    {categoryRules.map(rule => {
                                        const needsAttention = rule.status === 'failed' || rule.status === 'warning';
                                        const tip = needsAttention ? getRemediationTip(rule.checkName || rule.title) : null;
                                        const isTipsOpen = expandedTips.has(rule.id);

                                        return (
                                            <div key={rule.id} className="px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-700/30 transition-colors">
                                                <div className="flex items-start justify-between">
                                                    <div className="flex items-start space-x-3 flex-grow min-w-0">
                                                        <div className="mt-0.5 flex-shrink-0">{getStatusIcon(rule.status)}</div>
                                                        <div className="flex-grow min-w-0">
                                                            <div className="flex items-center justify-between gap-2 flex-wrap">
                                                                <p className="text-sm font-medium text-gray-900 dark:text-gray-200">{rule.title}</p>
                                                                {needsAttention && (
                                                                    <div className="flex items-center gap-2 flex-shrink-0">
                                                                        {tip && (
                                                                            <button onClick={() => toggleTips(rule.id)}
                                                                                className="px-2 py-1 text-xs font-medium text-blue-700 dark:text-blue-300 bg-blue-50 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-700 rounded hover:bg-blue-100 dark:hover:bg-blue-900/50 transition-colors flex items-center gap-1">
                                                                                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.346.346a3.51 3.51 0 00-.91 1.668H9.84a3.51 3.51 0 00-.91-1.668l-.346-.346z" />
                                                                                </svg>
                                                                                {isTipsOpen ? 'Hide tips' : 'Fix tips'}
                                                                            </button>
                                                                        )}
                                                                        <button onClick={() => handleFix(rule)}
                                                                            className={`px-3 py-1 text-white text-xs font-semibold rounded shadow-sm focus:outline-none focus:ring-2 focus:ring-offset-2 transition-all flex items-center ${rule.status === 'failed' ? 'bg-red-600 hover:bg-red-700 focus:ring-red-500' : 'bg-amber-500 hover:bg-amber-600 focus:ring-amber-400'}`}>
                                                                            <svg className="w-3 h-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                                                                            </svg>
                                                                            Fix
                                                                        </button>
                                                                    </div>
                                                                )}
                                                            </div>

                                                            {rule.description && (
                                                                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{rule.description}</p>
                                                            )}

                                                            {/* Expandable fix tips panel */}
                                                            {tip && isTipsOpen && (
                                                                <div className="mt-2 rounded-lg border border-blue-200 dark:border-blue-800 overflow-hidden">
                                                                    <div className="bg-blue-50 dark:bg-blue-900/30 px-3 py-2 border-b border-blue-200 dark:border-blue-800">
                                                                        <p className="text-xs font-semibold text-blue-800 dark:text-blue-300">How to fix manually</p>
                                                                        <p className="text-xs text-blue-700 dark:text-blue-200 mt-0.5">{tip.summary}</p>
                                                                    </div>
                                                                    <div className="bg-white dark:bg-gray-800/50 px-3 py-2">
                                                                        <ol className="space-y-1 list-decimal list-inside">
                                                                            {tip.steps.map((step, i) => (
                                                                                <li key={i} className="text-xs text-gray-700 dark:text-gray-300">{step}</li>
                                                                            ))}
                                                                        </ol>
                                                                        {tip.powershell && (
                                                                            <div className="mt-2">
                                                                                <div className="flex items-center justify-between mb-1">
                                                                                    <span className="text-xs font-semibold text-gray-600 dark:text-gray-400">PowerShell (run as Administrator):</span>
                                                                                    <button onClick={() => copyPowershell(rule.id, tip.powershell!)}
                                                                                        className="text-xs text-blue-600 dark:text-blue-400 hover:underline">
                                                                                        {copiedId === rule.id ? 'Copied!' : 'Copy'}
                                                                                    </button>
                                                                                </div>
                                                                                <pre className="text-xs bg-gray-900 text-green-400 p-2 rounded overflow-x-auto font-mono whitespace-pre-wrap break-all">{tip.powershell}</pre>
                                                                            </div>
                                                                        )}
                                                                    </div>
                                                                </div>
                                                            )}

                                                            {/* Backend-supplied remediation note */}
                                                            {rule.remediation && !isTipsOpen && (
                                                                <div className="mt-2 p-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-100 dark:border-blue-800 rounded-md">
                                                                    <div className="flex items-start">
                                                                        <svg className="h-4 w-4 text-blue-600 dark:text-blue-400 mt-0.5 flex-shrink-0" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
                                                                            <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
                                                                        </svg>
                                                                        <div className="ml-2">
                                                                            <h4 className="text-xs font-semibold text-blue-800 dark:text-blue-300">Remediation:</h4>
                                                                            <p className="text-xs text-blue-700 dark:text-blue-200 mt-0.5">{rule.remediation}</p>
                                                                        </div>
                                                                    </div>
                                                                </div>
                                                            )}

                                                            {rule.evidence && (
                                                                <div className="mt-2 p-2 bg-gray-100 dark:bg-gray-900/50 rounded text-xs font-mono text-gray-600 dark:text-gray-400 border border-gray-200 dark:border-gray-700">
                                                                    <span className="font-semibold select-none">Evidence: </span>{rule.evidence}
                                                                </div>
                                                            )}
                                                        </div>
                                                    </div>
                                                    <span className={`px-2 py-1 text-xs font-medium rounded-full whitespace-nowrap ml-3 flex-shrink-0 ${getStatusColor(rule.status)}`}>
                                                        {rule.status.toUpperCase()}
                                                    </span>
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>
                        );
                    })}
                </div>
            </div>

            <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-3 text-sm text-blue-800 dark:text-blue-200">
                <p className="font-medium">Compliance data from {data.framework}</p>
                <p className="text-xs mt-1">Click "Fix tips" on any failed or warning control for step-by-step remediation guidance and PowerShell commands.</p>
            </div>
        </div>
    );
};
