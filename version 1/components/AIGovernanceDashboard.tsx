

import React, { useState, useEffect, useMemo } from 'react';
import { AiSystem, AiRisk, RiskHistoryLog, RegisteredModel, ModelExperiment, ModelStage, User, AgenticStep, AiRiskStatus, AiRiskMitigationStatus } from '../types';
import { AiSystemRegistry } from './AiSystemRegistry';
import { ImpactAssessment } from './ImpactAssessment';
import { FairnessMetrics } from './FairnessMetrics';
import { AiRiskManagement } from './AiRiskManagement';
import { RiskFormModal } from './RiskFormModal';
import { RiskDetailModal } from './RiskDetailModal';
// FIX: Replaced non-existent BoxIcon with BotIcon and added BoxIcon to icons.tsx.
import { BotIcon, BookTextIcon, GavelIcon, ActivityIcon, ScaleIcon, FileCodeIcon, BrainCircuitIcon, SlidersHorizontalIcon, BoxIcon } from './icons';
import { AiSystemDetails } from './AiSystemDetails';
import { AiSystemDocumentation } from './AiSystemDocumentation';
import { AIGovernancePolicy } from './AIGovernancePolicy';
import { AiSystemControls } from './AiSystemControls';
import { AiSystemPerformance } from './AiSystemPerformance';
import { AiSystemFineTuning } from './AiSystemFineTuning';
import { RiskHistory } from './RiskHistory';
import { AIGovernanceSummary } from './AIGovernanceSummary';
import { ModelRegistry } from './ModelRegistry';
import { ExperimentTracker } from './ExperimentTracker';
import { AddAiSystemModal } from './AddAiSystemModal';
import { AutonomousRiskRemediation } from './AutonomousRiskRemediation';
import { generateRiskRemediationPlan } from '../services/apiService';


interface AIGovernanceDashboardProps {
    aiSystems: AiSystem[];
    registeredModels: RegisteredModel[];
    modelExperiments: ModelExperiment[];
    onUpdateSystem: (system: AiSystem) => void;
    onAddNewSystem: (data: Omit<AiSystem, 'id' | 'tenantId' | 'lastAssessmentDate' | 'fairnessMetrics' | 'impactAssessment' | 'risks' | 'documentation' | 'controls' | 'performanceData' | 'securityAlerts'>) => void;
    onPromoteModel: (modelId: string, toStage: ModelStage) => void;
    users: User[];
}

type GovernanceView = 'management' | 'policy' | 'registry' | 'experiments';
type DetailTabView = 'controls' | 'risk' | 'ethics' | 'docs' | 'finetuning';

const generateHistoryLog = (originalRisk: AiRisk | null, updatedRisk: AiRisk): RiskHistoryLog[] => {
    const changes: string[] = [];
    const user = "Admin User"; // In a real app, this would come from an auth context

    if (!originalRisk) {
        return [{
            id: `hist-${new Date().getTime()}`,
            timestamp: new Date().toISOString(),
            user,
            action: 'Created',
            details: 'Risk was created.'
        }];
    }
    
    if (originalRisk.title !== updatedRisk.title) changes.push(`Title changed to "${updatedRisk.title}".`);
    if (originalRisk.detail !== updatedRisk.detail) changes.push('Details were updated.');
    if (originalRisk.severity !== updatedRisk.severity) changes.push(`Severity changed from ${originalRisk.severity} to ${updatedRisk.severity}.`);
    if (originalRisk.status !== updatedRisk.status) changes.push(`Status changed from ${originalRisk.status} to ${updatedRisk.status}.`);
    if (originalRisk.mitigationStatus !== updatedRisk.mitigationStatus) changes.push(`Mitigation Status changed from ${originalRisk.mitigationStatus} to ${updatedRisk.mitigationStatus}.`);

    // Basic task change detection
    if (originalRisk.mitigationTasks.length !== updatedRisk.mitigationTasks.length) {
         changes.push(`Mitigation tasks were updated (count: ${originalRisk.mitigationTasks.length} -> ${updatedRisk.mitigationTasks.length}).`);
    } else {
        const taskChanges = originalRisk.mitigationTasks.some((origTask, index) => {
            const updatedTask = updatedRisk.mitigationTasks[index];
            return !updatedTask || origTask.status !== updatedTask.status || origTask.description !== updatedTask.description;
        });
        if(taskChanges) changes.push('One or more mitigation tasks were updated.');
    }


    if (changes.length > 0) {
        return [{
            id: `hist-${new Date().getTime()}`,
            timestamp: new Date().toISOString(),
            user,
            action: 'Edited',
            details: changes.join(' ')
        }];
    }

    return [];
};

export const AIGovernanceDashboard: React.FC<AIGovernanceDashboardProps> = ({ aiSystems, registeredModels, modelExperiments, onUpdateSystem, onAddNewSystem, onPromoteModel, users }) => {
  const [selectedSystem, setSelectedSystem] = useState<AiSystem | null>(aiSystems[0] || null);
  const [isDetailsExpanded, setIsDetailsExpanded] = useState(true);
  
  const [isRiskModalOpen, setIsRiskModalOpen] = useState(false);
  const [editingRisk, setEditingRisk] = useState<AiRisk | null>(null);
  
  const [isSystemModalOpen, setIsSystemModalOpen] = useState(false);
  const [systemToEdit, setSystemToEdit] = useState<AiSystem | null>(null);

  const [viewingRisk, setViewingRisk] = useState<AiRisk | null>(null);
  const [activeView, setActiveView] = useState<GovernanceView>('policy');
  const [activeDetailTab, setActiveDetailTab] = useState<DetailTabView>('controls');
  const [autonomousRun, setAutonomousRun] = useState<{
    status: 'idle' | 'running' | 'completed' | 'failed';
    steps: AgenticStep[];
    targetSystem: AiSystem | null;
    targetRisk: AiRisk | null;
  }>({ status: 'idle', steps: [], targetSystem: null, targetRisk: null });

  useEffect(() => {
    if (aiSystems.length > 0) {
        // If there's a selected system, find its updated version in the new props, otherwise default to the first
        const currentSelectedId = selectedSystem?.id;
        const updatedSelectedSystem = currentSelectedId ? aiSystems.find(s => s.id === currentSelectedId) : aiSystems[0];
        setSelectedSystem(updatedSelectedSystem || aiSystems[0] || null);
    } else {
        setSelectedSystem(null);
    }
  }, [aiSystems, selectedSystem?.id]);

  const recentRiskLogs = useMemo(() => {
    if (!selectedSystem) return [];
    return selectedSystem.risks
      .flatMap(risk => risk.history || []) // Safely get all history logs
      .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()) // Sort descending
      .slice(0, 5); // Take the last 5
  }, [selectedSystem]);


  const handleSelectSystem = (system: AiSystem) => {
    setSelectedSystem(aiSystems.find(s => s.id === system.id) || null);
    setIsDetailsExpanded(true); // Always expand details on new selection
    setActiveDetailTab('controls'); // Reset to default tab
  };

  const handleOpenRiskModal = (risk: AiRisk | null) => {
    setEditingRisk(risk);
    setIsRiskModalOpen(true);
  };
  
  const handleOpenSystemModal = (system: AiSystem | null) => {
      setSystemToEdit(system);
      setIsSystemModalOpen(true);
  };

  const handleViewRisk = (risk: AiRisk) => {
    setViewingRisk(risk);
  };

  const handleStartRiskRemediation = async (system: AiSystem) => {
    const highRisk = system.risks.find(r => r.status === 'Open' && (r.severity === 'Critical' || r.severity === 'High'));
    if (!highRisk) return;

    setAutonomousRun({ 
        status: 'running', 
        steps: [], 
        targetSystem: system,
        targetRisk: highRisk
    });
    try {
      for await (const step of generateRiskRemediationPlan(system, highRisk)) {
        setAutonomousRun(prev => ({
          ...prev,
          steps: [...prev.steps, step]
        }));
      }

      // After successful simulation, update the risk
      const updatedRisk: AiRisk = { 
          ...highRisk, 
          status: 'Mitigated', 
          mitigationStatus: 'Completed',
          history: [
              {
                  id: `hist-remediate-${Date.now()}`,
                  timestamp: new Date().toISOString(),
                  user: 'Omni-Agent AI',
                  action: 'AI Analyzed',
                  details: 'Autonomous remediation completed. Re-balanced dataset and triggered model retraining.'
              },
              ...(highRisk.history || [])
          ]
      };
      const updatedSystem: AiSystem = { 
          ...system, 
          risks: system.risks.map(r => r.id === updatedRisk.id ? updatedRisk : r)
      };
      onUpdateSystem(updatedSystem);

      setAutonomousRun(prev => ({ ...prev, status: 'completed' }));

    } catch (e) {
      const errorStep: AgenticStep = { type: 'observation', content: `Remediation failed: ${e instanceof Error ? e.message : 'Unknown error'}`, timestamp: new Date().toISOString() };
      setAutonomousRun(prev => ({ ...prev, status: 'failed', steps: [...prev.steps, errorStep] }));
    }
  };

  const handleSaveRisk = (riskToSave: AiRisk) => {
    if (!selectedSystem) return;
    
    const originalRisk = selectedSystem.risks.find(r => r.id === riskToSave.id) || null;
    const historyLogs = generateHistoryLog(originalRisk, riskToSave);
    
    const finalRisk = {
        ...riskToSave,
        history: [...historyLogs, ...(riskToSave.history || [])]
    };

    const riskExists = selectedSystem.risks.some(r => r.id === finalRisk.id);
    const updatedRisks = riskExists
      ? selectedSystem.risks.map(r => r.id === finalRisk.id ? finalRisk : r) // Update
      : [...selectedSystem.risks, finalRisk]; // Add

    const updatedSystem = { ...selectedSystem, risks: updatedRisks };
    
    onUpdateSystem(updatedSystem);
    
    setIsRiskModalOpen(false);
    setEditingRisk(null);
  };

  // FIX: Add missing function body and return statement
  const handleSaveSystem = (data: any) => {
      if (systemToEdit) {
          onUpdateSystem({ ...systemToEdit, ...data });
      } else {
          onAddNewSystem(data);
      }
      setIsSystemModalOpen(false);
  };

  const handleDeleteRisk = (riskId: string) => {
    if (!selectedSystem) return;

    if (window.confirm('Are you sure you want to delete this risk? This action cannot be undone.')) {
      const updatedRisks = selectedSystem.risks.filter(r => r.id !== riskId);
      const updatedSystem = { ...selectedSystem, risks: updatedRisks };
      onUpdateSystem(updatedSystem);
    }
  };
  
  const handleSystemControlsChange = (systemId: string, updatedControls: AiSystem['controls']) => {
      const systemToUpdate = aiSystems.find(s => s.id === systemId);
      if (systemToUpdate) {
          if(systemToUpdate.status === 'In Development' && updatedControls.isEnabled) {
              if (window.confirm('Enabling this system will move its status to "Active" and update its assessment date. Continue?')) {
                  const updatedSystem: AiSystem = { ...systemToUpdate, controls: updatedControls, status: 'Active', lastAssessmentDate: new Date().toISOString().split('T')[0] };
                  onUpdateSystem(updatedSystem);
              }
          } else {
              const updatedSystem = { ...systemToUpdate, controls: updatedControls };
              onUpdateSystem(updatedSystem);
          }
      }
  };

  const handleFineTuneComplete = (systemId: string, newVersion: string) => {
      const systemToUpdate = aiSystems.find(s => s.id === systemId);
      if (systemToUpdate) {
        const updatedSystem = { ...systemToUpdate, version: newVersion, lastAssessmentDate: new Date().toISOString().split('T')[0] };
        onUpdateSystem(updatedSystem);
      }
  };

  const tabBaseClasses = 'flex items-center whitespace-nowrap py-3 px-3 border-b-2 font-medium text-sm transition-colors rounded-t-lg';
  const tabInactiveClasses = 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-200 dark:hover:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-700/50';
  const tabActiveClasses = 'border-primary-500 text-primary-600 dark:text-primary-400 bg-primary-50 dark:bg-primary-900/20';

  return (
    <div className="container mx-auto">
      <h2 className="text-2xl font-semibold text-gray-800 dark:text-white mb-6">ISO 42001:2023 - AI Management System</h2>
      
      {/* Tab Navigation */}
      <div className="mb-6 border-b border-gray-200 dark:border-gray-700">
          <nav className="-mb-px flex space-x-6" aria-label="Tabs">
              <button onClick={() => setActiveView('management')} className={`flex items-center whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors ${activeView === 'management' ? 'border-primary-500 text-primary-600 dark:text-primary-400' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-200 dark:hover:border-gray-600'}`}>
                  <BookTextIcon size={18} className="mr-2" />
                  System Management
                  <span className={`ml-2 px-2 py-0.5 rounded-full text-xs font-medium ${activeView === 'management' ? 'bg-primary-100 dark:bg-primary-900 text-primary-600 dark:text-primary-300' : 'bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-300'}`}>
                      {aiSystems.length}
                  </span>
              </button>
              <button onClick={() => setActiveView('registry')} className={`flex items-center whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors ${activeView === 'registry' ? 'border-primary-500 text-primary-600 dark:text-primary-400' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-200 dark:hover:border-gray-600'}`}>
                  <BoxIcon size={18} className="mr-2" />
                  Model Registry
              </button>
              <button onClick={() => setActiveView('experiments')} className={`flex items-center whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors ${activeView === 'experiments' ? 'border-primary-500 text-primary-600 dark:text-primary-400' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-200 dark:hover:border-gray-600'}`}>
                  <BrainCircuitIcon size={18} className="mr-2" />
                  Experiment Tracking
              </button>
              <button onClick={() => setActiveView('policy')} className={`flex items-center whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors ${activeView === 'policy' ? 'border-primary-500 text-primary-600 dark:text-primary-400' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-200 dark:hover:border-gray-600'}`}>
                  <GavelIcon size={18} className="mr-2" />
                  Governance Policy
              </button>
          </nav>
      </div>

      {activeView === 'management' && (
        <>
            <AIGovernanceSummary aiSystems={aiSystems} />
            {autonomousRun.status !== 'idle' && (
                <AutonomousRiskRemediation 
                    runState={autonomousRun} 
                    onClose={() => setAutonomousRun({ status: 'idle', steps: [], targetSystem: null, targetRisk: null })}
                />
            )}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="lg:col-span-1 space-y-6">
                    <AiSystemRegistry 
                        systems={aiSystems}
                        selectedSystem={selectedSystem}
                        onSelectSystem={handleSelectSystem}
                        onAddNewSystem={() => handleOpenSystemModal(null)}
                    />
                    {selectedSystem && <RiskHistory logs={recentRiskLogs} />}
                </div>
                <div className="lg:col-span-2">
                    {selectedSystem ? (
                        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md">
                            <AiSystemDetails 
                                system={selectedSystem}
                                isExpanded={isDetailsExpanded}
                                onToggleExpand={() => setIsDetailsExpanded(prev => !prev)}
                                onEdit={() => handleOpenSystemModal(selectedSystem)}
                                onStartRemediation={handleStartRiskRemediation}
                             />

                            <div className="p-4 border-t border-gray-200 dark:border-gray-700">
                                <AiSystemPerformance system={selectedSystem} />
                            </div>

                            <div className="border-b border-t border-gray-200 dark:border-gray-700">
                                <nav className="-mb-px flex space-x-2 px-4" aria-label="Tabs">
                                    <button onClick={() => setActiveDetailTab('controls')} className={`${tabBaseClasses} ${activeDetailTab === 'controls' ? tabActiveClasses : tabInactiveClasses}`}>
                                        <SlidersHorizontalIcon size={16} className="mr-2"/> Controls
                                    </button>
                                    <button onClick={() => setActiveDetailTab('risk')} className={`${tabBaseClasses} ${activeDetailTab === 'risk' ? tabActiveClasses : tabInactiveClasses}`}>
                                        <ActivityIcon size={16} className="mr-2"/> Risk Management
                                    </button>
                                    <button onClick={() => setActiveDetailTab('ethics')} className={`${tabBaseClasses} ${activeDetailTab === 'ethics' ? tabActiveClasses : tabInactiveClasses}`}>
                                        <ScaleIcon size={16} className="mr-2"/> Ethics & Fairness
                                    </button>
                                    <button onClick={() => setActiveDetailTab('docs')} className={`${tabBaseClasses} ${activeDetailTab === 'docs' ? tabActiveClasses : tabInactiveClasses}`}>
                                        <FileCodeIcon size={16} className="mr-2"/> Documentation
                                    </button>
                                    <button onClick={() => setActiveDetailTab('finetuning')} className={`${tabBaseClasses} ${activeDetailTab === 'finetuning' ? tabActiveClasses : tabInactiveClasses}`}>
                                        <BrainCircuitIcon size={16} className="mr-2"/> Fine-Tuning
                                    </button>
                                </nav>
                            </div>

                            <div className="p-4">
                                {activeDetailTab === 'controls' && (
                                    <div className="space-y-6">
                                        <AiSystemControls system={selectedSystem} onControlsChange={handleSystemControlsChange} />
                                    </div>
                                )}
                                {activeDetailTab === 'risk' && (
                                    <div className="space-y-6">
                                        <AiRiskManagement 
                                            system={selectedSystem}
                                            onViewRisk={handleViewRisk}
                                            onEditRisk={handleOpenRiskModal}
                                            onAddRisk={() => handleOpenRiskModal(null)}
                                            onDeleteRisk={handleDeleteRisk}
                                        />
                                    </div>
                                )}
                                {activeDetailTab === 'ethics' && (
                                    <div className="space-y-6">
                                        <ImpactAssessment system={selectedSystem} />
                                        <FairnessMetrics system={selectedSystem} />
                                    </div>
                                )}
                                {activeDetailTab === 'docs' && <AiSystemDocumentation system={selectedSystem} />}
                                {activeDetailTab === 'finetuning' && <AiSystemFineTuning system={selectedSystem} onFineTuneComplete={handleFineTuneComplete} />}
                            </div>
                        </div>
                    ) : (
                        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md h-full flex items-center justify-center">
                            <div className="text-center text-gray-500 dark:text-gray-400 p-8">
                                <BotIcon size={48} className="mx-auto text-gray-400 dark:text-gray-500"/>
                                <p className="mt-4">No AI systems found for this tenant or none selected.</p>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </>
      )}

      {activeView === 'registry' && <ModelRegistry models={registeredModels} onPromoteModel={onPromoteModel} />}
      {activeView === 'experiments' && <ExperimentTracker experiments={modelExperiments} />}
      {activeView === 'policy' && <AIGovernancePolicy />}

      {isRiskModalOpen && (
          <RiskFormModal 
            isOpen={isRiskModalOpen}
            onClose={() => setIsRiskModalOpen(false)}
            onSave={handleSaveRisk}
            risk={editingRisk}
          />
      )}

      {viewingRisk && (
        <RiskDetailModal
            isOpen={!!viewingRisk}
            onClose={() => setViewingRisk(null)}
            risk={viewingRisk}
        />
      )}

      <AddAiSystemModal 
        isOpen={isSystemModalOpen}
        onClose={() => setIsSystemModalOpen(false)}
        onSave={handleSaveSystem}
        users={users}
        systemToEdit={systemToEdit}
      />
    </div>
  );
};
