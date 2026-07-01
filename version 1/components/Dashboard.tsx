import React from 'react';
import { Metric, Alert, ComplianceFramework, AiSystem, User, AppView } from '../types';
import { MetricCard } from './MetricCard';
import { AlertsPanel } from './AlertsPanel';
import { ComplianceStatus } from './ComplianceStatus';
import { AiInsights } from './AiInsights';
import { AiSystemHealth } from './AiSystemHealth';
import { SystemHealthChart } from './SystemHealthChart';
import { DashboardHeader } from './DashboardHeader';
import { BusinessKpiChart } from './BusinessKpiChart';

interface DashboardProps {
  metrics: Metric[];
  alerts: Alert[];
  complianceFrameworks: ComplianceFramework[];
  aiSystems: AiSystem[];
  currentUser: User;
  setCurrentView: (view: AppView) => void;
}

export const Dashboard: React.FC<DashboardProps> = ({ metrics, alerts, complianceFrameworks, aiSystems, currentUser, setCurrentView }) => {
  return (
    <div className="space-y-6">
      <DashboardHeader userName={currentUser.name} setCurrentView={setCurrentView} />
      
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 md:gap-6">
        {metrics.map(metric => <MetricCard key={metric.id} metric={metric} />)}
      </div>

      <AiInsights metrics={metrics} alerts={alerts} />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
            <SystemHealthChart metrics={metrics} />
            <BusinessKpiChart />
            <AlertsPanel alerts={alerts} />
        </div>
        <div className="space-y-6">
            <AiSystemHealth aiSystems={aiSystems} />
        </div>
      </div>

      <div>
        <ComplianceStatus frameworks={complianceFrameworks} />
      </div>
    </div>
  );
};