





import React, { useState, useEffect } from 'react';
import { SecurityCase, SecurityEvent, Playbook, Comment, ThreatIntelResult, User, SecurityView } from '../types';
// FIX: Replaced non-existent BoxIcon with BotIcon and added BoxIcon to icons.tsx.
import { ShieldZapIcon, ActivityIcon, BoxIcon, BotIcon, BarChart3Icon, XIcon, CheckIcon, AlertTriangleIcon, ShieldSearchIcon, ExternalLinkIcon } from './icons';
import { SecurityEventsFeed } from './SecurityEventsFeed';
import { CaseManagement } from './CaseManagement';
import { PlaybookManager } from './PlaybookManager';
import { AiInsights } from './AiInsights';
import { CaseDetailModal } from './CaseDetailModal';
import { useUser } from '../contexts/UserContext';
import { ExecutePlaybookModal } from './ExecutePlaybookModal';
import { SecurityMetrics } from './SecurityMetrics';
import { GeneratePlaybookModal } from './GeneratePlaybookModal';
import { ThreatIntelModal } from './ThreatIntelModal';
import * as api from '../services/apiService';
import { ThreatIntelFeed } from './ThreatIntelFeed';

interface SecurityDashboardProps {
    securityCases: SecurityCase[];
    playbooks: Playbook[];
    securityEvents: SecurityEvent[];
    users: User[];
    onCaseUpdate: (caseItem: SecurityCase) => Promise<SecurityCase>;
    onGeneratePlaybook: (prompt: string) => Promise<void>;
    onAnalyzeImpact: (type: 'case' | 'alert', id: string) => void;
    threatIntelFeed: ThreatIntelResult[];
}

export const SecurityDashboard: React.FC<SecurityDashboardProps> = (props) => {
    const { 
        securityCases, playbooks, securityEvents, 
        users, onCaseUpdate, onGeneratePlaybook, onAnalyzeImpact,
        threatIntelFeed
    } = props;

    const { currentUser } = useUser();
    const [activeView, setActiveView] = useState<SecurityView>('events');
    const [viewingCase, setViewingCase] = useState<SecurityCase | null>(null);
    const [playbookToExecute, setPlaybookToExecute] = useState<Playbook | null>(null);
    const [isGeneratePlaybookModalOpen, setIsGeneratePlaybookModalOpen] = useState(false);
    const [threatIntelResultForModal, setThreatIntelResultForModal] = useState<ThreatIntelResult | null>(null);

    useEffect(() => {
        if (viewingCase) {
            const updatedCase = securityCases.find(c => c.id === viewingCase.id);
            if (updatedCase) {
                setViewingCase(updatedCase);
            } else {
                setViewingCase(null);
            }
        }
    }, [securityCases, viewingCase]);
    
    const openCases = securityCases.filter(c => c.status !== 'Resolved').length;
    const criticalEvents = securityEvents.filter(e => e.severity === 'Critical').length;
    const highEvents = securityEvents.filter(e => e.severity === 'High').length;

    const handleViewCase = (caseItem: SecurityCase) => {
      setViewingCase(caseItem);
    };

    const handleCloseCaseModal = () => {
      setViewingCase(null);
    };

    const handleAddComment = async (caseId: string, content: string) => {
      if (!currentUser) return;
      const targetCase = securityCases.find(c => c.id === caseId);
      if (!targetCase) return;

      const newComment: Comment = {
        id: `comment-${Date.now()}`,
        timestamp: new Date().toISOString(),
        user: currentUser.name,
        content: content,
      };

      const updatedCase = { ...targetCase, comments: [...targetCase.comments, newComment] };
      const result = await onCaseUpdate(updatedCase);
      setViewingCase(result);
    };

    const handleScanArtifact = async (event: SecurityEvent, artifact: string, type: 'ip' | 'hash' | 'domain') => {
        try {
            const result = await api.scanArtifactWithVirusTotal(artifact, type);
            setThreatIntelResultForModal(result);
            
            const relatedCase = securityCases.find(c => c.relatedEvents.some(e => e.id === event.id));
            if (relatedCase) {
                const isAlreadyEnriched = relatedCase.enrichmentData.some(e => e.artifact === artifact);
                if (!isAlreadyEnriched) {
                    const updatedCase = { ...relatedCase, enrichmentData: [...relatedCase.enrichmentData, result] };
                    onCaseUpdate(updatedCase);
                }
            }
        } catch (error) {
            alert(`Failed to scan artifact: ${error instanceof Error ? error.message : 'Unknown error'}`);
        }
    };

    const renderActiveView = () => {
        switch (activeView) {
            case 'metrics':
                return <SecurityMetrics securityEvents={securityEvents} securityCases={securityCases} />;
            case 'events':
                return (
                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                        <div className="lg:col-span-2 space-y-6">
                            <SecurityEventsFeed events={securityEvents} onScanArtifact={handleScanArtifact} />
                            <ThreatIntelFeed feed={threatIntelFeed} onViewReport={setThreatIntelResultForModal} />
                        </div>
                        <div className="lg:col-span-1">
                            <AiInsights securityEvents={securityEvents} />
                        </div>
                    </div>
                );
            case 'cases':
                return <CaseManagement cases={securityCases} onViewCase={handleViewCase} />;
            case 'playbooks':
                return <PlaybookManager playbooks={playbooks} onExecutePlaybook={setPlaybookToExecute} onGeneratePlaybook={() => setIsGeneratePlaybookModalOpen(true)} />;
            default:
                return null;
        }
    };

    return (
        <div className="container mx-auto">
            <h2 className="text-2xl font-semibold text-gray-800 dark:text-white mb-2">Security Operations Center</h2>
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">Unified SIEM, XDR, and SOAR capabilities for proactive threat detection and response.</p>
            
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 md:gap-6 mb-6">
                <div className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow-md">
                    <p className="text-sm text-gray-500 dark:text-gray-400">Active Events (24h)</p>
                    <p className="text-2xl font-bold">{securityEvents.length}</p>
                </div>
                <div className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow-md">
                    <p className="text-sm text-gray-500 dark:text-gray-400">Open Cases</p>
                    <p className="text-2xl font-bold text-amber-500">{openCases}</p>
                </div>
                <div className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow-md">
                    <p className="text-sm text-gray-500 dark:text-gray-400">Critical Events</p>
                    <p className="text-2xl font-bold text-red-500">{criticalEvents}</p>
                </div>
                 <div className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow-md">
                    <p className="text-sm text-gray-500 dark:text-gray-400">High Severity Events</p>
                    <p className="text-2xl font-bold text-orange-500">{highEvents}</p>
                </div>
            </div>

            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md">
                <div className="border-b border-gray-200 dark:border-gray-700">
                    <nav className="-mb-px flex space-x-6 px-4" aria-label="Tabs">
                        <button onClick={() => setActiveView('metrics')} className={`flex items-center whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors ${activeView === 'metrics' ? 'border-primary-500 text-primary-600 dark:text-primary-400' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'}`}>
                           <BarChart3Icon size={18} className="mr-2"/> Metrics
                        </button>
                        <button onClick={() => setActiveView('events')} className={`flex items-center whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors ${activeView === 'events' ? 'border-primary-500 text-primary-600 dark:text-primary-400' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'}`}>
                           <ActivityIcon size={18} className="mr-2"/> Events Feed
                        </button>
                        <button onClick={() => setActiveView('cases')} className={`flex items-center whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors ${activeView === 'cases' ? 'border-primary-500 text-primary-600 dark:text-primary-400' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'}`}>
                           <BoxIcon size={18} className="mr-2"/> Case Management
                        </button>
                         <button onClick={() => setActiveView('playbooks')} className={`flex items-center whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors ${activeView === 'playbooks' ? 'border-primary-500 text-primary-600 dark:text-primary-400' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'}`}>
                           <BotIcon size={18} className="mr-2"/> SOAR Playbooks
                        </button>
                    </nav>
                </div>
                <div className="p-4 md:p-6">
                    {renderActiveView()}
                </div>
            </div>
            
            <CaseDetailModal 
                isOpen={!!viewingCase}
                onClose={handleCloseCaseModal}
                caseItem={viewingCase}
                onAddComment={handleAddComment}
                users={users}
                onAnalyzeImpact={onAnalyzeImpact}
            />
            <ThreatIntelModal 
                isOpen={!!threatIntelResultForModal}
                onClose={() => setThreatIntelResultForModal(null)}
                result={threatIntelResultForModal}
            />
            <ExecutePlaybookModal 
                isOpen={!!playbookToExecute}
                onClose={() => setPlaybookToExecute(null)}
                playbook={playbookToExecute}
                events={securityEvents}
                cases={securityCases}
            />
            <GeneratePlaybookModal
                isOpen={isGeneratePlaybookModalOpen}
                onClose={() => setIsGeneratePlaybookModalOpen(false)}
                onGenerate={onGeneratePlaybook}
            />
        </div>
    );
};
