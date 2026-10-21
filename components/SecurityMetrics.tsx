import React, { useMemo, useContext } from 'react';
import { SecurityEvent, SecurityCase, AlertSeverity } from '../types';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { ThemeContext } from '../contexts/ThemeContext';
import { BarChart3Icon } from './icons';

interface SecurityMetricsProps {
    securityEvents: SecurityEvent[];
    securityCases: SecurityCase[];
}

const severityOrder: AlertSeverity[] = ['Low', 'Medium', 'High', 'Critical'];

const ChartCard: React.FC<{ title: string; note: string; empty?: string; children: React.ReactNode }> = ({ title, note, empty, children }) => (
    <section aria-label={title} className="rounded-2xl bg-white dark:bg-gray-800 border border-gray-200/80 dark:border-white/[0.07] shadow-card p-5">
        <h3 className="text-[15px] font-semibold text-gray-900 dark:text-white">{title}</h3>
        <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">{note}</p>
        <div className="mt-4 h-64">
            {empty ? (
                <div className="h-full grid place-items-center text-center">
                    <div>
                        <BarChart3Icon size={24} className="mx-auto text-gray-400" />
                        <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">{empty}</p>
                    </div>
                </div>
            ) : children}
        </div>
    </section>
);

export const SecurityMetrics: React.FC<SecurityMetricsProps> = ({ securityEvents, securityCases }) => {
    const { theme } = useContext(ThemeContext);
    // Space-ramp neutrals and the cyan accent (design-system/omni-agent-2030/MASTER.md).
    const dark = theme === 'dark';
    const gridColor = dark ? 'rgba(255,255,255,0.07)' : '#E3E8EF';
    const textColor = dark ? '#8F9BB0' : '#637089';
    const tooltipStyle = { backgroundColor: dark ? '#161E30' : '#FFFFFF', border: `1px solid ${dark ? 'rgba(255,255,255,0.1)' : '#E3E8EF'}`, borderRadius: '0.75rem', fontSize: '0.8125rem' };

    const alertVolumeData = useMemo(() => {
        // Days are UTC dates (event timestamps are ISO UTC), so the labels are too.
        const last7Days = Array.from({ length: 7 }, (_, i) => {
            const d = new Date();
            d.setDate(d.getDate() - i);
            return d.toISOString().split('T')[0];
        }).reverse();

        const data = last7Days.map(date => {
            const dayEvents = securityEvents.filter(e => e.timestamp.startsWith(date));
            return {
                date: new Date(date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' }),
                Critical: dayEvents.filter(e => e.severity === 'Critical').length,
                High: dayEvents.filter(e => e.severity === 'High').length,
                Medium: dayEvents.filter(e => e.severity === 'Medium').length,
                Low: dayEvents.filter(e => e.severity === 'Low').length,
            };
        });
        return data;
    }, [securityEvents]);
    const weekTotal = alertVolumeData.reduce((sum, d) => sum + d.Critical + d.High + d.Medium + d.Low, 0);

    const resolvedCount = securityCases.filter(c => c.status === 'Resolved').length;
    const caseResolutionData = useMemo(() => {
        const resolvedCases = securityCases.filter(c => c.status === 'Resolved');
        const resolutionTimes: Record<AlertSeverity, { totalTime: number, count: number }> = {
            Critical: { totalTime: 0, count: 0 },
            High: { totalTime: 0, count: 0 },
            Medium: { totalTime: 0, count: 0 },
            Low: { totalTime: 0, count: 0 },
        };

        resolvedCases.forEach(c => {
            const created = new Date(c.createdAt).getTime();
            const resolved = new Date(c.updatedAt).getTime(); // Assuming updatedAt on resolve is resolution time
            const timeDiffHours = (resolved - created) / (1000 * 60 * 60);

            if (resolutionTimes[c.severity]) {
                resolutionTimes[c.severity].totalTime += timeDiffHours;
                resolutionTimes[c.severity].count++;
            }
        });

        return severityOrder.map(severity => ({
            name: severity,
            'Avg Resolution (hrs)': resolutionTimes[severity].count > 0 ? parseFloat((resolutionTimes[severity].totalTime / resolutionTimes[severity].count).toFixed(2)) : 0,
        }));

    }, [securityCases]);


    return (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            <ChartCard title="Event volume, last 7 days" note="Events per day (UTC) by severity" empty={weekTotal === 0 ? 'No events in the last 7 days.' : undefined}>
                <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={alertVolumeData}>
                        <CartesianGrid strokeDasharray="3 3" stroke={gridColor} vertical={false} />
                        <XAxis dataKey="date" stroke={textColor} fontSize={12} tickLine={false} axisLine={false} />
                        <YAxis stroke={textColor} fontSize={12} tickLine={false} axisLine={false} allowDecimals={false} />
                        <Tooltip contentStyle={tooltipStyle} labelStyle={{ color: textColor }} cursor={{ fill: dark ? 'rgba(255,255,255,0.04)' : 'rgba(6,10,20,0.04)' }} />
                        <Legend wrapperStyle={{ fontSize: '12px' }} itemSorter={item => -severityOrder.indexOf(item.value as AlertSeverity)} />
                        <Bar dataKey="Critical" stackId="a" fill="#ef4444" />
                        <Bar dataKey="High" stackId="a" fill="#f97316" />
                        <Bar dataKey="Medium" stackId="a" fill="#f59e0b" />
                        <Bar dataKey="Low" stackId="a" fill="#3b82f6" />
                    </BarChart>
                </ResponsiveContainer>
            </ChartCard>
            <ChartCard title="Average time to resolve" note="Hours from opening to the last update, resolved cases only" empty={resolvedCount === 0 ? 'No resolved cases yet.' : undefined}>
                <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={caseResolutionData} layout="vertical" margin={{ left: 10 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke={gridColor} horizontal={false} />
                        <XAxis type="number" stroke={textColor} fontSize={12} tickLine={false} axisLine={false} />
                        <YAxis type="category" dataKey="name" stroke={textColor} fontSize={12} width={60} tickLine={false} axisLine={false} />
                        <Tooltip contentStyle={tooltipStyle} labelStyle={{ color: textColor }} cursor={{ fill: dark ? 'rgba(255,255,255,0.04)' : 'rgba(6,10,20,0.04)' }} />
                        <Bar dataKey="Avg Resolution (hrs)" fill="#0891B2" barSize={18} radius={[0, 4, 4, 0]} />
                    </BarChart>
                </ResponsiveContainer>
            </ChartCard>
        </div>
    );
};
