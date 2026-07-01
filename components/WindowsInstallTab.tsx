import React from 'react';
import { DownloadIcon, ChevronDownIcon } from './icons';

interface CodeBlockProps {
    command: string;
}

const CodeBlock: React.FC<CodeBlockProps> = ({ command }) => {
    const [copied, setCopied] = React.useState(false);

    const handleCopy = () => {
        navigator.clipboard.writeText(command).then(() => {
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        });
    };

    return (
        <div className="relative bg-gray-900 dark:bg-black rounded-md p-4 font-mono text-sm text-gray-200">
            <pre className="whitespace-pre-wrap break-all"><code>{command}</code></pre>
            <button
                onClick={handleCopy}
                className="absolute top-2 right-2 p-1.5 rounded-md bg-gray-700 hover:bg-gray-600 text-gray-300 focus:outline-none focus:ring-2 focus:ring-primary-500"
                aria-label="Copy command"
            >
                {copied ? (
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-green-400"><polyline points="20 6 9 17 4 12" /></svg>
                ) : (
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="9" y="9" width="13" height="13" rx="2" /><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" /></svg>
                )}
            </button>
        </div>
    );
};

const WIN_CHECKS = [
    { category: "Firewall & Network", checks: ["Windows Firewall Profiles", "Risky Network Ports", "TLS Security Config", "SMBv1 Protocol Disabled", "LLMNR/NetBIOS Protection"] },
    { category: "Antivirus & Endpoint", checks: ["Windows Defender Antivirus", "Exploit Protection (DEP/ASLR)", "Attack Surface Reduction", "Controlled Folder Access"] },
    { category: "Authentication", checks: ["Password Policy (Min Length)", "Guest Account Disabled", "Maximum Password Age", "Account Lockout Policy", "Password Complexity", "Password History", "Minimum Password Age", "User Access Control"] },
    { category: "Remote Access", checks: ["RDP NLA Required", "Remote Desktop Service", "WinRM Service Status"] },
    { category: "Encryption & Boot", checks: ["BitLocker Encryption", "Secure Boot"] },
    { category: "Patching & Updates", checks: ["Windows Update Service"] },
    { category: "Audit & Logging", checks: ["Audit Logging Policy", "PowerShell Script Block Logging"] },
    { category: "Advanced Security", checks: ["Credential Guard", "Device Guard/WDAC"] },
    { category: "Compliance Ops", checks: ["Prohibited Software"] },
];

interface WindowsInstallTabProps {
    backendUrl: string;
    registrationKey: string;
}

export const WindowsInstallTab: React.FC<WindowsInstallTabProps> = ({ backendUrl, registrationKey }) => {
    const key = registrationKey || 'YOUR_REGISTRATION_KEY';
    const [buildState, setBuildState] = React.useState<'idle'|'building'|'done'|'failed'>('idle');
    const [buildError, setBuildError] = React.useState('');

    // Hide EXE download card on non-Windows — backend build requires Windows toolchain
    const isWindows = typeof navigator !== 'undefined' && /Win/i.test(navigator.platform || navigator.userAgent);

    // ── Build & Download handler ────────────────────────────────────────
    // POST /build → poll /build/{task_id} until done → download
    const handleBuildAndDownload = async () => {
        setBuildState('building');
        setBuildError('');
        try {
            // 1. Trigger the async build (runs Spyglass evidence collection + installer build)
            const triggerRes = await fetch(`${backendUrl}/api/agent-updates/build`, { method: 'POST' });
            if (!triggerRes.ok) {
                const err = await triggerRes.json().catch(() => ({}));
                setBuildError(err.detail || `HTTP ${triggerRes.status}`);
                setBuildState('failed');
                return;
            }
            const { task_id, poll_url } = await triggerRes.json();

            // 2. Poll until build is done (max 30s)
            let attempts = 0;
            const maxAttempts = 60;  // 30s at 500ms intervals
            let downloadUrl: string | null = null;

            while (attempts < maxAttempts) {
                await new Promise(r => setTimeout(r, 500));
                attempts++;

                const pollRes = await fetch(`${backendUrl}${poll_url}`);
                const state = await pollRes.json();

                if (state.status === 'done') {
                    downloadUrl = `${backendUrl}/api/agent-updates/download/OmniAgent-Setup.exe`;
                    break;
                }
                if (state.status === 'failed') {
                    setBuildError(state.error || 'Build failed');
                    setBuildState('failed');
                    return;
                }
            }

            if (!downloadUrl) {
                setBuildError('Build timed out after 30s. Try again.');
                setBuildState('failed');
                return;
            }

            // 3. Trigger the download
            setBuildState('done');
            const link = document.createElement('a');
            link.href = downloadUrl;
            link.download = 'OmniAgent-Setup.exe';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        } catch (err: any) {
            setBuildError(err.message || 'Build failed');
            setBuildState('failed');
        }
    };

    return (
        <div className="space-y-5">
            {/* EXE Installer download card — Windows only */}
            {isWindows ? (
            <div className="flex items-center gap-3 p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-200 dark:border-blue-800">
                <DownloadIcon size={20} className="text-blue-600 dark:text-blue-400 flex-shrink-0" />
                <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-blue-900 dark:text-blue-200">Windows Installer (EXE)</p>
                    <p className="text-xs text-blue-700 dark:text-blue-400">Click-to-install wizard — includes service + evidence collection</p>
                    {buildState === 'building' && (
                        <p className="text-xs text-amber-600 dark:text-amber-400 mt-1">
                            🔄 Building installer with Spyglass evidence collection… this may take 15–30s
                        </p>
                    )}
                    {buildError && (
                        <p className="text-xs text-red-600 dark:text-red-400 mt-1">❌ {buildError}</p>
                    )}
                </div>
                <button
                    onClick={handleBuildAndDownload}
                    disabled={buildState === 'building'}
                    className={`flex-shrink-0 px-3 py-1.5 text-white text-xs font-medium rounded-md transition-colors ${
                        buildState === 'building'
                            ? 'bg-gray-400 cursor-not-allowed'
                            : 'bg-blue-600 hover:bg-blue-700'
                    }`}
                >
                    {buildState === 'building' ? '⏳ Building…' : buildState === 'done' ? '✅ Download .exe' : 'Download .exe'}
                </button>
            </div>
            ) : (
            <div className="flex items-center gap-3 p-3 bg-gray-50 dark:bg-gray-800/20 rounded-lg border border-gray-200 dark:border-gray-700">
                <DownloadIcon size={20} className="text-gray-400 flex-shrink-0" />
                <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Windows Installer (EXE)</p>
                    <p className="text-xs text-gray-400 dark:text-gray-500">Available on Windows only — use the install commands below on target machines</p>
                </div>
            </div>
            )}

            {/* Step 1 — Install Agent Service */}
            <div className="space-y-3">
                <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
                    Step 1 — Install Agent Service
                </h4>
                <CodeBlock command={`# Run as Administrator in PowerShell\n$key = "${key}"\nInvoke-WebRequest -Uri "${backendUrl}/api/agent/install-script" -OutFile win-install.ps1 -UseBasicParsing\n.\\win-install.ps1 -ApiUrl "${backendUrl}" -RegistrationKey $key`} />
            </div>

            {/* Step 2 — Collect Evidence Now */}
            <div className="space-y-3">
                <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
                    Step 2 — Collect Evidence Now (runs immediately after service install)
                </h4>
                <CodeBlock command={`$evidenceScript = "C:\\Program Files\\OmniAgent\\Collect-Evidence.ps1"\npowershell -ExecutionPolicy Bypass -File $evidenceScript`} />
            </div>

            {/* Step 3 — Standalone evidence */}
            <div className="space-y-3">
                <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
                    Step 3 — Standalone Evidence Collection (no service install needed)
                </h4>
                <CodeBlock command={`# Run as Administrator — collects all 28 checks and submits evidence\n$key = "${key}"\nInvoke-WebRequest -Uri "${backendUrl}/api/agent/collect-evidence-script" -OutFile Collect-Evidence.ps1 -UseBasicParsing\n.\\Collect-Evidence.ps1 -ApiUrl "${backendUrl}" -RegKey $key`} />
            </div>

            {/* 28 checks collapsible */}
            <details className="mt-4 group">
                <summary className="cursor-pointer text-sm font-medium text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200 list-none flex items-center gap-2">
                    <ChevronDownIcon size={14} className="transition-transform group-open:rotate-180" />
                    28 Windows Compliance Checks Collected
                </summary>
                <div className="mt-3 grid grid-cols-1 gap-2 text-xs text-gray-600 dark:text-gray-400">
                    {WIN_CHECKS.map(({ category, checks }) => (
                        <div key={category}>
                            <span className="font-medium text-gray-700 dark:text-gray-300">{category}:</span>{" "}
                            {checks.join(", ")}
                        </div>
                    ))}
                </div>
            </details>
        </div>
    );
};
