
import React, { useState } from 'react';
import { AiSystem, AiRisk, AiRiskSeverity, AiRiskStatus, AiRiskMitigationStatus, RiskHistoryLog, AgenticStep } from '../types';
import { ActivityIcon, PencilIcon, PlusCircleIcon, TrashIcon, AlertTriangleIcon, ShieldCheckIcon, SparklesIcon, InfoIcon } from './icons';
import { useUser } from '../contexts/UserContext';
import { generateRiskRemediationPlan } from '../services/apiService';
import { RemediationPlanLog } from './RemediationPlanLog';


interface AiRiskManagementProps {
  system: AiSystem;
  onViewRisk: (risk: AiRisk) => void;
  onEditRisk: (risk: AiRisk) => void;
  onAddRisk: () => void;
  onDeleteRisk: (riskId: string) => void;
}

const severityClasses: Record<AiRiskSeverity, string> = {
  Critical: 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300',
  High: 'bg-orange-100 text-orange-800 dark:bg-orange-900/50 dark:text-orange-300',
  Medium: 'bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-300',
  Low: 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300',
};

const statusClasses: Record<AiRiskStatus, string> = {
    Open: 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300',
    Mitigated: 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300',
    Accepted: 'bg-gray-200 text-gray-800 dark:bg-gray-700 dark:text-gray-300',
    Closed: 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300',
};

const mitigationStatusClasses: Record<AiRiskMitigationStatus, string> = {
    'Not Started': 'bg-gray-200 text-gray-800 dark:bg-gray-700 dark:text-gray-300',
    'In Progress': 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300',
    'Pending Review': 'bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-300',
    'Completed': 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300',
};

const renderLastUpdateSummary = (latestUpdate: RiskHistoryLog | null) => {
    if (!latestUpdate) {
        return <span className="text-gray-400 dark:text-gray-500">-</span>;
    }

    let icon: React.ReactNode = <PencilIcon size={12} className="mr-1.5" />;
    let summaryText: string = latestUpdate.action;

    if (latestUpdate.action === 'Created') {
        icon = <PlusCircleIcon size={12} className="mr-1.5 text-green-500" />;
        summaryText = 'Created';
    } else if (latestUpdate.action === 'Edited') {
        const details = latestUpdate.details.toLowerCase();
        if (details.includes('severity')) {
            icon = <AlertTriangleIcon size={12} className="mr-1.5 text-orange-500" />;
            summaryText = 'Severity Updated';
        } else if (details.includes('status')) {
            icon = <ShieldCheckIcon size={12} className="mr-1.5 text-blue-500" />;
            summaryText = 'Status Updated';
        } else {
             summaryText = 'Details Edited';
        }
    }
    
    return (
        <div className="flex flex-col">
            <div className="flex items-center font-medium text-gray-800 dark:text-gray-200">
                {icon}
                <span>{summaryText}</span>
            </div>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                {new Date(latestUpdate.timestamp).toLocaleDateString()} by {latestUpdate.user}
            </p>
        </div>
    );
};

export const AiRiskManagement: React.FC<AiRiskManagementProps> = ({ system, onViewRisk, onEditRisk, onAddRisk, onDeleteRisk }) => {
  const { hasPermission } = useUser();
  const canManageRisks = hasPermission('manage:ai_risks');

  const [remediationPlans, setRemediationPlans] = useState<Record<string, AgenticStep[]>>({});
  const [loadingPlanId, setLoadingPlanId] = useState<string | null>(null);
  const [expandedPlanId, setExpandedPlanId] = useState<string | null>(null);

  const handleTogglePlan = async (risk: AiRisk) => {
    const riskId = risk.id;

    if (expandedPlanId === riskId) {
        setExpandedPlanId(null);
        return;
    }

    setExpandedPlanId(riskId);

    // If plan doesn't exist, generate it
    if (!remediationPlans[riskId]) {
        setLoadingPlanId(riskId);
        setRemediationPlans(prev => ({ ...prev, [riskId]: [] }));

        try {
            for await (const step of generateRiskRemediationPlan(system, risk)) {
                setRemediationPlans(prev => ({
                    ...prev,
                    [riskId]: [...(prev[riskId] || []), step]
                }));
            }
        } catch (e) {
            const errorStep: AgenticStep = { type: 'observation', content: `Failed to generate plan: ${e instanceof Error ? e.message : 'Unknown error'}`, timestamp: new Date().toISOString() };
             setRemediationPlans(prev => ({
                ...prev,
                [riskId]: [...(prev[riskId] || []), errorStep]
            }));
        } finally {
            setLoadingPlanId(null);
        }
    }
  };

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md">
      <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex justify-between items-center">
        <h3 className="text-lg font-semibold flex items-center">
          <ActivityIcon className="mr-2 text-primary-500" />
          AI Risk Register
          <span className="ml-3 text-xs font-medium bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-300 px-2 py-1 rounded-full">
            {system.risks.length} Total
          </span>
        </h3>
        {canManageRisks && (
            <button
                onClick={onAddRisk}
                className="flex items-center px-3 py-1.5 text-xs font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 disabled:bg-primary-400 disabled:cursor-not-allowed transition-colors"
            >
                <PlusCircleIcon size={16} className="mr-1.5" />
                Add New Risk
            </button>
        )}
      </div>
      <div className="p-4">
        {system.risks.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left text-gray-500 dark:text-gray-400">
                <thead className="text-xs text-gray-700 uppercase bg-gray-50 dark:bg-gray-700 dark:text-gray-400">
                    <tr>
                        <th scope="col" className="px-4 py-3">Risk Title</th>
                        <th scope="col" className="px-4 py-3">Severity</th>
                        <th scope="col" className="px-4 py-3">Status</th>
                        <th scope="col" className="px-4 py-3">Mitigation</th>
                        <th scope="col" className="px-4 py-3">Open Tasks</th>
                        <th scope="col" className="px-4 py-3">Last Update</th>
                        <th scope="col" className="px-4 py-3"><span className="sr-only">Actions</span></th>
                    </tr>
                </thead>
                <tbody>
                    {system.risks.map(risk => {
                      const openTasks = risk.mitigationTasks.filter(t => t.status !== 'Done').length;
                      const latestUpdate = risk.history && risk.history.length > 0 ? risk.history[0] : null;
                      return (
                        <React.Fragment key={risk.id}>
                          <tr onClick={() => onViewRisk(risk)} className="border-b dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600/50 cursor-pointer">
                              <td className="px-4 py-3">
                                <div className="font-medium text-gray-900 dark:text-white flex items-center">
                                    {risk.title}
                                    {risk.detail && <InfoIcon size={12} className="ml-2 text-gray-400" title={risk.detail.substring(0, 50) + "..."} />}
                                </div>
                              </td>
                              <td className="px-4 py-3">
                                  <span className={`px-2 py-1 text-xs font-medium rounded-full ${severityClasses[risk.severity]}`}>{risk.severity}</span>
                              </td>
                              <td className="px-4 py-3">
                                  <span className={`px-2 py-1 text-xs font-medium rounded-full ${statusClasses[risk.status]}`}>{risk.status}</span>
                              </td>
                              <td className="px-4 py-3">
                                  <span className={`px-2 py-1 text-xs font-medium rounded-full ${mitigationStatusClasses[risk.mitigationStatus]}`}>{risk.mitigationStatus}</span>
                              </td>
                              <td className="px-4 py-3">
                                  {risk.mitigationTasks.length > 0 ? (
                                      <span className={`px-2 py-1 text-xs font-medium rounded-full ${
                                          openTasks > 0 
                                          ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-300' 
                                          : 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300'
                                      }`}>
                                          {openTasks} / {risk.mitigationTasks.length}
                                      </span>
                                  ) : (
                                      <span className="text-gray-400 dark:text-gray-500">-</span>
                                  )}
                              </td>
                              <td className="px-4 py-3">
                                  {renderLastUpdateSummary(latestUpdate)}
                              </td>
                              <td className="px-4 py-3 text-right">
                                  {canManageRisks && (
                                    <div className="flex items-center justify-end space-x-1">
                                      {risk.status === 'Open' && (
                                          <button
                                              onClick={(e) => { e.stopPropagation(); handleTogglePlan(risk); }}
                                              className="p-1.5 text-gray-500 hover:text-indigo-600 dark:text-gray-400 dark:hover:text-indigo-400"
                                              title="Generate AI Remediation Plan"
                                          >
                                              <SparklesIcon size={14} />
                                          </button>
                                      )}
                                      <button onClick={(e) => { e.stopPropagation(); onEditRisk(risk); }} className="p-1.5 text-gray-500 hover:text-primary-600 dark:text-gray-400 dark:hover:text-primary-400" title="Edit">
                                          <PencilIcon size={14} />
                                      </button>
                                      <button onClick={(e) => { e.stopPropagation(); onDeleteRisk(risk.id); }} className="p-1.5 text-gray-500 hover:text-red-600 dark:text-gray-400 dark:hover:text-red-400" title="Delete">
                                          <TrashIcon size={14} />
                                      </button>
                                    </div>
                                  )}
                              </td>
                          </tr>
                          {expandedPlanId === risk.id && (
                              <tr className="bg-gray-50 dark:bg-gray-800/50">
                                  <td colSpan={7} className="p-0">
                                      <div className="p-4">
                                          <h4 className="font-semibold text-xs text-gray-600 dark:text-gray-400 mb-2">AI-Generated Remediation Plan</h4>
                                          <RemediationPlanLog 
                                              steps={remediationPlans[risk.id] || []} 
                                              isLoading={loadingPlanId === risk.id} 
                                          />
                                      </div>
                                  </td>
                              </tr>
                          )}
                        </React.Fragment>
                      )
                    })}
                </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-center text-gray-500 dark:text-gray-400 py-4">
            No risks have been formally registered for this system yet.
          </p>
        )}
      </div>
    </div>
  );
};
