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

  return (
    <div className="space-y-6 pb-8">
      <DashboardHeader userName={currentUser.name} setCurrentView={setCurrentView} />

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 md:gap-6">
        {metrics.map((metric, i) => <MetricCard key={metric.id} metric={metric} index={i} />)}
      </div>

      <SystemHealthChart metrics={metrics} />

      {showInsights && <AiInsights metrics={metrics} alerts={alerts} />}

      {(showKpi || showAiHealth) && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {showKpi && (
            <div className={showAiHealth ? 'lg:col-span-2' : 'lg:col-span-3'}>
              <BusinessKpiChart />
            </div>
          )}
          {showAiHealth && (
            <div className={showKpi ? 'space-y-6' : 'space-y-6 lg:col-span-3'}>
              <AiSystemHealth aiSystems={aiSystems} agents={agents} />
            </div>
          )}
        </div>
      )}

      {showAlerts && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2">
            <AlertsPanel alerts={alerts} />
          </div>
        </div>
      )}

      {showCompliance && (
        <div className="mt-8 space-y-6">
          <ComplianceScorePanel />
          <ComplianceStatus frameworks={complianceFrameworks} />
        </div>
      )}
    </div>
  );
};
