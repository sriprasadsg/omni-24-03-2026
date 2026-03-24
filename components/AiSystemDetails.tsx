
import React, { useState } from 'react';
import { AiSystem } from '../types';
// FIX: Replaced non-existent BoxIcon with BotIcon and added BoxIcon to icons.tsx.
import { BoxIcon, CopyIcon, CheckIcon, ActivityIcon, ScaleIcon, BrainCircuitIcon, FileCodeIcon, ChevronDownIcon, PencilIcon, ZapIcon, AlertTriangleIcon } from './icons';
import { useUser } from '../contexts/UserContext';

interface AiSystemDetailsProps {
  system: AiSystem;
  isExpanded: boolean;
  onToggleExpand: () => void;
  onEdit: () => void;
  onStartRemediation: (system: AiSystem) => void;
}

const statusClasses: Record<AiSystem['status'], string> = {
    Active: 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300',
    'In Development': 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300',
    Sunset: 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300',
};

const severityClasses: Record<string, string> = {
  Critical: 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300',
  High: 'bg-orange-100 text-orange-800 dark:bg-orange-900/50 dark:text-orange-300',
  Medium: 'bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-300',
  Low: 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300',
};

export const AiSystemDetails: React.FC<AiSystemDetailsProps> = ({ system, isExpanded, onToggleExpand, onEdit, onStartRemediation }) => {
  const [isCopied, setIsCopied] = useState(false);
  const { hasPermission } = useUser();
  const canManage = hasPermission('manage:ai_risks');
  const hasHighRisk = system.risks.some(r => r.status === 'Open' && (r.severity === 'Critical' || r.severity === 'High'));


  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(system.id).then(() => {
        setIsCopied(true);
        setTimeout(() => setIsCopied(false), 2000); // Reset after 2 seconds
    });
  };
  
  const lastRetraining = system.controls.lastRetrainingTriggered 
    ? new Date(system.controls.lastRetrainingTriggered).toLocaleDateString() 
    : 'N/A';

  const sortedRisks = [...system.risks].sort((a, b) => {
    const severityWeight: Record<string, number> = { Critical: 4, High: 3, Medium: 2, Low: 1 };
    return (severityWeight[b.severity] || 0) - (severityWeight[a.severity] || 0);
  });

  return (
    <div>
        <div className="p-4">
            <div className="flex justify-between items-start">
                <div>
                    <h3 className="text-lg font-semibold flex items-center">
                        <BoxIcon className="mr-2 text-primary-500" />
                        {system.name}
                    </h3>
                    <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{system.description}</p>
                </div>
                <div className="flex items-center flex-shrink-0 ml-4 space-x-2">
                    {hasHighRisk && canManage && (
                        <button 
                            onClick={() => onStartRemediation(system)}
                            title="Start Autonomous Remediation for high-priority risks"
                            className="flex items-center px-3 py-1.5 text-xs font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 animate-pulse shadow-lg shadow-primary-500/50"
                        >
                            <ZapIcon size={14} className="mr-1.5" />
                            Remediate Risks
                        </button>
                    )}
                    {canManage && (
                        <button onClick={onEdit} className="p-1.5 text-gray-500 hover:text-primary-600 dark:text-gray-400 dark:hover:text-primary-400">
                            <PencilIcon size={14} />
                        </button>
                    )}
                    <span className={`text-xs font-bold px-2 py-1 rounded-full ${statusClasses[system.status]}`}>{system.status}</span>
                    <button 
                        className="p-1" 
                        onClick={onToggleExpand}
                        aria-expanded={isExpanded}
                    >
                        <ChevronDownIcon size={20} className={`text-gray-500 dark:text-gray-400 transform transition-transform duration-300 ${isExpanded ? 'rotate-180' : ''}`} />
                    </button>
                </div>
            </div>
        </div>
        
        <div className={`grid overflow-hidden transition-all duration-300 ease-in-out ${isExpanded ? 'grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0'}`}>
            <div className="min-h-0">
                <div className="p-4 border-t border-gray-200 dark:border-gray-700 grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                    <div>
                        <p className="text-gray-500 dark:text-gray-400 font-medium">Version</p>
                        <p className="text-gray-800 dark:text-gray-200 font-semibold">{system.version}</p>
                    </div>
                    <div>
                        <p className="text-gray-500 dark:text-gray-400 font-medium">Owner</p>
                        <p className="text-gray-800 dark:text-gray-200 font-semibold">{system.owner}</p>
                    </div>
                    <div>
                        <p className="text-gray-500 dark:text-gray-400 font-medium">Last Assessment</p>
                        <p className="text-gray-800 dark:text-gray-200 font-semibold">{system.lastAssessmentDate}</p>
                    </div>
                     <div>
                        <p className="text-gray-500 dark:text-gray-400 font-medium flex items-center"><BrainCircuitIcon size={14} className="mr-1.5" />Last Retraining</p>
                        <p className="text-gray-800 dark:text-gray-200 font-semibold">{lastRetraining}</p>
                    </div>
                    <div>
                        <p className="text-gray-500 dark:text-gray-400 font-medium flex items-center"><ActivityIcon size={14} className="mr-1.5" />Registered Risks</p>
                        <p className="text-gray-800 dark:text-gray-200 font-semibold">{system.risks.length}</p>
                    </div>
                    <div>
                        <p className="text-gray-500 dark:text-gray-400 font-medium flex items-center"><ScaleIcon size={14} className="mr-1.5" />Fairness Metrics</p>
                        <p className="text-gray-800 dark:text-gray-200 font-semibold">{system.fairnessMetrics.length}</p>
                    </div>
                    <div>
                        <p className="text-gray-500 dark:text-gray-400 font-medium flex items-center"><FileCodeIcon size={14} className="mr-1.5" />Documentation</p>
                        <p className="text-gray-800 dark:text-gray-200 font-semibold">{system.documentation.length} links</p>
                    </div>
                    <div>
                        <p className="text-gray-500 dark:text-gray-400 font-medium">System ID</p>
                        <div className="flex items-center space-x-2">
                            <p className="font-mono text-xs text-gray-800 dark:text-gray-200 font-semibold">{system.id}</p>
                            <button onClick={handleCopy} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200">
                                {isCopied ? <CheckIcon size={14} className="text-green-500" /> : <CopyIcon size={14} />}
                            </button>
                        </div>
                    </div>
                </div>
                
                {sortedRisks.length > 0 && (
                    <div className="p-4 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/50">
                        <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-3 flex items-center">
                            <AlertTriangleIcon size={14} className="mr-2" />
                            Risk Snapshot
                        </h4>
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                            {sortedRisks.map(risk => (
                                <div key={risk.id} className="flex items-center justify-between p-2.5 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 shadow-sm">
                                    <span className="text-sm font-medium text-gray-700 dark:text-gray-300 truncate flex-1 mr-2" title={risk.title}>{risk.title}</span>
                                    <span className={`flex-shrink-0 px-2 py-0.5 text-[10px] font-bold uppercase rounded-full ${severityClasses[risk.severity]}`}>
                                        {risk.severity}
                                    </span>
                                </div>
                            ))}
                        </div>
                    </div>
                )}
            </div>
        </div>
    </div>
  );
};
