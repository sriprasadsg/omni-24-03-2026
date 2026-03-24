import React from 'react';
import { Metric, Alert, ComplianceFramework, AiSystem, User, AppView, Agent } from '../types';
import { MetricCard } from './MetricCard';
import { AlertsPanel } from './AlertsPanel';
import { ComplianceStatus } from './ComplianceStatus';
import { AiInsights } from './AiInsights';
import { AiSystemHealth } from './AiSystemHealth';
import { DashboardHeader } from './DashboardHeader';
import { BusinessKpiChart } from './BusinessKpiChart';

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
  return (
    <div className="space-y-6 pb-8">
      <DashboardHeader userName={currentUser.name} setCurrentView={setCurrentView} />

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 md:gap-6">
        {metrics.map(metric => <MetricCard key={metric.name} metric={metric} />)}
      </div>

      <AiInsights metrics={metrics} alerts={alerts} />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <BusinessKpiChart />
        </div>
        <div className="space-y-6">
          <AiSystemHealth aiSystems={aiSystems} agents={agents} />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <AlertsPanel alerts={alerts} />
        </div>
      </div>

      <div className="mt-8">
        <ComplianceStatus frameworks={complianceFrameworks} />
      </div>
    </div>
  );
};
