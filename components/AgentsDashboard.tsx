import React, { useState, useMemo, useRef, useEffect } from 'react';
import { AgentList } from './AgentList';
import { ServerIcon, ZapIcon, CheckIcon, AlertTriangleIcon, CogIcon, PlusCircleIcon, XCircleIcon } from './icons';
import { Agent, AgenticStep, LogEntry, Asset, AgentUpgradeJob, Filter, Tenant } from '../types';
import { AgentLogsModal } from './AgentLogsModal';
import { AgentInstallation } from './AgentInstallation';
import { generateAgenticPlan, runAgentDiagnostics } from '../services/apiService';
import { AutonomousOpsLog } from './AutonomousOpsLog';
import { useUser } from '@/contexts/UserContext';
import { AgentDetailModal } from './AgentDetailModal';
import { RemediationLogsModal } from './RemediationLogsModal';
import { RemediationConfirmationModal } from './RemediationConfirmationModal';
import { AgentUpgradeManager } from './AgentUpgradeManager';
import { ManageAgentCapabilitiesModal } from './ManageAgentCapabilitiesModal';
import AgentRemoteControl from './AgentRemoteControl';
import { UpgradeModal } from './UpgradeModal';
import { fetchKpiSummary } from '../services/apiService';

interface AgentsDashboardProps {
  agents: Agent[];
  assets: Asset[];
  logs: LogEntry[];
  registrationKey: string | null;
  onRegisterAgent: () => void;
  onUpdateAgent: (agent: Agent) => void;
  agentUpgradeJobs: AgentUpgradeJob[];
  onScheduleUpgrade: (agentIds: string[], targetVersion: string) => void;
  filters: Filter[];
  onClearFilters: () => void;
  tenants?: Tenant[];
  onSelectTenant?: (tenantId: string) => void;
  onDeleteAgent?: (agent: Agent) => void;
  activeTenantId?: string | null;
  subscriptionTier?: string;
}

const isRemediationRateLimited = (agent: Agent): boolean => {
  const now = new Date().getTime();
  const oneHourAgo = now - 60 * 60 * 1000;
  const recentAttempts = (agent.remediationAttempts || []).filter(
    attempt => new Date(attempt.timestamp).getTime() > oneHourAgo
  );
  return recentAttempts.length >= 3;
};

export const AgentsDashboard: React.FC<AgentsDashboardProps> = ({ agents, assets, logs, registrationKey, onRegisterAgent, onUpdateAgent, agentUpgradeJobs, onScheduleUpgrade, filters, onClearFilters, tenants, onSelectTenant, onDeleteAgent, activeTenantId, subscriptionTier = 'Free' }) => {
  const { hasPermission } = useUser();
  const canRemediate = hasPermission('remediate:agents');

  const FREE_TIER_AGENT_LIMIT = 5;
  const isFreeTier = subscriptionTier === 'Free' || subscriptionTier === 'free';
  const [showUpgradeModal, setShowUpgradeModal] = useState(false);

  // Guard: show upgrade modal if Free tier is at agent limit
  const handleRegisterAgentGuarded = () => {
    if (isFreeTier && agents.length >= FREE_TIER_AGENT_LIMIT) {
      setShowUpgradeModal(true);
    } else {
      onRegisterAgent();
    }
  };

  const [viewingAgentLogs, setViewingAgentLogs] = useState<Agent | null>(null);
  const [viewingAgentDetails, setViewingAgentDetails] = useState<Agent | null>(null);
  const [selectedAgentIds, setSelectedAgentIds] = useState<Set<string>>(new Set());
  const [viewingRemediationLogsForAgent, setViewingRemediationLogsForAgent] = useState<Agent | null>(null);
  const [agentsToConfirmRemediation, setAgentsToConfirmRemediation] = useState<Agent[]>([]);
  const [managingCapabilitiesFor, setManagingCapabilitiesFor] = useState<Agent | null>(null);
  const [remoteControlAgent, setRemoteControlAgent] = useState<Agent | null>(null);

  const upgradeManagerRef = useRef<HTMLDivElement>(null);

  const [autonomousRun, setAutonomousRun] = useState<{
    status: 'idle' | 'running' | 'completed' | 'failed';
    steps: AgenticStep[];
    targetAgent: Agent | null;
  }>({ status: 'idle', steps: [], targetAgent: null });

  const [totalAgentsCount, setTotalAgentsCount] = useState<number | null>(null);
  const [onlineAgentsCount, setOnlineAgentsCount] = useState<number | null>(null);
  const [totalAssetsCount, setTotalAssetsCount] = useState<number | null>(null);
  const [isLoadingSummary, setIsLoadingSummary] = useState(false);

  useEffect(() => {
    const loadSummary = async () => {
      if (!activeTenantId) return;
      setIsLoadingSummary(true);
      try {
        const summary = await fetchKpiSummary(activeTenantId);
        if (summary) {
          setTotalAgentsCount(summary.total_agents);
          setOnlineAgentsCount(summary.online_agents);
          setTotalAssetsCount(summary.total_assets);
        }
      } catch (err) {
        console.error("Failed to fetch agent summary:", err);
      } finally {
        setIsLoadingSummary(false);
      }
    };

    loadSummary();
  }, [activeTenantId]);

  const onlineAgents = onlineAgentsCount ?? agents.filter(a => a.status === 'Online').length;
  const offlineAgents = (totalAgentsCount && onlineAgentsCount !== null)
    ? (totalAgentsCount - onlineAgentsCount)
    : agents.filter(a => a.status === 'Offline').length;
  const errorAgent = useMemo(() => agents.find(a => a.status === 'Error'), [agents]);

  const agentLogs = useMemo(() => {
    if (!viewingAgentLogs) return [];
    return logs.filter(log => {
      // Prefer agentId match if available, generic hostname match as fallback
      if (log.agentId && viewingAgentLogs.id) {
        return log.agentId === viewingAgentLogs.id;
      }
      return log.hostname === viewingAgentLogs.hostname;
    });
  }, [viewingAgentLogs, logs]);

  const upgradingAgentIds = useMemo(() => {
    const inProgressJobs = agentUpgradeJobs.filter(j => j.status === 'In Progress');
    const ids = new Set<string>();
    inProgressJobs.forEach(job => {
      job.agentIds.forEach(id => ids.add(id));
    });
    return ids;
  }, [agentUpgradeJobs]);

  const viewingAgentAsset = useMemo(() => {
    if (!viewingAgentDetails) return undefined;
    return assets.find(a => a.id === viewingAgentDetails.assetId);
  }, [viewingAgentDetails, assets]);

  const handleToggleSelection = (agentId: string) => {
    setSelectedAgentIds(prev => {
      const newSet = new Set(prev);
      if (newSet.has(agentId)) {
        newSet.delete(agentId);
      } else {
        newSet.add(agentId);
      }
      return newSet;
    });
  };

  const handleSelectAll = (filteredAgentIds: string[]) => {
    const allSelected = filteredAgentIds.length > 0 && filteredAgentIds.every(id => selectedAgentIds.has(id));
    if (allSelected) {
      setSelectedAgentIds(new Set());
    } else {
      setSelectedAgentIds(new Set(filteredAgentIds));
    }
  };


  const handleRestartAgent = (agent: Agent) => {
    if (window.confirm(`Are you sure you want to restart the agent on ${agent.hostname}?`)) {
      console.log(`Restart command issued for agent on: ${agent.hostname}`);
    }
  };

  const handleViewLogs = (agent: Agent) => {
    setViewingAgentLogs(agent);
  };

  const handleRunDiagnostics = async (agent: Agent) => {
    const confirmed = window.confirm(`Run diagnostics on ${agent.hostname}? This will check connectivity and service health.`);
    if (!confirmed) return;

    try {
      const updatedAgent = await runAgentDiagnostics(agent.id);
      onUpdateAgent(updatedAgent); // Sync with parent state
      alert(`Diagnostics completed for ${agent.hostname}.\nStatus: ${updatedAgent.health.overallStatus}`);
    } catch (e) {
      alert('Diagnostics failed to run.');
    }
  };

  const startRemediation = async (agent: Agent) => {
    // Check rate limit
    if (isRemediationRateLimited(agent)) {
      alert(`Remediation limit reached for ${agent.hostname}. Please try again later.`);
      return;
    }

    // Add a new attempt timestamp
    const updatedAgent = {
      ...agent,
      remediationAttempts: [...(agent.remediationAttempts || []), { timestamp: new Date().toISOString() }]
    };
    onUpdateAgent(updatedAgent);


    setAutonomousRun({
      status: 'running',
      steps: [],
      targetAgent: agent
    });
    try {
      for await (const step of generateAgenticPlan(agent)) {
        setAutonomousRun(prev => ({
          ...prev,
          steps: [...prev.steps, step]
        }));
      }
      setAutonomousRun(prev => ({ ...prev, status: 'completed' }));
    } catch (e) {
      const errorStep: AgenticStep = { type: 'observation', content: `Remediation failed: ${e instanceof Error ? e.message : 'Unknown error'}`, timestamp: new Date().toISOString() };
      setAutonomousRun(prev => ({ ...prev, status: 'failed', steps: [...prev.steps, errorStep] }));
    }
  };

  const handleAuthorizeRemediation = (agent: Agent) => {
    if (!canRemediate) {
      alert("You don't have permission to perform this action.");
      return;
    }
    if (isRemediationRateLimited(agent)) {
      alert(`Remediation limit reached for ${agent.hostname}. Please try again later.`);
      return;
    }
    setAgentsToConfirmRemediation([agent]);
  };

  const handleConfirmRemediation = () => {
    if (agentsToConfirmRemediation.length > 0) {
      // Always remediate the first agent in the list to show a single log stream
      startRemediation(agentsToConfirmRemediation[0]);
    }
    setAgentsToConfirmRemediation([]);
    setSelectedAgentIds(new Set());
  };

  const handleBulkRestart = () => {
    if (window.confirm(`Are you sure you want to restart ${selectedAgentIds.size} selected agent(s)?`)) {
      console.log(`Restarting agents:`, Array.from(selectedAgentIds));
      alert(`Restart command issued for ${selectedAgentIds.size} agent(s).`);
      setSelectedAgentIds(new Set());
    }
  };

  const handleBulkDiagnostics = async () => {
    if (selectedAgentIds.size === 0) return;

    const confirmed = window.confirm(`Run diagnostics on ${selectedAgentIds.size} selected agent(s)?`);
    if (!confirmed) return;

    try {
      const updatedAgents = await Promise.all(Array.from(selectedAgentIds).map((id: string) => runAgentDiagnostics(id)));
      updatedAgents.forEach(agent => onUpdateAgent(agent)); // Sync with parent state
      alert(`Diagnostics completed for ${updatedAgents.length} agents.`);
      setSelectedAgentIds(new Set());
    } catch (e: unknown) {
      const errorMessage = e instanceof Error ? e.message : 'Unknown error';
      alert(`Bulk diagnostics failed: ${errorMessage}`);
    }
  };

  const handleBulkRemediate = () => {
    const agentsToFix = agents.filter(agent => selectedAgentIds.has(agent.id) && agent.status === 'Error');
    if (agentsToFix.length > 0) {
      setAgentsToConfirmRemediation(agentsToFix);
    }
  };

  const handleScheduleUpgrade = (agentIds: string[], targetVersion: string) => {
    onScheduleUpgrade(agentIds, targetVersion);
    setSelectedAgentIds(new Set()); // Clear selection after starting job
    setTimeout(() => {
      upgradeManagerRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, 500);
  };

  const handleOpenManageCapabilities = (agent: Agent) => {
    setViewingAgentDetails(null);
    setManagingCapabilitiesFor(agent);
  };

  const handleSaveCapabilities = (updatedAgent: Agent) => {
    onUpdateAgent(updatedAgent);
    setManagingCapabilitiesFor(null);
  };

  const isErrorAgentRateLimited = errorAgent ? isRemediationRateLimited(errorAgent) : false;

  return (
    <div className="container mx-auto">
      <h2 className="text-2xl font-semibold text-gray-800 dark:text-white mb-2">Agent Fleet Management</h2>
      <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">Monitor the status and health of all deployed Omni-Agents.</p>

      {/* Stats Cards */}
      {/* Stats Cards - Flash UI Style */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4 md:gap-6 mb-6">
        {/* Total Agents */}
        <div className="glass rounded-2xl p-6 flex items-center justify-between transition-all duration-300 transform hover:scale-[1.03] hover:shadow-[0_0_20px_rgba(0,210,255,0.3)] hover:border-primary-400 group cursor-pointer">
          <div className="flex items-center">
            <div className="mr-4 p-3 rounded-2xl bg-primary-50 dark:bg-primary-900/30 text-primary-600 dark:text-primary-400 transition-transform duration-300 group-hover:rotate-12">
              <ServerIcon size={24} />
            </div>
            <div>
              <p className="text-xs font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-1">Total Agents</p>
              <p className="text-3xl font-extrabold text-gray-900 dark:text-white tracking-tight">
                {isLoadingSummary ? '...' : (totalAgentsCount ?? agents.length)}
              </p>
            </div>
          </div>
        </div>

        {/* Online */}
        <div className="glass rounded-2xl p-6 flex items-center justify-between transition-all duration-300 transform hover:scale-[1.03] hover:shadow-[0_0_20px_rgba(34,197,94,0.3)] hover:border-green-400 group cursor-pointer">
          <div className="flex items-center">
            <div className="mr-4 p-3 rounded-2xl bg-green-50 dark:bg-green-900/30 text-green-600 dark:text-green-400 transition-transform duration-300 group-hover:rotate-12">
              <CheckIcon size={24} />
            </div>
            <div>
              <p className="text-xs font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-1">Online</p>
              <p className="text-3xl font-extrabold text-gray-900 dark:text-white tracking-tight">
                {isLoadingSummary ? '...' : onlineAgents}
              </p>
            </div>
          </div>
        </div>

        {/* Offline */}
        <div className="glass rounded-2xl p-6 flex items-center justify-between transition-all duration-300 transform hover:scale-[1.03] hover:shadow-[0_0_20px_rgba(107,114,128,0.3)] hover:border-gray-400 group cursor-pointer">
          <div className="flex items-center">
            <div className="mr-4 p-3 rounded-2xl bg-gray-50 dark:bg-gray-800 text-gray-500 dark:text-gray-400 transition-transform duration-300 group-hover:rotate-12">
              <XCircleIcon size={24} />
            </div>
            <div>
              <p className="text-xs font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-1">Offline</p>
              <p className="text-3xl font-extrabold text-gray-900 dark:text-white tracking-tight">
                {isLoadingSummary ? '...' : offlineAgents}
              </p>
            </div>
          </div>
        </div>

        {/* Errors */}
        <div className="glass rounded-2xl p-6 flex items-center justify-between transition-all duration-300 transform hover:scale-[1.03] hover:shadow-[0_0_20px_rgba(239,68,68,0.3)] hover:border-red-400 group cursor-pointer">
          <div className="flex items-center">
            <div className="mr-4 p-3 rounded-2xl bg-red-50 dark:bg-red-900/30 text-red-600 dark:text-red-400 transition-transform duration-300 group-hover:rotate-12">
              <AlertTriangleIcon size={24} />
            </div>
            <div>
              <p className="text-xs font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-1">Errors</p>
              <p className="text-3xl font-extrabold text-gray-900 dark:text-white tracking-tight">{errorAgent ? agents.filter(a => a.status === 'Error').length : 0}</p>
            </div>
          </div>
        </div>

        {/* Avg Uptime */}
        <div className="glass rounded-2xl p-6 flex items-center justify-between transition-all duration-300 transform hover:scale-[1.03] hover:shadow-[0_0_20px_rgba(59,130,246,0.3)] hover:border-blue-400 group cursor-pointer">
          <div className="flex items-center">
            <div className="mr-4 p-3 rounded-2xl bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 transition-transform duration-300 group-hover:rotate-12">
              <ZapIcon size={24} />
            </div>
            <div>
              <p className="text-xs font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-1">Avg Uptime</p>
              <p className="text-3xl font-extrabold text-gray-900 dark:text-white tracking-tight">99.8%</p>
            </div>
          </div>
        </div>
      </div>

      {/* Banner - Flash Style */}
      <div className="mb-6 glass border-l-4 border-l-amber-500 p-4 flex items-start bg-amber-50/10 rounded-r-lg">
        <AlertTriangleIcon className="text-amber-500 mt-0.5 mr-3 flex-shrink-0" size={20} />
        <p className="text-sm text-gray-800 dark:text-gray-200">
          <span className="font-semibold text-amber-600 dark:text-amber-400">Installation Unavailable.</span> Please select a tenant to view agent installation commands. Super Admins must select 'View Tenant' from the Tenant Management dashboard.
        </p>
      </div>

      {filters.length > 0 && (
        <div className="mb-4 p-3 bg-primary-50 dark:bg-primary-900/50 rounded-lg flex items-center justify-between border border-primary-200 dark:border-primary-800">
          <div className="flex items-center space-x-2">
            <span className="font-semibold text-sm text-primary-800 dark:text-primary-200">Active AI Filter:</span>
            {filters.map((filter, index) => (
              <span key={index} className="px-2 py-1 text-xs font-medium rounded-full bg-primary-100 text-primary-700 dark:bg-primary-900 dark:text-primary-200">
                {filter.type}: <strong>{filter.value}</strong>
              </span>
            ))}
          </div>
          <button onClick={onClearFilters} className="flex items-center text-xs font-medium text-primary-600 hover:text-primary-800">
            <XCircleIcon size={14} className="mr-1" />
            Clear Filter
          </button>
        </div>
      )}

      {/* Autonomous Operations Section */}
      {(errorAgent || autonomousRun.status !== 'idle') && (
        <div className="mb-6 bg-white dark:bg-gray-800 rounded-lg shadow-md">
          <div className="p-4 border-b border-gray-200 dark:border-gray-700">
            <h3 className="text-lg font-semibold flex items-center">
              <ZapIcon className="mr-2 text-primary-500" />
              Autonomous Operations
            </h3>
          </div>
          <div className="p-4">
            {autonomousRun.status === 'idle' && errorAgent ? (
              <div className="flex flex-col md:flex-row items-center justify-between gap-4">
                <div className="flex items-start">
                  <AlertTriangleIcon className="text-red-500 mr-3 mt-1 flex-shrink-0" size={20} />
                  <div>
                    <p className="font-semibold text-gray-800 dark:text-gray-200">Action Required: Agent in Error State</p>
                    <p className="text-sm text-gray-500 dark:text-gray-400">The agent on <span className="font-medium text-red-600 dark:text-red-400">{errorAgent.hostname}</span> is reporting an error. You can authorize the Omni-Agent AI to attempt an autonomous remediation.</p>
                  </div>
                </div>
                <button
                  onClick={() => handleAuthorizeRemediation(errorAgent)}
                  disabled={!canRemediate || isErrorAgentRateLimited}
                  title={!canRemediate ? "You do not have permission to perform this action" : isErrorAgentRateLimited ? "Remediation limit reached (3/hr). Try again later." : "Authorize Autonomous Remediation"}
                  className="w-full md:w-auto flex-shrink-0 flex items-center justify-center px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
                >
                  Authorize Autonomous Remediation
                </button>
              </div>
            ) : (
              <div>
                <div className="flex justify-between items-center mb-4">
                  <p className="font-semibold">Remediation Log for: <span className="font-mono text-primary-600 dark:text-primary-400 text-xs">{autonomousRun.targetAgent?.hostname}</span></p>
                  {autonomousRun.status === 'running' && <span className="flex items-center text-sm font-medium text-amber-600 dark:text-amber-400"><CogIcon size={16} className="animate-spin mr-2" />Running...</span>}
                  {autonomousRun.status === 'completed' && <span className="flex items-center text-sm font-medium text-green-600 dark:text-green-400"><CheckIcon size={16} className="mr-2" />Completed</span>}
                  {autonomousRun.status === 'failed' && <span className="flex items-center text-sm font-medium text-red-600 dark:text-red-400"><AlertTriangleIcon size={16} className="mr-2" />Failed</span>}
                </div>
                <AutonomousOpsLog steps={autonomousRun.steps} />
              </div>
            )}
          </div>
        </div>
      )}

      {/* Agent Installation Section */}
      <div id="agent-installation-section" className="mb-6">
        <AgentInstallation registrationKey={registrationKey} tenantId={activeTenantId} tenants={tenants} onSelectTenant={onSelectTenant} />
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md">
        <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex justify-between items-center">
          <h3 className="text-lg font-semibold flex items-center">
            <ServerIcon className="mr-2 text-primary-500" />
            Registered Agents
            {/* Free tier usage badge */}
            {isFreeTier && (
              <span className={`ml-3 px-2.5 py-0.5 text-xs font-bold rounded-full ${agents.length >= FREE_TIER_AGENT_LIMIT
                ? 'bg-red-100 dark:bg-red-900/50 text-red-700 dark:text-red-400'
                : agents.length >= FREE_TIER_AGENT_LIMIT - 1
                  ? 'bg-amber-100 dark:bg-amber-900/50 text-amber-700 dark:text-amber-400'
                  : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300'
                }`}>
                {agents.length} / {FREE_TIER_AGENT_LIMIT} agents · Free
              </span>
            )}
          </h3>
          {canRemediate && (
            <button
              onClick={handleRegisterAgentGuarded}
              className={`flex items-center px-3 py-1.5 text-xs font-medium text-white rounded-lg focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 ${isFreeTier && agents.length >= FREE_TIER_AGENT_LIMIT
                ? 'bg-amber-500 hover:bg-amber-600'
                : 'bg-primary-600 hover:bg-primary-700'
                }`}
              title={isFreeTier && agents.length >= FREE_TIER_AGENT_LIMIT ? 'Upgrade to add more agents' : 'Register a new agent'}
            >
              <PlusCircleIcon size={16} className="mr-1.5" />
              {isFreeTier && agents.length >= FREE_TIER_AGENT_LIMIT ? '⚡ Upgrade to Add More' : 'Register Agent'}
            </button>
          )}
        </div>
        <AgentList
          agents={agents}
          assets={assets}
          selectedAgentIds={selectedAgentIds}
          upgradingAgentIds={upgradingAgentIds}
          onToggleSelection={handleToggleSelection}
          onSelectAll={handleSelectAll}
          onRestartAgent={handleRestartAgent}
          onViewLogs={handleViewLogs}
          onRunDiagnostics={handleRunDiagnostics}
          onViewDetails={setViewingAgentDetails}
          onAuthorizeRemediation={handleAuthorizeRemediation}
          onViewRemediationLogs={setViewingRemediationLogsForAgent}
          onBulkRestart={handleBulkRestart}
          onBulkDiagnostics={handleBulkDiagnostics}
          onBulkRemediate={handleBulkRemediate}
          onUpdateAgent={onUpdateAgent}
          onRegisterAgent={onRegisterAgent}
          onRemoteControl={setRemoteControlAgent}
          onDeleteAgent={onDeleteAgent}
          filters={filters}
        />
      </div>

      <div className="mt-6">
        <AgentUpgradeManager
          agents={agents}
          selectedAgentIds={selectedAgentIds}
          jobs={agentUpgradeJobs}
          onScheduleUpgrade={handleScheduleUpgrade}
          managerRef={upgradeManagerRef}
        />
      </div>

      <AgentLogsModal
        isOpen={!!viewingAgentLogs}
        onClose={() => setViewingAgentLogs(null)}
        agent={viewingAgentLogs}
        logs={agentLogs}
      />
      <AgentDetailModal
        isOpen={!!viewingAgentDetails}
        onClose={() => setViewingAgentDetails(null)}
        agent={viewingAgentDetails}
        asset={viewingAgentAsset}
        onManageCapabilities={handleOpenManageCapabilities}
        onViewRemediationLogs={(agentForLogs) => {
          setViewingAgentDetails(null);
          setViewingRemediationLogsForAgent(agentForLogs);
        }}
        onViewLogs={(agentForLogs) => {
          setViewingAgentDetails(null);
          setViewingAgentLogs(agentForLogs);
        }}
        onRunDiagnostics={handleRunDiagnostics}
        onDeleteAgent={onDeleteAgent}
      />
      <RemediationLogsModal
        isOpen={!!viewingRemediationLogsForAgent}
        onClose={() => setViewingRemediationLogsForAgent(null)}
        agent={viewingRemediationLogsForAgent}
      />
      <RemediationConfirmationModal
        isOpen={agentsToConfirmRemediation.length > 0}
        onClose={() => setAgentsToConfirmRemediation([])}
        onConfirm={handleConfirmRemediation}
        agentsToRemediate={agentsToConfirmRemediation}
      />
      <ManageAgentCapabilitiesModal
        isOpen={!!managingCapabilitiesFor}
        onClose={() => setManagingCapabilitiesFor(null)}
        agent={managingCapabilitiesFor}
        onSave={handleSaveCapabilities}
      />
      {remoteControlAgent && (
        <AgentRemoteControl
          agent={remoteControlAgent}
          onClose={() => setRemoteControlAgent(null)}
        />
      )}

      {/* Free Tier Upgrade Modal */}
      <UpgradeModal
        isOpen={showUpgradeModal}
        onClose={() => setShowUpgradeModal(false)}
        agentCount={agents.length}
        agentLimit={FREE_TIER_AGENT_LIMIT}
        subscriptionTier={subscriptionTier}
      />
    </div>
  );
};
