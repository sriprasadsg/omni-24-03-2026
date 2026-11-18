import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Activity, AlertCircle, Bot, Box, Download, Grid3x3, Layers, LayoutDashboard, Search, ShieldAlert, Workflow } from 'lucide-react';
import { SecurityCase, SecurityEvent, Playbook, Comment, ThreatIntelResult, User } from '../types';
import { SecurityEventsFeed } from './SecurityEventsFeed';
import { CaseManagement } from './CaseManagement';
import { PlaybookManager } from './PlaybookManager';
import { AiInsights } from './AiInsights';
import { CaseDetailModal } from './CaseDetailModal';
import { useUser } from '../contexts/UserContext';
import { ExecutePlaybookModal } from './ExecutePlaybookModal';
import { GeneratePlaybookModal } from './GeneratePlaybookModal';
import { ThreatIntelModal } from './ThreatIntelModal';
import * as api from '../services/apiService';
import { authFetch } from '../services/apiService';
import { socketService } from '../services/socketService';
import { ThreatIntelFeed } from './ThreatIntelFeed';
import { showToast } from '../utils/toast';
import { Skeleton } from './ui/skeleton';
import { LiveStatus, PageHeader, ghostButton, useLiveData } from './network/NetworkKit';
import { SOC_RANGES, fetchApprovals, fetchSocSummary, revokeApproval, type Approval, type SocAlert, type SocRange } from './security/soc/socData';
import { SocKpis } from './security/soc/SocKpis';
import { AlertTrend } from './security/soc/AlertTrend';
import { DetectionHealth, EndpointsAtRisk, MitreTechniques, TopDetections, type QueueFocus } from './security/soc/SocPanels';
import { AlertQueue } from './security/soc/AlertQueue';
import { AlertDrawer } from './security/soc/AlertDrawer';
import { IncidentsTab } from './security/soc/IncidentsTab';
import { CoverageTab } from './security/soc/CoverageTab';
import { RulesTab } from './security/soc/RulesTab';
import { HuntTab } from './security/soc/HuntTab';
import { WatchlistPanel } from './security/soc/WatchlistPanel';
import { SlaPanel } from './security/soc/SlaPanel';
import { segment, segmented } from './security/soc/SocKit';

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

type Tab = 'overview' | 'incidents' | 'queue' | 'hunt' | 'coverage' | 'rules' | 'cases' | 'playbooks' | 'events';

// New alerts are pushed (security_alert) as agents raise them; this poll catches anything a push missed.
const POLL_MS = 30_000;
const PUSH_REFRESH_MS = 5_000;

/**
 * Security Operations Center (the Security Overview screen): live alerts from every detection,
 * the queue analysts work, cases, playbooks and the older event feed.
 */
export const SecurityDashboard: React.FC<SecurityDashboardProps> = (props) => {
    const {
        securityCases, playbooks, securityEvents,
        users, onCaseUpdate, onGeneratePlaybook, onAnalyzeImpact,
        threatIntelFeed
    } = props;

    const { currentUser } = useUser();
    const [tab, setTab] = useState<Tab>('overview');
    const [range, setRange] = useState<SocRange>('24h');
    const [focus, setFocus] = useState<QueueFocus | null>(null);
    const [openAlert, setOpenAlert] = useState<SocAlert | null>(null);
    const [queueKey, setQueueKey] = useState(0);
    const [approvals, setApprovals] = useState<Approval[] | null>(null);
    const [revoking, setRevoking] = useState<string | null>(null);
    const [streamUp, setStreamUp] = useState(socketService.connected);
    // Cases opened from alerts here, until App's own list has them.
    const [casesFromAlerts, setCasesFromAlerts] = useState<SecurityCase[]>([]);
    const [viewingCase, setViewingCase] = useState<SecurityCase | null>(null);
    const [playbookToExecute, setPlaybookToExecute] = useState<Playbook | null>(null);
    const [isGeneratePlaybookModalOpen, setIsGeneratePlaybookModalOpen] = useState(false);
    const [threatIntelResultForModal, setThreatIntelResultForModal] = useState<ThreatIntelResult | null>(null);
    // Server answers to Enable/Disable, laid over the playbooks App loaded.
    const [playbookEnabled, setPlaybookEnabled] = useState<Record<string, boolean>>({});
    // Lookups made on this screen, shown ahead of the feed App loaded.
    const [newLookups, setNewLookups] = useState<ThreatIntelResult[]>([]);

    const fetcher = useCallback(() => fetchSocSummary(authFetch, range), [range]);
    const live = useLiveData(fetcher, POLL_MS);
    const { refresh, paused, data } = live;
    const pausedRef = useRef(paused);
    pausedRef.current = paused;
    const rangeLong = SOC_RANGES.find(r => r.key === range)?.long ?? range;

    const firstRun = useRef(true);
    useEffect(() => {
        if (firstRun.current) { firstRun.current = false; return; }
        refresh();
    }, [range, refresh]);

    const loadApprovals = useCallback(() => {
        fetchApprovals(authFetch).then(setApprovals).catch(() => setApprovals([]));
    }, []);
    useEffect(() => { loadApprovals(); }, [loadApprovals]);

    useEffect(() => {
        let last = 0;
        const onPush = () => {
            if (pausedRef.current || Date.now() - last < PUSH_REFRESH_MS) return;
            last = Date.now();
            refresh();
            setQueueKey(k => k + 1);
        };
        socketService.on('security_alert', onPush);
        const tick = setInterval(() => setStreamUp(socketService.connected), 5000);
        return () => { socketService.off('security_alert', onPush); clearInterval(tick); };
    }, [refresh]);

    const cases = useMemo(
        () => [...casesFromAlerts.filter(c => !securityCases.some(s => s.id === c.id)), ...securityCases],
        [casesFromAlerts, securityCases],
    );

    useEffect(() => {
        if (viewingCase) {
            const updatedCase = cases.find(c => c.id === viewingCase.id);
            if (updatedCase) {
                if (updatedCase !== viewingCase) setViewingCase(updatedCase);
            } else {
                setViewingCase(null);
            }
        }
    }, [cases, viewingCase]);

    const shownPlaybooks = playbooks.map(p => (p.id in playbookEnabled ? { ...p, enabled: playbookEnabled[p.id] } : p));
    const shownThreatIntel = [...newLookups, ...threatIntelFeed.filter(t => !newLookups.some(n => n.id === t.id))];
    const dayAgo = Date.now() - 24 * 60 * 60 * 1000;
    const eventsLast24h = securityEvents.filter(e => new Date(e.timestamp).getTime() >= dayAgo).length;

    const showQueue = (f: QueueFocus) => { setFocus(f); setTab('queue'); };
    const exportCsv = async (kind: 'alerts' | 'incidents') => {
        try {
            const res = await authFetch(`/api/security/soc/report.csv?kind=${kind}&range=${range}`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const url = URL.createObjectURL(await res.blob());
            const a = document.createElement('a');
            a.href = url; a.download = `soc-${kind}-${range}.csv`; a.click();
            URL.revokeObjectURL(url);
        } catch (e) {
            showToast(`The ${kind} export failed: ${e instanceof Error ? e.message : 'unknown error'}`, 'error');
        }
    };
    const alertsChanged = () => { refresh(); setQueueKey(k => k + 1); };

    const handleAddComment = async (caseId: string, content: string) => {
      if (!currentUser) return;
      const targetCase = cases.find(c => c.id === caseId);
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

    const handleCaseFromAlert = (caseItem: Record<string, unknown>) => {
        const opened = caseItem as unknown as SecurityCase;
        setCasesFromAlerts(prev => (prev.some(c => c.id === opened.id) ? prev : [opened, ...prev]));
        setOpenAlert(null);
        setTab('cases');
        setViewingCase(opened);
        alertsChanged();
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
        setTab('cases');
    };

    const handleRunPlaybook = (_event: SecurityEvent) => {
        // A disabled playbook is never offered from an event.
        const runnable = shownPlaybooks.find(p => p.enabled !== false);
        if (runnable) {
            setPlaybookToExecute(runnable);
        } else {
            setTab('playbooks');
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

            const relatedCase = cases.find(c => c.relatedEvents.some(e => e.id === event.id));
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

    const handleRevoke = async (approval: Approval) => {
        setRevoking(approval.id);
        try {
            await revokeApproval(authFetch, approval.id);
            showToast(`${approval.process} is no longer approved; its next detection raises an alert`, 'success');
            loadApprovals();
        } catch (e) {
            showToast(e instanceof Error ? e.message : 'The approval was not removed', 'error');
        } finally {
            setRevoking(null);
        }
    };

    const tabs: { id: Tab; label: string; icon: React.ReactNode; count?: number }[] = [
        { id: 'overview', label: 'Overview', icon: <LayoutDashboard size={15} /> },
        { id: 'incidents', label: 'Incidents', icon: <Layers size={15} />, count: data?.counts?.activeIncidents },
        { id: 'queue', label: 'Alert queue', icon: <ShieldAlert size={15} />, count: data?.kpis?.active },
        { id: 'hunt', label: 'Hunting', icon: <Search size={15} />, count: data?.counts?.savedHunts },
        { id: 'coverage', label: 'ATT&CK coverage', icon: <Grid3x3 size={15} /> },
        { id: 'rules', label: 'Automation', icon: <Workflow size={15} /> },
        { id: 'cases', label: 'Cases', icon: <Box size={15} />, count: cases.length },
        { id: 'playbooks', label: 'Playbooks', icon: <Bot size={15} />, count: playbooks.length },
        { id: 'events', label: 'Event feed', icon: <Activity size={15} />, count: securityEvents.length },
    ];
    const typeOptions = data?.sources?.map(s => ({ type: s.type, label: s.label })) ?? [];

    const overview = () => {
        if (!data) {
            return live.error ? (
                <div role="alert" className="rounded-2xl border border-red-200 dark:border-red-500/30 bg-red-50 dark:bg-red-500/10 p-5 flex items-start gap-3">
                    <AlertCircle className="w-5 h-5 text-red-600 dark:text-red-400 mt-0.5" aria-hidden="true" />
                    <div className="flex-1">
                        <p className="font-medium text-red-800 dark:text-red-200">The security overview could not be loaded</p>
                        <p className="mt-1 text-sm text-red-700 dark:text-red-300">{live.error}</p>
                    </div>
                    <button type="button" onClick={refresh} className={ghostButton}>Try again</button>
                </div>
            ) : (
                <div className="space-y-3" aria-busy="true">
                    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">{[0, 1, 2, 3].map(i => <Skeleton key={i} variant="card" height={132} />)}</div>
                    <Skeleton variant="card" height={320} />
                </div>
            );
        }
        return (
            <div className="space-y-3">
                <SocKpis data={data} rangeLabel={rangeLong} />
                <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,65fr)_minmax(0,35fr)] gap-3">
                    <AlertTrend data={data} rangeLabel={rangeLong} />
                    <TopDetections data={data} rangeLabel={rangeLong} onFocus={showQueue} />
                </div>
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                    <EndpointsAtRisk data={data} onFocus={showQueue} />
                    <MitreTechniques data={data} />
                </div>
                <DetectionHealth data={data} approvals={approvals} onRevoke={handleRevoke} busyId={revoking} />
            </div>
        );
    };

    const renderActiveView = () => {
        switch (tab) {
            case 'overview':
                return overview();
            case 'incidents':
                return <IncidentsTab reloadKey={queueKey} onOpenAlert={setOpenAlert} onCaseOpened={handleCaseFromAlert} onChanged={alertsChanged} />;
            case 'queue':
                return <AlertQueue focus={focus} onClearFocus={() => setFocus(null)} types={typeOptions} reloadKey={queueKey} onOpen={setOpenAlert} onChanged={alertsChanged} />;
            case 'hunt':
                return <HuntTab />;
            case 'coverage':
                return <CoverageTab range={range} rangeLabel={rangeLong} />;
            case 'rules':
                return <div className="space-y-3"><RulesTab types={typeOptions} /><SlaPanel /><WatchlistPanel /></div>;
            case 'events':
                return (
                    <div className="space-y-5">
                        <p className="text-sm text-gray-600 dark:text-gray-300">
                            Events posted to the platform's event feed: <span className="font-semibold tabular-nums">{eventsLast24h}</span> in the last 24 hours, {securityEvents.length} in the feed.
                            Agent detections are in the alert queue.
                        </p>
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
                return <CaseManagement cases={cases} onViewCase={setViewingCase} />;
            case 'playbooks':
                return <PlaybookManager playbooks={shownPlaybooks} onExecutePlaybook={setPlaybookToExecute} onGeneratePlaybook={() => setIsGeneratePlaybookModalOpen(true)} onTogglePlaybook={handleTogglePlaybook} />;
            default:
                return null;
        }
    };

    return (
        <div className="space-y-4 pb-8 fade-in">
            <PageHeader
                title="Security Operations Center"
                subtitle="Alerts from your endpoints, who is handling them, and how detection is doing"
                status={
                    <span title={streamUp ? 'New alerts are pushed as agents raise them' : `Refreshing every ${POLL_MS / 1000} s; live push is not connected`}>
                        <LiveStatus updatedAt={live.updatedAt} error={live.error} paused={paused} liveLabel={streamUp ? 'Stream: Live' : 'Live (polling)'} />
                    </span>
                }
                paused={paused}
                onTogglePause={() => live.setPaused(p => !p)}
                onRefresh={alertsChanged}
                refreshing={live.loading}
            >
                <button type="button" className={ghostButton} onClick={() => exportCsv('alerts')} title={`Alerts of the last ${rangeLong} as CSV`}>
                    <Download className="w-4 h-4" aria-hidden="true" />Export alerts
                </button>
                <button type="button" className={ghostButton} onClick={() => exportCsv('incidents')} title={`Incidents of the last ${rangeLong} as CSV`}>
                    <Download className="w-4 h-4" aria-hidden="true" />Export incidents
                </button>
                <div role="group" aria-label="Time range" className={segmented}>
                    {SOC_RANGES.map(r => (
                        <button key={r.key} type="button" aria-pressed={range === r.key} onClick={() => setRange(r.key)} className={`${segment(range === r.key)} font-mono`}>{r.label}</button>
                    ))}
                </div>
            </PageHeader>

            <div className="border-b border-gray-200/80 dark:border-white/[0.07]">
                <nav className="-mb-px flex gap-6 overflow-x-auto" aria-label="Security views">
                    {tabs.map(t => (
                        <button
                            key={t.id}
                            type="button"
                            onClick={() => setTab(t.id)}
                            aria-current={tab === t.id ? 'page' : undefined}
                            className={`flex items-center gap-1.5 whitespace-nowrap py-3 border-b-2 text-sm font-medium transition-colors ${tab === t.id
                                ? 'border-primary-500 text-gray-900 dark:border-primary-400 dark:text-white'
                                : 'border-transparent text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-200'}`}
                        >
                            <span className={tab === t.id ? 'text-primary-600 dark:text-primary-400' : ''} aria-hidden="true">{t.icon}</span>
                            {t.label}
                            {t.count !== undefined && (
                                <span className={`ml-0.5 px-1.5 py-px rounded-full text-[11px] font-semibold tabular-nums ${tab === t.id ? 'bg-primary-500/15 text-primary-700 dark:text-primary-300' : 'bg-gray-100 text-gray-600 dark:bg-white/[0.06] dark:text-gray-400'}`}>{t.count}</span>
                            )}
                        </button>
                    ))}
                </nav>
            </div>

            {renderActiveView()}

            {openAlert && (
                <AlertDrawer alert={openAlert} onClose={() => setOpenAlert(null)} onCaseOpened={handleCaseFromAlert}
                    onChanged={() => { alertsChanged(); loadApprovals(); }} />
            )}
            <CaseDetailModal
                isOpen={!!viewingCase}
                onClose={() => setViewingCase(null)}
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
                cases={cases}
            />
            <GeneratePlaybookModal
                isOpen={isGeneratePlaybookModalOpen}
                onClose={() => setIsGeneratePlaybookModalOpen(false)}
                onGenerate={onGeneratePlaybook}
            />
        </div>
    );
};
