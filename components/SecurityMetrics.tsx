import React, { useMemo, useContext } from 'react';
import { SecurityEvent, SecurityCase, AlertSeverity } from '../types';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { ThemeContext } from '../contexts/ThemeContext';

interface SecurityMetricsProps {
    securityEvents: SecurityEvent[];
    securityCases: SecurityCase[];
}

const severityOrder: AlertSeverity[] = ['Low', 'Medium', 'High', 'Critical'];

export const SecurityMetrics: React.FC<SecurityMetricsProps> = ({ securityEvents, securityCases }) => {
    const { theme } = useContext(ThemeContext);
    const gridColor = theme === 'dark' ? '#374151' : '#e5e7eb';
    const textColor = theme === 'dark' ? '#d1d5db' : '#374151';

    const alertVolumeData = useMemo(() => {
        const last7Days = Array.from({ length: 7 }, (_, i) => {
            const d = new Date();
            d.setDate(d.getDate() - i);
            return d.toISOString().split('T')[0];
        }).reverse();

        const data = last7Days.map(date => {
            const dayEvents = securityEvents.filter(e => e.timestamp.startsWith(date));
            return {
                date: new Date(date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
                Critical: dayEvents.filter(e => e.severity === 'Critical').length,
                High: dayEvents.filter(e => e.severity === 'High').length,
                Medium: dayEvents.filter(e => e.severity === 'Medium').length,
                Low: dayEvents.filter(e => e.severity === 'Low').length,
            };
        });
        return data;
    }, [securityEvents]);
    
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
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow-md">
                <h3 className="text-md font-semibold mb-4 text-gray-800 dark:text-white">Alert Volume (Last 7 Days)</h3>
                <div className="h-64">
                    <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={alertVolumeData}>
                            <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
                            <XAxis dataKey="date" stroke={textColor} fontSize={12} />
                            <YAxis stroke={textColor} fontSize={12} />
                            <Tooltip contentStyle={{ backgroundColor: theme === 'dark' ? '#1f2937' : '#ffffff', border: `1px solid ${gridColor}`, borderRadius: '0.5rem' }} />
                            <Legend wrapperStyle={{fontSize: "12px"}}/>
                            <Bar dataKey="Critical" stackId="a" fill="#ef4444" />
                            <Bar dataKey="High" stackId="a" fill="#f97316" />
                            <Bar dataKey="Medium" stackId="a" fill="#f59e0b" />
                            <Bar dataKey="Low" stackId="a" fill="#3b82f6" />
                        </BarChart>
                    </ResponsiveContainer>
                </div>
            </div>
             <div className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow-md">
                <h3 className="text-md font-semibold mb-4 text-gray-800 dark:text-white">Average Case Resolution Time</h3>
                <div className="h-64">
                    <ResponsiveContainer width="100%" height="100%">
                         <BarChart data={caseResolutionData} layout="vertical" margin={{ left: 10 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
                            <XAxis type="number" stroke={textColor} fontSize={12} />
                            <YAxis type="category" dataKey="name" stroke={textColor} fontSize={12} width={60} />
                            <Tooltip contentStyle={{ backgroundColor: theme === 'dark' ? '#1f2937' : '#ffffff', border: `1px solid ${gridColor}`, borderRadius: '0.5rem' }} />
                            <Bar dataKey="Avg Resolution (hrs)" fill="#8884d8" barSize={20} />
                        </BarChart>
                    </ResponsiveContainer>
                </div>
            </div>
        </div>
    );
};
