
// This file is the single source of truth for the in-memory database.
import {
    User, Role, Tenant, Metric, Alert, ComplianceFramework, AiSystem, Asset, Patch, SecurityCase, Playbook, SecurityEvent, CloudAccount, CSPMFinding, Notification, AuditLog, Integration, AlertRule, Agent, DatabaseSettings, LlmSettings, DataSource, Sbom, SoftwareComponent, AgentUpgradeJob, PatchDeploymentJob, LogEntry, UebaFinding, ModelExperiment, RegisteredModel, AutomationPolicy, SastFinding, CodeRepository, ApiDocEndpoint, IncidentImpactGraph, BusinessKpi, SensitiveDataFinding, AttackPath, ServiceTemplate, ProvisionedService, DoraMetrics, ChaosExperiment, ProactiveInsight, Trace, ServiceMap, TraceSpan,
    VulnerabilityScanJob,
    NetworkDevice, AgentHealth, ThreatIntelResult, AssetCompliance
} from './types';
import { ALL_PERMISSIONS } from './constants';

const generateMetricData = (base: number, variance: number, points: number = 30) => {
    let data = [];
    for (let i = 0; i < points; i++) {
        data.push({
            time: `${i}m ago`,
            value: Math.round(Math.min(100, Math.max(0, base + (Math.random() - 0.5) * variance))),
        });
    }
    return data;
};

export const USERS_DATA: User[] = [
    { id: 'user-super-admin', tenantId: 'platform-admin', tenantName: 'Platform', name: 'Super Admin', email: 'super@omni.ai', password: 'password123', role: 'Super Admin', avatar: 'https://i.pravatar.cc/150?u=super-admin', status: 'Active' },
    { id: 'user-acme-admin', tenantId: 'tenant-acme-corp', tenantName: 'Acme Corp', name: 'Alice Admin', email: 'alice@acme.com', password: 'password123', role: 'Tenant Admin', avatar: 'https://i.pravatar.cc/150?u=alice-admin', status: 'Active' },
    { id: 'user-acme-secops', tenantId: 'tenant-acme-corp', tenantName: 'Acme Corp', name: 'Bob Security', email: 'bob@acme.com', password: 'password123', role: 'SecOps Analyst', avatar: 'https://i.pravatar.cc/150?u=bob-secops', status: 'Active' },
    { id: 'user-acme-devops', tenantId: 'tenant-acme-corp', tenantName: 'Acme Corp', name: 'Charlie DevOps', email: 'charlie@acme.com', password: 'password123', role: 'DevOps Engineer', avatar: 'https://i.pravatar.cc/150?u=charlie-devops', status: 'Disabled' },
    { id: 'user-initech-admin', tenantId: 'tenant-initech', tenantName: 'Initech', name: 'Eve Engineer', email: 'eve@initech.com', password: 'password123', role: 'Tenant Admin', avatar: 'https://i.pravatar.cc/150?u=eve-engineer', status: 'Active' },
    { id: 'user-sriprasad-admin', tenantId: 'tenant-sriprasad', tenantName: 'Sri Prasad Corp', name: 'Sri Prasad', email: 'sri@omni.ai', password: 'password123', role: 'Tenant Admin', avatar: 'https://i.pravatar.cc/150?u=sri', status: 'Active' },
    { id: 'user-sriprasad-admin', tenantId: 'tenant-sriprasad', tenantName: 'Sri Prasad Corp', name: 'Sri Prasad', email: 'sri@omni.ai', password: 'password123', role: 'Tenant Admin', avatar: 'https://i.pravatar.cc/150?u=sri', status: 'Active' },
];

export const ROLES_DATA: Role[] = [
    { id: 'role-super-admin', name: 'Super Admin', description: 'Has all permissions across all tenants.', permissions: ALL_PERMISSIONS, isEditable: false, tenantId: 'platform' },
    { id: 'role-tenant-admin', name: 'Tenant Admin', description: 'Full access within their own tenant.', permissions: ALL_PERMISSIONS.filter(p => p !== 'manage:tenants'), isEditable: false, tenantId: 'standard' },
    { id: 'role-secops', name: 'SecOps Analyst', description: 'Manages security events, cases, and compliance.', permissions: ['view:dashboard', 'view:security', 'manage:security_cases', 'investigate:security', 'view:compliance', 'view:assets', 'view:agents', 'view:agent_logs', 'view:cloud_security', 'view:reporting'], isEditable: true, tenantId: 'standard' },
    { id: 'role-devops', name: 'DevOps Engineer', description: 'Manages agents, assets, and patching.', permissions: ['view:dashboard', 'view:agents', 'remediate:agents', 'view:assets', 'view:patching', 'manage:patches', 'view:agent_logs'], isEditable: true, tenantId: 'standard' },
    { id: 'role-readonly', name: 'Read-Only', description: 'View-only access to most dashboards.', permissions: ['view:dashboard', 'view:agents', 'view:assets', 'view:security', 'view:compliance', 'view:ai_governance'], isEditable: true, tenantId: 'standard' },
    { id: 'role-ai-governance', name: 'AI Governance Officer', description: 'Manages AI systems, risks, and ethics.', permissions: ['view:dashboard', 'view:ai_governance', 'manage:ai_risks'], isEditable: true, tenantId: 'custom-acme' },
];

export const TENANTS_DATA: Tenant[] = [
    {
        id: 'platform-admin',
        name: 'Platform',
        subscriptionTier: 'Enterprise',
        registrationKey: 'platform-key-xyz',
        dataIngestionGB: 500,
        apiCallsMillions: 50.0,
        aiComputeVCPUHours: 2500,
        enabledFeatures: [],
        apiKeys: [],
        budget: { monthlyLimit: 10000 },
        finOpsData: {
            currentMonthCost: 5850.50,
            forecastedCost: 8500.00,
            potentialSavings: 1200.00,
            costBreakdown: [
                { service: 'AI Compute', cost: 2500 },
                { service: 'Data Ingestion', cost: 1500 },
                { service: 'Storage', cost: 950.50 },
                { service: 'API Calls', cost: 900 },
            ],
            costTrend: [
                { month: 'Feb', actual: 4800, forecast: 4700 },
                { month: 'Mar', actual: 5200, forecast: 5100 },
                { month: 'Apr', actual: 5000, forecast: 5200 },
                { month: 'May', actual: 5600, forecast: 5500 },
                { month: 'Jun', actual: 5400, forecast: 5600 },
                { month: 'Jul', actual: 5850.50, forecast: 8500 },
            ]
        }
    },
    {
        id: 'tenant-acme-corp',
        name: 'Acme Corp',
        subscriptionTier: 'Enterprise',
        registrationKey: 'acme-corp-reg-key-12345',
        dataIngestionGB: 1250,
        apiCallsMillions: 85.5,
        aiComputeVCPUHours: 4200,
        enabledFeatures: ALL_PERMISSIONS.filter(p => p !== 'manage:tenants'),
        apiKeys: [
            { id: 'key-acme-1', name: 'CI/CD Pipeline', key: 'omni_sk_abc123def456ghi789jkl', createdAt: '2024-07-01T10:00:00Z', userId: 'user-acme-admin' }
        ],
        budget: { monthlyLimit: 5000 },
        finOpsData: {
            currentMonthCost: 3450.75,
            forecastedCost: 5200.00,
            potentialSavings: 850.00,
            costBreakdown: [
                { service: 'AI Compute', cost: 1500 },
                { service: 'Data Ingestion', cost: 800 },
                { service: 'Storage', cost: 550.75 },
                { service: 'API Calls', cost: 600 },
            ],
            costTrend: [
                { month: 'Feb', actual: 2800, forecast: 2700 },
                { month: 'Mar', actual: 3100, forecast: 3000 },
                { month: 'Apr', actual: 2950, forecast: 3100 },
                { month: 'May', actual: 3300, forecast: 3200 },
                { month: 'Jun', actual: 3200, forecast: 3300 },
                { month: 'Jul', actual: 3450.75, forecast: 5200 },
            ]
        }
    },
    {
        id: 'tenant-initech',
        name: 'Initech',
        subscriptionTier: 'Pro',
        registrationKey: 'initech-corp-reg-key-67890',
        dataIngestionGB: 480,
        apiCallsMillions: 22.1,
        aiComputeVCPUHours: 1500,
        enabledFeatures: ['view:dashboard', 'view:assets', 'view:agents', 'view:security', 'view:reporting', 'export:reports', 'view:compliance', 'view:finops', 'view:audit_log'],
        apiKeys: [],
        budget: { monthlyLimit: 2000 },
        finOpsData: {
            currentMonthCost: 1250.30,
            forecastedCost: 1900.00,
            potentialSavings: 320.00,
            costBreakdown: [
                { service: 'AI Compute', cost: 600 },
                { service: 'Data Ingestion', cost: 320 },
                { service: 'Storage', cost: 180.30 },
                { service: 'API Calls', cost: 150 },
            ],
            costTrend: [
                { month: 'Feb', actual: 980, forecast: 950 },
                { month: 'Mar', actual: 1100, forecast: 1050 },
                { month: 'Apr', actual: 1050, forecast: 1100 },
                { month: 'May', actual: 1180, forecast: 1150 },
                { month: 'Jun', actual: 1200, forecast: 1180 },
                { month: 'Jul', actual: 1250.30, forecast: 1900 },
            ]
        }
    },
    {
        id: 'tenant-sriprasad',
        name: 'Sri Prasad Corp',
        subscriptionTier: 'Enterprise',
        registrationKey: 'sri-corp-reg-key-99999',
        dataIngestionGB: 100,
        apiCallsMillions: 5.0,
        aiComputeVCPUHours: 200,
        enabledFeatures: ALL_PERMISSIONS.filter(p => p !== 'manage:tenants'),
        apiKeys: [],
        budget: { monthlyLimit: 1000 },
        finOpsData: {
            currentMonthCost: 385.50,
            forecastedCost: 650.00,
            potentialSavings: 95.00,
            costBreakdown: [
                { service: 'AI Compute', cost: 150 },
                { service: 'Data Ingestion', cost: 80 },
                { service: 'Storage', cost: 95.50 },
                { service: 'API Calls', cost: 60 },
            ],
            costTrend: [
                { month: 'Feb', actual: 280, forecast: 270 },
                { month: 'Mar', actual: 310, forecast: 300 },
                { month: 'Apr', actual: 295, forecast: 310 },
                { month: 'May', actual: 330, forecast: 320 },
                { month: 'Jun', actual: 350, forecast: 360 },
                { month: 'Jul', actual: 385.50, forecast: 650 },
            ]
        }
    },
    {
        id: 'tenant-sriprasad',
        name: 'Sri Prasad Corp',
        subscriptionTier: 'Enterprise',
        registrationKey: 'sri-corp-reg-key-99999',
        dataIngestionGB: 100,
        apiCallsMillions: 5.0,
        aiComputeVCPUHours: 200,
        enabledFeatures: ALL_PERMISSIONS.filter(p => p !== 'manage:tenants'),
        apiKeys: [],
        budget: { monthlyLimit: 1000 },
        finOpsData: {
            currentMonthCost: 385.50,
            forecastedCost: 650.00,
            potentialSavings: 95.00,
            costBreakdown: [
                { service: 'AI Compute', cost: 150 },
                { service: 'Data Ingestion', cost: 80 },
                { service: 'Storage', cost: 95.50 },
                { service: 'API Calls', cost: 60 },
            ],
            costTrend: [
                { month: 'Feb', actual: 280, forecast: 270 },
                { month: 'Mar', actual: 310, forecast: 300 },
                { month: 'Apr', actual: 295, forecast: 310 },
                { month: 'May', actual: 330, forecast: 320 },
                { month: 'Jun', actual: 350, forecast: 360 },
                { month: 'Jul', actual: 385.50, forecast: 650 },
            ]
        }
    },
];

export const METRICS_DATA: Metric[] = [
    { id: 'cpu-usage', type: 'cpu', title: 'System Load', value: '38.6%', change: '2.5%', changeType: 'increase', data: generateMetricData(38, 5) },
    { id: 'mem-usage', type: 'memory', title: 'Memory Usage', value: '77.4%', change: '1.2%', changeType: 'decrease', data: generateMetricData(77, 4) },
    { id: 'uptime', type: 'network', title: 'System Uptime', value: '97.8%', change: '0.5%', changeType: 'increase', data: generateMetricData(98, 1) },
    { id: 'active-agents', type: 'disk', title: 'Active Agents', value: '12', change: '2', changeType: 'increase', data: generateMetricData(12, 2) },
];

export const ALERTS_DATA: Alert[] = [
    { id: 'alert-1', severity: 'Critical', message: 'High-CPU utilization on production database', source: 'db-prod-01', timestamp: '2m ago' },
    { id: 'alert-2', severity: 'High', message: 'Anomalous outbound traffic detected', source: 'web-server-03', timestamp: '15m ago' },
    { id: 'alert-3', severity: 'Medium', message: 'Disk space is running low (85% used)', source: 'app-server-12', timestamp: '45m ago' },
    { id: 'alert-4', severity: 'Low', message: 'New user login from an unrecognized IP', source: 'auth-service', timestamp: '1h ago' },
];

export const ASSETS_DATA: Asset[] = [
    { id: 'asset-1', tenantId: 'tenant-acme-corp', hostname: 'db-prod-01', osName: 'Ubuntu', osVersion: '22.04 LTS', kernel: '5.15.0-78-generic', ipAddress: '10.0.1.10', macAddress: '00:1A:2B:3C:4D:5E', cpuModel: 'Intel Xeon Gold 6248R', ram: '64 GB', disks: [{ device: '/dev/sda1', total: '500 GB', used: '320 GB', usedPercent: 64, type: 'SSD' }], serialNumber: 'SN-DBPROD01', installedSoftware: [{ name: 'nginx', version: '1.18.0', installDate: '2023-01-15' }, { name: 'openssh-server', version: '8.9p1', installDate: '2023-01-15' }], criticalFiles: [{ path: '/etc/passwd', status: 'Matched', lastModified: '2023-07-10', checksum: 'a1b2c3d4...' }], lastScanned: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(), patchStatus: { critical: 1, high: 2, medium: 0, low: 5 }, vulnerabilities: [{ id: 'CVE-2023-1234', cveId: 'CVE-2023-1234', severity: 'High', status: 'Open', affectedSoftware: 'nginx 1.18.0' }, { id: 'CVE-2023-5678', cveId: 'CVE-2023-5678', severity: 'Critical', status: 'Open', affectedSoftware: 'kernel 5.15.0' }], agentStatus: 'Online', agentVersion: '2.1.0', agentCapabilities: ['metrics_collection', 'log_collection', 'fim', 'predictive_health', 'ebpf_tracing'] },
    { id: 'asset-2', tenantId: 'tenant-acme-corp', hostname: 'web-server-03', osName: 'Windows Server 2022', osVersion: '21H2', kernel: '10.0.20348', ipAddress: '10.0.2.15', macAddress: '00:1A:2B:3C:4D:5F', cpuModel: 'AMD EPYC 7R32', ram: '32 GB', disks: [{ device: 'C:', total: '256 GB', used: '200 GB', usedPercent: 78, type: 'SSD' }], serialNumber: 'SN-WEB03', installedSoftware: [{ name: 'IIS', version: '10.0', installDate: '2023-02-20' }], criticalFiles: [{ path: 'C:\\Windows\\System32\\drivers\\etc\\hosts', status: 'Mismatch', lastModified: '2023-08-01', checksum: 'e5f6g7h8...' }], lastScanned: new Date(Date.now() - 36 * 60 * 60 * 1000).toISOString(), patchStatus: { critical: 0, high: 0, medium: 3, low: 1 }, vulnerabilities: [], agentStatus: 'Error', agentVersion: '2.0.5', agentCapabilities: ['metrics_collection', 'vulnerability_scanning', 'log_collection', 'runtime_security'] },
    { id: 'asset-3', tenantId: 'tenant-initech', hostname: 'dev-box-01', osName: 'Red Hat Enterprise Linux', osVersion: '9.1', kernel: '5.14.0-162.6.1.el9_1.x86_64', ipAddress: '192.168.1.50', macAddress: '00:1A:2B:3C:4D:6A', cpuModel: 'Intel Core i9-13900K', ram: '128 GB', disks: [], serialNumber: 'SN-DEV01', installedSoftware: [], criticalFiles: [], lastScanned: new Date(Date.now() - 12 * 60 * 60 * 1000).toISOString(), patchStatus: { critical: 0, high: 1, medium: 1, low: 0 }, vulnerabilities: [{ id: 'CVE-2023-ABCD', cveId: 'CVE-2023-ABCD', severity: 'High', status: 'Open', affectedSoftware: 'glibc 2.34' }], agentStatus: 'Offline', agentVersion: '2.1.0', agentCapabilities: ['metrics_collection', 'vulnerability_scanning'] },
    { id: 'asset-sri-1', tenantId: 'tenant-sriprasad', hostname: 'sri-server-01', osName: 'Windows Server 2022', osVersion: '21H2', kernel: '10.0.20348', ipAddress: '192.168.10.5', macAddress: '00:1A:2B:3C:4D:77', cpuModel: 'AMD EPYC 7763', ram: '64 GB', disks: [], serialNumber: 'SN-SRI01', installedSoftware: [], criticalFiles: [], lastScanned: new Date().toISOString(), patchStatus: { critical: 0, high: 0, medium: 0, low: 0 }, vulnerabilities: [], agentStatus: 'Online', agentVersion: '2.1.0', agentCapabilities: ['metrics_collection', 'log_collection'] },
    { id: 'asset-sri-1', tenantId: 'tenant-sriprasad', hostname: 'sri-server-01', osName: 'Windows Server 2022', osVersion: '21H2', kernel: '10.0.20348', ipAddress: '192.168.10.5', macAddress: '00:1A:2B:3C:4D:77', cpuModel: 'AMD EPYC 7763', ram: '64 GB', disks: [], serialNumber: 'SN-SRI01', installedSoftware: [], criticalFiles: [], lastScanned: new Date().toISOString(), patchStatus: { critical: 0, high: 0, medium: 0, low: 0 }, vulnerabilities: [], agentStatus: 'Online', agentVersion: '2.1.0', agentCapabilities: ['metrics_collection', 'log_collection'] },
];

export const AGENTS_DATA: Agent[] = [
    {
        id: 'agent-1',
        tenantId: 'tenant-1',
        assetId: 'asset-1',
        hostname: 'EILT0197',
        platform: 'Windows',
        status: 'Online',
        version: '2.0.0-rust',
        ipAddress: '10.0.0.4',
        lastSeen: new Date().toISOString(),
        capabilities: ['metrics_collection', 'log_collection', 'compliance_enforcement', 'runtime_security'],
        health: {
            overallStatus: 'Healthy',
            checks: [
                { name: 'Connectivity', status: 'Pass', message: 'Connected to control plane' },
                { name: 'Service Status', status: 'Pass', message: 'All services running' },
            ]
        },
        meta: {
            compliance_enforcement: {
                score: 50,
                passed: 1,
                failed: 1,
                warnings: 1,
                total_rules: 3,
                framework: 'Compliance',
                compliance_checks: [
                    { check: 'BitLocker Encryption', status: 'Warning', details: 'Check requires Admin privileges', evidence_content: 'Get-BitLockerVolume Output: manage-bde output: BitLocker Drive Encryption: Configuration', remediation: 'Enable BitLocker Drive Encryption on the system drive.' },
                    { check: 'Windows Firewall Profiles', status: 'Compliant', details: 'Firewall is enabled', evidence_content: 'Domain Profile: On, Private Profile: On, Public Profile: On' },
                    { check: 'Windows Defender Antivirus', status: 'Non-Compliant', details: 'Antivirus signature is out of date', evidence_content: 'Signature Version: 0.0.0.0', remediation: 'Update Windows Defender definitions.' }
                ]
            }
        }
    },
];

export const COMPLIANCE_DATA: ComplianceFramework[] = [
    {
        id: 'soc2',
        name: 'SOC 2 Type II',
        shortName: 'SOC 2',
        description: 'Service Organization Control 2',
        status: 'Compliant',
        progress: 100,
        controls: [
            { id: 'CC6.1', name: 'Logical Access Security', description: 'The entity implements logical access security software, infrastructure, and architectures over protected information assets to protect them from security events to meet the entity\'s objectives.', category: 'Common Criteria', status: 'Implemented', lastReviewed: '2023-06-01', evidence: [] },
            { id: 'CC6.2', name: 'User Registration', description: 'Prior to issuing system credentials and granting system access, the entity registers and authorizes new internal and external users whose access is administered by the entity.', category: 'Common Criteria', status: 'Implemented', lastReviewed: '2023-06-05', evidence: [] },
            { id: 'CC6.3', name: 'Access Removal', description: 'The entity authorizes, modifies, or removes access to data, software, functions, and other protected information assets based on roles, responsibilities, or the entity\'s system design and changes, giving consideration to total cost of ownership.', category: 'Common Criteria', status: 'In Progress', lastReviewed: '2023-06-10', evidence: [] },
            { id: 'CC6.6', name: 'Boundary Protection', description: 'The entity implements boundary protection devices, methodologies, and procedures to prevent unauthorized access and data exfiltration.', category: 'Common Criteria', status: 'Implemented', lastReviewed: '2023-06-12', evidence: [] },
            { id: 'CC6.7', name: 'Transmission Protection', description: 'The entity restricts the transmission, movement, and conversion of information to authorized users and processes and protects information during transmission, movement, or conversion to meet the entity\'s objectives.', category: 'Common Criteria', status: 'Implemented', lastReviewed: '2023-06-14', evidence: [] },
            { id: 'CC6.8', name: 'Prevent/Detect Malicious Software', description: 'The entity implements controls to prevent or detect and act upon the introduction of malicious software to meet the entity\'s objectives.', category: 'Common Criteria', status: 'Implemented', lastReviewed: '2023-06-15', evidence: [] },
            { id: 'CC7.1', name: 'Configuration Management', description: 'The entity restricts the ability to perform configuration management and configuration parameters to authorized users and processes.', category: 'Common Criteria', status: 'In Progress', lastReviewed: '2023-06-20', evidence: [] },
            { id: 'CC7.2', name: 'Vulnerability Management', description: 'The entity utilizes vulnerability scanning or penetration testing to identify and rectify vulnerabilities.', category: 'Common Criteria', status: 'At Risk', lastReviewed: '2023-06-22', evidence: [] },
            { id: 'CC7.3', name: 'Patch Management', description: 'The entity implements a patch management process to ensure that all systems are updated with the latest security patches.', category: 'Common Criteria', status: 'Implemented', lastReviewed: '2023-06-25', evidence: [] },
            { id: 'CC8.1', name: 'Change Management', description: 'The entity authorizes, designs, develops or acquires, configures, documents, tests, approves, and implements changes to infrastructure, data, software, and procedures to meet the entity\'s objectives.', category: 'Common Criteria', status: 'Implemented', lastReviewed: '2023-06-28', evidence: [] },
            { id: 'CC9.2', name: 'Incident Response', description: 'The entity responds to identified security incidents by executing a defined incident response program to understand, contain, remediate, and communicate security incidents, as appropriate.', category: 'Common Criteria', status: 'Implemented', lastReviewed: '2023-07-01', evidence: [] },
        ]
    },
    {
        id: 'iso27001',
        name: 'ISO/IEC 27001:2022',
        shortName: 'ISO 27001',
        description: 'Information Security Management',
        status: 'Pending',
        progress: 85,
        controls: [
            { id: 'A.5.1', name: 'Policies for Information Security', description: 'Information security policy and topic-specific policies shall be defined, approved by management, published, communicated to and acknowledged by relevant personnel and relevant interested parties.', category: 'Organizational', status: 'Implemented', lastReviewed: '2023-08-15', evidence: [] },
            { id: 'A.5.15', name: 'Access Control', description: 'Rules to control physical and logical access to information and other associated assets shall be established and implemented based on business and information security requirements.', category: 'Organizational', status: 'Implemented', lastReviewed: '2023-08-18', evidence: [] },
            { id: 'A.6.1', name: 'Screening', description: 'Background verification checks on all candidates for employment, contractors and other personnel shall be carried out in accordance with relevant laws, regulations and ethics and shall be proportional to the business requirements, the classification of the information to be accessed and the perceived risks.', category: 'People', status: 'Implemented', lastReviewed: '2023-09-01', evidence: [] },
            { id: 'A.7.2', name: 'Physical Entry Controls', description: 'Secure areas shall be protected by appropriate entry controls and access points.', category: 'Physical', status: 'Implemented', lastReviewed: '2023-09-05', evidence: [] },
            { id: 'A.8.1', name: 'User Endpoint Devices', description: 'Information stored on, processed by or accessible via user endpoint devices shall be protected.', category: 'Technological', status: 'Implemented', lastReviewed: '2023-11-08', evidence: [] },
            { id: 'A.8.2', name: 'Privileged Access Rights', description: 'The allocation and use of privileged access rights shall be restricted and managed.', category: 'Technological', status: 'In Progress', lastReviewed: '2023-11-10', evidence: [] },
            { id: 'A.8.7', name: 'Protection against Malware', description: 'Protection against malware shall be implemented and supported by appropriate user awareness.', category: 'Technological', status: 'Implemented', lastReviewed: '2023-11-11', evidence: [] },
            { id: 'A.8.8', name: 'Management of Technical Vulnerabilities', description: 'Information about technical vulnerabilities of information systems being used shall be obtained, the entity\'s exposure to such vulnerabilities evaluated and appropriate measures taken.', category: 'Technological', status: 'At Risk', lastReviewed: '2023-11-11', evidence: [] },
            { id: 'A.8.10', name: 'Information Deletion', description: 'Information stored in information systems, devices or in any other storage media shall be deleted when no longer required.', category: 'Technological', status: 'Not Implemented', lastReviewed: '2023-11-11', evidence: [] },
            { id: 'A.8.12', name: 'Data Leakage Prevention', description: 'Data leakage prevention measures shall be applied to systems, networks and any other devices that process, store or transmit sensitive information.', category: 'Technological', status: 'Not Implemented', lastReviewed: '2023-11-12', evidence: [] },
            { id: 'A.8.13', name: 'Information Backup', description: 'Backup copies of information, software and system images shall be taken and tested regularly in accordance with an agreed backup policy.', category: 'Technological', status: 'Implemented', lastReviewed: '2023-11-13', evidence: [] },
            { id: 'A.8.24', name: 'Use of Cryptography', description: 'Rules for the effective use of cryptography, including cryptographic key management, shall be defined and implemented.', category: 'Technological', status: 'Implemented', lastReviewed: '2023-11-14', evidence: [] },
            { id: 'A.8.28', name: 'Secure Coding', description: 'Secure coding principles shall be applied to software development.', category: 'Technological', status: 'In Progress', lastReviewed: '2023-11-15', evidence: [] },
            { id: 'A.9.4.1', name: 'Password Policy', description: 'The allocation and use of passwords shall be controlled through a formal management process.', category: 'Technological', status: 'Implemented', lastReviewed: '2023-11-16', evidence: [] },
            { id: 'A.12.6.1', name: 'Software Updates', description: 'Information about technical vulnerabilities of information systems being used shall be obtained, the organization\'s exposure to such vulnerabilities evaluated and appropriate measures taken.', category: 'Technological', status: 'Implemented', lastReviewed: '2023-11-17', evidence: [] },
        ]
    },
    {
        id: 'gdpr',
        name: 'General Data Protection Regulation',
        shortName: 'GDPR',
        description: 'EU Data Protection',
        status: 'Compliant',
        progress: 100,
        controls: [
            { id: 'Art. 32', name: 'Security of Processing', description: 'Implement appropriate technical and organizational measures to ensure a level of security appropriate to the risk.', category: 'Security', status: 'Implemented', lastReviewed: '2023-07-20', evidence: [] },
            { id: 'Art. 35', name: 'Data Protection Impact Assessment', description: 'Carry out an assessment of the impact of the envisaged processing operations on the protection of personal data.', category: 'Accountability', status: 'Implemented', lastReviewed: '2023-07-25', evidence: [] },
        ]
    },
    {
        id: 'hipaa',
        name: 'Health Insurance Portability and Accountability Act',
        shortName: 'HIPAA',
        description: 'Healthcare Data Privacy',
        status: 'At Risk',
        progress: 72,
        controls: [
            { id: '164.308(a)(1)', name: 'Security Management Process', description: 'Implement policies and procedures to prevent, detect, contain, and correct security violations.', category: 'Administrative Safeguard', status: 'Implemented', lastReviewed: '2023-10-01', evidence: [] },
            { id: '164.308(a)(5)', name: 'Security Awareness and Training', description: 'Implement a security awareness and training program for all members of its workforce.', category: 'Administrative Safeguard', status: 'In Progress', lastReviewed: '2023-10-15', evidence: [] },
            { id: '164.310(a)(1)', name: 'Facility Access Controls', description: 'Limit physical access to electronic information systems and the facility in which they are housed.', category: 'Physical Safeguard', status: 'Implemented', lastReviewed: '2023-09-20', evidence: [] },
            { id: '164.312(a)(1)', name: 'Access Control', description: 'Implement technical policies and procedures for electronic information systems that maintain electronic protected health information to allow access only to those persons or software programs that have been granted access rights.', category: 'Technical Safeguard', status: 'At Risk', lastReviewed: '2023-11-05', evidence: [] },
            { id: '164.312(a)(2)(iv)', name: 'Encryption and Decryption', description: 'Implement a mechanism to encrypt and decrypt electronic protected health information.', category: 'Technical Safeguard', status: 'Not Implemented', lastReviewed: '2023-11-01', evidence: [] },
        ]
    },
    {
        id: 'pci-dss',
        name: 'Payment Card Industry Data Security Standard',
        shortName: 'PCI DSS',
        description: 'Cardholder Data Protection',
        status: 'Compliant',
        progress: 100,
        controls: [
            { id: 'PCI-1.1', name: 'Firewall Configuration', description: 'Install and maintain a firewall configuration to protect cardholder data.', category: 'Build and Maintain a Secure Network', status: 'Implemented', lastReviewed: '2023-10-20', evidence: [] },
            { id: 'PCI-2.1', name: 'System Defaults', description: 'Do not use vendor-supplied defaults for system passwords and other security parameters.', category: 'Build and Maintain a Secure Network', status: 'Implemented', lastReviewed: '2023-10-22', evidence: [] },
            { id: 'PCI-3.4', name: 'Protect Stored Data', description: 'Render PAN unreadable anywhere it is stored (including on portable digital media, backup media, and in logs).', category: 'Protect Cardholder Data', status: 'Implemented', lastReviewed: '2023-10-25', evidence: [] },
            { id: 'PCI-4.1', name: 'Encrypt Transmission', description: 'Encrypt transmission of cardholder data across open, public networks.', category: 'Protect Cardholder Data', status: 'Implemented', lastReviewed: '2023-10-28', evidence: [] },
            { id: 'PCI-5.1', name: 'Anti-Virus Software', description: 'Protect all systems against malware and regularly update anti-virus software or programs.', category: 'Maintain a Vulnerability Management Program', status: 'Implemented', lastReviewed: '2023-10-30', evidence: [] },
            { id: 'PCI-6.2', name: 'System Patches', description: 'Ensure that all system components and software are protected from known vulnerabilities by installing applicable vendor-supplied security patches.', category: 'Maintain a Vulnerability Management Program', status: 'In Progress', lastReviewed: '2023-11-02', evidence: [] },
            { id: 'PCI-7.1', name: 'Access Restriction', description: 'Restrict access to cardholder data by business need to know.', category: 'Implement Strong Access Control Measures', status: 'Implemented', lastReviewed: '2023-11-05', evidence: [] },
            { id: 'PCI-8.1.1', name: 'Unique IDs', description: 'Assign a unique ID to each person with computer access.', category: 'Implement Strong Access Control Measures', status: 'Implemented', lastReviewed: '2023-11-08', evidence: [] },
            { id: 'PCI-9.1', name: 'Physical Security', description: 'Restrict physical access to cardholder data.', category: 'Implement Strong Access Control Measures', status: 'In Progress', lastReviewed: '2023-11-10', evidence: [] },
            { id: 'PCI-10.1', name: 'Audit Logging', description: 'Track and monitor all access to network resources and cardholder data.', category: 'Regularly Monitor and Test Networks', status: 'Implemented', lastReviewed: '2023-11-12', evidence: [] },
            { id: 'PCI-11.2', name: 'Vulnerability Scanning', description: 'Run internal and external network vulnerability scans at least quarterly and after any significant change in the network.', category: 'Regularly Monitor and Test Networks', status: 'At Risk', lastReviewed: '2023-11-15', evidence: [] },
            { id: 'PCI-12.1', name: 'Information Security Policy', description: 'Maintain a policy that addresses information security for all personnel.', category: 'Maintain an Information Security Policy', status: 'Implemented', lastReviewed: '2023-11-18', evidence: [] },
        ]
    },
    {
        id: 'iso42001',
        name: 'ISO/IEC 42001:2023',
        shortName: 'ISO 42001',
        description: 'AI Management System',
        status: 'Pending',
        progress: 65,
        controls: [
            { id: 'B.6.1', name: 'AI Risk Assessment', description: 'Assess the risks associated with the use of AI systems.', category: 'Risk Management', status: 'Implemented', lastReviewed: '2024-01-10', evidence: [] },
            { id: 'B.7.2', name: 'Data Quality', description: 'Ensure that data used for AI systems is of sufficient quality to meet the system\'s requirements.', category: 'Data', status: 'In Progress', lastReviewed: '2024-02-01', evidence: [] },
            { id: 'B.9.3', name: 'Human Oversight', description: 'Implement mechanisms for human oversight of AI systems.', category: 'Operation', status: 'Not Implemented', lastReviewed: '2024-02-15', evidence: [] },
        ]
    },
    {
        id: 'nistcsf',
        name: 'NIST Cybersecurity Framework',
        shortName: 'NIST CSF',
        description: 'US National Institute of Standards and Technology Framework',
        status: 'Compliant',
        progress: 95,
        nistFunctions: [
            { id: 'identify', name: 'Identify', progress: 100 },
            { id: 'protect', name: 'Protect', progress: 92 },
            { id: 'detect', name: 'Detect', progress: 98 },
            { id: 'respond', name: 'Respond', progress: 90 },
            { id: 'recover', name: 'Recover', progress: 95 },
        ],
        controls: [
            { id: 'ID.AM-1', name: 'Asset Management', description: 'Physical devices and systems within the organization are inventoried.', category: 'Identify', status: 'Implemented', lastReviewed: '2023-10-05', evidence: [] },
            { id: 'ID.AM-2', name: 'Software Inventory', description: 'Software platforms and applications within the organization are inventoried.', category: 'Identify', status: 'Implemented', lastReviewed: '2023-10-06', evidence: [] },
            { id: 'ID.RA-1', name: 'Risk Assessment', description: 'Asset vulnerabilities are identified and documented.', category: 'Identify', status: 'At Risk', lastReviewed: '2023-10-07', evidence: [] },
            { id: 'PR.AC-1', name: 'Access Control', description: 'Access to assets and associated facilities is limited to authorized users, processes, or devices, and to authorized activities and transactions.', category: 'Protect', status: 'Implemented', lastReviewed: '2023-10-08', evidence: [] },
            { id: 'PR.AC-5', name: 'Network Segregation', description: 'Network integrity is protected (e.g., network segregation, network segmentation).', category: 'Protect', status: 'In Progress', lastReviewed: '2023-10-09', evidence: [] },
            { id: 'PR.DS-1', name: 'Data at Rest', description: 'Data-at-rest is protected.', category: 'Protect', status: 'Implemented', lastReviewed: '2023-10-10', evidence: [] },
            { id: 'PR.DS-2', name: 'Data in Transit', description: 'Data-in-transit is protected.', category: 'Protect', status: 'Implemented', lastReviewed: '2023-10-11', evidence: [] },
            { id: 'DE.AE-1', name: 'Anomalies and Events', description: 'A baseline of network operations and expected data flows for users and systems is established and managed.', category: 'Detect', status: 'Implemented', lastReviewed: '2023-10-12', evidence: [] },
            { id: 'DE.CM-1', name: 'Security Monitoring', description: 'The network is monitored to detect potential cybersecurity events.', category: 'Detect', status: 'Implemented', lastReviewed: '2023-10-13', evidence: [] },
            { id: 'RS.RP-1', name: 'Response Planning', description: 'Response processes and procedures are executed and maintained.', category: 'Respond', status: 'Implemented', lastReviewed: '2023-10-14', evidence: [] },
            { id: 'RC.RP-1', name: 'Recovery Planning', description: 'Recovery processes and procedures are executed and maintained.', category: 'Recover', status: 'Implemented', lastReviewed: '2023-10-15', evidence: [] },
        ]
    },
];

export const AI_SYSTEMS_DATA: AiSystem[] = [
    {
        id: 'ai-sys-1',
        tenantId: 'tenant-acme-corp',
        name: 'Threat Detection Engine',
        description: 'Real-time analysis of network traffic for malicious patterns.',
        version: '2.3.1',
        owner: 'Bob Security',
        status: 'Active',
        lastAssessmentDate: '2024-06-15',
        impactAssessment: {
            summary: 'High impact system critical for security operations.',
            initialRisks: [{ title: 'Algorithmic Bias', detail: 'May disproportionately flag traffic from specific regions.' }],
            mitigations: [{ title: 'Regular Auditing', detail: 'Monthly review of flagged events for bias.' }]
        },
        fairnessMetrics: [{
            id: 'fm-1',
            name: 'Equal Opportunity Difference',
            description: 'Difference in true positive rates across demographic groups.',
            value: '0.08',
            status: 'Pass'
        }],
        risks: [
            {
                id: 'risk-bias-1',
                title: 'Algorithmic Bias in Threat Scoring',
                detail: 'The model may be unfairly flagging traffic from certain geographic regions due to imbalances in the training data, leading to false positives for specific user groups.',
                severity: 'High',
                status: 'Open',
                mitigationStatus: 'Not Started',
                mitigationTasks: [
                    {
                        id: 'task-1',
                        description: 'Audit training data for geographic representation.',
                        owner: 'Data Team',
                        dueDate: '2024-08-01',
                        status: 'To Do',
                        priority: 'High'
                    }
                ],
                history: [
                    {
                        id: 'hist-risk-1',
                        timestamp: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString(),
                        user: 'System',
                        action: 'Created',
                        details: 'Risk identified during initial impact assessment.'
                    }
                ]
            },
            {
                id: 'risk-drift-1',
                title: 'Model Drift',
                detail: 'Model performance may degrade over time as attack patterns evolve.',
                severity: 'Medium',
                status: 'Mitigated',
                mitigationStatus: 'Completed',
                mitigationTasks: [],
                history: []
            }
        ],
        documentation: [],
        controls: { isEnabled: true, confidenceThreshold: 85, lastRetrainingTriggered: new Date(Date.now() - 10 * 24 * 60 * 60 * 1000).toISOString() },
        performanceData: Array.from({ length: 30 }, (_, i) => ({ time: `${30 - i}m`, latency: 120 + Math.random() * 20, throughput: 500 + Math.random() * 50, errorRate: 1 + Math.random() * 0.5 })),
        securityAlerts: []
    },
    {
        id: 'ai-sys-2',
        tenantId: 'tenant-acme-corp',
        name: 'Cost Optimization AI',
        description: 'Predicts cloud usage and suggests cost-saving measures.',
        version: '1.1.0',
        owner: 'Alice Admin',
        status: 'In Development',
        lastAssessmentDate: '2024-05-20',
        impactAssessment: {
            summary: 'Medium impact system for financial planning.',
            initialRisks: [],
            mitigations: []
        },
        fairnessMetrics: [],
        risks: [],
        documentation: [],
        controls: { isEnabled: false, confidenceThreshold: 95, lastRetrainingTriggered: null },
        performanceData: [],
        securityAlerts: []
    },
];

export const PATCHES_DATA: Patch[] = [
    { id: 'patch-1', cveId: 'CVE-2023-5678', description: 'Kernel vulnerability allowing for privilege escalation.', severity: 'Critical', status: 'Pending', releaseDate: '2024-07-20', affectedAssets: ['asset-1'] },
    { id: 'patch-2', cveId: 'CVE-2023-1234', description: 'Nginx request smuggling vulnerability.', severity: 'High', status: 'Pending', releaseDate: '2024-07-18', affectedAssets: ['asset-1'] },
];

export const SECURITY_EVENTS_DATA: SecurityEvent[] = [
    { id: 'se-1', tenantId: 'tenant-acme-corp', timestamp: new Date().toISOString(), severity: 'High', description: 'Potential SQL Injection attempt detected.', type: 'Web Attack', source: { ip: '198.51.100.12', hostname: 'web-server-03' }, mitreAttack: { technique: 'T1190', url: 'https://attack.mitre.org/techniques/T1190/' } },
    { id: 'se-2', tenantId: 'tenant-acme-corp', timestamp: new Date(Date.now() - 5 * 60000).toISOString(), severity: 'Medium', description: 'Multiple failed login attempts from same IP.', type: 'Authentication', source: { ip: '203.0.113.45', hostname: 'auth-service' }, mitreAttack: { technique: 'T1110', url: 'https://attack.mitre.org/techniques/T1110/' } },
    { id: 'se-3', tenantId: 'tenant-initech', timestamp: new Date(Date.now() - 10 * 60000).toISOString(), severity: 'Critical', description: 'Malware signature detected in file download.', type: 'Malware', source: { ip: '192.168.1.50', hostname: 'dev-box-01' }, details: { fileHash: 'e4d909c290d0fb1ca068ffaddf22cbd0', signature: 'Win.Trojan.Generic-12345' } },
];

export const SECURITY_CASES_DATA: SecurityCase[] = [
    {
        id: 'case-001', tenantId: 'tenant-acme-corp', title: 'Investigate Anomalous Outbound Traffic on web-server-03', status: 'In Progress', severity: 'High', owner: 'Bob Security', createdAt: new Date(Date.now() - 24 * 3600000).toISOString(), updatedAt: new Date().toISOString(), relatedEvents: [SECURITY_EVENTS_DATA[0]], comments: [{ id: 'c-1', timestamp: new Date().toISOString(), user: 'Alice Admin', content: 'Bob, please prioritize this.' }],
        enrichmentData: [
            {
                id: 'vt-enrich-1',
                artifact: '198.51.100.12',
                artifactType: 'ip',
                source: 'Simulated Feed',
                verdict: 'Malicious',
                detectionRatio: '12/92',
                scanDate: new Date(Date.now() - 23 * 3600000).toISOString(),
                reportUrl: '#'
            }
        ]
    },
    { id: 'case-002', tenantId: 'tenant-initech', title: 'Malware Detected on Developer Machine', status: 'New', severity: 'Critical', owner: 'Unassigned', createdAt: new Date().toISOString(), updatedAt: new Date().toISOString(), relatedEvents: [SECURITY_EVENTS_DATA[2]], comments: [], enrichmentData: [] },
];

export const PLAYBOOKS_DATA: Playbook[] = [
    { id: 'pb-1', name: 'Phishing Email Response', description: 'Automated response to a reported phishing email.', trigger: 'User Report', source: 'User', conditions: [], steps: [] },
    {
        id: 'pb-2', name: 'Malware Containment', description: 'Isolate host, detonate malware, and block indicators.', trigger: 'Malware Alert', source: 'AI-Generated',
        conditions: [
            { id: 'cond-1', field: 'event.severity', operator: 'equals', value: 'Critical' }
        ],
        steps: []
    },
];

export const CLOUD_ACCOUNTS_DATA: CloudAccount[] = [
    { id: 'ca-1', tenantId: 'tenant-acme-corp', provider: 'AWS', name: 'Production Account', accountId: '1234-5678-9012', status: 'Connected' },
    { id: 'ca-2', tenantId: 'tenant-acme-corp', provider: 'Azure', name: 'Dev/Test Subscription', accountId: 'sub-abcdef-1234', status: 'Error' },
];

export const CSPM_FINDINGS_DATA: CSPMFinding[] = [
    { id: 'cspm-1', tenantId: 'tenant-acme-corp', title: 'S3 Bucket is publicly accessible', description: 'S3 bucket `acme-public-data` allows for public read access which may expose sensitive data.', severity: 'Critical', provider: 'AWS', resourceId: 'arn:aws:s3:::acme-public-data', lastSeen: new Date().toISOString(), remediation: { cli: 'aws s3api put-public-access-block ...', console: 'Navigate to S3 > Bucket > Permissions and edit Block Public Access settings.' } },
];

export const NOTIFICATIONS_DATA: Notification[] = [
    { id: 'notif-1', message: 'Critical Patch CVE-2023-5678 is available for 1 asset.', timestamp: new Date(Date.now() - 3600000).toISOString(), isRead: false, linkTo: 'patchManagement' },
    { id: 'notif-2', message: 'New security case #case-002 created for malware detection.', timestamp: new Date().toISOString(), isRead: true, linkTo: 'security' },
];

export const AUDIT_LOGS_DATA: AuditLog[] = [
    { id: 'log-1', timestamp: new Date().toISOString(), userName: 'Alice Admin', action: 'user.login', resourceType: 'user', resourceId: 'user-acme-admin', details: 'User logged in successfully.' },
    { id: 'log-2', timestamp: new Date(Date.now() - 120000).toISOString(), userName: 'Super Admin', action: 'tenant.create', resourceType: 'tenant', resourceId: 'tenant-initech', details: 'Created new tenant Initech.' },
];

export const INTEGRATIONS_DATA: Integration[] = [
    { id: 'pagerduty', name: 'PagerDuty', description: 'Trigger incidents for on-call teams.', category: 'Observability', isEnabled: false, config: { apiKey: '' } },
    { id: 'jira', name: 'Jira', description: 'Create tickets for security cases and tasks.', category: 'Ticketing', isEnabled: true, config: { apiUrl: 'https://omni.atlassian.net', apiToken: '', projectKey: 'SEC' } },
    { id: 'splunk', name: 'Splunk', description: 'Forward events and logs to your Splunk instance.', category: 'SIEM', isEnabled: false, config: {} },
    { id: 'datadog', name: 'Datadog', description: 'Correlate Omni-Agent data with Datadog metrics.', category: 'Observability', isEnabled: false, config: {} },
    { id: 'crowdstrike', name: 'CrowdStrike', description: 'Enrich findings with Falcon platform data.', category: 'Security', isEnabled: false, config: {} },
];

export const ALERT_RULES_DATA: AlertRule[] = [
    { id: 'rule-1', name: 'High CPU Usage', metric: 'cpu', condition: '>', threshold: 90, duration: 5, severity: 'Critical', isEnabled: true },
];

export const HISTORICAL_DATA: any = {
    alerts: [{ date: 'Feb', Critical: 5, High: 10, Medium: 20 }, { date: 'Mar', Critical: 7, High: 12, Medium: 25 }],
    compliance: [{ date: 'Feb', posture: 92 }, { date: 'Mar', posture: 94 }],
    vulnerabilities: [{ date: 'Feb', Critical: 10, High: 30 }, { date: 'Mar', Critical: 8, High: 25 }],
};

export const DATABASE_SETTINGS_DATA: DatabaseSettings = { type: 'MongoDB', host: 'localhost', port: 27017, username: 'admin', databaseName: 'omni_db' };

export const LLM_SETTINGS_DATA: LlmSettings = { provider: 'Gemini', apiKey: 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx', model: 'gemini-flash-latest', host: 'http://localhost:11434' };

export const DATA_SOURCES_DATA: DataSource[] = [
    { id: 'ds-1', tenantId: 'tenant-acme-corp', name: 'Production Postgres DB', type: 'PostgreSQL', status: 'Connected', config: { host: 'prod-db.acme.internal' }, lastTested: new Date().toISOString() }
];

export const SBOMS_DATA: Sbom[] = [
    { id: 'sbom-1', applicationName: 'Auth Service', uploadedAt: new Date().toISOString(), componentCount: 152 }
];

export const SOFTWARE_COMPONENTS_DATA: SoftwareComponent[] = [
    { id: 'comp-1', name: 'log4j-core', version: '2.14.1', type: 'library', supplier: 'Apache', licenses: [{ id: 'apache-2.0', name: 'Apache-2.0' }], vulnerabilities: [{ cve: 'CVE-2021-44228', severity: 'Critical', summary: 'Log4Shell vulnerability' }] }
];

export const AGENT_UPGRADE_JOBS_DATA: AgentUpgradeJob[] = [
    { id: 'job-1', scheduledAt: new Date(Date.now() - 3600000).toISOString(), startedAt: null, completedAt: null, targetVersion: '2.2.1', status: 'Queued', agentIds: ['agent-3'], progress: 0, statusLog: [] }
];

export const PATCH_DEPLOYMENT_JOBS_DATA: PatchDeploymentJob[] = [];
export const VULNERABILITY_SCAN_JOBS_DATA: VulnerabilityScanJob[] = [];

export const LOGS_DATA: LogEntry[] = [
    { id: 'log-101', timestamp: new Date(Date.now() - 1 * 60000).toISOString(), service: 'auth-service', hostname: 'auth-1', severity: 'INFO', message: 'User alice@acme.com logged in successfully.' },
    { id: 'log-102', timestamp: new Date(Date.now() - 2 * 60000).toISOString(), service: 'api-gateway', hostname: 'gw-1', severity: 'WARN', message: 'Latency for /api/data/assets is high: 520ms.' },
    { id: 'log-103', timestamp: new Date(Date.now() - 3 * 60000).toISOString(), service: 'db-proxy', hostname: 'db-proxy-1', severity: 'ERROR', message: 'Failed to connect to replica DB.' },
];

export const UEBA_FINDINGS_DATA: UebaFinding[] = [
    { id: 'ueba-1', userId: 'user-acme-secops', riskScore: 82, summary: 'Anomalous login time and unusual data access pattern.', timestamp: new Date().toISOString(), relatedLogIds: ['log-101'], details: 'User logged in outside of normal business hours and accessed sensitive financial data, which is atypical for this role.', status: 'Open' },
];

export const MODEL_EXPERIMENTS_DATA: ModelExperiment[] = [
    { id: 'exp-1', modelName: 'Threat Detection v3', createdAt: new Date().toISOString(), status: 'Completed', metrics: { accuracy: 0.981, precision: 0.975, recall: 0.988, f1Score: 0.981 }, parameters: { learningRate: 0.001, epochs: 10, batchSize: 64 } },
    { id: 'exp-2', modelName: 'Threat Detection v3.1', createdAt: new Date().toISOString(), status: 'Running', metrics: { accuracy: 0.0, precision: 0.0, recall: 0.0, f1Score: 0.0 }, parameters: { learningRate: 0.0005, epochs: 15, batchSize: 32 } },
];

export const REGISTERED_MODELS_DATA: RegisteredModel[] = [
    {
        id: 'reg-model-1', name: 'Threat Detection', description: 'Primary model for detecting network threats.', latestVersion: '3.0.0', stage: 'Production', versions: [
            { version: '3.0.0', experimentId: 'exp-1', promotedAt: new Date(Date.now() - 5 * 24 * 3600000).toISOString(), promotedBy: 'Alice Admin' },
            { version: '2.5.0', experimentId: 'exp-pre-1', promotedAt: new Date(Date.now() - 30 * 24 * 3600000).toISOString(), promotedBy: 'Alice Admin' },
        ]
    },
];
export const AUTOMATION_POLICIES_DATA: AutomationPolicy[] = [
    { id: 'policy-1', name: 'Auto-remediate Agent Errors', description: 'Automatically attempts to remediate an agent when a critical disk space alert is triggered.', trigger: 'alert.critical', conditions: [{ field: 'error_message', operator: 'contains', value: 'disk space' }], action: 'remediate.agent', isEnabled: true },
    { id: 'policy-2', name: 'Create Case for Critical Alerts', description: 'Automatically creates a security case when a critical alert is triggered.', trigger: 'alert.critical', conditions: [], action: 'create.case', isEnabled: true },
    { id: 'policy-3', name: 'Disabled Example Policy', description: 'This policy is currently disabled and will not run.', trigger: 'agent.error', conditions: [], action: 'remediate.agent', isEnabled: false },
];

export const SAST_FINDINGS_DATA: SastFinding[] = [
    { id: 'sast-1', repositoryId: 'repo-1', fileName: 'auth/login.go', line: 125, type: 'SQL Injection', severity: 'High', codeSnippet: 'query := fmt.Sprintf("SELECT * FROM users WHERE username = \'%s\' AND password = \'%s\'", user, pass)' },
    { id: 'sast-2', repositoryId: 'repo-1', fileName: 'views/profile.html', line: 42, type: 'Cross-Site Scripting', severity: 'Medium', codeSnippet: '<div>Welcome, {{ .Username }}</div>' },
];

export const CODE_REPOSITORIES_DATA: CodeRepository[] = [
    { id: 'repo-1', name: 'omni-auth-service', url: 'https://github.com/omni-ai/auth-service', lastScan: new Date().toISOString(), secretFindings: 1, dependencyVulnerabilities: 5, sastFindings: 2 },
    { id: 'repo-2', name: 'omni-api-gateway', url: 'https://github.com/omni-ai/api-gateway', lastScan: new Date(Date.now() - 2 * 24 * 3600000).toISOString(), secretFindings: 0, dependencyVulnerabilities: 2, sastFindings: 0 },
];

export const API_DOCS_DATA: ApiDocEndpoint[] = [
    { id: 'api-1', method: 'POST', path: '/api/login', description: 'Authenticate a user and receive a JWT.' },
    { id: 'api-2', method: 'GET', path: '/api/data/assets', description: 'Retrieve a list of all assets for the tenant.' },
];

export const INCIDENT_IMPACT_GRAPH_DATA: IncidentImpactGraph = {
    nodes: [
        { id: 'alert-2', label: 'Anomalous Outbound Traffic', type: 'Alert' },
        { id: 'web-server-03', label: 'web-server-03', type: 'Service' },
        { id: 'auth-service', label: 'auth-service', type: 'Service' },
        { id: 'user-db', label: 'user-db', type: 'Service' },
        { id: 'login-latency', label: 'Login Latency KPI', type: 'KPI' },
    ],
    edges: [
        { from: 'alert-2', to: 'web-server-03', label: 'Detected on' },
        { from: 'web-server-03', to: 'auth-service', label: 'Depends on' },
        { from: 'auth-service', to: 'user-db', label: 'Depends on' },
        { from: 'auth-service', to: 'login-latency', label: 'Impacts' },
    ],
};

export const SENSITIVE_DATA_FINDINGS_DATA: SensitiveDataFinding[] = [
    { id: 'sdf-1', tenantId: 'tenant-acme-corp', assetId: 'asset-1', assetName: 'db-prod-01', classification: 'PII', resource: 'db://users/credit_card_number', finding: 'Credit card numbers found in unencrypted column.', severity: 'Critical' },
    { id: 'sdf-2', tenantId: 'tenant-acme-corp', assetId: 'asset-2', assetName: 'web-server-03', classification: 'Financial', resource: 's3://acme-corp-financials/q3_report.docx', finding: 'Publicly exposed S3 bucket contains sensitive financial report.', severity: 'High' },
    { id: 'sdf-3', tenantId: 'tenant-initech', assetId: 'asset-3', assetName: 'dev-box-01', classification: 'IP', resource: 'git://source-code/project-x/main.py', finding: 'Source code for Project X contains hardcoded API keys.', severity: 'High' },
];

export const ATTACK_PATHS_DATA: AttackPath[] = [
    {
        id: 'ap-1',
        tenantId: 'tenant-acme-corp',
        name: 'Public S3 Bucket to Production Database',
        nodes: [
            { id: 'node-1', type: 'Public Asset', label: 'Public S3 Bucket', vulnerabilities: 1 },
            { id: 'node-2', type: 'Internal Service', label: 'Data Processing Lambda', vulnerabilities: 0 },
            { id: 'node-3', type: 'Database', label: 'Production User DB', vulnerabilities: 1 },
            { id: 'node-4', type: 'Crown Jewel', label: 'Customer PII Data', vulnerabilities: 0 },
        ],
        edges: [
            { from: 'node-1', to: 'node-2', label: 'Leaked IAM credentials' },
            { from: 'node-2', to: 'node-3', label: 'Exploits CVE-2023-5678' },
            { from: 'node-3', to: 'node-4', label: 'Has read access' },
        ]
    }
];

export const SERVICE_TEMPLATES_DATA: ServiceTemplate[] = [
    { id: 'tmpl-omni-agent', name: 'Omni Agent', description: 'Universal lightweight endpoint agent with EDR, FIM, and Log capabilities.', type: 'Service', tags: ['Security', 'Observability', 'Agent'], icon: 'ServerIcon', version: '2.5.0', category: 'Core Infrastructure' },
    { id: 'tmpl-compliance-scanner', name: 'Compliance Scanner - CIS', description: 'Automated CIS Benchmark scanning container.', type: 'Container', tags: ['Compliance', 'Audit'], icon: 'ShieldIcon', version: '1.2.0', category: 'Compliance' },
    { id: 'tmpl-vuln-scanner', name: 'Next-Gen Vulnerability Scanner', description: 'Agentless vulnerability assessment for cloud workloads.', type: 'Service', tags: ['Security', 'Vulnerability'], icon: 'SearchIcon', version: '4.0.0', category: 'Security Tools' },
    { id: 'tmpl-ai-guardian', name: 'AI Safety Guardian', description: 'LLM firewall for intercepting prompt injections and PII leakage.', type: 'Service', tags: ['AI Safety', 'Security'], icon: 'CpuIcon', version: '0.9.5', category: 'AI Governance' },
    { id: 'tmpl-log-collector', name: 'Centralized Log Aggregator', description: 'High-throughput log forwarder (Fluentd based).', type: 'Service', tags: ['Observability', 'Logs'], icon: 'DatabaseIcon', version: '1.8.1', category: 'Observability' },
    { id: 'tmpl-finops-exporter', name: 'FinOps Cost Exporter', description: 'Exports cloud usage data to central FinOps dashboard.', type: 'Service', tags: ['FinOps', 'Cost'], icon: 'DollarSignIcon', version: '1.0.0', category: 'Management' },
    { id: 'tmpl-incident-response', name: 'Automated Incident Response', description: 'SOAR playbook runner for auto-remediation.', type: 'Service', tags: ['Security', 'Automation'], icon: 'ZapIcon', version: '2.1.0', category: 'Automation' },
    { id: 'tmpl-1', name: 'Go Microservice', description: 'A standardized Go template for building backend microservices with Gin.', type: 'Go Microservice', tags: ['backend', 'go', 'api'] },
    { id: 'tmpl-2', name: 'Python API', description: 'A FastAPI template for Python-based APIs with built-in observability.', type: 'Python API', tags: ['backend', 'python', 'ml'] },
    { id: 'tmpl-3', name: 'Node.js Web App', description: 'A Next.js template for building performant web applications.', type: 'Node.js Web App', tags: ['frontend', 'react', 'nodejs'] },
];


export const SERVICE_PRICING_DATA: { id: string, name: string, unit: string, price: number, category: string, description: string }[] = [
    // Management & Settings
    { id: 'price-sys-settings', name: 'System Settings', unit: 'included', price: 0, category: 'Management & Settings', description: 'Core system configuration and branding.' },
    { id: 'price-rbac', name: 'Role & Permission Management', unit: 'per_user_mo', price: 2.00, category: 'Management & Settings', description: 'Advanced RBAC with custom roles.' },
    { id: 'price-api-keys', name: 'API Key Management', unit: 'per_key_mo', price: 0.50, category: 'Management & Settings', description: 'Secure API key generation and rotation.' },
    { id: 'price-finops', name: 'FinOps & Billing', unit: 'percent_cloud_spend', price: 0.01, category: 'Management & Settings', description: 'Cloud cost analytics and optimization.' },
    { id: 'price-user-profile', name: 'User Profile', unit: 'included', price: 0, category: 'Management & Settings', description: 'Individual user profile settings.' },
    { id: 'price-tenant-mgmt', name: 'Tenant Management', unit: 'per_tenant_mo', price: 10.00, category: 'Management & Settings', description: 'Multi-tenancy and isolation management.' },
    { id: 'price-webhooks', name: 'Webhook Management', unit: 'per_million_events', price: 1.00, category: 'Management & Settings', description: 'Outbound event notifications.' },
    { id: 'price-data-warehouse', name: 'Data Warehouse', unit: 'per_gb_storage_mo', price: 0.50, category: 'Management & Settings', description: 'Long-term analytical storage.' },

    // Security & Compliance
    { id: 'price-sec-ops', name: 'Security Operations Center', unit: 'per_analyst_mo', price: 150.00, category: 'Security', description: 'Centralized dashboard for security monitoring.' },
    { id: 'price-case-mgmt', name: 'Manage Security Cases', unit: 'per_case', price: 5.00, category: 'Security', description: 'Incident case management and tracking.' },
    { id: 'price-soar', name: 'Manage SOAR Playbooks', unit: 'per_playbook_run', price: 0.50, category: 'Security', description: 'Automated incident response workflows.' },
    { id: 'price-threat-intel', name: 'Threat Intelligence Feed', unit: 'per_month', price: 500.00, category: 'Security', description: 'Premium threat feeds and enrichment.' },
    { id: 'price-cloud-sec', name: 'Cloud Security (CSPM)', unit: 'per_resource_mo', price: 0.05, category: 'Security', description: 'Cloud posture management and compliance.' },
    { id: 'price-patch-mgmt', name: 'Patch Management', unit: 'per_asset_mo', price: 3.00, category: 'Security', description: 'Vulnerability patching and reporting.' },
    { id: 'price-patch-deploy', name: 'Deploy Patches', unit: 'per_patch', price: 0.10, category: 'Security', description: 'Automated patch deployment actions.' },
    { id: 'price-threat-hunt', name: 'Threat Hunting', unit: 'per_query', price: 1.00, category: 'Security', description: 'Advanced query capabilities for threat hunting.' },
    { id: 'price-compliance', name: 'Compliance Management', unit: 'per_framework_mo', price: 200.00, category: 'Compliance', description: 'Management of compliance frameworks (SOC2, ISO, etc.).' },
    { id: 'price-evidence', name: 'Manage Compliance Evidence', unit: 'per_gb_mo', price: 1.00, category: 'Compliance', description: 'Secure storage for audit evidence.' },
    { id: 'price-audit-log', name: 'Audit Log Retention', unit: 'per_gb_mo', price: 0.50, category: 'Compliance', description: 'Long-term retention of system audit logs.' },

    // Observability
    { id: 'price-agent-fleet', name: 'Agent Fleet Management', unit: 'per_agent_mo', price: 5.00, category: 'Observability', description: 'Centralized agent control and health monitoring.' },
    { id: 'price-soft-hub', name: 'Software Deployment Hub', unit: 'per_deploy_job', price: 0.20, category: 'Observability', description: 'Bulk software installation and updates.' },
    { id: 'price-view-logs', name: 'View Agent Logs', unit: 'per_gb_ingest', price: 0.30, category: 'Observability', description: 'Real-time log streaming from agents.' },
    { id: 'price-remediation', name: 'Agent Remediation', unit: 'per_action', price: 1.00, category: 'Observability', description: 'Remote remediation actions on agents.' },
    { id: 'price-asset-mgmt', name: 'Asset Management', unit: 'per_asset_mo', price: 2.00, category: 'Observability', description: 'Hardware and software inventory tracking.' },
    { id: 'price-log-explorer', name: 'Log Explorer', unit: 'per_query_hour', price: 5.00, category: 'Observability', description: 'Advanced log search and visualization.' },
    { id: 'price-insights', name: 'Proactive Insights', unit: 'per_insight', price: 2.00, category: 'Observability', description: 'AI-driven system health insights.' },
    { id: 'price-dist-trace', name: 'Distributed Tracing', unit: 'per_million_spans', price: 10.00, category: 'Observability', description: 'End-to-end request tracing.' },
    { id: 'price-net-obs', name: 'Network Observability', unit: 'per_device_mo', price: 15.00, category: 'Observability', description: 'Network device monitoring and flow analysis.' },

    // AI Governance
    { id: 'price-ai-gov', name: 'AI Governance Platform', unit: 'per_model_mo', price: 100.00, category: 'AI Governance', description: 'Model registry and policy enforcement.' },
    { id: 'price-ai-risk', name: 'Manage AI Risks', unit: 'per_risk_assessment', price: 50.00, category: 'AI Governance', description: 'AI risk assessment and mitigation tracking.' },

    // Automation
    { id: 'price-auto-workflow', name: 'Automation Workflows', unit: 'per_workflow_mo', price: 20.00, category: 'Automation', description: 'Custom automation workflow builder.' },
    { id: 'price-manage-auto', name: 'Manage Automations', unit: 'included', price: 0, category: 'Automation', description: 'Management interface for automations.' },

    // Developer Tools
    { id: 'price-devsecops', name: 'DevSecOps Dashboard', unit: 'per_repo_mo', price: 10.00, category: 'Developer Tools', description: 'Pipeline security and vulnerability visibility.' },
    { id: 'price-dev-hub', name: 'Developer Hub (API Docs)', unit: 'included', price: 0, category: 'Developer Tools', description: 'Centralized API documentation and testing.' },

    // Advanced Platform
    { id: 'price-dspm', name: 'Data Security (DSPM)', unit: 'per_store_scanned', price: 25.00, category: 'Advanced', description: 'Data Store Posture Management and scanning.' },
    { id: 'price-attack-path', name: 'Attack Path Analysis', unit: 'per_asset_mo', price: 5.00, category: 'Advanced', description: 'Graph-based attack path visualization.' },
    { id: 'price-idp', name: 'Service Catalog (IDP)', unit: 'per_user_mo', price: 8.00, category: 'Advanced', description: 'Internal Developer Platform and Service Catalog.' },
    { id: 'price-dora', name: 'DORA Metrics', unit: 'per_team_mo', price: 50.00, category: 'Advanced', description: 'DevOps Research and Assessment metrics.' },
    { id: 'price-chaos', name: 'Chaos Engineering', unit: 'per_experiment', price: 10.00, category: 'Advanced', description: 'Controlled fault injection experiments.' },
];

export const PROVISIONED_SERVICES_DATA: ProvisionedService[] = [
    { id: 'svc-agent-fleet', templateId: 'tmpl-omni-agent', name: 'Primary Agent Fleet', owner: 'Platform Admin', provisionedAt: '2023-01-15T08:00:00Z', status: 'Active', endpoints: ['https://agent-gw.omni.ai'] },
    { id: 'svc-log-agg', templateId: 'tmpl-log-collector', name: 'Log Streamer', owner: 'Platform Admin', provisionedAt: '2023-02-10T14:30:00Z', status: 'Active', endpoints: ['https://logs.omni.ai/ingest'] },
    { id: 'svc-ai-guard', templateId: 'tmpl-ai-guardian', name: 'Prod AI Firewall', owner: 'Platform Admin', provisionedAt: '2023-05-20T09:15:00Z', status: 'Healthy', endpoints: ['https://ai-safety.omni.ai'] },
    { id: 'svc-1', templateId: 'tmpl-1', name: 'auth-service', owner: 'Alice Admin', provisionedAt: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString(), status: 'Running' },
    { id: 'svc-2', templateId: 'tmpl-2', name: 'recommendation-engine', owner: 'Charlie DevOps', provisionedAt: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString(), status: 'Running' },
];

export const DORA_METRICS_DATA: DoraMetrics[] = [
    { tenantId: 'tenant-acme-corp', date: 'May', deploymentFrequency: 2.5, leadTimeForChanges: 24, changeFailureRate: 5, meanTimeToRecovery: 4 },
    { tenantId: 'tenant-acme-corp', date: 'Jun', deploymentFrequency: 3.1, leadTimeForChanges: 20, changeFailureRate: 4, meanTimeToRecovery: 3.5 },
    { tenantId: 'tenant-acme-corp', date: 'Jul', deploymentFrequency: 4.0, leadTimeForChanges: 16, changeFailureRate: 3, meanTimeToRecovery: 2.8 },
    { tenantId: 'tenant-initech', date: 'Jul', deploymentFrequency: 1.0, leadTimeForChanges: 48, changeFailureRate: 10, meanTimeToRecovery: 8 },
];

export const CHAOS_EXPERIMENTS_DATA: ChaosExperiment[] = [
    { id: 'chaos-1', tenantId: 'tenant-acme-corp', name: 'DB Failover Test', type: 'Pod Failure', target: 'db-prod-01', status: 'Completed', lastRun: new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString() },
    { id: 'chaos-2', tenantId: 'tenant-acme-corp', name: 'API Latency Spike', type: 'Latency Injection', target: 'api-gateway', status: 'Scheduled', lastRun: new Date(Date.now() - 14 * 24 * 60 * 60 * 1000).toISOString() },
    { id: 'chaos-3', tenantId: 'tenant-initech', name: 'CPU Hog', type: 'CPU Hog', target: 'dev-box-01', status: 'Failed', lastRun: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString() },
];

export const BUSINESS_KPI_DATA: BusinessKpi[] = [
    { date: 'Jul 26', revenue: 12000, userSignups: 50, cpu: 14 },
    { date: 'Jul 27', revenue: 12500, userSignups: 55, cpu: 18 },
    { date: 'Jul 28', revenue: 11800, userSignups: 48, cpu: 15 },
    { date: 'Jul 29', revenue: 13000, userSignups: 60, cpu: 25 },
    { date: 'Jul 30', revenue: 13500, userSignups: 62, cpu: 28 },
    { date: 'Jul 31', revenue: 14000, userSignups: 65, cpu: 20 },
    { date: 'Aug 01', revenue: 13800, userSignups: 63, cpu: 22 },
];

export const PROACTIVE_INSIGHTS_DATA: ProactiveInsight[] = [
    { id: 'pred-1', type: 'PREDICTIVE_ALERT', title: 'Disk Space Exhaustion', summary: 'Predicted to reach 95% capacity in 3 days.', timestamp: new Date().toISOString(), severity: 'High', details: { entity: 'db-prod-01' } },
    { id: 'pred-2', type: 'PREDICTIVE_ALERT', title: 'API Latency SLA Breach', summary: 'High probability of SLA breach during peak hours tomorrow.', timestamp: new Date().toISOString(), severity: 'Medium', details: { entity: 'api-gateway' } },
    { id: 'anom-1', type: 'ANOMALY_DETECTION', title: 'Unusual Network Traffic', summary: 'Outbound traffic to a new geo-location detected, deviating from baseline.', timestamp: new Date(Date.now() - 1 * 60 * 60 * 1000).toISOString(), severity: 'Medium', details: { entity: 'web-server-03' } },
    { id: 'rca-1', type: 'ROOT_CAUSE_ANALYSIS', title: 'Root Cause Analysis: API Outage', summary: 'The outage was caused by a memory leak in the `auth-service` triggered by a recent deployment, leading to cascading failures in downstream services.', timestamp: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(), severity: 'High', details: { status: 'Completed' } }
];

export const SERVICE_MAP_DATA: ServiceMap = {
    nodes: [
        { id: 'api-gateway', requestCount: 12500, errorCount: 15, avgLatency: 55 },
        { id: 'auth-service', requestCount: 8300, errorCount: 5, avgLatency: 120 },
        { id: 'user-db', requestCount: 15000, errorCount: 1, avgLatency: 15 },
        { id: 'asset-service', requestCount: 4200, errorCount: 10, avgLatency: 80 },
    ],
    edges: [
        { from: 'api-gateway', to: 'auth-service', requestCount: 8300 },
        { from: 'api-gateway', to: 'asset-service', requestCount: 4200 },
        { from: 'auth-service', to: 'user-db', requestCount: 15000 },
    ]
};

const createTrace = (id: string, rootSpanName: string, error: boolean, timestamp: Date): Trace => {
    const rootSpan: TraceSpan = {
        id: `${id}-span-1`,
        name: rootSpanName,
        service: 'api-gateway',
        startTime: timestamp.getTime(),
        duration: 255,
        status: error ? 'ERROR' : 'OK',
        children: [
            {
                id: `${id}-span-2`,
                parentId: `${id}-span-1`,
                name: 'HTTP POST /auth',
                service: 'auth-service',
                startTime: timestamp.getTime() + 5,
                duration: 120,
                status: error ? 'ERROR' : 'OK',
                children: [
                    {
                        id: `${id}-span-3`,
                        parentId: `${id}-span-2`,
                        name: 'SELECT user',
                        service: 'user-db',
                        startTime: timestamp.getTime() + 10,
                        duration: 15,
                        status: 'OK',
                        children: [],
                    }
                ]
            }
        ]
    };
    return {
        id: id,
        rootSpan: rootSpan,
        totalDuration: 255,
        serviceCount: 3,
        errorCount: error ? 1 : 0,
        timestamp: timestamp.toISOString(),
    };
}

export const TRACES_DATA: Trace[] = [
    createTrace('trace-1', '/api/login', false, new Date(Date.now() - 5000)),
    createTrace('trace-2', '/api/users/me', true, new Date(Date.now() - 10000)),
    createTrace('trace-3', '/api/assets', false, new Date(Date.now() - 15000)),
];



export const THREAT_INTEL_FEED_DATA: ThreatIntelResult[] = [
    { id: 'tif-1', artifact: '1.2.3.4', artifactType: 'ip', source: 'VirusTotal', verdict: 'Malicious', detectionRatio: '15/92', scanDate: new Date(Date.now() - 1 * 60000).toISOString(), reportUrl: '#' },
    { id: 'tif-2', artifact: 'evil-domain.com', artifactType: 'domain', source: 'VirusTotal', verdict: 'Malicious', detectionRatio: '8/91', scanDate: new Date(Date.now() - 3 * 60000).toISOString(), reportUrl: '#' },
    { id: 'tif-3', artifact: '8.8.8.8', artifactType: 'ip', source: 'VirusTotal', verdict: 'Harmless', detectionRatio: '0/92', scanDate: new Date(Date.now() - 5 * 60000).toISOString(), reportUrl: '#' },
    { id: 'tif-4', artifact: 'd41d8cd98f00b204e9800998ecf8427e', artifactType: 'hash', source: 'VirusTotal', verdict: 'Harmless', detectionRatio: '0/89', scanDate: new Date(Date.now() - 8 * 60000).toISOString(), reportUrl: '#' },
    { id: 'tif-5', artifact: 'suspicious-site.net', artifactType: 'domain', source: 'VirusTotal', verdict: 'Suspicious', detectionRatio: '2/91', scanDate: new Date(Date.now() - 12 * 60000).toISOString(), reportUrl: '#' },
];

export const ASSET_COMPLIANCE_DATA: AssetCompliance[] = [
    {
        id: 'ac-1',
        assetId: 'asset-1',
        controlId: 'AC-1',
        status: 'Compliant',
        evidence: [{ id: 'ev-1', name: 'Access Control Policy.pdf', url: '#', date: '2023-11-01' }],
        lastUpdated: '2023-11-01'
    },
    {
        id: 'ac-2',
        assetId: 'asset-2',
        controlId: 'AC-1',
        status: 'Non-Compliant',
        evidence: [],
        lastUpdated: '2023-11-05'
    },
    {
        id: 'ac-3',
        assetId: 'asset-1',
        controlId: 'AC-2',
        status: 'Pending_Evidence',
        evidence: [],
        lastUpdated: '2023-11-02'
    },
    {
        id: 'ac-sri-1',
        assetId: 'asset-sri-1',
        controlId: 'soc2-cc6-1',
        status: 'Non-Compliant',
        evidence: [],
        lastUpdated: new Date().toISOString()
    }
];