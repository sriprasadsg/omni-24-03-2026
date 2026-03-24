from pydantic import BaseModel, Field
from typing import Any, Optional
from datetime import datetime

# Agent Models
class AgentHealthCheck(BaseModel):
    name: str
    status: str  # Pass, Fail
    message: str

class AgentHealth(BaseModel):
    overallStatus: str  # Healthy, Degraded, Unhealthy
    checks: list[AgentHealthCheck] = []

class Agent(BaseModel):
    id: str
    tenantId: str
    hostname: str
    platform: str
    version: str
    ipAddress: str
    status: str  # Online, Offline, Error
    meta: dict[str, Any] = {}
    health: AgentHealth
    lastSeen: str
    assetId: str | None = None
    createdAt: str | None = None
    updatedAt: str | None = None

# Asset Models
class DiskInfo(BaseModel):
    device: str
    total: str
    used: str
    usedPercent: float
    type: str
    fileSystem: str | None = None

class SoftwareInfo(BaseModel):
    name: str
    version: str
    installDate: str
    vendor: str | None = None

class CriticalFile(BaseModel):
    path: str
    status: str  # Matched, Mismatch
    lastModified: str
    checksum: str
    size: int | None = None

class SecurityFeatures(BaseModel):
    bitlockerEnabled: bool | None = None
    bitlockerStatus: str | None = None
    firewallEnabled: bool | None = None
    antivirusInstalled: bool | None = None
    antivirusName: str | None = None

class RAMDetails(BaseModel):
    total: str
    available: str
    used: str
    percent: float

class PatchStatus(BaseModel):
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0

class Asset(BaseModel):
    id: str
    tenantId: str
    hostname: str
    osName: str
    osVersion: str
    kernel: str
    ipAddress: str
    macAddress: str
    cpuModel: str
    cpuCores: int | None = None
    cpuThreads: int | None = None
    ram: str
    ramDetails: RAMDetails | None = None
    disks: list[DiskInfo] = []
    serialNumber: str
    installedSoftware: list[SoftwareInfo] = []
    criticalFiles: list[CriticalFile] = []
    securityFeatures: SecurityFeatures | None = None
    lastScanned: str
    patchStatus: PatchStatus = PatchStatus()
    vulnerabilities: list[str] = []  # List of vulnerability IDs
    agentStatus: str | None = None
    agentVersion: str | None = None
    agentCapabilities: list[str] = []
    createdAt: str | None = None
    updatedAt: str | None = None

# Vulnerability Model
class Vulnerability(BaseModel):
    id: str
    tenantId: str
    assetId: str
    cveId: str | None = None
    severity: str  # Critical, High, Medium, Low, Informational
    status: str  # Open, Patched, Risk Accepted
    affectedSoftware: str
    discoveredAt: str
    lastChecked: str | None = None

# Patch Model
class Patch(BaseModel):
    id: str
    tenantId: str
    cveId: str
    description: str
    severity: str
    status: str  # Pending, Deployed, Failed, Superseded
    affectedAssets: list[str] = []
    releaseDate: str
    deployedAt: str | None = None

# Security Event Model
class SecurityEventSource(BaseModel):
    ip: str | None = None
    hostname: str | None = None
    user: str | None = None

class SecurityEvent(BaseModel):
    id: str
    tenantId: str
    timestamp: str
    severity: str  # Critical, High, Medium, Low
    type: str
    description: str
    source: SecurityEventSource | None = None
    details: dict[str, Any] = {}
    status: str = "New" # New, Investigating, Resolved

# Security Case Model
class SecurityCase(BaseModel):
    id: str
    tenantId: str
    title: str
    description: str
    severity: str
    status: str # Open, In Progress, Closed
    assignee: str | None = None
    createdAt: str
    updatedAt: str
    relatedEvents: list[str] = [] # List of Security Event IDs
    artifacts: list[dict[str, Any]] = []

# Audit Log Model
class AuditLog(BaseModel):
    id: str
    tenantId: str
    timestamp: str
    userName: str
    action: str
    resourceType: str
    resourceId: str | None = None
    details: str | None = None
    ipAddress: str | None = None

# Tenant Model
class Tenant(BaseModel):
    id: str
    name: str
    subscriptionTier: str
    registrationKey: str | None = None
    enabledFeatures: list[str] = []
    apiKeys: list[dict[str, Any]] = []
    createdAt: str | None = None
    finOpsData: dict[str, Any] | None = None

# User Model
class User(BaseModel):
    id: str
    email: str
    name: str
    role: str
    tenantId: str
    avatar: str | None = None
    password: str | None = None # In real app, this should be hashed
    status: str = "Active"
    lastLogin: str | None = None

# Role Model
class Role(BaseModel):
    id: str
    name: str
    description: str
    permissions: list[str] = []
    isCustom: bool = False
    tenantId: str | None = None

# Playbook Model
class Playbook(BaseModel):
    id: str
    tenantId: str
    name: str
    description: str
    trigger: str
    steps: list[dict[str, Any]] = []
    isActive: bool = True
    lastRun: str | None = None

# Notification Model
class Notification(BaseModel):
    id: str
    tenantId: str
    title: str
    message: str
    type: str # info, warning, error, success
    timestamp: str
    read: bool = False
    link: str | None = None

# Cloud Account Model
class CloudAccount(BaseModel):
    id: str
    tenantId: str
    name: str
    provider: str # AWS, Azure, GCP
    accountId: str
    status: str # Connected, Error
    lastSync: str | None = None
    regions: list[str] = []

# Pricing Model
class ServicePricing(BaseModel):
    id: str  # e.g., "service_agent"
    name: str # e.g., "Managed Agent"
    unit: str # e.g., "per_agent_per_month"
    price: float # e.g., 5.00
    category: str # e.g., "Infrastructure", "Security"
    description: str | None = None


# AI Governance Models
class AiModelVersion(BaseModel):
    version: str
    createdAt: str
    createdBy: str
    status: str # Staging, Production, Archived
    artifacts: list[dict[str, Any]] = [] # e.g. {path: "s3://...", hash: "sha256..."}
    metrics: dict[str, Any] = {} # e.g. {accuracy: 0.95, latency: 20ms}
    trainingDataRef: str | None = None

class AiModel(BaseModel):
    id: str
    tenantId: str
    name: str
    description: str
    framework: str # PyTorch, TensorFlow, Sklearn
    type: str # LLM, Regression, Classification
    owner: str
    versions: list[AiModelVersion] = []
    currentVersion: str | None = None
    riskLevel: str = "Low" # Low, Medium, High, Critical
    createdAt: str
    updatedAt: str

class AiPolicyRule(BaseModel):
    id: str
    name: str
    condition: str # e.g. "metrics.accuracy < 0.9"
    action: str # e.g. "block_deployment", "notify_admin"
    params: dict[str, Any] = {}

class AiPolicy(BaseModel):
    id: str
    tenantId: str
    name: str
    description: str
    rules: list[AiPolicyRule] = []
    scope: dict[str, Any] = {} # e.g. {framework: "PyTorch"} - applies to specific models
    isActive: bool = True
    createdAt: str
    updatedAt: str

class SystemFeature(BaseModel):
    id: str  # Unique identifier, e.g., "view:dashboard"
    name: str # e.g. "Dashboard"
    category: str # e.g. "Main"
    key: str # permission key or internal ID
    description: str | None = None
    verificationStatus: str = "Active" # Active, Deprecated, Missing
    lastVerifiedAt: str # ISO timestamp
    metadata: dict[str, Any] = {} # Extra data like icon name, route path

# Remediation Model
class RemediationRequest(BaseModel):
    id: str | None = None
    tenantId: str
    assetId: str
    vulnerabilityId: str
    proposedAction: str # e.g. "update_package", "modify_config"
    scriptContent: str # PowerShell/Bash script
    status: str = "Pending" # Pending, Approved, Rejected, Executed, Failed
    executionLog: str | None = None
    createdAt: str
    updatedAt: str

