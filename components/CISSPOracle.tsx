import React, { useState, useEffect, useRef } from 'react';

const API = 'http://localhost:5000';

// CISSP Domain colors matching backend
const DOMAIN_COLORS: Record<number, string> = {
    1: '#6366f1', 2: '#ec4899', 3: '#f59e0b', 4: '#10b981',
    5: '#3b82f6', 6: '#f97316', 7: '#ef4444', 8: '#8b5cf6',
};

interface Domain {
    id: number;
    code: string;
    name: string;
    weight: string;
    description: string;
    key_concepts: string[];
    agent_checks: string[];
    color: string;
}

interface ChatMessage {
    role: 'user' | 'oracle';
    content: string;
    domains?: number[];
    recommendations?: string[];
    timestamp: string;
}

interface Assessment {
    id: string;
    hostname: string;
    status: string;
    overall_score?: number;
    overall_risk_level?: string;
    completedAt?: string;
}

// ── Chat bubble component ─────────────────────────────────────────────────────
function ChatBubble({ msg }: { msg: ChatMessage }) {
    const isOracle = msg.role === 'oracle';
    return (
        <div className={`cissp-bubble ${isOracle ? 'oracle' : 'user'}`}>
            {isOracle && (
                <div className="bubble-header">
                    <span className="oracle-badge">CISSP Oracle</span>
                    {msg.domains?.map(d => (
                        <span key={d} className="domain-badge" style={{ background: DOMAIN_COLORS[d] + '22', color: DOMAIN_COLORS[d], border: `1px solid ${DOMAIN_COLORS[d]}40` }}>
                            D{d}
                        </span>
                    ))}
                </div>
            )}
            <div className="bubble-content" style={{ whiteSpace: 'pre-wrap' }}>{msg.content}</div>
            {isOracle && msg.recommendations && msg.recommendations.length > 0 && (
                <div className="recommendations">
                    <div className="rec-title">Quick Actions:</div>
                    {msg.recommendations.map((r, i) => (
                        <div key={i} className="rec-item">
                            <span className="rec-bullet">→</span> {r}
                        </div>
                    ))}
                </div>
            )}
            <div className="bubble-time">{new Date(msg.timestamp).toLocaleTimeString()}</div>
        </div>
    );
}

// ── Domain card ───────────────────────────────────────────────────────────────
function DomainCard({ domain, onClick }: { domain: Domain; onClick: () => void }) {
    return (
        <div className="cissp-domain-card" onClick={onClick} style={{ borderLeft: `4px solid ${domain.color}` }}>
            <div className="domain-card-header">
                <span className="domain-code" style={{ color: domain.color }}>{domain.code}</span>
                <span className="domain-weight">{domain.weight}</span>
            </div>
            <div className="domain-card-name">{domain.name}</div>
            <div className="domain-card-desc">{domain.description.substring(0, 100)}...</div>
            <div className="domain-concepts">
                {domain.key_concepts.slice(0, 3).map(c => (
                    <span key={c} className="concept-pill">{c}</span>
                ))}
            </div>
        </div>
    );
}

// ── Main Component ─────────────────────────────────────────────────────────────
export default function CISSPOracle() {
    const [tab, setTab] = useState<'domains' | 'oracle' | 'assess'>('domains');
    const [domains, setDomains] = useState<Domain[]>([]);
    const [selectedDomain, setSelectedDomain] = useState<Domain | null>(null);
    const [chatMessages, setChatMessages] = useState<ChatMessage[]>([
        {
            role: 'oracle',
            content: "Welcome to the CISSP Oracle.\n\nI'm your AI security advisor trained across all 8 CISSP domains. Ask me anything about security architecture, risk management, identity & access, incident response, compliance controls, or any security finding you'd like classified and remediated.\n\nExamples:\n• \"BitLocker is not enabled on some endpoints — what's the risk?\"\n• \"Explain CISSP Domain 5 IAM controls\"\n• \"What's the difference between vulnerability assessment and penetration testing?\"\n• \"Our audit log retention is 30 days — is that sufficient for PCI DSS?\"",
            domains: [1, 2, 3, 4, 5, 6, 7, 8],
            timestamp: new Date().toISOString(),
        }
    ]);
    const [inputValue, setInputValue] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [assessments, setAssessments] = useState<Assessment[]>([]);
    const [assessRunning, setAssessRunning] = useState(false);
    const [currentAssessId, setCurrentAssessId] = useState<string | null>(null);
    const [pollCount, setPollCount] = useState(0);
    const messagesEndRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        fetchDomains();
        fetchAssessments();
    }, []);

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [chatMessages]);

    // Poll for assessment result
    useEffect(() => {
        if (!currentAssessId || !assessRunning) return;
        const timer = setInterval(async () => {
            setPollCount(p => p + 1);
            try {
                const r = await fetch(`${API}/api/cissp/oracle/assess/${currentAssessId}`);
                if (r.ok) {
                    const data = await r.json();
                    if (data.assessment?.status === 'completed') {
                        setAssessRunning(false);
                        setCurrentAssessId(null);
                        fetchAssessments();
                    }
                }
            } catch (e) { }
        }, 4000);
        return () => clearInterval(timer);
    }, [currentAssessId, assessRunning]);

    const fetchDomains = async () => {
        try {
            const r = await fetch(`${API}/api/cissp/oracle/domains`);
            const data = await r.json();
            setDomains(data.domains || []);
        } catch (e) { console.error(e); }
    };

    const fetchAssessments = async () => {
        try {
            const r = await fetch(`${API}/api/cissp/oracle/assessments`);
            const data = await r.json();
            setAssessments(data.assessments || []);
        } catch (e) { }
    };

    const sendMessage = async () => {
        const msg = inputValue.trim();
        if (!msg || isLoading) return;
        setInputValue('');

        const userMsg: ChatMessage = { role: 'user', content: msg, timestamp: new Date().toISOString() };
        setChatMessages(prev => [...prev, userMsg]);
        setIsLoading(true);

        try {
            const r = await fetch(`${API}/api/cissp/oracle/chat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: msg }),
            });
            const data = await r.json();
            const oracleMsg: ChatMessage = {
                role: 'oracle',
                content: data.response || 'I could not generate a response at this time.',
                domains: data.domain_classifications || [],
                recommendations: data.recommendations || [],
                timestamp: data.timestamp || new Date().toISOString(),
            };
            setChatMessages(prev => [...prev, oracleMsg]);
        } catch (e) {
            setChatMessages(prev => [...prev, {
                role: 'oracle',
                content: 'Oracle is currently unavailable. Please check the backend connection.',
                timestamp: new Date().toISOString(),
            }]);
        } finally {
            setIsLoading(false);
        }
    };

    const triggerAssessment = async () => {
        setAssessRunning(true);
        setPollCount(0);
        try {
            const r = await fetch(`${API}/api/cissp/oracle/assess`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({}),
            });
            const data = await r.json();
            setCurrentAssessId(data.assessment_id);
        } catch (e) {
            setAssessRunning(false);
        }
    };

    const riskColor = (level: string) => {
        if (level === 'Low') return '#10b981';
        if (level === 'Medium') return '#f59e0b';
        if (level === 'High') return '#f97316';
        return '#ef4444';
    };

    return (
        <div className="cissp-oracle-page">
            {/* Header */}
            <div className="cissp-header">
                <div className="cissp-header-left">
                    <div className="cissp-logo">
                        <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
                            <rect width="32" height="32" rx="8" fill="#6366f1" />
                            <path d="M16 6L6 11V21L16 26L26 21V11L16 6Z" stroke="white" strokeWidth="2" fill="none" />
                            <circle cx="16" cy="16" r="4" fill="white" />
                        </svg>
                    </div>
                    <div>
                        <h1 className="cissp-title">CISSP Oracle</h1>
                        <p className="cissp-subtitle">AI Security Advisor · 8 Domains · (ISC)² Aligned</p>
                    </div>
                </div>
                <div className="cissp-tabs">
                    {(['domains', 'oracle', 'assess'] as const).map(t => (
                        <button key={t} className={`cissp-tab ${tab === t ? 'active' : ''}`} onClick={() => setTab(t)}>
                            {t === 'domains' ? '8 Domains' : t === 'oracle' ? 'AI Advisor' : 'Assessment'}
                        </button>
                    ))}
                </div>
            </div>

            {/* ── DOMAINS TAB ─────────────────────────────────────────────────────── */}
            {tab === 'domains' && (
                <div className="cissp-content">
                    {selectedDomain ? (
                        <div className="domain-detail">
                            <button className="back-btn" onClick={() => setSelectedDomain(null)}>← Back to Domains</button>
                            <div className="domain-detail-header" style={{ borderLeft: `6px solid ${selectedDomain.color}` }}>
                                <div className="domain-detail-code" style={{ color: selectedDomain.color }}>{selectedDomain.code}</div>
                                <div className="domain-detail-name">{selectedDomain.name}</div>
                                <div className="domain-detail-weight">Exam Weight: {selectedDomain.weight}</div>
                            </div>
                            <p className="domain-detail-desc">{selectedDomain.description}</p>
                            <div className="domain-detail-section">
                                <h3>Key Concepts</h3>
                                <div className="concept-grid">
                                    {selectedDomain.key_concepts.map(c => (
                                        <div key={c} className="concept-card">{c}</div>
                                    ))}
                                </div>
                            </div>
                            <div className="domain-detail-section">
                                <h3>Agent Checks Mapped</h3>
                                <div className="checks-list">
                                    {selectedDomain.agent_checks.map(c => (
                                        <div key={c} className="check-item">
                                            <span className="check-dot" style={{ background: selectedDomain.color }}></span>{c}
                                        </div>
                                    ))}
                                </div>
                            </div>
                            <button className="ask-oracle-btn" style={{ background: selectedDomain.color }}
                                onClick={() => { setTab('oracle'); setInputValue(`Tell me about CISSP ${selectedDomain.name} domain`); }}>
                                Ask Oracle about {selectedDomain.name} →
                            </button>
                        </div>
                    ) : (
                        <>
                            <div className="domains-intro">
                                <h2>CISSP 8 Domain Framework</h2>
                                <p>The CISSP certification by (ISC)² covers 8 information security domains. Click a domain to explore concepts and see how the agent maps evidence to each.</p>
                            </div>
                            <div className="domains-grid">
                                {domains.map(d => <DomainCard key={d.id} domain={d} onClick={() => setSelectedDomain(d)} />)}
                            </div>
                        </>
                    )}
                </div>
            )}

            {/* ── ORACLE CHAT TAB ──────────────────────────────────────────────────── */}
            {tab === 'oracle' && (
                <div className="cissp-chat-container">
                    <div className="chat-messages">
                        {chatMessages.map((m, i) => <ChatBubble key={i} msg={m} />)}
                        {isLoading && (
                            <div className="cissp-bubble oracle">
                                <div className="bubble-header"><span className="oracle-badge">CISSP Oracle</span></div>
                                <div className="typing-indicator"><span /><span /><span /></div>
                            </div>
                        )}
                        <div ref={messagesEndRef} />
                    </div>
                    <div className="chat-input-area">
                        <div className="quick-questions">
                            {['Explain BitLocker risk', 'Password policy best practices', 'What is zero trust?', 'CISSP Domain 7 incident response'].map(q => (
                                <button key={q} className="quick-q" onClick={() => { setInputValue(q); }}>
                                    {q}
                                </button>
                            ))}
                        </div>
                        <div className="chat-input-row">
                            <textarea
                                className="chat-textarea"
                                value={inputValue}
                                onChange={e => setInputValue(e.target.value)}
                                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); } }}
                                placeholder="Ask the CISSP Oracle anything about security..."
                                rows={2}
                            />
                            <button className="send-btn" onClick={sendMessage} disabled={isLoading || !inputValue.trim()}>
                                {isLoading ? '...' : 'Send'}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* ── ASSESSMENT TAB ───────────────────────────────────────────────────── */}
            {tab === 'assess' && (
                <div className="cissp-content">
                    <div className="assess-header">
                        <div>
                            <h2>CISSP 8-Domain Assessment</h2>
                            <p>Run a real security assessment against all 8 CISSP domains using system-level checks. Results include domain scores, risk levels, and prioritized findings.</p>
                        </div>
                        <button className="run-assess-btn" onClick={triggerAssessment} disabled={assessRunning}>
                            {assessRunning ? `Running... (${pollCount * 4}s)` : 'Run Assessment'}
                        </button>
                    </div>
                    {assessRunning && (
                        <div className="assess-running">
                            <div className="assess-spinner" />
                            <div>
                                <div className="assess-running-title">CISSP Assessment In Progress</div>
                                <div className="assess-running-sub">Running {pollCount * 4 < 8 ? 'Domain 1-2' : pollCount * 4 < 20 ? 'Domain 3-5' : 'Domain 6-8'} checks...</div>
                            </div>
                        </div>
                    )}
                    {assessments.length > 0 ? (
                        <div className="assessments-list">
                            <h3>Assessment Reports</h3>
                            {assessments.map(a => (
                                <div key={a.id} className={`assess-card ${a.status}`}>
                                    <div className="assess-card-left">
                                        <div className="assess-hostname">{a.hostname}</div>
                                        <div className="assess-id">{a.id}</div>
                                        <div className="assess-date">{a.completedAt ? new Date(a.completedAt).toLocaleString() : 'Running...'}</div>
                                    </div>
                                    {a.overall_score !== undefined && (
                                        <div className="assess-score-section">
                                            <div className="assess-donut" style={{ '--score': a.overall_score, '--color': riskColor(a.overall_risk_level || '') } as React.CSSProperties}>
                                                <div className="assess-score-num">{a.overall_score}</div>
                                                <div className="assess-score-label">/100</div>
                                            </div>
                                            <div className="assess-risk" style={{ color: riskColor(a.overall_risk_level || '') }}>
                                                {a.overall_risk_level} Risk
                                            </div>
                                        </div>
                                    )}
                                    <div className={`assess-status-badge ${a.status}`}>{a.status}</div>
                                </div>
                            ))}
                        </div>
                    ) : (
                        !assessRunning && (
                            <div className="no-assessments">
                                <div className="no-assess-icon">🔍</div>
                                <div>No assessments yet. Click "Run Assessment" to generate your first CISSP report.</div>
                            </div>
                        )
                    )}
                </div>
            )}

            <style>{`
        .cissp-oracle-page { display:flex; flex-direction:column; height:100vh; background:#0f1117; color:#e2e8f0; font-family:'Inter',sans-serif; }
        .cissp-header { display:flex; align-items:center; justify-content:space-between; padding:16px 24px; background:#161b27; border-bottom:1px solid #2d3748; flex-shrink:0; }
        .cissp-header-left { display:flex; align-items:center; gap:12px; }
        .cissp-title { font-size:20px; font-weight:700; color:#f8fafc; margin:0; }
        .cissp-subtitle { font-size:12px; color:#64748b; margin:0; }
        .cissp-tabs { display:flex; gap:4px; background:#0f1117; border-radius:8px; padding:4px; }
        .cissp-tab { padding:8px 16px; border:none; border-radius:6px; background:transparent; color:#64748b; cursor:pointer; font-size:13px; font-weight:500; transition:all 0.15s; }
        .cissp-tab.active { background:#6366f1; color:white; }
        .cissp-tab:hover:not(.active) { background:#1e293b; color:#e2e8f0; }
        .cissp-content { flex:1; overflow-y:auto; padding:24px; }
        .domains-intro { margin-bottom:24px; }
        .domains-intro h2 { font-size:22px; font-weight:700; color:#f8fafc; margin:0 0 8px; }
        .domains-intro p { color:#94a3b8; margin:0; }
        .domains-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(280px,1fr)); gap:16px; }
        .cissp-domain-card { background:#1e293b; border-radius:12px; padding:20px; cursor:pointer; transition:all 0.2s; }
        .cissp-domain-card:hover { background:#263347; transform:translateY(-2px); }
        .domain-card-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; }
        .domain-code { font-size:13px; font-weight:700; }
        .domain-weight { font-size:11px; color:#64748b; background:#0f1117; padding:2px 8px; border-radius:4px; }
        .domain-card-name { font-size:15px; font-weight:600; color:#f8fafc; margin-bottom:8px; }
        .domain-card-desc { font-size:12px; color:#94a3b8; margin-bottom:12px; line-height:1.5; }
        .domain-concepts { display:flex; flex-wrap:wrap; gap:4px; }
        .concept-pill { font-size:11px; background:#0f1117; color:#94a3b8; padding:2px 8px; border-radius:4px; }
        .domain-detail { max-width:700px; }
        .back-btn { background:none; border:1px solid #334155; color:#94a3b8; padding:8px 16px; border-radius:6px; cursor:pointer; margin-bottom:20px; font-size:13px; }
        .back-btn:hover { border-color:#6366f1; color:#6366f1; }
        .domain-detail-header { background:#1e293b; border-radius:12px; padding:20px; margin-bottom:20px; }
        .domain-detail-code { font-size:13px; font-weight:700; margin-bottom:4px; }
        .domain-detail-name { font-size:24px; font-weight:700; color:#f8fafc; margin-bottom:8px; }
        .domain-detail-weight { font-size:13px; color:#64748b; }
        .domain-detail-desc { color:#94a3b8; line-height:1.7; margin-bottom:24px; }
        .domain-detail-section { margin-bottom:24px; }
        .domain-detail-section h3 { font-size:14px; font-weight:600; color:#94a3b8; text-transform:uppercase; letter-spacing:0.05em; margin-bottom:12px; }
        .concept-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(160px,1fr)); gap:8px; }
        .concept-card { background:#1e293b; border-radius:8px; padding:10px 14px; font-size:13px; color:#e2e8f0; }
        .checks-list { display:flex; flex-direction:column; gap:6px; }
        .check-item { display:flex; align-items:center; gap:8px; font-size:13px; color:#94a3b8; }
        .check-dot { width:6px; height:6px; border-radius:50%; flex-shrink:0; }
        .ask-oracle-btn { margin-top:8px; padding:12px 24px; border:none; border-radius:8px; color:white; font-weight:600; cursor:pointer; font-size:14px; }
        /* Chat */
        .cissp-chat-container { display:flex; flex-direction:column; flex:1; min-height:0; }
        .chat-messages { flex:1; overflow-y:auto; padding:20px 24px; display:flex; flex-direction:column; gap:16px; }
        .cissp-bubble { max-width:80%; border-radius:12px; padding:14px 16px; }
        .cissp-bubble.oracle { background:#1e293b; border:1px solid #2d3748; align-self:flex-start; }
        .cissp-bubble.user { background:#6366f1; align-self:flex-end; margin-left:auto; }
        .bubble-header { display:flex; align-items:center; gap:6px; margin-bottom:8px; }
        .oracle-badge { font-size:11px; font-weight:600; color:#6366f1; background:#6366f122; padding:2px 8px; border-radius:4px; border:1px solid #6366f140; }
        .domain-badge { font-size:10px; font-weight:600; padding:2px 6px; border-radius:4px; }
        .bubble-content { font-size:14px; line-height:1.7; color:#e2e8f0; }
        .cissp-bubble.user .bubble-content { color:white; }
        .recommendations { margin-top:12px; border-top:1px solid #2d3748; padding-top:10px; }
        .rec-title { font-size:11px; font-weight:600; color:#64748b; text-transform:uppercase; margin-bottom:6px; }
        .rec-item { font-size:12px; color:#94a3b8; margin-bottom:4px; }
        .rec-bullet { color:#6366f1; font-weight:700; margin-right:4px; }
        .bubble-time { font-size:10px; color:#475569; margin-top:8px; }
        .typing-indicator { display:flex; gap:4px; align-items:center; height:20px; }
        .typing-indicator span { width:8px; height:8px; background:#6366f1; border-radius:50%; animation:bounce 1s infinite; }
        .typing-indicator span:nth-child(2) { animation-delay:0.2s; }
        .typing-indicator span:nth-child(3) { animation-delay:0.4s; }
        @keyframes bounce { 0%,80%,100%{transform:scale(0.8);opacity:0.5} 40%{transform:scale(1.2);opacity:1} }
        .chat-input-area { background:#161b27; border-top:1px solid #2d3748; padding:12px 24px; flex-shrink:0; }
        .quick-questions { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:10px; }
        .quick-q { background:#1e293b; border:1px solid #334155; color:#94a3b8; padding:6px 12px; border-radius:6px; font-size:12px; cursor:pointer; white-space:nowrap; transition:all 0.15s; }
        .quick-q:hover { border-color:#6366f1; color:#6366f1; }
        .chat-input-row { display:flex; gap:8px; align-items:flex-end; }
        .chat-textarea { flex:1; background:#1e293b; border:1px solid #334155; color:#e2e8f0; border-radius:8px; padding:10px 14px; font-size:14px; resize:none; outline:none; font-family:inherit; line-height:1.5; }
        .chat-textarea:focus { border-color:#6366f1; }
        .send-btn { background:#6366f1; color:white; border:none; border-radius:8px; padding:10px 20px; font-size:14px; font-weight:600; cursor:pointer; white-space:nowrap; }
        .send-btn:disabled { opacity:0.4; cursor:not-allowed; }
        /* Assessment */
        .assess-header { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:24px; }
        .assess-header h2 { font-size:22px; font-weight:700; color:#f8fafc; margin:0 0 8px; }
        .assess-header p { color:#94a3b8; max-width:600px; margin:0; }
        .run-assess-btn { background:#6366f1; color:white; border:none; border-radius:8px; padding:12px 24px; font-size:14px; font-weight:600; cursor:pointer; white-space:nowrap; flex-shrink:0; }
        .run-assess-btn:disabled { opacity:0.6; cursor:not-allowed; }
        .assess-running { display:flex; align-items:center; gap:16px; background:#1e293b; border:1px solid #334155; border-radius:12px; padding:20px; margin-bottom:24px; }
        .assess-spinner { width:36px; height:36px; border:3px solid #334155; border-top-color:#6366f1; border-radius:50%; animation:spin 0.8s linear infinite; flex-shrink:0; }
        @keyframes spin { to{transform:rotate(360deg)} }
        .assess-running-title { font-weight:600; color:#f8fafc; margin-bottom:4px; }
        .assess-running-sub { font-size:13px; color:#64748b; }
        .assessments-list h3 { font-size:16px; font-weight:600; color:#f8fafc; margin-bottom:16px; }
        .assess-card { display:flex; align-items:center; justify-content:space-between; background:#1e293b; border-radius:12px; padding:20px; margin-bottom:12px; border:1px solid #2d3748; }
        .assess-hostname { font-size:15px; font-weight:600; color:#f8fafc; margin-bottom:4px; }
        .assess-id { font-size:11px; color:#475569; font-family:monospace; margin-bottom:4px; }
        .assess-date { font-size:12px; color:#64748b; }
        .assess-score-section { display:flex; flex-direction:column; align-items:center; gap:4px; }
        .assess-donut { position:relative; width:64px; height:64px; border-radius:50%;
          background: conic-gradient(var(--color, #6366f1) calc(var(--score, 0) * 3.6deg), #1e293b 0deg);
          display:flex; flex-direction:column; align-items:center; justify-content:center; }
        .assess-donut::before { content:''; position:absolute; inset:8px; background:#1e293b; border-radius:50%; }
        .assess-score-num { font-size:16px; font-weight:700; color:#f8fafc; position:relative; z-index:1; line-height:1.1; }
        .assess-score-label { font-size:9px; color:#64748b; position:relative; z-index:1; }
        .assess-risk { font-size:12px; font-weight:600; }
        .assess-status-badge { font-size:12px; font-weight:600; padding:4px 12px; border-radius:20px; }
        .assess-status-badge.completed { background:#10b98122; color:#10b981; }
        .assess-status-badge.running { background:#6366f122; color:#6366f1; }
        .no-assessments { text-align:center; padding:60px 20px; color:#475569; }
        .no-assess-icon { font-size:48px; margin-bottom:16px; }
      `}</style>
        </div>
    );
}
