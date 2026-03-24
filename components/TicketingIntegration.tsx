import React, { useEffect, useState } from 'react';

const API = '/api';
function getHeaders(): HeadersInit {
    const keys = ['access_token', 'token', 'authToken'];
    let t = ''; for (const k of keys) { t = localStorage.getItem(k) || ''; if (t) break; }
    return { 'Content-Type': 'application/json', ...(t ? { Authorization: `Bearer ${t}` } : {}) };
}

const PROVIDERS = ['jira', 'servicenow', 'zoho', 'custom'];
const SEVERITIES = ['critical', 'high', 'medium', 'low'];

export default function TicketingIntegration() {
    const [config, setConfig] = useState<any>({
        provider: 'jira',
        auto_create_severity: ['critical'],
        jira_issue_type: 'Bug',
        custom_webhook_method: 'POST',
        custom_webhook_headers: {},
        custom_webhook_payload: {}
    });
    const [tickets, setTickets] = useState<any[]>([]);
    const [testing, setTesting] = useState(false);
    const [saving, setSaving] = useState(false);
    const [feedback, setFeedback] = useState<{ msg: string; ok: boolean } | null>(null);
    const [tab, setTab] = useState<'config' | 'tickets'>('config');

    const load = async () => {
        const [r1, r2] = await Promise.all([
            fetch(`${API}/ticketing/config`, { headers: getHeaders() }).then(r => r.json()).catch(() => { }),
            fetch(`${API}/ticketing/tickets`, { headers: getHeaders() }).then(r => r.json()).catch(() => []),
        ]);
        if (r1 && r1.provider) {
            // Ensure JSON fields are parsed if they come as strings (though backend sends objects)
            setConfig((c: any) => ({ ...c, ...r1 }));
        }
        setTickets(Array.isArray(r2) ? r2 : []);
    };
    useEffect(() => { load(); }, []);

    const save = async () => {
        setSaving(true);
        const r = await fetch(`${API}/ticketing/config`, { method: 'POST', headers: getHeaders(), body: JSON.stringify(config) });
        const d = await r.json();
        setFeedback({ msg: d.success ? 'Configuration saved!' : 'Failed to save.', ok: !!d.success });
        setTimeout(() => setFeedback(null), 3000);
        setSaving(false);
    };

    const testConnection = async () => {
        setTesting(true);
        const r = await fetch(`${API}/ticketing/test`, { method: 'POST', headers: getHeaders(), body: JSON.stringify({ provider: config.provider }) });
        const d = await r.json();
        setFeedback({ msg: d.success ? `✓ Test ticket created: ${d.ticket_key || d.ticket_number || 'ok'}` : `✗ ${d.error || 'Connection failed'}`, ok: !!d.success });
        setTimeout(() => setFeedback(null), 5000);
        setTesting(false);
        load();
    };

    const toggleSeverity = (sev: string) => {
        setConfig((c: any) => ({
            ...c,
            auto_create_severity: c.auto_create_severity.includes(sev)
                ? c.auto_create_severity.filter((s: string) => s !== sev)
                : [...c.auto_create_severity, sev],
        }));
    };

    const Field = ({ label, children }: { label: string; children: React.ReactNode }) => (
        <div style={{ marginBottom: 16 }}>
            <label style={{ color: '#94a3b8', fontSize: 12, display: 'block', marginBottom: 4 }}>{label}</label>
            {children}
        </div>
    );
    const Input = ({ value, onChange, placeholder, type = 'text' }: { value: string; onChange: (v: string) => void; placeholder?: string; type?: string }) => (
        <input type={type} value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder}
            style={{ width: '100%', padding: 10, background: '#0f172a', border: '1px solid #334155', borderRadius: 8, color: '#f1f5f9', fontSize: 14, boxSizing: 'border-box' }} />
    );
    const TextArea = ({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder?: string }) => (
        <textarea value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder} rows={4}
            style={{ width: '100%', padding: 10, background: '#0f172a', border: '1px solid #334155', borderRadius: 8, color: '#f1f5f9', fontSize: 13, boxSizing: 'border-box', fontFamily: 'monospace' }} />
    );

    const JsonField = ({ label, value, onChange }: { label: string; value: any; onChange: (val: any) => void }) => {
        const [text, setText] = useState(JSON.stringify(value, null, 2));
        const handleBlur = () => {
            try {
                const parsed = JSON.parse(text);
                onChange(parsed);
            } catch (e) {
                setFeedback({ msg: `Invalid JSON in ${label}`, ok: false });
            }
        };
        return (
            <Field label={label}>
                <TextArea value={text} onChange={setText} />
                <button onClick={handleBlur} style={{ marginTop: 4, fontSize: 11, background: '#334155', border: 'none', color: '#94a3b8', padding: '2px 8px', borderRadius: 4, cursor: 'pointer' }}>Apply JSON</button>
            </Field>
        );
    };

    return (
        <div style={{ background: '#0f172a', minHeight: '100vh', color: '#f1f5f9', padding: 24, paddingBottom: 100 }}>
            <div style={{ marginBottom: 24 }}>
                <h1 style={{ margin: 0, fontSize: 26, fontWeight: 800, background: 'linear-gradient(135deg,#0ea5e9,#7c3aed)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>Ticketing Integration</h1>
                <p style={{ color: '#64748b', margin: '4px 0 0' }}>Connect with Jira, ServiceNow, Zoho Desk or any Custom Webhook</p>
            </div>

            {/* Tabs */}
            <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
                {[{ id: 'config', label: '⚙ Configuration' }, { id: 'tickets', label: `🎫 Tickets Created (${tickets.length})` }].map(t => (
                    <button key={t.id} onClick={() => setTab(t.id as any)}
                        style={{
                            padding: '8px 20px', borderRadius: 8, border: 'none', cursor: 'pointer', fontWeight: 600, fontSize: 14,
                            background: tab === t.id ? '#7c3aed' : '#1e293b', color: tab === t.id ? 'white' : '#94a3b8'
                        }}>
                        {t.label}
                    </button>
                ))}
            </div>

            {tab === 'config' && (
                <div style={{ maxWidth: 680 }}>
                    {/* Provider select */}
                    <div style={{ background: '#1e293b', borderRadius: 12, padding: 24, marginBottom: 16, border: '1px solid #334155' }}>
                        <h3 style={{ margin: '0 0 20px', fontSize: 16 }}>Provider</h3>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 20 }}>
                            {PROVIDERS.map(p => {
                                const icons: any = { jira: '🔵 Jira', servicenow: '🟢 ServiceNow', zoho: '🟠 Zoho Desk', custom: '🛠 Custom' };
                                return (
                                    <button key={p} onClick={() => setConfig((c: any) => ({ ...c, provider: p }))}
                                        style={{
                                            padding: 14, borderRadius: 10, border: `2px solid ${config.provider === p ? '#7c3aed' : '#334155'}`,
                                            background: config.provider === p ? 'rgba(124,58,237,0.15)' : '#0f172a', color: config.provider === p ? '#a78bfa' : '#64748b', cursor: 'pointer', fontWeight: 700, fontSize: 14, textAlign: 'left'
                                        }}>
                                        {icons[p]}
                                    </button>
                                );
                            })}
                        </div>

                        {config.provider === 'jira' && (
                            <>
                                <Field label="Jira URL (e.g. https://yourorg.atlassian.net)">
                                    <Input value={config.jira_url || ''} onChange={v => setConfig((c: any) => ({ ...c, jira_url: v }))} placeholder="https://yourorg.atlassian.net" />
                                </Field>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                                    <Field label="Project Key"><Input value={config.jira_project_key || ''} onChange={v => setConfig((c: any) => ({ ...c, jira_project_key: v }))} placeholder="SEC" /></Field>
                                    <Field label="Issue Type"><Input value={config.jira_issue_type || ''} onChange={v => setConfig((c: any) => ({ ...c, jira_issue_type: v }))} placeholder="Bug" /></Field>
                                </div>
                                <Field label="Email (Jira account)"><Input value={config.jira_email || ''} onChange={v => setConfig((c: any) => ({ ...c, jira_email: v }))} placeholder="you@company.com" /></Field>
                                <Field label="API Token"><Input type="password" value={config.jira_api_token || ''} onChange={v => setConfig((c: any) => ({ ...c, jira_api_token: v }))} placeholder="••••••••••••••••" /></Field>
                            </>
                        )}

                        {config.provider === 'servicenow' && (
                            <>
                                <Field label="ServiceNow Instance (e.g. myorg)"><Input value={config.snow_instance || ''} onChange={v => setConfig((c: any) => ({ ...c, snow_instance: v }))} placeholder="myorg" /></Field>
                                <Field label="Username"><Input value={config.snow_username || ''} onChange={v => setConfig((c: any) => ({ ...c, snow_username: v }))} placeholder="admin" /></Field>
                                <Field label="Password"><Input type="password" value={config.snow_password || ''} onChange={v => setConfig((c: any) => ({ ...c, snow_password: v }))} placeholder="••••••••" /></Field>
                            </>
                        )}

                        {config.provider === 'zoho' && (
                            <>
                                <Field label="Zoho Org ID"><Input value={config.zoho_org_id || ''} onChange={v => setConfig((c: any) => ({ ...c, zoho_org_id: v }))} placeholder="0000000" /></Field>
                                <Field label="Zoho Department ID"><Input value={config.zoho_department_id || ''} onChange={v => setConfig((c: any) => ({ ...c, zoho_department_id: v }))} placeholder="000000000000000" /></Field>
                                <Field label="Auth Token (Zoho-oauthtoken)"><Input type="password" value={config.zoho_token || ''} onChange={v => setConfig((c: any) => ({ ...c, zoho_token: v }))} placeholder="1000.xxxx.yyyy" /></Field>
                            </>
                        )}

                        {config.provider === 'custom' && (
                            <>
                                <Field label="Webhook URL"><Input value={config.custom_webhook_url || ''} onChange={v => setConfig((c: any) => ({ ...c, custom_webhook_url: v }))} placeholder="https://api.yourservice.com/webhook" /></Field>
                                <Field label="Method">
                                    <select value={config.custom_webhook_method || 'POST'} onChange={e => setConfig((c: any) => ({ ...c, custom_webhook_method: e.target.value }))}
                                        style={{ width: '100%', padding: 10, background: '#0f172a', border: '1px solid #334155', borderRadius: 8, color: '#f1f5f9' }}>
                                        <option value="POST">POST</option>
                                        <option value="PUT">PUT</option>
                                    </select>
                                </Field>
                                <JsonField label="Headers (JSON)" value={config.custom_webhook_headers} onChange={v => setConfig((c: any) => ({ ...c, custom_webhook_headers: v }))} />
                                <JsonField label="Payload Template (JSON) — use {{field}} for substitution" value={config.custom_webhook_payload} onChange={v => setConfig((c: any) => ({ ...c, custom_webhook_payload: v }))} />
                            </>
                        )}
                    </div>

                    {/* Auto-create threshold */}
                    <div style={{ background: '#1e293b', borderRadius: 12, padding: 24, marginBottom: 16, border: '1px solid #334155' }}>
                        <h3 style={{ margin: '0 0 12px', fontSize: 16 }}>Auto-Create Threshold</h3>
                        <p style={{ color: '#64748b', fontSize: 13, margin: '0 0 16px' }}>Automatically create a ticket when an alert of these severities fires:</p>
                        <div style={{ display: 'flex', gap: 10 }}>
                            {SEVERITIES.map(sev => {
                                const colors: any = { critical: '#ef4444', high: '#f97316', medium: '#eab308', low: '#22c55e' };
                                const active = config.auto_create_severity?.includes(sev);
                                return (
                                    <button key={sev} onClick={() => toggleSeverity(sev)}
                                        style={{
                                            flex: 1, padding: '10px 8px', borderRadius: 8, border: `2px solid ${active ? colors[sev] : '#334155'}`,
                                            background: active ? colors[sev] + '22' : 'transparent', color: active ? colors[sev] : '#64748b', cursor: 'pointer', fontWeight: 700, textTransform: 'capitalize'
                                        }}>
                                        {sev}
                                    </button>
                                );
                            })}
                        </div>
                    </div>

                    {feedback && (
                        <div style={{ padding: 12, borderRadius: 8, marginBottom: 16, background: feedback.ok ? 'rgba(34,197,94,0.1)' : 'rgba(239,68,68,0.1)', border: `1px solid ${feedback.ok ? '#22c55e' : '#ef4444'}`, color: feedback.ok ? '#22c55e' : '#ef4444' }}>
                            {feedback.msg}
                        </div>
                    )}

                    <div style={{ display: 'flex', gap: 12 }}>
                        <button onClick={testConnection} disabled={testing}
                            style={{ flex: 1, padding: 12, background: '#1e293b', border: '1px solid #334155', borderRadius: 8, color: '#94a3b8', cursor: 'pointer', fontWeight: 600 }}>
                            {testing ? 'Testing Connection...' : '🔌 Test Connection'}
                        </button>
                        <button onClick={save} disabled={saving}
                            style={{ flex: 1, padding: 12, background: '#7c3aed', border: 'none', borderRadius: 8, color: 'white', cursor: 'pointer', fontWeight: 600 }}>
                            {saving ? 'Saving...' : '💾 Save Configuration'}
                        </button>
                    </div>
                </div>
            )}

            {tab === 'tickets' && (
                <div>
                    {tickets.length === 0 && <div style={{ color: '#64748b', textAlign: 'center', padding: 40 }}>No tickets created yet. Configure a provider and create your first ticket from an alert.</div>}
                    {tickets.map((t, i) => (
                        <div key={i} style={{ background: '#1e293b', borderRadius: 10, padding: 16, marginBottom: 10, border: '1px solid #334155', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <div>
                                <div style={{ fontWeight: 700, fontSize: 15 }}>{t.ticket_ref}</div>
                                <div style={{ color: '#64748b', fontSize: 12 }}>Alert: {t.alert_id} • {new Date(t.created_at).toLocaleString()}</div>
                            </div>
                            <a href={t.url} target="_blank" rel="noopener noreferrer"
                                style={{ color: '#7c3aed', fontSize: 13, textDecoration: 'none', padding: '6px 14px', border: '1px solid #7c3aed', borderRadius: 6 }}>
                                View in {t.provider ? (t.provider.charAt(0).toUpperCase() + t.provider.slice(1)) : 'Provider'} →
                            </a>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
