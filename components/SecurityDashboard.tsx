import React, { useState, useEffect } from 'react';
import { SecurityCase, SecurityEvent, Playbook, Comment, ThreatIntelResult, User, SecurityView } from '../types';
import { ActivityIcon, BoxIcon, BotIcon, BarChart3Icon, AlertTriangleIcon, ShieldAlertIcon } from './icons';
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
import { showToast } from '../utils/toast';
import { StatTile, bigNumber } from './StatTile';

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
    // Server answers to Enable/Disable, laid over the playbooks App loaded.
    const [playbookEnabled, setPlaybookEnabled] = useState<Record<string, boolean>>({});
    // Lookups made on this screen, shown ahead of the feed App loaded.
    const [newLookups, setNewLookups] = useState<ThreatIntelResult[]>([]);

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

    const shownPlaybooks = playbooks.map(p => (p.id in playbookEnabled ? { ...p, enabled: playbookEnabled[p.id] } : p));
    const shownThreatIntel = [...newLookups, ...threatIntelFeed.filter(t => !newLookups.some(n => n.id === t.id))];

    const dayAgo = Date.now() - 24 * 60 * 60 * 1000;
    const eventsLast24h = securityEvents.filter(e => new Date(e.timestamp).getTime() >= dayAgo).length;
    const openCases = securityCases.filter(c => c.status !== 'Resolved').length;
    const newCases = securityCases.filter(c => c.status === 'New').length;
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

    const handleCreateCase = async (event: SecurityEvent) => {
        if (!currentUser) return;
        const now = new Date().toISOString();
        const newCase: SecurityCase = {
            id: `case-${Date.now()}`,
            tenantId: event.tenantId ?? '',
            title: `Case: ${event.description}`,
            status: 'New',
            severity: event.severity,
            owner: currentUser.name,
            createdAt: now,
            updatedAt: now,
            relatedEvents: [event],
            comments: [],
            enrichmentData: [],
        };
        await onCaseUpdate(newCase);
        setActiveView('cases');
    };

    const handleRunPlaybook = (event: SecurityEvent) => {
        // A disabled playbook is never offered from an event.
        const runnable = shownPlaybooks.find(p => p.enabled !== false);
        if (runnable) {
            setPlaybookToExecute(runnable);
        } else {
            setActiveView('playbooks');
        }
    };

    const handleTogglePlaybook = async (playbook: Playbook) => {
        const result = await api.togglePlaybook(playbook.id);
        if (result && typeof result.enabled === 'boolean') {
            setPlaybookEnabled(prev => ({ ...prev, [playbook.id]: result.enabled }));
        } else {
            showToast(`Couldn't ${playbook.enabled === false ? 'enable' : 'disable'} "${playbook.name}". Try again.`, 'error');
        }
    };

    const handleScanArtifact = async (event: SecurityEvent, artifact: string, type: 'ip' | 'hash' | 'domain') => {
        try {
            const result = await api.scanArtifactWithVirusTotal(artifact, type);
            setThreatIntelResultForModal(result);
            setNewLookups(prev => [result, ...prev]);

            const relatedCase = securityCases.find(c => c.relatedEvents.some(e => e.id === event.id));
            if (relatedCase) {
                const isAlreadyEnriched = relatedCase.enrichmentData.some(e => e.artifact === artifact);
                if (!isAlreadyEnriched) {
                    const updatedCase = { ...relatedCase, enrichmentData: [...relatedCase.enrichmentData, result] };
                    onCaseUpdate(updatedCase);
                }
            }
        } catch (error) {
            showToast(`Couldn't scan ${artifact}: ${error instanceof Error ? error.message : 'Unknown error'}`, 'error');
        }
    };

    const tabs: { id: SecurityView; label: string; icon: React.ReactNode; count?: number }[] = [
        { id: 'events', label: 'Events', icon: <ActivityIcon size={15} />, count: securityEvents.length },
        { id: 'cases', label: 'Cases', icon: <BoxIcon size={15} />, count: securityCases.length },
        { id: 'playbooks', label: 'Playbooks', icon: <BotIcon size={15} />, count: playbooks.length },
        { id: 'metrics', label: 'Metrics', icon: <BarChart3Icon size={15} /> },
    ];

    const renderActiveView = () => {
        switch (activeView) {
            case 'metrics':
                return <SecurityMetrics securityEvents={securityEvents} securityCases={securityCases} />;
            case 'events':
                return (
                    <div className="space-y-5">
                        <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 lg:h-[560px]">
                            <div className="lg:col-span-8 min-h-0">
                                <SecurityEventsFeed events={securityEvents} onScanArtifact={handleScanArtifact} onCreateCase={handleCreateCase} onRunPlaybook={handleRunPlaybook} />
                            </div>
                            <div className="lg:col-span-4 min-h-0">
                                <ThreatIntelFeed feed={shownThreatIntel} onViewReport={setThreatIntelResultForModal} />
                            </div>
                        </div>
                        <AiInsights securityEvents={securityEvents} />
                    </div>
                );
            case 'cases':
                return <CaseManagement cases={securityCases} onViewCase={handleViewCase} />;
            case 'playbooks':
                return <PlaybookManager playbooks={shownPlaybooks} onExecutePlaybook={setPlaybookToExecute} onGeneratePlaybook={() => setIsGeneratePlaybookModalOpen(true)} onTogglePlaybook={handleTogglePlaybook} />;
            default:
                return null;
        }
    };

    return (
        <div className="space-y-6 fade-in">
            <header>
                <h2 className="text-[30px] font-semibold tracking-[-0.03em] text-gray-900 dark:text-white">Security overview</h2>
                <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                    Events your agents raise, the cases they become and the playbooks that respond.
                </p>
            </header>

            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-5">
                <StatTile icon={<ActivityIcon size={18} />} label="Events, last 24 hours" tone="primary" footnote={`${securityEvents.length} in the feed`}>
                    <p className={`${bigNumber} text-gray-900 dark:text-white`}>{eventsLast24h}</p>
                </StatTile>
                <StatTile icon={<BoxIcon size={18} />} label="Open cases" tone="blue" footnote={newCases === 0 ? 'None waiting to be picked up' : `${newCases} not picked up yet`}>
                    <p className={`${bigNumber} text-gray-900 dark:text-white`}>{openCases}</p>
                </StatTile>
                <StatTile icon={<ShieldAlertIcon size={18} />} label="Critical events" tone="red" footnote="In the feed">
                    <p className={`${bigNumber} ${criticalEvents > 0 ? 'text-red-600 dark:text-red-400' : 'text-gray-900 dark:text-white'}`}>{criticalEvents}</p>
                </StatTile>
                <StatTile icon={<AlertTriangleIcon size={18} />} label="High-severity events" tone="orange" footnote="In the feed">
                    <p className={`${bigNumber} ${highEvents > 0 ? 'text-orange-600 dark:text-orange-400' : 'text-gray-900 dark:text-white'}`}>{highEvents}</p>
                </StatTile>
            </div>

            <div className="border-b border-gray-200/80 dark:border-white/[0.07]">
                <nav className="-mb-px flex gap-6 overflow-x-auto" aria-label="Security views">
                    {tabs.map(tab => (
                        <button
                            key={tab.id}
                            onClick={() => setActiveView(tab.id)}
                            aria-current={activeView === tab.id ? 'page' : undefined}
                            className={`flex items-center gap-1.5 whitespace-nowrap py-3 border-b-2 text-sm font-medium transition-colors ${activeView === tab.id
                                ? 'border-primary-500 text-gray-900 dark:border-primary-400 dark:text-white'
                                : 'border-transparent text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-200'}`}
                        >
                            <span className={activeView === tab.id ? 'text-primary-600 dark:text-primary-400' : ''}>{tab.icon}</span>
                            {tab.label}
                            {tab.count !== undefined && (
                                <span className={`ml-0.5 px-1.5 py-px rounded-full text-[10px] font-semibold tabular-nums ${activeView === tab.id ? 'bg-primary-500/15 text-primary-700 dark:text-primary-300' : 'bg-gray-100 text-gray-600 dark:bg-white/[0.06] dark:text-gray-400'}`}>{tab.count}</span>
                            )}
                        </button>
                    ))}
                </nav>
            </div>

            {renderActiveView()}

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
