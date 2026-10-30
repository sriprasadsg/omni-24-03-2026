import React, { useCallback, useEffect, useRef, useState } from 'react';
import { fetchPlatformHealth } from '../services/autonomousOpsApi';
import type { PlatformHealthDocument, PlatformHealthService, ServiceState } from '../services/autonomousOpsApi';
import { formatWhen } from './AutonomousOpsActivityList';
import { HealthChip } from './AutonomousOpsHealthChips';
import type { HealthChipKind } from './AutonomousOpsHealthChips';

export const HEALTH_POLL_MS = 30_000;

interface PlatformHealthProps {
    /** The page Refresh button's counter (AutonomousOpsActivity); a change refetches the section. */
    refreshSignal?: number;
}

// The fixed order of the services grid: MongoDB first because it is restarted first (D-09).
const SERVICE_ORDER: Array<{ id: string; name: string }> = [
    { id: 'mongod', name: 'MongoDB' },
    { id: 'omni-backend', name: 'Backend' },
    { id: 'nginx', name: 'nginx' },
    { id: 'ollama', name: 'Ollama' },
];

const SERVICE_CHIP: Record<ServiceState, HealthChipKind> = {
    healthy: 'healthy', checking: 'checking', down: 'down', restarting: 'restarting', gave_up: 'gave_up',
    expected_off: 'expected_off', unexpected_running: 'notice',
};

// ── data ────────────────────────────────────────────────────────────────────

function usePlatformHealth() {
    const [doc, setDoc] = useState<PlatformHealthDocument | null>(null);
    const alive = useRef(true);

    const load = useCallback(async () => {
        try {
            const next = await fetchPlatformHealth();
            if (alive.current) setDoc(next);
        } catch { /* the tracer keeps whatever it has */ }
    }, []);

    useEffect(() => {
        alive.current = true;
        void load();
        return () => { alive.current = false; };
    }, [load]);

    return { doc };
}

// ── pieces ──────────────────────────────────────────────────────────────────

const ServiceCell: React.FC<{ order: { id: string; name: string }; service: PlatformHealthService | undefined }> = ({ order, service }) => {
    const state = service?.state ?? null;
    return (
        <div className="min-w-0">
            <dt>
                <span className="block break-words text-sm font-semibold text-gray-900 dark:text-white">{order.name}</span>
                <span className="block break-words font-mono text-xs text-gray-500 dark:text-gray-400">{service?.unit ?? order.id}</span>
            </dt>
            <dd className="mt-2 flex flex-col gap-2">
                <span><HealthChip kind={state ? SERVICE_CHIP[state] : 'unknown'} /></span>
            </dd>
        </div>
    );
};

const WatchdogRow: React.FC<{ doc: PlatformHealthDocument }> = ({ doc }) => {
    const seen = doc.watchdog.lastSeenAt ? formatWhen(doc.watchdog.lastSeenAt) : null;
    return (
        <div className="flex flex-wrap items-center justify-between gap-4">
            <dl>
                <dt className="text-xs text-gray-500 dark:text-gray-400">Watchdog</dt>
                <dd className="mt-1"><HealthChip kind={doc.watchdog.state === 'running' ? 'running' : 'unknown'} /></dd>
            </dl>
            {seen && <p className="break-words text-xs text-gray-500 dark:text-gray-400" title={seen.title}>Last seen {seen.text}.</p>}
        </div>
    );
};

/**
 * The Platform health section of the Autonomous Ops screen (D-20): the watchdog and its four services first.
 * Rendered only for a holder of control:platform_autonomous_ops in platform scope (AutonomousOpsActivity).
 */
export const AutonomousOpsPlatformHealth: React.FC<PlatformHealthProps> = () => {
    const { doc } = usePlatformHealth();

    return (
        <section id="platform-health" aria-labelledby="platform-health-title" className="space-y-6">
            <div className="flex flex-wrap items-center justify-between gap-4">
                <h2 id="platform-health-title" tabIndex={-1} className="text-lg font-semibold leading-tight text-gray-900 dark:text-white">
                    Platform health
                </h2>
            </div>
            {doc && (
                <div className="card flex flex-col gap-6 p-6">
                    <WatchdogRow doc={doc} />
                    <div className="border-t border-gray-200 pt-6 dark:border-white/10">
                        <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
                            {SERVICE_ORDER.map(order => (
                                <ServiceCell key={order.id} order={order} service={doc.services.find(s => s.id === order.id)} />
                            ))}
                        </dl>
                    </div>
                </div>
            )}
        </section>
    );
};

export default AutonomousOpsPlatformHealth;
