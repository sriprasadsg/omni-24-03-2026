"""
Agent Capabilities Module
"""
from .base import BaseCapability
from .metrics import MetricsCapability
from .logs import LogsCapability
from .fim import FIMCapability
from .real_scan import RealVulnerabilityScanningCapability as VulnerabilityScanningCapability
from .compliance import ComplianceEnforcementCapability
from .runtime_security import RuntimeSecurityCapability
from .predictive_health import PredictiveHealthCapability
from .ueba import UEBACapability
from .sbom import SBOMAnalysisCapability
from .ebpf import eBPFTracingCapability
from .system_patching import SystemPatchingCapability
from .software_management import SoftwareManagementCapability
from .remote_access import RemoteAccessCapability
from .network_discovery import NetworkDiscoveryCapability
from .update_capability import AgentUpdateCapability
from .patch_installer import PatchInstallerCapability
from .process_injection_simulation import ProcessInjectionSimulationCapability
from .persistence_detection import PersistenceDetectionCapability
from .remediation import RemediationCapability
from .real_fim import RealTimeFIMCapability
from .shadow_ai import ShadowAICapability
from .pii_scanner import PIIScannerCapability
from .cloud_metadata import CloudMetadataCapability
from .web_monitor import WebMonitorCapability
from .vss_manager import VSSManagerCapability
from .autonomous_response import AutonomousResponseCapability
from .edr_realtime import EDRRealtimeCapability
from .process_monitor import ProcessMonitorCapability
from .log_shipper import LogShipperCapability
from .compliance_evidence_collector import ComplianceEvidenceCollectorCapability
from .vendor_risk import VendorRiskCapability
from .backup_verifier import BackupVerifierCapability
from .deception_monitor import DeceptionMonitorCapability
from .threat_intel import ThreatIntelCapability
from .ticket_reporter import TicketReporterCapability
from .chat_window import ChatWindowCapability
from .virustotal_scan import VirusTotalScanCapability # ADDED

# CISSP analysis is a standalone function module (no BaseCapability subclass needed)

__all__ = [
    'BaseCapability',
    'MetricsCapability',
    'LogsCapability',
    'FIMCapability',
    'VulnerabilityScanningCapability',
    'ComplianceEnforcementCapability',
    'RuntimeSecurityCapability',
    'PredictiveHealthCapability',
    'UEBACapability',
    'SBOMAnalysisCapability',
    'eBPFTracingCapability',
    'SystemPatchingCapability',
    'SoftwareManagementCapability',
    'RemoteAccessCapability',
    'AgentUpdateCapability',
    'PatchInstallerCapability',
    'ProcessInjectionSimulationCapability',
    'PersistenceDetectionCapability',
    'RemediationCapability',
    'RealTimeFIMCapability',
    'ShadowAICapability',
    'PIIScannerCapability',
    'CloudMetadataCapability',
    'WebMonitorCapability',
    'VSSManagerCapability',
    'AutonomousResponseCapability',
    'EDRRealtimeCapability',
    'ProcessMonitorCapability',
    'LogShipperCapability',
    'ComplianceEvidenceCollectorCapability',
    'VendorRiskCapability',
    'BackupVerifierCapability',
    'DeceptionMonitorCapability',
    'ThreatIntelCapability',
    'TicketReporterCapability',
    'ChatWindowCapability',
    'VirusTotalScanCapability', # ADDED
]

# Capability registry mapping IDs to classes
CAPABILITY_REGISTRY = {
    'metrics_collection':           MetricsCapability,
    'log_collection':               LogsCapability,
    'fim':                          FIMCapability,
    'vulnerability_scanning':       VulnerabilityScanningCapability,
    'compliance_enforcement':       ComplianceEnforcementCapability,
    'runtime_security':             RuntimeSecurityCapability,
    'predictive_health':            PredictiveHealthCapability,
    'ueba':                         UEBACapability,
    'sbom_analysis':                SBOMAnalysisCapability,
    'ebpf_tracing':                 eBPFTracingCapability,
    'system_patching':              SystemPatchingCapability,
    'software_management':          SoftwareManagementCapability,
    'remote_access':                RemoteAccessCapability,
    'network_discovery':            NetworkDiscoveryCapability,
    'agent_update':                 AgentUpdateCapability,
    'patch_installer':              PatchInstallerCapability,
    'process_injection_simulation': ProcessInjectionSimulationCapability,
    'persistence_detection':        PersistenceDetectionCapability,
    'remediation_executor':         RemediationCapability,
    'real_time_fim':                RealTimeFIMCapability,
    'shadow_ai':                    ShadowAICapability,
    'pii_scanner':                  PIIScannerCapability,
    'cloud_metadata':               CloudMetadataCapability,
    'web_monitor':                  WebMonitorCapability,
    'vss_manager':                  VSSManagerCapability,
    'autonomous_response':          AutonomousResponseCapability,
    'edr_realtime':                 EDRRealtimeCapability,
    'process_monitor':              ProcessMonitorCapability,
    'log_shipper':                       LogShipperCapability,
    'compliance_evidence_collector':     ComplianceEvidenceCollectorCapability,
    'vendor_risk':                       VendorRiskCapability,
    'backup_verifier':                   BackupVerifierCapability,
    'deception_monitor':                 DeceptionMonitorCapability,
    'threat_intel':                      ThreatIntelCapability,
    'ticket_reporter':                   TicketReporterCapability,
    'chat_window':                       ChatWindowCapability,
    'virustotal_scan':                 VirusTotalScanCapability, # ADDED
}
