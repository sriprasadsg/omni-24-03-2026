import React from 'react';
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
  const showCompliance = can('compliance');
  const showKpi = can('cxo');
  const showInsights = can('aiAssistantChat');
  const showAlerts = can('alertManagement');
  const showAiHealth = can('aiGovernance') || can('agents');
  const anyGated = showCompliance || showKpi || showInsights || showAlerts || showAiHealth;

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
      <DashboardHeader userName={currentUser.name} setCurrentView={setCurrentView} />

      <section aria-label="Key metrics" className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        {metrics.map((metric, i) => <MetricCard key={metric.id} metric={metric} index={i} />)}
      </section>

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4 md:gap-5">
        <div className={`bento-cell xl:h-[440px] ${showAlerts ? 'xl:col-span-8' : 'xl:col-span-12'}`}>
          <SystemHealthChart metrics={metrics} />
        </div>
        {showAlerts && (
          <div className="bento-cell xl:col-span-4 h-[440px] min-h-0">
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
