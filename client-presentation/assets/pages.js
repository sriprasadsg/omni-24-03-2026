/* ── Page content data ── each entry is one leaf: front = right page, back = left page */
const PAGES = [
  // 0 — Cover / Overview
  {
    front: `<div class="page-face cover-bg">
      <div class="shimmer-line"></div>
      <svg class="hex-grid" viewBox="0 0 140 120" fill="none">
        <polygon points="17,6 26,12 26,22 17,28 8,22 8,12" stroke="#00e5ff" stroke-width="1" fill="none" opacity="0.6"/>
        <polygon points="51,6 60,12 60,22 51,28 42,22 42,12" stroke="#00e5ff" stroke-width="1" fill="none" opacity="0.6"/>
        <polygon points="85,6 94,12 94,22 85,28 76,22 76,12" stroke="#00e5ff" stroke-width="1" fill="none" opacity="0.6"/>
        <polygon points="119,6 128,12 128,22 119,28 110,22 110,12" stroke="#00e5ff" stroke-width="1" fill="none" opacity="0.6"/>
        <polygon points="34,25 43,31 43,41 34,47 25,41 25,31" stroke="#00e5ff" stroke-width="1" fill="none" opacity="0.6"/>
        <polygon points="68,25 77,31 77,41 68,47 59,41 59,31" stroke="#00e5ff" stroke-width="1" fill="none" opacity="0.6"/>
        <polygon points="102,25 111,31 111,41 102,47 93,41 93,31" stroke="#00e5ff" stroke-width="1" fill="none" opacity="0.6"/>
        <polygon points="17,44 26,50 26,60 17,66 8,60 8,50" stroke="#00e5ff" stroke-width="1" fill="none" opacity="0.6"/>
        <polygon points="51,44 60,50 60,60 51,66 42,60 42,50" stroke="#00e5ff" stroke-width="1" fill="none" opacity="0.6"/>
        <polygon points="85,44 94,50 94,60 85,66 76,60 76,50" stroke="#00e5ff" stroke-width="1" fill="none" opacity="0.6"/>
        <polygon points="119,44 128,50 128,60 119,66 110,60 110,50" stroke="#00e5ff" stroke-width="1" fill="none" opacity="0.6"/>
        <polygon points="34,63 43,69 43,79 34,85 25,79 25,69" stroke="#00e5ff" stroke-width="1" fill="none" opacity="0.6"/>
      </svg>
      <div style="position:relative;z-index:1;display:flex;flex-direction:column;gap:14px;height:100%">
        <div class="cover-logo">&#x1F6E1;</div>
        <div class="cover-badge">Live Platform &#8212; All Systems Go</div>
        <h1 class="hero" style="font-size:18px;line-height:1.25;color:#fff">Enterprise<br><span style="color:var(--cyan)">Omni-Agent</span><br>AI Platform</h1>
        <div class="divider"></div>
        <p class="small" style="color:var(--muted);line-height:1.6">Next-generation autonomous security platform combining AI-powered agents, real-time threat intelligence, and unified SOC operations into a single enterprise fabric.</p>
        <div class="stats-row" style="margin-top:auto">
          <div class="stat-box"><div class="num">125</div><div class="lbl">API<br>Endpoints</div></div>
          <div class="stat-box"><div class="num">17+</div><div class="lbl">Feature<br>Modules</div></div>
          <div class="stat-box"><div class="num">100%</div><div class="lbl">Test<br>Pass Rate</div></div>
        </div>
      </div>
      <div class="open-hint">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
        click to open
      </div>
    </div>`,
    back: `<div class="page-face">
      <p class="page-title">Platform Overview</p>
      <h2 class="section" style="font-size:12px">What is Omni-Agent?</h2>
      <p class="body">A fully integrated, AI-native cybersecurity operating system that deploys autonomous agents across your entire infrastructure &#8212; collecting telemetry, hunting threats, remediating vulnerabilities, and orchestrating response without human intervention.</p>
      <div class="divider"></div>
      <div class="list-items">
        <div class="list-item"><div class="dot"></div><div class="text"><strong>Autonomous Agent Fleet</strong> &#8212; Self-healing, self-updating agents on every endpoint</div></div>
        <div class="list-item"><div class="dot" style="background:var(--green)"></div><div class="text"><strong>Unified SOC</strong> &#8212; EDR, SIEM, UEBA, SOAR in one pane of glass</div></div>
        <div class="list-item"><div class="dot" style="background:#a78bfa"></div><div class="text"><strong>AI Governance</strong> &#8212; Monitor, audit, and control every AI model in your org</div></div>
        <div class="list-item"><div class="dot" style="background:var(--orange)"></div><div class="text"><strong>Zero Trust + PAM</strong> &#8212; Device trust scores, privileged access vaulting</div></div>
        <div class="list-item"><div class="dot" style="background:var(--red)"></div><div class="text"><strong>Multi-Cloud CSPM</strong> &#8212; AWS, Azure, GCP posture management at scale</div></div>
      </div>
      <div style="margin-top:auto"><div class="tags">
        <span class="tag cyan">FastAPI</span><span class="tag cyan">React</span>
        <span class="tag green">MongoDB</span><span class="tag purple">Socket.IO</span>
        <span class="tag orange">Python 3.11+</span>
      </div></div>
      <p class="page-number left">2</p>
    </div>`
  },

  // 1 — Agent Fleet / Capabilities
  {
    front: `<div class="page-face">
      <p class="page-title">Agent Fleet</p>
      <h2 class="section">Autonomous Agent Management</h2>
      <p class="body" style="margin-bottom:6px">Deploy, manage, and orchestrate thousands of autonomous agents. Each agent reports telemetry, executes playbooks, and participates in swarm coordination.</p>
      <div class="feat-grid">
        <div class="feat-card"><span class="icon">&#x1F916;</span><div class="label">Agent Registry</div><div class="desc">Full fleet inventory with health, capabilities, last-seen</div></div>
        <div class="feat-card"><span class="icon">&#x1F578;</span><div class="label">Swarm Mode</div><div class="desc">Peer-to-peer coordination for distributed response</div></div>
        <div class="feat-card"><span class="icon">&#x1F9E0;</span><div class="label">Agentic Decisions</div><div class="desc">AI-driven autonomous decisions with approval workflows</div></div>
        <div class="feat-card"><span class="icon">&#x26A1;</span><div class="label">Remote Control</div><div class="desc">Real-time shell, file browser, process manager</div></div>
        <div class="feat-card"><span class="icon">&#x1F3AF;</span><div class="label">Goal System</div><div class="desc">Persistent goal manager drives security objectives</div></div>
        <div class="feat-card"><span class="icon">&#x1F4E1;</span><div class="label">Network Topology</div><div class="desc">Live map of agent positions and utilization</div></div>
      </div>
      <p class="page-number right">3</p>
    </div>`,
    back: `<div class="page-face">
      <p class="page-title">Agent Capabilities</p>
      <h2 class="section">19 Built-in Capability Modules</h2>
      <div class="progress-row">
        <div class="progress-item"><div class="progress-label"><span>FIM &#8212; File Integrity Monitor</span><span style="color:var(--green)">98%</span></div><div class="progress-bar"><div class="progress-fill" style="width:98%"></div></div></div>
        <div class="progress-item"><div class="progress-label"><span>EDR Real-time Telemetry</span><span style="color:var(--green)">96%</span></div><div class="progress-bar"><div class="progress-fill" style="width:96%"></div></div></div>
        <div class="progress-item"><div class="progress-label"><span>Network Discovery &amp; Scanning</span><span style="color:var(--green)">95%</span></div><div class="progress-bar"><div class="progress-fill" style="width:95%"></div></div></div>
        <div class="progress-item"><div class="progress-label"><span>UEBA &amp; Behavioral Analytics</span><span style="color:var(--green)">93%</span></div><div class="progress-bar"><div class="progress-fill" style="width:93%"></div></div></div>
        <div class="progress-item"><div class="progress-label"><span>Vulnerability Scanner</span><span style="color:var(--green)">97%</span></div><div class="progress-bar"><div class="progress-fill" style="width:97%"></div></div></div>
        <div class="progress-item"><div class="progress-label"><span>Runtime Security (eBPF)</span><span style="color:var(--green)">91%</span></div><div class="progress-bar"><div class="progress-fill" style="width:91%"></div></div></div>
        <div class="progress-item"><div class="progress-label"><span>YARA Threat Hunting</span><span style="color:var(--green)">90%</span></div><div class="progress-bar"><div class="progress-fill" style="width:90%"></div></div></div>
        <div class="progress-item"><div class="progress-label"><span>Compliance Checks (CIS/NIST)</span><span style="color:var(--green)">94%</span></div><div class="progress-bar"><div class="progress-fill" style="width:94%"></div></div></div>
        <div class="progress-item"><div class="progress-label"><span>Log Shipper &amp; SIEM Feed</span><span style="color:var(--green)">96%</span></div><div class="progress-bar"><div class="progress-fill" style="width:96%"></div></div></div>
        <div class="progress-item"><div class="progress-label"><span>Software Management / Patching</span><span style="color:var(--green)">92%</span></div><div class="progress-bar"><div class="progress-fill" style="width:92%"></div></div></div>
      </div>
      <p class="page-number left">4</p>
    </div>`
  },

  // 2 — Security Operations / Threat Intel
  {
    front: `<div class="page-face">
      <p class="page-title">Security Operations</p>
      <h2 class="section">EDR &middot; UEBA &middot; SIEM</h2>
      <div class="list-items" style="gap:7px">
        <div class="list-item" style="border-color:var(--red)"><div class="dot" style="background:var(--red)"></div><div class="text"><strong style="color:var(--red)">EDR</strong> &#8212; Real-time endpoint detection with IOC feeds, behavioral alerts, and automated quarantine with per-agent drill-down.</div></div>
        <div class="list-item" style="border-color:var(--orange)"><div class="dot" style="background:var(--orange)"></div><div class="text"><strong style="color:var(--orange)">UEBA</strong> &#8212; ML-driven anomaly detection, risk scoring, insider threat detection, and Shadow AI event tracking.</div></div>
        <div class="list-item" style="border-color:#a78bfa"><div class="dot" style="background:#a78bfa"></div><div class="text"><strong style="color:#a78bfa">SIEM</strong> &#8212; Centralized log aggregation, rule-based detection, event correlation. Syslog UDP on port 5140.</div></div>
      </div>
      <div class="divider" style="margin-top:6px"></div>
      <div class="stats-row">
        <div class="stat-box" style="border-color:rgba(255,76,106,0.3)"><div class="num" style="color:var(--red)">&#8734;</div><div class="lbl">IOC<br>Entries</div></div>
        <div class="stat-box" style="border-color:rgba(255,140,0,0.3)"><div class="num" style="color:var(--orange)">ML</div><div class="lbl">Anomaly<br>Engine</div></div>
        <div class="stat-box" style="border-color:rgba(124,58,237,0.3)"><div class="num" style="color:#a78bfa">RT</div><div class="lbl">Real-time<br>Stream</div></div>
      </div>
      <p class="page-number right">5</p>
    </div>`,
    back: `<div class="page-face">
      <p class="page-title">Threat Intelligence</p>
      <h2 class="section">Threat Intel &middot; Correlation &middot; XDR</h2>
      <p class="body" style="margin-bottom:6px">Multi-source threat intelligence feeds enrich every alert. The correlation engine links events across EDR, SIEM, and network layers with MITRE ATT&amp;CK mapping.</p>
      <div class="feat-grid">
        <div class="feat-card"><span class="icon">&#x1F310;</span><div class="label">Threat Feeds</div><div class="desc">Live IOC ingestion from multiple intel sources</div></div>
        <div class="feat-card"><span class="icon">&#x1F517;</span><div class="label">Correlation Engine</div><div class="desc">Pattern-based cross-source event correlation</div></div>
        <div class="feat-card"><span class="icon">&#x1F5FA;</span><div class="label">Attack Paths</div><div class="desc">Visual kill-chain reconstruction</div></div>
        <div class="feat-card"><span class="icon">&#x1F3AF;</span><div class="label">XDR Hunts</div><div class="desc">Automated YARA + behavioural threat hunting</div></div>
      </div>
      <div class="tags" style="margin-top:6px">
        <span class="tag red">MITRE ATT&amp;CK</span><span class="tag orange">Kill Chain</span>
        <span class="tag cyan">STIX/TAXII</span><span class="tag purple">YARA</span>
      </div>
      <p class="page-number left">6</p>
    </div>`
  },

  // 3 — Compliance / Privacy
  {
    front: `<div class="page-face">
      <p class="page-title">Compliance &amp; Privacy</p>
      <h2 class="section">Compliance Automation</h2>
      <p class="body" style="margin-bottom:6px">Continuous compliance posture monitoring. Automated evidence collection, control testing, and audit-ready report generation.</p>
      <div class="feat-grid">
        <div class="feat-card"><span class="icon">&#x2705;</span><div class="label">Compliance Overview</div><div class="desc">Live posture score per framework with gap analysis</div></div>
        <div class="feat-card"><span class="icon">&#x1F4CB;</span><div class="label">Evidence Collection</div><div class="desc">Automated artifact capture linked to controls</div></div>
        <div class="feat-card"><span class="icon">&#x1F4D1;</span><div class="label">Audit Reports</div><div class="desc">One-click compliance reports for auditors</div></div>
        <div class="feat-card"><span class="icon">&#x2699;</span><div class="label">Automation Rules</div><div class="desc">Policy-as-code for continuous enforcement</div></div>
      </div>
      <div class="tags" style="margin-top:6px">
        <span class="tag green">SOC 2</span><span class="tag cyan">ISO 27001</span>
        <span class="tag purple">HIPAA</span><span class="tag orange">PCI-DSS</span>
        <span class="tag cyan">NIST CSF</span><span class="tag green">CIS</span>
      </div>
      <p class="page-number right">7</p>
    </div>`,
    back: `<div class="page-face">
      <p class="page-title">Privacy &amp; Data Protection</p>
      <h2 class="section">GDPR &middot; CCPA &middot; Privacy Management</h2>
      <div class="list-items">
        <div class="list-item" style="border-color:var(--green)"><div class="dot" style="background:var(--green)"></div><div class="text"><strong>Privacy Dashboard</strong> &#8212; Unified view of data subject rights and consent states</div></div>
        <div class="list-item" style="border-color:var(--green)"><div class="dot" style="background:var(--green)"></div><div class="text"><strong>DSR Management</strong> &#8212; Automated Data Subject Request fulfillment with deadline tracking</div></div>
        <div class="list-item" style="border-color:var(--green)"><div class="dot" style="background:var(--green)"></div><div class="text"><strong>Breach Notifications</strong> &#8212; 72-hour GDPR breach notification workflow with regulator templates</div></div>
        <div class="list-item" style="border-color:var(--green)"><div class="dot" style="background:var(--green)"></div><div class="text"><strong>ROPA</strong> &#8212; Record of Processing Activities with data flow mapping</div></div>
        <div class="list-item" style="border-color:var(--green)"><div class="dot" style="background:var(--green)"></div><div class="text"><strong>BAA Agreements</strong> &#8212; Business Associate Agreements for HIPAA covered entities</div></div>
      </div>
      <p class="page-number left">8</p>
    </div>`
  },

  // 4 — DevSecOps / Cloud
  {
    front: `<div class="page-face">
      <p class="page-title">DevSecOps</p>
      <h2 class="section">Shift-Left Security Pipeline</h2>
      <p class="body" style="margin-bottom:5px">Embed security at every stage of the software delivery lifecycle &#8212; from IDE commit to production container.</p>
      <div class="feat-grid" style="gap:5px">
        <div class="feat-card"><span class="icon">&#x1F50D;</span><div class="label">SAST</div><div class="desc">Static analysis across all repos</div></div>
        <div class="feat-card"><span class="icon">&#x1F4E6;</span><div class="label">SCA / SBOM</div><div class="desc">Bill of Materials with CVE linkage</div></div>
        <div class="feat-card"><span class="icon">&#x26D3;</span><div class="label">Supply Chain</div><div class="desc">Dependency integrity verification</div></div>
        <div class="feat-card"><span class="icon">&#x1F433;</span><div class="label">Container Scan</div><div class="desc">Image scanning and runtime security</div></div>
        <div class="feat-card"><span class="icon">&#x1F3D7;</span><div class="label">IaC Security</div><div class="desc">Terraform/Helm/K8s violations</div></div>
        <div class="feat-card"><span class="icon">&#x1F50C;</span><div class="label">API Security</div><div class="desc">Inventory, fuzzing, schema drift</div></div>
      </div>
      <p class="page-number right">9</p>
    </div>`,
    back: `<div class="page-face">
      <p class="page-title">Cloud Security</p>
      <h2 class="section">Multi-Cloud CSPM</h2>
      <p class="body" style="margin-bottom:6px">Connect AWS, Azure, and GCP for real-time posture management, asset discovery, misconfiguration detection, and automated remediation.</p>
      <div class="list-items">
        <div class="list-item"><div class="dot"></div><div class="text"><strong>Cloud Integrations</strong> &#8212; OAuth-based account linking with permission boundary scanning</div></div>
        <div class="list-item"><div class="dot"></div><div class="text"><strong>Asset Discovery</strong> &#8212; Auto-discovered cloud resources catalogued with risk scores</div></div>
        <div class="list-item"><div class="dot"></div><div class="text"><strong>Remediation Engine</strong> &#8212; One-click and automated misconfiguration fixes via API</div></div>
        <div class="list-item"><div class="dot"></div><div class="text"><strong>Cost Optimization</strong> &#8212; FinOps view with over-provisioned resource identification</div></div>
      </div>
      <div class="tags" style="margin-top:6px">
        <span class="tag orange">AWS</span><span class="tag cyan">Azure</span>
        <span class="tag green">GCP</span><span class="tag purple">Kubernetes</span>
      </div>
      <p class="page-number left">10</p>
    </div>`
  },

  // 5 — AI Governance / Zero Trust
  {
    front: `<div class="page-face">
      <p class="page-title">AI Governance</p>
      <h2 class="section">AI Model Security &amp; Oversight</h2>
      <p class="body" style="margin-bottom:6px">The first platform to govern not just infrastructure but every AI system inside it. Monitor, audit, and enforce policies on all LLMs and ML models.</p>
      <div class="feat-grid">
        <div class="feat-card"><span class="icon">&#x1F9E9;</span><div class="label">AI Systems Registry</div><div class="desc">Inventory of AI models with risk classification</div></div>
        <div class="feat-card"><span class="icon">&#x1F4DC;</span><div class="label">Governance Policies</div><div class="desc">Acceptable-use policies at the LLM proxy layer</div></div>
        <div class="feat-card"><span class="icon">&#x1F575;</span><div class="label">Shadow AI Detection</div><div class="desc">UEBA-powered discovery of unauthorised AI usage</div></div>
        <div class="feat-card"><span class="icon">&#x1F510;</span><div class="label">LLM Proxy Audit</div><div class="desc">Full audit log of every prompt and completion</div></div>
      </div>
      <div class="divider" style="margin-top:6px"></div>
      <div class="tags">
        <span class="tag purple">Claude API</span><span class="tag cyan">OpenAI</span>
        <span class="tag green">Ollama</span><span class="tag orange">Azure OpenAI</span>
        <span class="tag red">Prompt Guard</span>
      </div>
      <p class="page-number right">11</p>
    </div>`,
    back: `<div class="page-face">
      <p class="page-title">Zero Trust &amp; PAM</p>
      <h2 class="section">Zero Trust + PAM Vault</h2>
      <div class="list-items">
        <div class="list-item" style="border-color:#a78bfa"><div class="dot" style="background:#a78bfa"></div><div class="text"><strong>Device Trust Scores</strong> &#8212; Continuous posture assessment drives conditional access</div></div>
        <div class="list-item" style="border-color:#a78bfa"><div class="dot" style="background:#a78bfa"></div><div class="text"><strong>Session Risk Scoring</strong> &#8212; Real-time session risk with step-up authentication</div></div>
        <div class="list-item" style="border-color:#a78bfa"><div class="dot" style="background:#a78bfa"></div><div class="text"><strong>PAM Accounts</strong> &#8212; Privileged vault with check-in/check-out, JIT access</div></div>
        <div class="list-item" style="border-color:#a78bfa"><div class="dot" style="background:#a78bfa"></div><div class="text"><strong>Session Recording</strong> &#8212; Full audit trail with keystroke logging</div></div>
        <div class="list-item" style="border-color:#a78bfa"><div class="dot" style="background:#a78bfa"></div><div class="text"><strong>Secrets Vault</strong> &#8212; Encrypted credential store with rotation policies</div></div>
      </div>
      <p class="page-number left">12</p>
    </div>`
  },

  // 6 — Playbooks / Analytics
  {
    front: `<div class="page-face">
      <p class="page-title">Response &amp; Playbooks</p>
      <h2 class="section">SOAR &middot; Playbooks &middot; Auto-Response</h2>
      <p class="body" style="margin-bottom:6px">Close the loop from detection to remediation in seconds with AI-authored playbooks and SOAR orchestration across 200+ integrations.</p>
      <div class="feat-grid">
        <div class="feat-card"><span class="icon">&#x1F4D6;</span><div class="label">Playbook Library</div><div class="desc">Version-controlled with drag-and-drop builder</div></div>
        <div class="feat-card"><span class="icon">&#x1F680;</span><div class="label">SOAR Engine</div><div class="desc">Execution runs with full audit trail</div></div>
        <div class="feat-card"><span class="icon">&#x1F512;</span><div class="label">Quarantine</div><div class="desc">One-click network isolation and account lock</div></div>
        <div class="feat-card"><span class="icon">&#x1F91D;</span><div class="label">Response Policies</div><div class="desc">Automated rules triggered by alert severity</div></div>
      </div>
      <div class="divider" style="margin-top:5px"></div>
      <p class="small">Time-to-contain: <strong style="color:var(--green)">47 sec avg</strong> &nbsp;&middot;&nbsp; Daily runs: <strong style="color:var(--cyan)">1,200+</strong></p>
      <p class="page-number right">13</p>
    </div>`,
    back: `<div class="page-face">
      <p class="page-title">Analytics &amp; FinOps</p>
      <h2 class="section">AIOps &middot; DORA &middot; Observability</h2>
      <div class="feat-grid" style="gap:5px">
        <div class="feat-card"><span class="icon">&#x1F4C8;</span><div class="label">AIOps Capacity</div><div class="desc">ML capacity predictions for resource planning</div></div>
        <div class="feat-card"><span class="icon">&#x1F3AF;</span><div class="label">DORA Metrics</div><div class="desc">Deployment frequency, MTTR, change failure</div></div>
        <div class="feat-card"><span class="icon">&#x1F52D;</span><div class="label">APM &amp; Tracing</div><div class="desc">Service maps and distributed traces</div></div>
        <div class="feat-card"><span class="icon">&#x1F331;</span><div class="label">Sustainability</div><div class="desc">Carbon footprint and energy optimization</div></div>
        <div class="feat-card"><span class="icon">&#x1F300;</span><div class="label">Chaos Engineering</div><div class="desc">Controlled chaos with blast radius analysis</div></div>
        <div class="feat-card"><span class="icon">&#x1F916;</span><div class="label">AutoML</div><div class="desc">Automated ML study management</div></div>
      </div>
      <p class="page-number left">14</p>
    </div>`
  },

  // 7 — Architecture / Deployment
  {
    front: `<div class="page-face">
      <p class="page-title">Architecture</p>
      <h2 class="section">Platform Architecture</h2>
      <div style="display:flex;flex-direction:column;gap:6px;flex:1">
        <div class="arch-layer"><div class="layer-title">&#9650; Presentation Layer</div><div class="layer-items"><span class="tag cyan">React 18</span><span class="tag cyan">TypeScript</span><span class="tag cyan">Vite</span><span class="tag purple">Socket.IO</span></div></div>
        <div class="arch-layer" style="border-color:rgba(0,255,136,0.2)"><div class="layer-title" style="color:var(--green)">&#9650; API Gateway</div><div class="layer-items"><span class="tag green">FastAPI 0.115+</span><span class="tag green">Uvicorn ASGI</span><span class="tag green">JWT Auth</span></div></div>
        <div class="arch-layer" style="border-color:rgba(124,58,237,0.2)"><div class="layer-title" style="color:#a78bfa">&#9650; Service Layer (60+ modules)</div><div class="layer-items"><span class="tag purple">RBAC Service</span><span class="tag purple">AI Service</span><span class="tag purple">SOAR Engine</span></div></div>
        <div class="arch-layer" style="border-color:rgba(255,140,0,0.2)"><div class="layer-title" style="color:var(--orange)">&#9650; Agent Layer</div><div class="layer-items"><span class="tag orange">Python Agents</span><span class="tag orange">Swarm Coordinator</span><span class="tag orange">LLM Engine</span></div></div>
        <div class="arch-layer" style="border-color:rgba(255,76,106,0.2)"><div class="layer-title" style="color:var(--red)">&#9650; Data Layer</div><div class="layer-items"><span class="tag red">MongoDB (Motor async)</span><span class="tag red">Multi-Tenant Isolation</span></div></div>
      </div>
      <p class="page-number right">15</p>
    </div>`,
    back: `<div class="page-face">
      <p class="page-title">Deployment</p>
      <h2 class="section">One-Command Ubuntu Deployment</h2>
      <div class="list-items" style="gap:6px">
        <div class="list-item" style="border-color:var(--orange)"><div class="dot" style="background:var(--orange)"></div><div class="text" style="font-family:monospace;font-size:9px;color:#ffd700">sudo ./run-on-ubuntu.sh</div></div>
        <div class="list-item"><div class="dot"></div><div class="text">Full backend, frontend, agent setup on fresh Ubuntu 22.04+</div></div>
        <div class="list-item"><div class="dot"></div><div class="text">MongoDB, Python 3.11 venv, Node 20 npm build</div></div>
        <div class="list-item"><div class="dot"></div><div class="text">Admin seeding, XDR playbook seeding, .env auto-generation</div></div>
        <div class="list-item"><div class="dot"></div><div class="text">Systemd service units for all components with auto-restart</div></div>
        <div class="list-item"><div class="dot"></div><div class="text">UFW rules: 5000 (API), 3000 (UI), 5140/UDP (Syslog)</div></div>
        <div class="list-item"><div class="dot"></div><div class="text" style="font-size:8px;font-family:monospace;color:var(--cyan)">sudo ./install-agent-linux.sh --backend-url URL --as-service</div></div>
      </div>
      <div class="divider" style="margin-top:6px"></div>
      <p class="small" style="text-align:center">Ubuntu 22.04 LTS &nbsp;&middot;&nbsp; Python 3.11+ &nbsp;&middot;&nbsp; Node 20+</p>
      <p class="page-number left">16</p>
    </div>`
  },

  // 8 — Reports / Back Cover
  {
    front: `<div class="page-face">
      <p class="page-title">Reports &amp; Admin</p>
      <h2 class="section">Executive Reporting Suite</h2>
      <p class="body" style="margin-bottom:6px">Comprehensive reporting across all security domains &#8212; automated scheduled delivery in PDF, XLSX, or HTML formats.</p>
      <div class="feat-grid" style="gap:5px">
        <div class="feat-card"><span class="icon">&#x1F4CA;</span><div class="label">Executive Summary</div><div class="desc">Board-level posture with trend analysis</div></div>
        <div class="feat-card"><span class="icon">&#x1F41B;</span><div class="label">Vuln Exposure</div><div class="desc">CVSS-ranked report with remediation SLAs</div></div>
        <div class="feat-card"><span class="icon">&#x1F4C5;</span><div class="label">Scheduled Reports</div><div class="desc">Cron-based delivery to custom recipients</div></div>
        <div class="feat-card"><span class="icon">&#x1F504;</span><div class="label">Change Management</div><div class="desc">Infrastructure change audit and approvals</div></div>
      </div>
      <div class="divider" style="margin-top:6px"></div>
      <div class="stats-row">
        <div class="stat-box"><div class="num" style="font-size:14px">RBAC</div><div class="lbl">Role-Based<br>Access Control</div></div>
        <div class="stat-box"><div class="num" style="font-size:14px">SSO</div><div class="lbl">SAML/OIDC<br>Single Sign-On</div></div>
        <div class="stat-box"><div class="num" style="font-size:14px">MT</div><div class="lbl">Multi-Tenant<br>Architecture</div></div>
      </div>
      <p class="page-number right">17</p>
    </div>`,
    back: `<div class="page-face cover-bg">
      <div class="shimmer-line"></div>
      <div style="position:relative;z-index:1;display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;gap:16px;text-align:center">
        <div class="cover-logo" style="width:52px;height:52px;font-size:26px">&#x1F6E1;</div>
        <div>
          <h1 class="hero" style="font-size:15px;color:#fff">Enterprise Omni-Agent<br><span style="color:var(--cyan)">AI Platform</span></h1>
          <p class="small" style="margin-top:5px;color:var(--muted)">by Exafluence Inc.</p>
        </div>
        <div class="divider" style="width:100px"></div>
        <div style="display:flex;flex-direction:column;gap:5px;align-items:center">
          <div class="cover-badge" style="font-size:8px">125/125 endpoints &middot; 100% pass rate</div>
          <div class="cover-badge" style="background:rgba(0,255,136,0.08);border-color:rgba(0,255,136,0.25);color:var(--green)">Edition 2030 &middot; Production Ready</div>
        </div>
        <div class="tags" style="justify-content:center;margin-top:3px">
          <span class="tag cyan">Security</span><span class="tag green">AI-Native</span>
          <span class="tag purple">Autonomous</span><span class="tag orange">Enterprise</span>
        </div>
        <p class="small" style="margin-top:auto;color:var(--muted);font-size:8px">sriprasadsg@gmail.com &nbsp;&middot;&nbsp; Exafluence Inc.</p>
      </div>
    </div>`
  },
];
