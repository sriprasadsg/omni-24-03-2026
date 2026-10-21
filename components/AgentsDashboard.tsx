import React, { useState, useMemo, useRef, useEffect } from 'react';
import { AgentList, effectiveAgentStatus } from './AgentList';
import { ServerIcon, ZapIcon, CheckIcon, AlertTriangleIcon, CogIcon, PlusCircleIcon, XCircleIcon, DownloadIcon } from './icons';
import { StatTile, bigNumber } from './StatTile';
import { Agent, AgenticStep, LogEntry, Asset, AgentUpgradeJob, Filter, Tenant } from '../types';
import { AgentLogsModal } from './AgentLogsModal';
import { AgentInstallation } from './AgentInstallation';
import { generateAgenticPlan, runAgentDiagnostics, deleteAgent, quarantineAgent, setAgentSoftwareExclusion, fetchAgents } from '../services/apiService';
import { AutonomousOpsLog } from './AutonomousOpsLog';
import { useUser } from '@/contexts/UserContext';
import { AgentDetailModal } from './AgentDetailModal';
import { RemediationLogsModal } from './RemediationLogsModal';
import { RemediationConfirmationModal } from './RemediationConfirmationModal';
import { AgentUpgradeManager } from './AgentUpgradeManager';
import { PendingAgentsPanel } from './PendingAgentsPanel';
import { ManageAgentCapabilitiesModal } from './ManageAgentCapabilitiesModal';
import { UpgradeModal } from './UpgradeModal';
import { fetchKpiSummary } from '../services/apiService';
import { showToast } from '../utils/toast';

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
  const { hasPermission, currentUser } = useUser();
  const canRemediate = hasPermission('remediate:agents');
  const _isSuperAdmin = ['Super Admin', 'super_admin', 'superadmin', 'platform-admin'].includes(currentUser?.role ?? '');

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
    if (!activeTenantId) return;
    let cancelled = false;
    const loadSummary = async (first: boolean) => {
      if (first) setIsLoadingSummary(true);
      try {
        // /api/kpi/summary answers totalAgents / onlineAgents / totalAssets.
        const summary = await fetchKpiSummary(activeTenantId);
        if (summary && !cancelled) {
          setTotalAgentsCount(summary.totalAgents ?? summary.total_agents ?? null);
          setOnlineAgentsCount(summary.onlineAgents ?? summary.online_agents ?? null);
          setTotalAssetsCount(summary.totalAssets ?? summary.total_assets ?? null);
        }
      } catch (err) {
        console.error("Failed to fetch agent summary:", err);
      } finally {
        if (first && !cancelled) setIsLoadingSummary(false);
      }
    };

    loadSummary(true);
    const timer = setInterval(() => loadSummary(false), 60_000);
    return () => { cancelled = true; clearInterval(timer); };
  }, [activeTenantId]);

  // The agents list is the first page (50) of /api/agents and refreshes every 5s; the summary counts the
  // whole fleet. Count from the live list unless the summary shows the list is cut off.
  const listIsPartial = totalAgentsCount !== null && totalAgentsCount > agents.length;
  const fleetTotal = listIsPartial ? (totalAgentsCount as number) : agents.length;
  const statusCounts = useMemo(() => {
    const now = Date.now();
    const counts = { Online: 0, Offline: 0, Error: 0, Quarantined: 0 } as Record<string, number>;
    agents.forEach(a => { const s = effectiveAgentStatus(a, now); counts[s] = (counts[s] || 0) + 1; });
    return counts;
  }, [agents]);
  const onlineAgents = listIsPartial && onlineAgentsCount !== null ? onlineAgentsCount : statusCounts.Online;
  const offlineAgents = statusCounts.Offline;
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

  // Keep the open detail modal in sync with the 5s parent poll
  useEffect(() => {
    if (!viewingAgentDetails) return;
    const updated = agents.find(a => a.id === viewingAgentDetails.id);
    if (updated) setViewingAgentDetails(updated);
  }, [agents]);

  const [isRefreshingAgent, setIsRefreshingAgent] = useState(false);

  const handleRefreshAgentDetails = async () => {
    if (!viewingAgentDetails) return;
    setIsRefreshingAgent(true);
    try {
      const freshAgents = await fetchAgents(viewingAgentDetails.tenantId);
      const fresh = freshAgents.find((a: Agent) => a.id === viewingAgentDetails.id);
      if (fresh) setViewingAgentDetails(fresh);
    } catch (e) {
      console.error('Failed to refresh agent details', e);
    } finally {
      setIsRefreshingAgent(false);
    }
  };

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


  const handleViewLogs = (agent: Agent) => {
    setViewingAgentLogs(agent);
  };

  const handleRunDiagnostics = async (agent: Agent) => {
    const confirmed = window.confirm(`Run diagnostics on ${agent.hostname}? This will check connectivity and service health.`);
    if (!confirmed) return;

    try {
      const updatedAgent = await runAgentDiagnostics(agent.id);
      onUpdateAgent(updatedAgent); // Sync with parent state
      showToast(`Diagnostics completed for ${agent.hostname}. Status: ${updatedAgent.health.overallStatus}`, 'success');
    } catch (e) {
      showToast('Diagnostics failed to run.', 'error');
    }
  };

  const startRemediation = async (agent: Agent) => {
    // Check rate limit
    if (isRemediationRateLimited(agent)) {
      showToast(`Remediation limit reached for ${agent.hostname}. Please try again later.`, 'error');
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
      showToast("You don't have permission to perform this action.", 'error');
      return;
    }
    if (isRemediationRateLimited(agent)) {
      showToast(`Remediation limit reached for ${agent.hostname}. Please try again later.`, 'error');
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

  const handleBulkDiagnostics = async () => {
    if (selectedAgentIds.size === 0) return;

    const confirmed = window.confirm(`Run diagnostics on ${selectedAgentIds.size} selected agent(s)?`);
    if (!confirmed) return;

    try {
      const updatedAgents = await Promise.all(Array.from(selectedAgentIds).map((id: string) => runAgentDiagnostics(id)));
      updatedAgents.forEach(agent => onUpdateAgent(agent)); // Sync with parent state
      showToast(`Diagnostics completed for ${updatedAgents.length} agents.`, 'success');
      setSelectedAgentIds(new Set());
    } catch (e: unknown) {
      const errorMessage = e instanceof Error ? e.message : 'Unknown error';
      showToast(`Bulk diagnostics failed: ${errorMessage}`, 'error');
    }
  };

  const handleBulkRemediate = () => {
    const agentsToFix = agents.filter(agent => selectedAgentIds.has(agent.id) && agent.status === 'Error');
    if (agentsToFix.length > 0) {
      setAgentsToConfirmRemediation(agentsToFix);
    }
  };

  const handleBulkDelete = async () => {
    const ids = Array.from(selectedAgentIds);
    if (!window.confirm(`Deregister and delete ${ids.length} selected agent(s)? This cannot be undone.`)) return;
    const results = await Promise.allSettled(ids.map(id => deleteAgent(id)));
    const succeeded = results.filter(r => r.status === 'fulfilled').length;
    const failed = results.length - succeeded;
    ids.forEach((id, i) => {
      if (results[i].status === 'fulfilled') {
        const agent = agents.find(a => a.id === id);
        if (agent && onDeleteAgent) onDeleteAgent(agent);
      }
    });
    setSelectedAgentIds(new Set());
    if (failed > 0) {
      showToast(`Deleted ${succeeded} agent(s). ${failed} failed.`, 'error');
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

  const atFreeLimit = isFreeTier && agents.length >= FREE_TIER_AGENT_LIMIT;
  const listedNote = listIsPartial ? ` among the ${agents.length} listed` : '';

  return (
    <div className="space-y-6 fade-in">
      <div className="flex flex-col md:flex-row justify-between md:items-end gap-4">
        <header>
          <h2 className="text-[30px] font-semibold tracking-[-0.03em] text-gray-900 dark:text-white">Agents</h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Every Omni-Agent in your organization, its heartbeat and what it is allowed to do.
          </p>
        </header>
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => document.getElementById('agent-installation-section')?.scrollIntoView({ behavior: 'smooth' })}
            className="flex items-center gap-2 h-10 px-4 text-sm font-medium text-gray-700 dark:text-gray-200 glass rounded-xl transition-all hover:border-primary-500/40 active:scale-[0.98]"
          >
            <DownloadIcon size={15} className="text-primary-600 dark:text-primary-400" />
            Install agent
          </button>
          {canRemediate && (
            <button
              onClick={handleRegisterAgentGuarded}
              title={atFreeLimit ? 'Upgrade to add more agents' : 'Register a new agent'}
              className={`flex items-center gap-2 h-10 px-5 text-sm font-semibold text-white rounded-xl transition-all active:scale-[0.98] ${atFreeLimit ? 'bg-amber-600 hover:bg-amber-700' : 'bg-primary-600 hover:bg-primary-700'}`}
            >
              <PlusCircleIcon size={15} />
              {atFreeLimit ? 'Upgrade to add more' : 'Register agent'}
            </button>
          )}
        </div>
      </div>

      {/* The platform tenant's own view lists every tenant's waiting agents. */}
      <PendingAgentsPanel tenantId={activeTenantId === 'platform-admin' ? null : activeTenantId} />

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-5">
        <StatTile icon={<ServerIcon size={18} />} label="Agents" tone="blue"
          footnote={listIsPartial ? `The list below shows the first ${agents.length}` : fleetTotal ? `${Math.round((onlineAgents / fleetTotal) * 100)}% online now` : 'None registered yet'}>
          <p className={`${bigNumber} text-gray-900 dark:text-white`}>{isLoadingSummary ? '…' : fleetTotal}</p>
        </StatTile>
        <StatTile icon={<CheckIcon size={18} />} label="Online" tone="primary" footnote="Heartbeat in the last 2 minutes">
          <p className={`${bigNumber} text-gray-900 dark:text-white`}>{isLoadingSummary ? '…' : onlineAgents}</p>
        </StatTile>
        <StatTile icon={<XCircleIcon size={18} />} label="Offline" tone="amber" footnote={`No recent heartbeat${listedNote}`}>
          <p className={`${bigNumber} ${offlineAgents > 0 ? 'text-amber-600 dark:text-amber-400' : 'text-gray-900 dark:text-white'}`}>{offlineAgents}</p>
        </StatTile>
        <StatTile icon={<AlertTriangleIcon size={18} />} label="Errors" tone="red" footnote={`${statusCounts.Quarantined} quarantined${listedNote}`}>
          <p className={`${bigNumber} ${statusCounts.Error > 0 ? 'text-red-600 dark:text-red-400' : 'text-gray-900 dark:text-white'}`}>{statusCounts.Error}</p>
        </StatTile>
      </div>

      {/* Banner — only shown to Super Admins who haven't selected a tenant yet */}
      {_isSuperAdmin && !activeTenantId && (
        <div className="p-3.5 rounded-xl flex items-start gap-3 text-sm text-amber-900 dark:text-amber-100 bg-amber-500/[0.08] ring-1 ring-inset ring-amber-500/25">
          <AlertTriangleIcon className="text-amber-600 dark:text-amber-400 mt-0.5 flex-shrink-0" size={18} />
          <p>
            <span className="font-semibold">Select a tenant.</span> Pick 'View Tenant' in Tenant Management to see that tenant's agent installation commands.
          </p>
        </div>
      )}

      {filters.length > 0 && (
        <div className="flex items-center justify-between gap-3 rounded-2xl px-4 py-3 bg-primary-500/[0.06] ring-1 ring-inset ring-primary-500/20">
          <div className="flex items-center gap-3 flex-wrap min-w-0">
            <span className="text-[13px] font-medium text-gray-700 dark:text-gray-300">Filtered by AI</span>
            {filters.map((filter, index) => (
              <span key={index} className="px-2.5 py-0.5 text-xs font-medium rounded-full bg-white/70 dark:bg-white/[0.06] text-primary-700 dark:text-primary-300 ring-1 ring-inset ring-primary-500/25">
                {filter.type}: {filter.value}
              </span>
            ))}
          </div>
          <button onClick={onClearFilters} aria-label="Clear filters" className="grid place-items-center h-8 w-8 flex-shrink-0 rounded-lg text-gray-500 hover:text-gray-900 hover:bg-gray-900/5 dark:hover:text-white dark:hover:bg-white/10 transition-colors">
            <XCircleIcon size={16} />
          </button>
        </div>
      )}

      {/* Autonomous Operations Section */}
      {(errorAgent || autonomousRun.status !== 'idle') && (
        <section aria-label="Autonomous operations" className="rounded-2xl bg-white dark:bg-gray-800 border border-gray-200/80 dark:border-white/[0.07] shadow-card overflow-hidden">
          <div className="px-5 pt-4 pb-3 border-b border-gray-100 dark:border-white/[0.06] flex items-center justify-between gap-3">
            <h3 className="text-[15px] font-semibold text-gray-900 dark:text-white flex items-center gap-2">
              <ZapIcon size={16} className="text-primary-500" />
              Autonomous operations
            </h3>
            {autonomousRun.status === 'running' && <span className="flex items-center gap-1.5 text-xs font-semibold text-amber-700 dark:text-amber-300"><CogIcon size={14} className="animate-spin" />Running</span>}
            {autonomousRun.status === 'completed' && <span className="flex items-center gap-1.5 text-xs font-semibold text-emerald-700 dark:text-emerald-300"><CheckIcon size={14} />Completed</span>}
            {autonomousRun.status === 'failed' && <span className="flex items-center gap-1.5 text-xs font-semibold text-red-700 dark:text-red-300"><AlertTriangleIcon size={14} />Failed</span>}
          </div>
          <div className="p-5">
            {autonomousRun.status === 'idle' && errorAgent ? (
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div className="flex items-start gap-3">
                  <span className="grid place-items-center h-9 w-9 flex-shrink-0 rounded-xl ring-1 ring-inset text-red-600 dark:text-red-400 bg-red-500/10 ring-red-500/20"><AlertTriangleIcon size={18} /></span>
                  <div>
                    <p className="font-semibold text-gray-900 dark:text-gray-100">An agent is in an error state</p>
                    <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">The agent on <span className="font-medium text-red-700 dark:text-red-300">{errorAgent.hostname}</span> is reporting an error. You can authorize the Omni-Agent AI to attempt an autonomous remediation.</p>
                  </div>
                </div>
                <button
                  onClick={() => handleAuthorizeRemediation(errorAgent)}
                  disabled={!canRemediate || isErrorAgentRateLimited}
                  title={!canRemediate ? "You do not have permission to perform this action" : isErrorAgentRateLimited ? "Remediation limit reached (3/hr). Try again later." : "Authorize Autonomous Remediation"}
                  className="w-full md:w-auto flex-shrink-0 flex items-center justify-center gap-2 h-10 px-4 text-sm font-semibold text-white rounded-xl bg-primary-600 hover:bg-primary-700 transition-all active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <ZapIcon size={15} />
                  Authorize remediation
                </button>
              </div>
            ) : (
              <div>
                <p className="mb-3 text-sm text-gray-600 dark:text-gray-300">Remediation log for <span className="font-mono text-[13px] text-gray-900 dark:text-white">{autonomousRun.targetAgent?.hostname}</span></p>
                <AutonomousOpsLog steps={autonomousRun.steps} />
              </div>
            )}
          </div>
        </section>
      )}

      {/* Agent Installation Section */}
      <div id="agent-installation-section" className="scroll-mt-24">
        <AgentInstallation registrationKey={registrationKey} tenantId={activeTenantId} tenants={tenants} onSelectTenant={onSelectTenant} />
      </div>

      <section aria-label="Registered agents" className="rounded-2xl bg-white dark:bg-gray-800 border border-gray-200/80 dark:border-white/[0.07] shadow-card overflow-hidden">
        <div className="px-5 pt-4 pb-3 border-b border-gray-100 dark:border-white/[0.06] flex flex-wrap items-center gap-2">
          <h3 className="text-[15px] font-semibold text-gray-900 dark:text-white flex items-center gap-2">
            <ServerIcon size={16} className="text-primary-500" />
            Registered agents
            <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold tabular-nums text-gray-600 dark:text-gray-300 bg-gray-100 dark:bg-white/[0.06]">{agents.length}</span>
          </h3>
          {/* Free tier usage badge */}
          {isFreeTier && (
            <span className={`px-2 py-0.5 text-[11px] font-semibold rounded-full ring-1 ring-inset ${atFreeLimit
              ? 'text-red-700 dark:text-red-300 bg-red-500/10 ring-red-500/20'
              : agents.length >= FREE_TIER_AGENT_LIMIT - 1
                ? 'text-amber-700 dark:text-amber-300 bg-amber-500/10 ring-amber-500/20'
                : 'text-gray-600 dark:text-gray-300 bg-gray-500/10 ring-gray-500/20'
              }`}>
              {agents.length} / {FREE_TIER_AGENT_LIMIT} agents · Free
            </span>
          )}
          {listIsPartial && (
            <span className="text-xs text-amber-700 dark:text-amber-300">
              Showing the first {agents.length} of {fleetTotal}
            </span>
          )}
        </div>
        <AgentList
          agents={agents}
          assets={assets}
          selectedAgentIds={selectedAgentIds}
          upgradingAgentIds={upgradingAgentIds}
          onToggleSelection={handleToggleSelection}
          onSelectAll={handleSelectAll}
          onViewLogs={handleViewLogs}
          onRunDiagnostics={handleRunDiagnostics}
          onViewDetails={setViewingAgentDetails}
          onAuthorizeRemediation={handleAuthorizeRemediation}
          onViewRemediationLogs={setViewingRemediationLogsForAgent}
          onBulkDiagnostics={handleBulkDiagnostics}
          onBulkRemediate={handleBulkRemediate}
          onBulkDelete={onDeleteAgent ? handleBulkDelete : undefined}
          onUpdateAgent={onUpdateAgent}
          onRegisterAgent={onRegisterAgent}
          onDeleteAgent={onDeleteAgent}
          onQuarantineAgent={canRemediate ? async (agent: Agent) => {
            const reason = window.prompt(`Quarantine reason for ${agent.hostname || agent.id}:`);
            if (!reason) return;
            try {
              await quarantineAgent(agent.id, reason);
              onUpdateAgent({ ...agent, status: 'Quarantined' as any });
              showToast(`Agent ${agent.hostname || agent.id} quarantined.`, 'success');
            } catch (e: any) {
              showToast(e.message || 'Failed to quarantine agent', 'error');
            }
          } : undefined}
          onToggleSoftwareExclusion={canRemediate ? async (agent: Agent) => {
            const isExcluded = !!(agent as any).excludeFromSoftwareOps;
            const label = agent.hostname || agent.id;
            try {
              await setAgentSoftwareExclusion(agent.id, !isExcluded);
              onUpdateAgent({ ...agent, excludeFromSoftwareOps: !isExcluded } as any);
              showToast(
                isExcluded
                  ? `${label} re-included in software operations.`
                  : `${label} excluded from software operations.`,
                'success'
              );
            } catch (e: any) {
              showToast(e.message || 'Failed to update exclusion', 'error');
            }
          } : undefined}
          filters={filters}
        />
      </section>

      <AgentUpgradeManager
        agents={agents}
        selectedAgentIds={selectedAgentIds}
        jobs={agentUpgradeJobs}
        onScheduleUpgrade={handleScheduleUpgrade}
        managerRef={upgradeManagerRef}
      />

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
        onRefresh={handleRefreshAgentDetails}
        isRefreshing={isRefreshingAgent}
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
