import React, { useState } from 'react';
import { Metric, Alert, ComplianceFramework, AiSystem, User, AppView, Agent } from '../types';
import { MetricCard } from './MetricCard';
import { AlertsPanel } from './AlertsPanel';
import { ComplianceStatus } from './ComplianceStatus';
import { ComplianceScorePanel } from './ComplianceScorePanel';
import { AiInsights } from './AiInsights';
import { AiSystemHealth } from './AiSystemHealth';
import { DashboardHeader } from './DashboardHeader';
import { BusinessKpiChart } from './BusinessKpiChart';
import { SystemHealthChart } from './SystemHealthChart';
import { AllPartsHiddenNotice } from './NoAccessPanel';
import { useUser } from '../contexts/UserContext';
import { canReadView, landingView } from '../utils/viewAccess';
import { catalogueFor } from '../utils/catalogueAccess';
import { OverviewCustomizer, OverviewWidgetId, useOverviewHidden } from './OverviewCustomizer';
import { navMemoryKey } from '../hooks/useNavMemory';

interface DashboardProps {
  metrics: Metric[];
  alerts: Alert[];
  complianceFrameworks: ComplianceFramework[];
  aiSystems: AiSystem[];
  agents: Agent[];
  currentUser: User;
  setCurrentView: (view: AppView) => void;
}

export const Dashboard: React.FC<DashboardProps> = ({ metrics, alerts, complianceFrameworks, aiSystems, agents, currentUser, setCurrentView }) => {
  const { hasPermission } = useUser();
  const can = (view: AppView) => canReadView(view, currentUser, hasPermission);

  // Phase 77 (D-08): each widget is backed by a catalogue; one the role cannot read is not rendered
  // and its fetch never starts. Metric cards and the health chart read /api/metrics, which no
  // catalogue owns, so they stay.
  const roleCompliance = can('compliance');
  const roleKpi = can('cxo');
  const roleInsights = can('aiAssistantChat');
  const roleAlerts = can('alertManagement');
  const roleAiHealth = can('aiGovernance') || can('agents');
  const anyGated = roleCompliance || roleKpi || roleInsights || roleAlerts || roleAiHealth;

  // The user's own layout choice only subtracts from what the role allows.
  const { hidden, setHidden } = useOverviewHidden(navMemoryKey(currentUser));
  const [isCustomizing, setIsCustomizing] = useState(false);
  const shown = (id: OverviewWidgetId) => !hidden.includes(id);
  const available: OverviewWidgetId[] = [
    ...(metrics.length > 0 ? ['metrics' as const] : []), 'health',
    ...(roleAlerts ? ['alerts' as const] : []), ...(roleInsights ? ['insights' as const] : []),
    ...(roleKpi ? ['kpi' as const] : []), ...(roleAiHealth ? ['aiHealth' as const] : []),
    ...(roleCompliance ? ['compliance' as const] : []),
  ];
  const showMetrics = shown('metrics');
  const showHealth = shown('health');
  const showAlerts = roleAlerts && shown('alerts');
  const showInsights = roleInsights && shown('insights');
  const showKpi = roleKpi && shown('kpi');
  const showAiHealth = roleAiHealth && shown('aiHealth');
  const showCompliance = roleCompliance && shown('compliance');
  const nothingShown = available.every(id => !shown(id));

  if (!anyGated && metrics.length === 0) {
    const landing = landingView(currentUser, hasPermission);
    const target = landing && landing !== 'dashboard' ? landing : null;
    return (
      <div className="space-y-6 pb-8">
        <DashboardHeader userName={currentUser.name} setCurrentView={setCurrentView} />
        <AllPartsHiddenNotice
          landingLabel={target ? catalogueFor(target)?.label : undefined}
          onGoToLanding={target ? () => setCurrentView(target) : undefined}
        />
      </div>
    );
  }

  // Spatial Glass bento: KPI tiles, then 12-column rows. Every widget keeps its own gate above;
  // a hidden widget's neighbour widens to fill the row.
  return (
    <div className="space-y-5 pb-8">
      <DashboardHeader userName={currentUser.name} setCurrentView={setCurrentView} onCustomize={() => setIsCustomizing(true)} />
      <OverviewCustomizer isOpen={isCustomizing} onClose={() => setIsCustomizing(false)} available={available} hidden={hidden} onChange={setHidden} />

      {nothingShown && (
        <div className="rounded-2xl p-10 text-center bg-white dark:bg-gray-800 border border-gray-200/80 dark:border-white/[0.07] shadow-card">
          <p className="text-sm font-medium text-gray-800 dark:text-gray-200">Every widget is hidden</p>
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">You chose to hide them all. Bring back the ones you want.</p>
          <button onClick={() => setIsCustomizing(true)} className="mt-4 h-9 px-4 rounded-xl text-sm font-semibold text-white bg-primary-600 hover:bg-primary-700 transition-colors">
            Customize Overview
          </button>
        </div>
      )}

      {showMetrics && (
        <section aria-label="Key metrics" className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
          {metrics.map((metric, i) => <MetricCard key={metric.id} metric={metric} index={i} />)}
        </section>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4 md:gap-5">
        {showHealth && (
          <div className={`bento-cell xl:h-[440px] ${showAlerts ? 'xl:col-span-8' : 'xl:col-span-12'}`}>
            <SystemHealthChart metrics={metrics} />
          </div>
        )}
        {showAlerts && (
          <div className={`bento-cell h-[440px] min-h-0 ${showHealth ? 'xl:col-span-4' : 'xl:col-span-12'}`}>
            <AlertsPanel alerts={alerts} />
          </div>
        )}

        {showInsights && (
          <div className="bento-cell xl:col-span-12">
            <AiInsights metrics={metrics} alerts={alerts} />
          </div>
        )}

        {/* KPI and AI health share a row (UI-SPEC C17/C20); the one that remains takes all of it. */}
        {showKpi && (
          <div className={`bento-cell ${showAiHealth ? 'xl:col-span-8' : 'xl:col-span-12'}`}>
            <BusinessKpiChart />
          </div>
        )}
        {showAiHealth && (
          <div className={`bento-cell space-y-5 ${showKpi ? 'xl:col-span-4' : 'xl:col-span-12'}`}>
            <AiSystemHealth aiSystems={aiSystems} agents={agents} />
          </div>
        )}

        {showCompliance && (
          <>
            <div className="bento-cell xl:col-span-5">
              <ComplianceScorePanel />
            </div>
            <div className="bento-cell xl:col-span-7">
              <ComplianceStatus frameworks={complianceFrameworks} />
            </div>
          </>
        )}
      </div>
    </div>
  );
};
