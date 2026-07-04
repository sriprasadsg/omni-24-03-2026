import React, { useState } from 'react';
import { authFetch } from '../services/apiService';
import { showToast } from '../utils/toast';

const MCP_TOOLS = [
  { name: 'list_frameworks', desc: 'List all compliance frameworks', params: '{}' },
  { name: 'get_control_status', desc: 'Get control status across assets', params: '{"control_id": "CC6.1"}' },
  { name: 'run_cloud_check', desc: 'Run a cloud security check', params: '{"provider": "aws", "account_id": "123"}' },
  { name: 'list_findings', desc: 'List security findings', params: '{"severity": "high"}' },
  { name: 'get_compliance_score', desc: 'Get compliance score', params: '{"framework": "soc2"}' },
];

const DO_CHECKS = [
  'Firewall Rules Restrict SSH', 'Firewall Rules Restrict RDP',
  'Managed Database Encryption', 'Database Backups Enabled',
  'Spaces Bucket Public Access Disabled', 'Load Balancer SSL Enabled',
  'Droplet Monitoring Enabled', 'VPC Network Isolation',
  'Kubernetes Auto-Upgrade Enabled', 'App Platform HTTPS Enforced',
];

export const ApiExtensionsDashboard: React.FC = () => {
  const [toolResult, setToolResult] = useState<any>(null);
  const [running, setRunning] = useState('');
  const [toolInputs, setToolInputs] = useState<any>({});

  const runTool = async (name: string) => {
    setRunning(name);
    setToolResult(null);
    try {
      const params = toolInputs[name] ? JSON.parse(toolInputs[name]) : {};
      const rawRes = await authFetch(`/api/mcp/execute/${name}`, {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(params),
      });
      const res = await rawRes.json();
      setToolResult(res);
      if (!rawRes.ok) showToast(res.detail || 'Tool execution failed', 'error');
    } catch (e: any) { showToast(e.message || 'Failed', 'error'); }
    finally { setRunning(''); }
  };

  const exportOcsf = async (endpoint: string, filename: string) => {
    try {
      const res = await authFetch(endpoint);
      if (!res.ok) throw new Error(`Export failed (${res.status})`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a'); a.href = url; a.download = filename;
      a.click(); URL.revokeObjectURL(url);
      showToast(`Exported ${filename}`, 'success');
    } catch { showToast('Export failed', 'error'); }
  };

  return (
    <div className="space-y-6">
      {/* MCP Tools */}
      <div className="space-y-2">
        <h3 className="text-sm font-semibold">MCP Protocol Tools</h3>
        <div className="grid grid-cols-1 gap-2">
          {MCP_TOOLS.map(t => (
            <div key={t.name} className="flex items-center gap-3 p-3 bg-white dark:bg-gray-800 rounded shadow-sm text-xs">
              <div className="flex-1">
                <span className="font-medium text-blue-600 dark:text-blue-400">{t.name}</span>
                <p className="text-gray-500">{t.desc}</p>
                <input
                  className="mt-1 w-full p-1 border rounded dark:bg-gray-700 dark:border-gray-600 font-mono text-xs"
                  placeholder={`Params: ${t.params}`}
                  value={toolInputs[t.name] || ''}
                  onChange={e => setToolInputs({...toolInputs, [t.name]: e.target.value})}
                />
              </div>
              <button onClick={() => runTool(t.name)} disabled={running === t.name}
                className="px-3 py-1 bg-blue-600 text-white rounded shrink-0 disabled:opacity-50">
                {running === t.name ? 'Running...' : 'Execute'}
              </button>
            </div>
          ))}
        </div>
        {toolResult && (
          <div className="p-3 bg-gray-50 dark:bg-gray-800 rounded text-xs font-mono border dark:border-gray-600">
            <pre className="whitespace-pre-wrap">{JSON.stringify(toolResult, null, 2)}</pre>
          </div>
        )}
      </div>

      {/* OCSF Export */}
      <div className="space-y-2">
        <h3 className="text-sm font-semibold">OCSF 1.0 Export</h3>
        <div className="flex gap-2">
          <button onClick={() => exportOcsf('/api/ocsf/findings', 'findings-ocsf.json')}
            className="px-4 py-2 bg-green-600 text-white text-xs rounded">
            Export Findings (OCSF)
          </button>
          <button onClick={() => exportOcsf('/api/ocsf/cloud-checks', 'cloud-checks-ocsf.json')}
            className="px-4 py-2 bg-green-600 text-white text-xs rounded">
            Export Cloud Checks (OCSF)
          </button>
        </div>
      </div>

      {/* DigitalOcean */}
      <div className="space-y-2">
        <h3 className="text-sm font-semibold">DigitalOcean Checks</h3>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
          {DO_CHECKS.map((c, i) => (
            <div key={i} className="p-2 bg-white dark:bg-gray-800 rounded shadow-sm text-xs flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-blue-400 shrink-0" />
              {c}
            </div>
          ))}
        </div>
      </div>

      {/* CLI Quickstart */}
      <div className="space-y-2">
        <h3 className="text-sm font-semibold">CLI Quickstart</h3>
        <div className="p-3 bg-gray-900 text-gray-200 rounded-md text-xs font-mono">
          <p># Install / configure</p>
          <p>export OMNI_API_URL="http://localhost:5000"</p>
          <p>export OMNI_API_TOKEN="your-api-token"</p>
          <p></p>
          <p># List frameworks</p>
          <p>python backend/scripts/omni-cli.py frameworks list</p>
          <p></p>
          <p># Cloud scan</p>
          <p>python backend/scripts/omni-cli.py scan cloud --provider digitalocean --account-id 12345</p>
          <p></p>
          <p># List high-severity findings</p>
          <p>python backend/scripts/omni-cli.py findings list --severity high --limit 10</p>
          <p></p>
          <p># Compliance score</p>
          <p>python backend/scripts/omni-cli.py score --framework soc2</p>
        </div>
      </div>
    </div>
  );
};
