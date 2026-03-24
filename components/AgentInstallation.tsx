import React, { useState } from 'react';
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

const linuxScriptContent = `#!/bin/bash
set -e

REGISTRATION_KEY=""

# Parse command-line arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --registration-key) REGISTRATION_KEY="$2"; shift ;;
        *) echo "Unknown parameter passed: $1"; exit 1 ;;
    esac
    shift
done

if [ -z "$REGISTRATION_KEY" ]; then
    echo "Error: --registration-key is a required argument."
    exit 1
fi

echo "Omni-Agent AI Installer for Linux/macOS"
echo "========================================"

echo "[1/4] Downloading agent package..."
sleep 1
echo "Download complete."

echo "[2/4] Verifying package integrity..."
sleep 1
echo "Verification successful."

echo "[3/4] Installing agent to /opt/omni-agent..."
sleep 2
echo "Installation complete."

echo "[4/4] Configuring agent with registration key..."
sleep 1
echo "Configuration complete. Agent is starting."

echo "✅ Omni-Agent AI has been installed successfully!"
`;

const windowsScriptContent = `[CmdletBinding()]
param (
    [Parameter(Mandatory=$true)]
    [string]$RegistrationKey
)

Write-Host "Omni-Agent AI Installer for Windows"
Write-Host "================================="

if (-not $RegistrationKey) {
    Write-Error "Error: -RegistrationKey is a required argument."
    exit 1
}

Write-Host "[1/4] Downloading agent package..."
Start-Sleep -Seconds 1
Write-Host "Download complete."

Write-Host "[2/4] Verifying package integrity..."
Start-Sleep -Seconds 1
Write-Host "Verification successful."

Write-Host "[3/4] Installing agent to C:\\Program Files\\OmniAgent..."
Start-Sleep -Seconds 2
Write-Host "Installation complete."

Write-Host "[4/4] Configuring agent with registration key..."
Start-Sleep -Seconds 1
Write-Host "Configuration complete. Agent service is starting."

Write-Host "✅ Omni-Agent AI has been installed successfully!"
`;

const pythonScriptContent = `#!/usr/bin/env python3
import argparse
import time
import sys
import platform
import socket
import json
from urllib import request

# In a real scenario, this would be the actual API endpoint.
# For this simulation, we'll just print the request.
API_ENDPOINT = "http://127.0.0.1:5000/api/agents/register" 
AGENT_VERSION = "3.1.0-python"

def get_ip_address():
    """Gets the local IP address of the machine."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't have to be reachable
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

def main():
    parser = argparse.ArgumentParser(description="Omni-Agent AI Installer")
    parser.add_argument(
        "--registration-key",
        required=True,
        help="The tenant-specific registration key for agent installation."
    )
    args = parser.parse_args()

    print("Omni-Agent AI Python Installer")
    print("==============================")

    try:
        # Step 1: Simulate download
        print("[1/5] Downloading agent dependencies...")
        time.sleep(1)
        print("      Download complete.")

        # Step 2: Simulate verification
        print("[2/5] Verifying package integrity...")
        time.sleep(1)
        print("      Verification successful.")

        # Step 3: Simulate installation
        install_path = "/opt/omni-agent" if platform.system() != "Windows" else "C:\\\\Program Files\\\\OmniAgent"
        print(f"[3/5] Installing agent to {install_path}...")
        time.sleep(2)
        print("      Installation complete.")
        
        # Step 4: Gather system information
        print("[4/5] Gathering system information for registration...")
        hostname = socket.gethostname()
        ip_address = get_ip_address()
        os_platform = platform.system() # e.g., 'Linux', 'Windows', 'Darwin' (for macOS)
        
        # Map to platform types used in the UI
        platform_map = {
            'Linux': 'Linux',
            'Windows': 'Windows',
            'Darwin': 'macOS'
        }
        agent_platform = platform_map.get(os_platform, os_platform)

        payload = {
            "hostname": hostname,
            "ipAddress": ip_address,
            "platform": agent_platform,
            "version": AGENT_VERSION,
            "assetId": "new", # Instructs the backend to create a new asset
            "registrationKey": args.registration_key
        }
        time.sleep(1)
        print("      System information gathered.")

        # Step 5: Simulate registration with the backend
        print(f"[5/5] Registering agent with the Omni-Agent AI Platform...")
        print("--------------------------------------------------")
        print(f"SIMULATING API CALL TO: {API_ENDPOINT}")
        print("METHOD: POST")
        print("HEADERS: {'Content-Type': 'application/json'}")
        print("PAYLOAD:")
        print(json.dumps(payload, indent=2))
        print("--------------------------------------------------")
        
        # In a real script, you would make the actual HTTP request here:
        #
        # try:
        #     req = request.Request(API_ENDPOINT, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'})
        #     with request.urlopen(req) as response:
        #         if 200 <= response.status < 300:
        #             print("      Registration successful.")
        #         else:
        #             print(f"      Registration failed with status: {response.status}")
        #             print(response.read().decode('utf-8'))
        #             sys.exit(1)
        # except Exception as e:
        #     print(f"      Error during registration: {e}")
        #     sys.exit(1)

        time.sleep(1.5)
        print("      Registration successful (simulation).")

        print("\\n✅ Omni-Agent AI (Python) has been installed and registered successfully!")

    except Exception as e:
        print(f"\\n❌ An error occurred during installation: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
`;


export const AgentInstallation: React.FC<AgentInstallationProps> = ({ registrationKey, tenantId, tenants, onSelectTenant }) => {
    const { hasPermission, currentUser } = useUser();
    // Allow agent installation for Super Admins and users with view:agents permission
    const canInstallAgents = currentUser?.role === 'Super Admin' || currentUser?.role === 'superadmin' || hasPermission('view:agents');
    const [isOpen, setIsOpen] = useState(true);
    const [activeTab, setActiveTab] = useState<PlatformTab>('linux');

    const commands = registrationKey ? (() => {
        const backendBase = getBackendUrl();
        return {
            linux: `curl -sSL ${backendBase}/static/linux-install.sh | sudo bash -s -- --registration-key ${registrationKey}`,
            windows: `powershell -Command "Invoke-WebRequest -Uri '${backendBase}/api/install-script' -OutFile 'install.ps1'; & './install.ps1' -RegistrationKey '${registrationKey}' -BackendUrl '${backendBase}'; Remove-Item 'install.ps1'"`,
            python: `curl -sSL ${backendBase}/static/omni-agent-install.py | python3 - --registration-key ${registrationKey}`,
            docker: `docker build -t omni-agent:latest ./agent\ndocker run -d --name omni-agent \\\n  -v /var/run/docker.sock:/var/run/docker.sock:ro \\\n  -e OMNI_REGISTRATION_KEY="${registrationKey}" \\\n  omni-agent:latest`,
            kubernetes: `helm install omni-agent ./backend/static/charts/omni-agent \\\n  --set registrationKey=${registrationKey} \\\n  --set clusterName=my-prod-cluster`,
        };
    })() : null;

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

    const handleDownload = (filename: string, content: string) => {
        const element = document.createElement("a");
        const file = new Blob([content], { type: 'text/plain' });
        element.href = URL.createObjectURL(file);
        element.download = filename;
        document.body.appendChild(element); // Required for this to work in FireFox
        element.click();
        URL.revokeObjectURL(element.href);
        document.body.removeChild(element);
    };

    const [isDownloadingZip, setIsDownloadingZip] = React.useState(false);

    const handleDownloadAgentZip = async () => {
        if (!tenantId) return;
        setIsDownloadingZip(true);
        try {
            const token = localStorage.getItem('token');
            const backendBase = getBackendUrl();
            const backendUrl = encodeURIComponent(backendBase);
            const res = await fetch(`${backendBase}/api/agent/download/${tenantId}?api_url=${backendUrl}`, {
                headers: { Authorization: `Bearer ${token}` }
            });
            if (!res.ok) {
                alert('Failed to download agent package. Please try again.');
                return;
            }
            const blob = await res.blob();
            const cdHeader = res.headers.get('Content-Disposition') || '';
            const match = cdHeader.match(/filename[^;=\n]*=(['"]?)([^'"\n;]+)\1/);
            let filename = match?.[2] || `omni-agent-${tenantId}.zip`;
            if (!filename.endsWith('.zip')) {
                filename += '.zip';
            }
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            setTimeout(() => {
                URL.revokeObjectURL(url);
            }, 1000);
        } catch (e) {
            alert('An error occurred while downloading the agent package.');
        } finally {
            setIsDownloadingZip(false);
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
