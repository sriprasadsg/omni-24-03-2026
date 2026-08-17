import{a as e,n as t,t as n}from"./jsx-runtime-B-hcVAMW.js";import{y as r}from"./apiService-BhsXSDm8.js";var i=e(t(),1),a=n(),o={1:`#6366f1`,2:`#ec4899`,3:`#f59e0b`,4:`#10b981`,5:`#3b82f6`,6:`#f97316`,7:`#ef4444`,8:`#8b5cf6`};function s({msg:e}){let t=e.role===`oracle`;return(0,a.jsxs)(`div`,{className:`cissp-bubble ${t?`oracle`:`user`}`,children:[t&&(0,a.jsxs)(`div`,{className:`bubble-header`,children:[(0,a.jsx)(`span`,{className:`oracle-badge`,children:`CISSP Oracle`}),e.domains?.map(e=>(0,a.jsxs)(`span`,{className:`domain-badge`,style:{background:o[e]+`22`,color:o[e],border:`1px solid ${o[e]}40`},children:[`D`,e]},e))]}),(0,a.jsx)(`div`,{className:`bubble-content`,style:{whiteSpace:`pre-wrap`},children:e.content}),t&&e.recommendations&&e.recommendations.length>0&&(0,a.jsxs)(`div`,{className:`recommendations`,children:[(0,a.jsx)(`div`,{className:`rec-title`,children:`Quick Actions:`}),e.recommendations.map((e,t)=>(0,a.jsxs)(`div`,{className:`rec-item`,children:[(0,a.jsx)(`span`,{className:`rec-bullet`,children:`→`}),` `,e]},t))]}),(0,a.jsx)(`div`,{className:`bubble-time`,children:new Date(e.timestamp).toLocaleTimeString()})]})}function c({domain:e,onClick:t}){return(0,a.jsxs)(`div`,{className:`cissp-domain-card`,onClick:t,style:{borderLeft:`4px solid ${e.color}`},children:[(0,a.jsxs)(`div`,{className:`domain-card-header`,children:[(0,a.jsx)(`span`,{className:`domain-code`,style:{color:e.color},children:e.code}),(0,a.jsx)(`span`,{className:`domain-weight`,children:e.weight})]}),(0,a.jsx)(`div`,{className:`domain-card-name`,children:e.name}),(0,a.jsxs)(`div`,{className:`domain-card-desc`,children:[e.description.substring(0,100),`...`]}),(0,a.jsx)(`div`,{className:`domain-concepts`,children:e.key_concepts.slice(0,3).map(e=>(0,a.jsx)(`span`,{className:`concept-pill`,children:e},e))})]})}function l(){let[e,t]=(0,i.useState)(`domains`),[n,o]=(0,i.useState)([]),[l,u]=(0,i.useState)(null),[d,f]=(0,i.useState)([{role:`oracle`,content:`Welcome to the CISSP Oracle.

I'm your AI security advisor trained across all 8 CISSP domains. Ask me anything about security architecture, risk management, identity & access, incident response, compliance controls, or any security finding you'd like classified and remediated.

Examples:
• "BitLocker is not enabled on some endpoints — what's the risk?"
• "Explain CISSP Domain 5 IAM controls"
• "What's the difference between vulnerability assessment and penetration testing?"
• "Our audit log retention is 30 days — is that sufficient for PCI DSS?"`,domains:[1,2,3,4,5,6,7,8],timestamp:new Date().toISOString()}]),[p,m]=(0,i.useState)(``),[h,g]=(0,i.useState)(!1),[_,v]=(0,i.useState)([]),[y,b]=(0,i.useState)(!1),[x,S]=(0,i.useState)(null),[C,w]=(0,i.useState)(0),T=(0,i.useRef)(null);(0,i.useEffect)(()=>{E(),D()},[]),(0,i.useEffect)(()=>{T.current?.scrollIntoView({behavior:`smooth`})},[d]),(0,i.useEffect)(()=>{if(!x||!y)return;let e=setInterval(async()=>{w(e=>e+1);try{let e=await r(`/api/cissp/oracle/assess/${x}`);e.ok&&(await e.json()).assessment?.status===`completed`&&(b(!1),S(null),D())}catch{}},4e3);return()=>clearInterval(e)},[x,y]);let E=async()=>{try{let e=await(await r(`/api/cissp/oracle/domains`)).json();o(e.domains||[])}catch(e){console.error(e)}},D=async()=>{try{let e=await(await r(`/api/cissp/oracle/assessments`)).json();v(e.assessments||[])}catch{}},O=async()=>{let e=p.trim();if(!e||h)return;m(``);let t={role:`user`,content:e,timestamp:new Date().toISOString()};f(e=>[...e,t]),g(!0);try{let t=await(await r(`/api/cissp/oracle/chat`,{method:`POST`,body:JSON.stringify({message:e})})).json(),n={role:`oracle`,content:t.response||`I could not generate a response at this time.`,domains:t.domain_classifications||[],recommendations:t.recommendations||[],timestamp:t.timestamp||new Date().toISOString()};f(e=>[...e,n])}catch{f(e=>[...e,{role:`oracle`,content:`Oracle is currently unavailable. Please check the backend connection.`,timestamp:new Date().toISOString()}])}finally{g(!1)}},k=async()=>{b(!0),w(0);try{let e=await(await r(`/api/cissp/oracle/assess`,{method:`POST`,body:JSON.stringify({})})).json();S(e.assessment_id)}catch{b(!1)}},A=e=>e===`Low`?`#10b981`:e===`Medium`?`#f59e0b`:e===`High`?`#f97316`:`#ef4444`;return(0,a.jsxs)(`div`,{className:`cissp-oracle-page`,children:[(0,a.jsxs)(`div`,{className:`cissp-header`,children:[(0,a.jsxs)(`div`,{className:`cissp-header-left`,children:[(0,a.jsx)(`div`,{className:`cissp-logo`,children:(0,a.jsxs)(`svg`,{width:`32`,height:`32`,viewBox:`0 0 32 32`,fill:`none`,children:[(0,a.jsx)(`rect`,{width:`32`,height:`32`,rx:`8`,fill:`#6366f1`}),(0,a.jsx)(`path`,{d:`M16 6L6 11V21L16 26L26 21V11L16 6Z`,stroke:`white`,strokeWidth:`2`,fill:`none`}),(0,a.jsx)(`circle`,{cx:`16`,cy:`16`,r:`4`,fill:`white`})]})}),(0,a.jsxs)(`div`,{children:[(0,a.jsx)(`h1`,{className:`cissp-title`,children:`CISSP Oracle`}),(0,a.jsx)(`p`,{className:`cissp-subtitle`,children:`AI Security Advisor · 8 Domains · (ISC)² Aligned`})]})]}),(0,a.jsx)(`div`,{className:`cissp-tabs`,children:[`domains`,`oracle`,`assess`].map(n=>(0,a.jsx)(`button`,{className:`cissp-tab ${e===n?`active`:``}`,onClick:()=>t(n),children:n===`domains`?`8 Domains`:n===`oracle`?`AI Advisor`:`Assessment`},n))})]}),e===`domains`&&(0,a.jsx)(`div`,{className:`cissp-content`,children:l?(0,a.jsxs)(`div`,{className:`domain-detail`,children:[(0,a.jsx)(`button`,{className:`back-btn`,onClick:()=>u(null),children:`← Back to Domains`}),(0,a.jsxs)(`div`,{className:`domain-detail-header`,style:{borderLeft:`6px solid ${l.color}`},children:[(0,a.jsx)(`div`,{className:`domain-detail-code`,style:{color:l.color},children:l.code}),(0,a.jsx)(`div`,{className:`domain-detail-name`,children:l.name}),(0,a.jsxs)(`div`,{className:`domain-detail-weight`,children:[`Exam Weight: `,l.weight]})]}),(0,a.jsx)(`p`,{className:`domain-detail-desc`,children:l.description}),(0,a.jsxs)(`div`,{className:`domain-detail-section`,children:[(0,a.jsx)(`h3`,{children:`Key Concepts`}),(0,a.jsx)(`div`,{className:`concept-grid`,children:l.key_concepts.map(e=>(0,a.jsx)(`div`,{className:`concept-card`,children:e},e))})]}),(0,a.jsxs)(`div`,{className:`domain-detail-section`,children:[(0,a.jsx)(`h3`,{children:`Agent Checks Mapped`}),(0,a.jsx)(`div`,{className:`checks-list`,children:l.agent_checks.map(e=>(0,a.jsxs)(`div`,{className:`check-item`,children:[(0,a.jsx)(`span`,{className:`check-dot`,style:{background:l.color}}),e]},e))})]}),(0,a.jsxs)(`button`,{className:`ask-oracle-btn`,style:{background:l.color},onClick:()=>{t(`oracle`),m(`Tell me about CISSP ${l.name} domain`)},children:[`Ask Oracle about `,l.name,` →`]})]}):(0,a.jsxs)(a.Fragment,{children:[(0,a.jsxs)(`div`,{className:`domains-intro`,children:[(0,a.jsx)(`h2`,{children:`CISSP 8 Domain Framework`}),(0,a.jsx)(`p`,{children:`The CISSP certification by (ISC)² covers 8 information security domains. Click a domain to explore concepts and see how the agent maps evidence to each.`})]}),(0,a.jsx)(`div`,{className:`domains-grid`,children:n.map(e=>(0,a.jsx)(c,{domain:e,onClick:()=>u(e)},e.id))})]})}),e===`oracle`&&(0,a.jsxs)(`div`,{className:`cissp-chat-container`,children:[(0,a.jsxs)(`div`,{className:`chat-messages`,children:[d.map((e,t)=>(0,a.jsx)(s,{msg:e},t)),h&&(0,a.jsxs)(`div`,{className:`cissp-bubble oracle`,children:[(0,a.jsx)(`div`,{className:`bubble-header`,children:(0,a.jsx)(`span`,{className:`oracle-badge`,children:`CISSP Oracle`})}),(0,a.jsxs)(`div`,{className:`typing-indicator`,children:[(0,a.jsx)(`span`,{}),(0,a.jsx)(`span`,{}),(0,a.jsx)(`span`,{})]})]}),(0,a.jsx)(`div`,{ref:T})]}),(0,a.jsxs)(`div`,{className:`chat-input-area`,children:[(0,a.jsx)(`div`,{className:`quick-questions`,children:[`Explain BitLocker risk`,`Password policy best practices`,`What is zero trust?`,`CISSP Domain 7 incident response`].map(e=>(0,a.jsx)(`button`,{className:`quick-q`,onClick:()=>{m(e)},children:e},e))}),(0,a.jsxs)(`div`,{className:`chat-input-row`,children:[(0,a.jsx)(`textarea`,{className:`chat-textarea`,value:p,onChange:e=>m(e.target.value),onKeyDown:e=>{e.key===`Enter`&&!e.shiftKey&&(e.preventDefault(),O())},placeholder:`Ask the CISSP Oracle anything about security...`,rows:2}),(0,a.jsx)(`button`,{className:`send-btn`,onClick:O,disabled:h||!p.trim(),children:h?`...`:`Send`})]})]})]}),e===`assess`&&(0,a.jsxs)(`div`,{className:`cissp-content`,children:[(0,a.jsxs)(`div`,{className:`assess-header`,children:[(0,a.jsxs)(`div`,{children:[(0,a.jsx)(`h2`,{children:`CISSP 8-Domain Assessment`}),(0,a.jsx)(`p`,{children:`Run a real security assessment against all 8 CISSP domains using system-level checks. Results include domain scores, risk levels, and prioritized findings.`})]}),(0,a.jsx)(`button`,{className:`run-assess-btn`,onClick:k,disabled:y,children:y?`Running... (${C*4}s)`:`Run Assessment`})]}),y&&(0,a.jsxs)(`div`,{className:`assess-running`,children:[(0,a.jsx)(`div`,{className:`assess-spinner`}),(0,a.jsxs)(`div`,{children:[(0,a.jsx)(`div`,{className:`assess-running-title`,children:`CISSP Assessment In Progress`}),(0,a.jsxs)(`div`,{className:`assess-running-sub`,children:[`Running `,C*4<8?`Domain 1-2`:C*4<20?`Domain 3-5`:`Domain 6-8`,` checks...`]})]})]}),_.length>0?(0,a.jsxs)(`div`,{className:`assessments-list`,children:[(0,a.jsx)(`h3`,{children:`Assessment Reports`}),_.map(e=>(0,a.jsxs)(`div`,{className:`assess-card ${e.status}`,children:[(0,a.jsxs)(`div`,{className:`assess-card-left`,children:[(0,a.jsx)(`div`,{className:`assess-hostname`,children:e.hostname}),(0,a.jsx)(`div`,{className:`assess-id`,children:e.id}),(0,a.jsx)(`div`,{className:`assess-date`,children:e.completedAt?new Date(e.completedAt).toLocaleString():`Running...`})]}),e.overall_score!==void 0&&(0,a.jsxs)(`div`,{className:`assess-score-section`,children:[(0,a.jsxs)(`div`,{className:`assess-donut`,style:{"--score":e.overall_score,"--color":A(e.overall_risk_level||``)},children:[(0,a.jsx)(`div`,{className:`assess-score-num`,children:e.overall_score}),(0,a.jsx)(`div`,{className:`assess-score-label`,children:`/100`})]}),(0,a.jsxs)(`div`,{className:`assess-risk`,style:{color:A(e.overall_risk_level||``)},children:[e.overall_risk_level,` Risk`]})]}),(0,a.jsx)(`div`,{className:`assess-status-badge ${e.status}`,children:e.status})]},e.id))]}):!y&&(0,a.jsxs)(`div`,{className:`no-assessments`,children:[(0,a.jsx)(`div`,{className:`no-assess-icon`,children:`🔍`}),(0,a.jsx)(`div`,{children:`No assessments yet. Click "Run Assessment" to generate your first CISSP report.`})]})]}),(0,a.jsx)(`style`,{children:`
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
      `})]})}export{l as default};