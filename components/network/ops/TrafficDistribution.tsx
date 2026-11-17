import React from 'react';
import { Panel, RankedList } from '../NetworkKit';
import { formatBytes } from '../networkData';
import type { TrafficSummary } from '../opsData';

const subhead = 'text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400';

export const TrafficDistribution: React.FC<{ data: TrafficSummary; rangeLabel: string }> = ({ data, rangeLabel }) => {
    const protocols = data.protocols.filter(p => p.connections > 0 || p.name === 'HTTPS' || p.name === 'HTTP')
        .map(p => ({ key: p.name, label: p.name === 'Internal' ? 'Internal (private addresses)' : p.name, value: p.connections }));
    const totalConnections = protocols.reduce((s, p) => s + p.value, 0);
    const moved = data.endpoints
        .map(e => ({ key: e.agentId, label: e.hostname, value: e.rangeTxBytes + e.rangeRxBytes }))
        .filter(e => e.value > 0)
        .sort((a, b) => b.value - a.value);
    const top = moved.slice(0, 6);
    if (moved.length > 6) top.push({ key: '__other', label: `Other endpoints (${moved.length - 6})`, value: moved.slice(6).reduce((s, e) => s + e.value, 0) });
    const totalMoved = moved.reduce((s, e) => s + e.value, 0);

    return (
        <Panel title="Traffic distribution" note="Open connections by protocol, and data moved by endpoint">
            <h3 className={subhead}>Connections by protocol</h3>
            <div className="mt-3">
                {totalConnections ? <RankedList items={protocols} format={v => `${v} conn.`} total={totalConnections} />
                    : <p className="text-sm text-gray-500 dark:text-gray-400">No open web connections in the endpoints' latest reports.</p>}
                <p className="mt-3 flex items-baseline justify-between gap-3 text-sm text-gray-500 dark:text-gray-400">
                    <span>DNS · SSH · UDP</span>
                    <span className="inline-flex rounded-md px-1.5 py-0.5 text-[11px] font-medium bg-gray-100 dark:bg-white/[0.06]">Not collected</span>
                </p>
                <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
                    Counts come from the Web Monitor on Linux agents (ports 80, 443, 8080, 8443). Bytes per protocol are not collected.
                </p>
            </div>

            <h3 className={`${subhead} mt-6`}>Moved in the last {rangeLabel}</h3>
            <div className="mt-3">
                {top.length ? <RankedList items={top} format={v => formatBytes(v)} total={totalMoved} />
                    : <p className="text-sm text-gray-500 dark:text-gray-400">No transfer measured in this range yet.</p>}
            </div>
        </Panel>
    );
};
