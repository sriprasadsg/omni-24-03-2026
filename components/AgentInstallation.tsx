import React, { useState } from 'react';
import { authFetch } from '../services/apiService';
import { CopyIcon, CheckIcon, LinuxIcon, WindowsIcon, DockerIcon, KubernetesIcon, ChevronDownIcon, AlertTriangleIcon, DownloadIcon, InfoIcon, CodeIcon, BuildingIcon } from './icons';
import { useUser } from '../contexts/UserContext';
import { Tenant } from '../types';

/** Dynamically resolve the backend base URL from the browser's current location.
 *  - On Ubuntu/production (nginx at port 80/443): returns '' so fetch uses relative /api/... paths via nginx proxy.
 *  - On local dev (Vite at port 3000): returns 'http://hostname:5000' for direct backend access.
 */
function getBackendUrl(): string {
    const port = window.location.port;
    // If on port 80/443 (nginx/production), use relative empty string — nginx proxies /api to :5000
    if (!port || port === '80' || port === '443') {
        return '';
    }
    // Otherwise (local dev on 3000), call backend directly
    const hostname = window.location.hostname;
    return `http://${hostname}:5000`;
}

interface CodeBlockProps {
    command: string;
}

const CodeBlock: React.FC<CodeBlockProps> = ({ command }) => {
    const [copied, setCopied] = useState(false);

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
                {copied ? <CheckIcon size={16} className="text-green-400" /> : <CopyIcon size={16} />}
            </button>
        </div>
    );
};

type PlatformTab = 'linux' | 'windows' | 'python' | 'docker' | 'kubernetes';

interface AgentInstallationProps {
    registrationKey: string | null;
    tenantId?: string | null;
    tenants?: Tenant[];
    onSelectTenant?: (tenantId: string) => void;
}



export const AgentInstallation: React.FC<AgentInstallationProps> = ({ registrationKey, tenantId, tenants, onSelectTenant }) => {
    const { hasPermission, currentUser } = useUser();
    // Allow agent installation for Super Admins and users with view:agents permission
    const canInstallAgents = currentUser?.role === 'Super Admin' || currentUser?.role === 'superadmin' || hasPermission('view:agents');
    const [isOpen, setIsOpen] = useState(true);
    const [activeTab, setActiveTab] = useState<PlatformTab>('linux');

    // Editable server URL — agents embed this in their config.yaml to call back to the platform.
    // Defaults to the auto-detected backend URL but must be set to the real server IP/hostname
    // when agents will run on machines other than localhost.
    const [serverUrl, setServerUrl] = useState<string>(() => getBackendUrl() || window.location.origin);
    const isLocalhost = /localhost|127\.0\.0\.1/.test(serverUrl);

    const commands = registrationKey ? {
        linux: `curl -sSL ${serverUrl}/static/linux-install.sh | sudo bash -s -- --registration-key ${registrationKey}`,
        windows: `powershell -Command "Invoke-WebRequest -Uri '${serverUrl}/api/install-script' -OutFile 'install.ps1'; & './install.ps1' -RegistrationKey '${registrationKey}' -BackendUrl '${serverUrl}'; Remove-Item 'install.ps1'"`,
        python: `curl -sSL ${serverUrl}/static/omni-agent-install.py | python3 - --registration-key ${registrationKey} --api-url ${serverUrl}`,
        docker: `docker build -t omni-agent:latest ./agent\ndocker run -d --name omni-agent \\\n  -v /var/run/docker.sock:/var/run/docker.sock:ro \\\n  -e OMNI_REGISTRATION_KEY="${registrationKey}" \\\n  omni-agent:latest`,
        kubernetes: `helm install omni-agent ./backend/static/charts/omni-agent \\\n  --set registrationKey=${registrationKey} \\\n  --set clusterName=my-prod-cluster`,
    } : null;

    const tabs: { id: PlatformTab; name: string; icon: React.ReactNode }[] = [
        { id: 'linux', name: 'Linux/macOS', icon: <LinuxIcon size={20} /> },
        { id: 'windows', name: 'Windows', icon: <WindowsIcon size={20} /> },
        { id: 'python', name: 'Python', icon: <CodeIcon size={20} /> },
        { id: 'docker', name: 'Docker', icon: <DockerIcon size={20} /> },
        { id: 'kubernetes', name: 'Kubernetes', icon: <KubernetesIcon size={20} /> },
    ];

    let instructionMessage: string | null = null;
    if (!canInstallAgents) {
        instructionMessage = "You do not have the required permissions to install new agents.";
    } else if (!registrationKey) {
        if (!tenants || tenants.length === 0) {
            instructionMessage = "Please select a tenant to view agent installation commands. Super Admins must select 'View Tenant' from the Tenant Management dashboard.";
        }
    }

    const [isDownloadingZip, setIsDownloadingZip] = React.useState(false);

    const handleDownloadAgentZip = async () => {
        if (!tenantId) return;
        setIsDownloadingZip(true);
        try {
            const backendUrl = encodeURIComponent(serverUrl);

            // Step 1: exchange the JWT for a short-lived (60s) one-time download token.
            // This avoids the fetch()+blob+proxy pipeline that causes ERR_FAILED 200 on
            // the Vite dev proxy (and some nginx configurations) for binary responses.
            const tokenRes = await authFetch(`/api/agent/download-token/${tenantId}`, {
                method: 'POST',
            });
            if (!tokenRes.ok) {
                alert('Failed to initiate download. Please try again.');
                return;
            }
            const { token: downloadToken } = await tokenRes.json();

            // Step 2: trigger a direct browser navigation so the download manager
            // receives the ZIP — no JS body-reading, no proxy buffering issues.
            window.location.href = `/api/agent/download/${tenantId}?download_token=${downloadToken}&api_url=${backendUrl}`;
        } catch (e) {
            alert('An error occurred while downloading the agent package.');
        } finally {
            // Give the browser a moment to initiate the download before clearing the spinner
            setTimeout(() => setIsDownloadingZip(false), 1500);
        }
    };


    const isFreeTierDownloadable = !!tenantId;

    return (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md">
            <button
                className="w-full p-4 flex justify-between items-center text-left"
                onClick={() => setIsOpen(!isOpen)}
                aria-expanded={isOpen}
            >
                <h3 className="text-lg font-semibold flex items-center">
                    Agent Installation
                </h3>
                <ChevronDownIcon
                    size={20}
                    className={`text-gray-500 dark:text-gray-400 transition-transform duration-300 ${isOpen ? 'rotate-180' : ''}`}
                />
            </button>

            {isOpen && (
                <div className="p-4 border-t border-gray-200 dark:border-gray-700">
                    {instructionMessage ? (
                        <div className="p-4 bg-amber-50 dark:bg-amber-900/50 rounded-lg flex items-center text-sm text-amber-800 dark:text-amber-300 border border-amber-200 dark:border-amber-800">
                            <AlertTriangleIcon size={20} className="mr-3 flex-shrink-0 text-amber-500" />
                            <div>
                                <span className="font-semibold">Installation Unavailable.</span> {instructionMessage}
                            </div>
                        </div>
                    ) : (
                        <>
                            <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
                                Use the tenant-specific registration key below with the appropriate one-line command to install a new agent. The agent will automatically register to the correct tenant.
                            </p>

                            {/* Server URL — embedded in agent config.yaml and install commands */}
                            <div className="mb-4">
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                                    Platform Server URL
                                </label>
                                <input
                                    type="text"
                                    value={serverUrl}
                                    onChange={e => setServerUrl(e.target.value.trimEnd())}
                                    placeholder="http://192.168.1.100:5000"
                                    className="block w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-primary-500"
                                />
                                {isLocalhost ? (
                                    <p className="mt-1 text-xs text-amber-600 dark:text-amber-400 flex items-center gap-1">
                                        <AlertTriangleIcon size={12} />
                                        Using localhost — agents on remote machines won't be able to reach the server. Replace with your server's IP or hostname (e.g. <code className="font-mono">http://192.168.1.100:5000</code>).
                                    </p>
                                ) : (
                                    <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                                        This URL is embedded in install commands and the agent config.yaml so agents can call back to the platform.
                                    </p>
                                )}
                            </div>

                            <div className="flex flex-col sm:flex-row sm:items-end gap-4">
                                <div className="flex-grow">
                                    {registrationKey ? (
                                        <>
                                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                                                Tenant Registration Key
                                            </label>
                                            <CodeBlock command={registrationKey} />
                                        </>
                                    ) : (
                                        tenants && onSelectTenant && (
                                            <div>
                                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                                    Select Tenant to Install Agent
                                                </label>
                                                <div className="relative">
                                                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                                                        <BuildingIcon className="text-gray-500" size={18} />
                                                    </div>
                                                    <select
                                                        className="block w-full pl-10 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-primary-500 focus:border-primary-500 sm:text-sm rounded-md dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                                                        onChange={(e) => onSelectTenant(e.target.value)}
                                                        defaultValue=""
                                                    >
                                                        <option value="" disabled>Select a tenant...</option>
                                                        {tenants.map((tenant) => (
                                                            <option key={tenant.id} value={tenant.id}>
                                                                {tenant.name}
                                                            </option>
                                                        ))}
                                                    </select>
                                                </div>
                                                <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
                                                    Select a tenant to generate the installation commands for that specific environment.
                                                </p>
                                            </div>
                                        )
                                    )}
                                </div>
                            </div>

                            {registrationKey && commands && (
                                <div className="mt-6">
                                    <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Platform-Specific Commands</h4>
                                    <div className="border-b border-gray-200 dark:border-gray-700">
                                        <nav className="-mb-px flex space-x-6 overflow-x-auto" aria-label="Tabs">
                                            {tabs.map(tab => (
                                                <button
                                                    key={tab.id}
                                                    onClick={() => setActiveTab(tab.id)}
                                                    className={`flex items-center whitespace-nowrap py-3 px-1 border-b-2 font-medium text-sm transition-colors ${activeTab === tab.id
                                                        ? 'border-primary-500 text-primary-600 dark:text-primary-400'
                                                        : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-200'
                                                        }`}
                                                >
                                                    <span className="mr-2">{tab.icon}</span>
                                                    {tab.name}
                                                </button>
                                            ))}
                                        </nav>
                                    </div>

                                    <div className="pt-4">
                                        <CodeBlock command={commands[activeTab]} />

                                        {/* Download Agent Zip Button */}
                                        {isFreeTierDownloadable && (
                                            <div className="mt-4">
                                                <button
                                                    onClick={handleDownloadAgentZip}
                                                    disabled={isDownloadingZip}
                                                    className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl font-semibold text-sm text-white bg-gradient-to-r from-primary-600 to-indigo-600 hover:from-primary-700 hover:to-indigo-700 disabled:opacity-60 disabled:cursor-not-allowed transition-all duration-200 shadow-md hover:shadow-lg hover:-translate-y-0.5"
                                                >
                                                    <DownloadIcon size={16} />
                                                    {isDownloadingZip ? 'Generating package...' : '⬇ Download Agent Package (.zip)'}
                                                </button>
                                                <p className="mt-2 text-xs text-center text-gray-500 dark:text-gray-400">
                                                    Pre-configured with your tenant's registration key — just extract and run <code className="font-mono bg-gray-100 dark:bg-gray-700 px-1 rounded">python agent.py</code>
                                                </p>
                                            </div>
                                        )}

                                        <div className="mt-3 text-xs text-gray-500 dark:text-gray-400">
                                            {activeTab === 'linux' && (
                                                <div className="flex items-center">
                                                    <DownloadIcon size={14} className="mr-2" />
                                                    Alternatively, you can <a href={`${getBackendUrl()}/static/linux-install.sh`} download className="text-primary-600 dark:text-primary-400 hover:underline font-medium">download the installation script</a>.
                                                </div>
                                            )}
                                            {activeTab === 'windows' && (
                                                <div className="flex items-center">
                                                    <DownloadIcon size={14} className="mr-2" />
                                                    Alternatively, you can <a href={`${getBackendUrl()}/api/install-script`} download className="text-primary-600 dark:text-primary-400 hover:underline font-medium">download the installation script</a>.
                                                </div>
                                            )}
                                            {activeTab === 'python' && (
                                                <div className="flex items-center">
                                                    <DownloadIcon size={14} className="mr-2" />
                                                    Alternatively, you can <a href={`${getBackendUrl()}/static/omni-agent-install.py`} download className="text-primary-600 dark:text-primary-400 hover:underline font-medium">download the installation script</a>.
                                                </div>
                                            )}
                                            {activeTab === 'docker' && (
                                                <div className="flex items-center">
                                                    <InfoIcon size={14} className="mr-2" />
                                                    The Docker command builds the agent image locally and runs it.
                                                </div>
                                            )}
                                            {activeTab === 'kubernetes' && (
                                                <div className="flex items-center">
                                                    <InfoIcon size={14} className="mr-2" />
                                                    The Helm command installs the agent using the local chart located in <code>backend/static/charts/omni-agent</code>.
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            )}
                        </>
                    )}
                </div>
            )}
        </div>
    );
};
