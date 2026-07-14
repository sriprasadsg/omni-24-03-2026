import React, { useState, useRef, useEffect } from 'react';

const API = '/api/security-copilot';

type CopilotTab = 'chat' | 'kql' | 'incident' | 'threat';

interface Message { role: 'user' | 'assistant'; content: string; }

export default function SecurityCopilotDashboard() {
  const [tab, setTab] = useState<CopilotTab>('chat');

  // Chat
  const [messages, setMessages] = useState<Message[]>([
    { role: 'assistant', content: 'Hello! I\'m your AI Security Copilot. Ask me about threats, incidents, or generate KQL queries. How can I help?' }
  ]);
  const [chatInput, setChatInput] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // KQL Generator
  const [kqlPrompt, setKqlPrompt] = useState('');
  const [kqlResult, setKqlResult] = useState('');
  const [kqlLoading, setKqlLoading] = useState(false);
  const [kqlCopied, setKqlCopied] = useState(false);

  // Incident Analyzer
  const [incidentId, setIncidentId] = useState('');
  const [incidentAnalysis, setIncidentAnalysis] = useState<any>(null);
  const [incidentLoading, setIncidentLoading] = useState(false);

  // Threat Analyzer
  const [iocInput, setIocInput] = useState('');
  const [threatAnalysis, setThreatAnalysis] = useState<any>(null);
  const [threatLoading, setThreatLoading] = useState(false);

  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  const authHeader = () => ({ Authorization: `Bearer ${localStorage.getItem('token')}`, 'Content-Type': 'application/json' });

  const sendChat = async () => {
    if (!chatInput.trim() || chatLoading) return;
    const userMsg: Message = { role: 'user', content: chatInput };
    setMessages(prev => [...prev, userMsg]);
    setChatInput('');
    setChatLoading(true);
    try {
      const r = await fetch(`${API}/chat`, { method: 'POST', headers: authHeader(), body: JSON.stringify({ message: chatInput }) });
      const data = await r.json();
      setMessages(prev => [...prev, { role: 'assistant', content: data.response || data.message || 'I\'m analyzing your request...' }]);
    } catch {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Unable to connect to AI service. Please check your LLM configuration.' }]);
    }
    setChatLoading(false);
  };

  const generateKql = async () => {
    if (!kqlPrompt.trim()) return;
    setKqlLoading(true);
    try {
      const r = await fetch(`${API}/generate-kql`, { method: 'POST', headers: authHeader(), body: JSON.stringify({ prompt: kqlPrompt }) });
      const data = await r.json();
      setKqlResult(data.kql || data.query || '// No query generated');
    } catch { setKqlResult('// Error generating query'); }
    setKqlLoading(false);
  };

  const analyzeIncident = async () => {
    if (!incidentId.trim()) return;
    setIncidentLoading(true);
    try {
      const r = await fetch(`${API}/summarize-incident`, { method: 'POST', headers: authHeader(), body: JSON.stringify({ incident_id: incidentId }) });
      setIncidentAnalysis(await r.json());
    } catch { setIncidentAnalysis({ error: 'Failed to analyze incident' }); }
    setIncidentLoading(false);
  };

  const analyzeThreat = async () => {
    if (!iocInput.trim()) return;
    setThreatLoading(true);
    try {
      const r = await fetch(`${API}/analyze-threat`, { method: 'POST', headers: authHeader(), body: JSON.stringify({ indicator: iocInput }) });
      setThreatAnalysis(await r.json());
    } catch { setThreatAnalysis({ error: 'Failed to analyze threat' }); }
    setThreatLoading(false);
  };

  const TABS: { id: CopilotTab; label: string }[] = [
    { id: 'chat', label: 'Chat' },
    { id: 'kql', label: 'KQL Generator' },
    { id: 'incident', label: 'Incident Analyzer' },
    { id: 'threat', label: 'Threat Analyzer' },
  ];

  return (
    <div className="p-6 space-y-6 h-full flex flex-col">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-white font-bold text-lg">AI</div>
        <div>
          <h2 className="text-2xl font-bold text-white">Security Copilot</h2>
          <p className="text-sm text-slate-400">AI-powered SOC assistant</p>
        </div>
      </div>

      <div className="flex rounded-lg overflow-hidden border border-slate-700 w-fit">
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-sm font-medium transition-colors ${tab === t.id ? 'bg-blue-600 text-white' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'}`}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'chat' && (
        <div className="flex flex-col flex-1 min-h-0 bg-slate-800/50 rounded-xl border border-slate-700">
          <div className="flex-1 overflow-y-auto p-4 space-y-4 min-h-[300px] max-h-[400px]">
            {messages.map((m, i) => (
              <div key={i} className={`flex gap-3 ${m.role === 'user' ? 'flex-row-reverse' : ''}`}>
                <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 ${m.role === 'assistant' ? 'bg-blue-600 text-white' : 'bg-slate-600 text-white'}`}>
                  {m.role === 'assistant' ? 'AI' : 'U'}
                </div>
                <div className={`max-w-[80%] px-4 py-2 rounded-xl text-sm ${m.role === 'assistant' ? 'bg-slate-700 text-slate-200' : 'bg-blue-600 text-white'}`}>
                  {m.content}
                </div>
              </div>
            ))}
            {chatLoading && <div className="flex gap-3"><div className="w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center text-xs font-bold text-white">AI</div><div className="bg-slate-700 text-slate-400 px-4 py-2 rounded-xl text-sm animate-pulse">Thinking...</div></div>}
            <div ref={messagesEndRef} />
          </div>
          <div className="border-t border-slate-700 p-3 flex gap-2">
            <input value={chatInput} onChange={e => setChatInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && sendChat()}
              placeholder="Ask about threats, incidents, or request KQL queries..."
              className="flex-1 bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
            <button onClick={sendChat} disabled={chatLoading || !chatInput.trim()}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors">Send</button>
          </div>
        </div>
      )}

      {tab === 'kql' && (
        <div className="space-y-4">
          <div className="bg-slate-800 border border-slate-700 rounded-xl p-4 space-y-3">
            <label className="text-sm font-medium text-slate-300">Describe what you want to detect in plain English</label>
            <textarea value={kqlPrompt} onChange={e => setKqlPrompt(e.target.value)} rows={3}
              placeholder="e.g. Show me all failed logins from non-corporate IPs in the last 24 hours"
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500 resize-none" />
            <button onClick={generateKql} disabled={kqlLoading || !kqlPrompt.trim()}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors">
              {kqlLoading ? 'Generating...' : 'Generate KQL'}
            </button>
          </div>
          {kqlResult && (
            <div className="bg-slate-900 border border-slate-700 rounded-xl p-4 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-slate-300">Generated Query</span>
                <button onClick={() => { navigator.clipboard.writeText(kqlResult); setKqlCopied(true); setTimeout(() => setKqlCopied(false), 2000); }}
                  className="text-xs text-blue-400 hover:text-blue-300">{kqlCopied ? 'Copied!' : 'Copy'}</button>
              </div>
              <pre className="text-sm text-emerald-400 font-mono overflow-x-auto whitespace-pre-wrap">{kqlResult}</pre>
            </div>
          )}
        </div>
      )}

      {tab === 'incident' && (
        <div className="space-y-4">
          <div className="bg-slate-800 border border-slate-700 rounded-xl p-4 space-y-3">
            <label className="text-sm font-medium text-slate-300">Incident ID</label>
            <div className="flex gap-2">
              <input value={incidentId} onChange={e => setIncidentId(e.target.value)}
                placeholder="Enter incident ID..."
                className="flex-1 bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
              <button onClick={analyzeIncident} disabled={incidentLoading || !incidentId.trim()}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors">
                {incidentLoading ? 'Analyzing...' : 'Analyze'}
              </button>
            </div>
          </div>
          {incidentAnalysis && (
            <div className="bg-slate-800 border border-slate-700 rounded-xl p-4 space-y-3">
              {incidentAnalysis.error
                ? <p className="text-red-400 text-sm">{incidentAnalysis.error}</p>
                : (
                  <>
                    {incidentAnalysis.summary && <div><div className="text-xs text-slate-400 mb-1">Summary</div><p className="text-sm text-slate-200">{incidentAnalysis.summary}</p></div>}
                    {incidentAnalysis.recommended_actions?.length > 0 && (
                      <div><div className="text-xs text-slate-400 mb-1">Recommended Actions</div>
                        <ul className="space-y-1">{incidentAnalysis.recommended_actions.map((a: string, i: number) => <li key={i} className="text-sm text-slate-300 flex gap-2"><span className="text-blue-400">•</span>{a}</li>)}</ul>
                      </div>
                    )}
                    {incidentAnalysis.mitre_techniques?.length > 0 && (
                      <div><div className="text-xs text-slate-400 mb-1">MITRE Techniques</div>
                        <div className="flex flex-wrap gap-2">{incidentAnalysis.mitre_techniques.map((t: string) => <span key={t} className="text-xs bg-orange-500/20 text-orange-400 border border-orange-500/30 px-2 py-0.5 rounded">{t}</span>)}</div>
                      </div>
                    )}
                  </>
                )}
            </div>
          )}
        </div>
      )}

      {tab === 'threat' && (
        <div className="space-y-4">
          <div className="bg-slate-800 border border-slate-700 rounded-xl p-4 space-y-3">
            <label className="text-sm font-medium text-slate-300">IOC (IP, domain, hash, URL)</label>
            <div className="flex gap-2">
              <input value={iocInput} onChange={e => setIocInput(e.target.value)}
                placeholder="e.g. 192.168.1.1, malware.exe sha256, evil.com"
                className="flex-1 bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
              <button onClick={analyzeThreat} disabled={threatLoading || !iocInput.trim()}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors">
                {threatLoading ? 'Analyzing...' : 'Analyze'}
              </button>
            </div>
          </div>
          {threatAnalysis && (
            <div className="bg-slate-800 border border-slate-700 rounded-xl p-4 space-y-3">
              {threatAnalysis.error
                ? <p className="text-red-400 text-sm">{threatAnalysis.error}</p>
                : (
                  <>
                    {threatAnalysis.verdict && (
                      <div className="flex items-center gap-3">
                        <span className="text-sm font-medium text-slate-300">Verdict:</span>
                        <span className={`text-sm font-bold ${threatAnalysis.verdict === 'Malicious' ? 'text-red-400' : threatAnalysis.verdict === 'Suspicious' ? 'text-yellow-400' : 'text-emerald-400'}`}>{threatAnalysis.verdict}</span>
                      </div>
                    )}
                    {threatAnalysis.summary && <p className="text-sm text-slate-200">{threatAnalysis.summary}</p>}
                    {threatAnalysis.sources && <div className="text-xs text-slate-400">Sources: {threatAnalysis.sources}</div>}
                  </>
                )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
