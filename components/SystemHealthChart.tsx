import React, { useContext, useMemo } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { Metric } from '../types';
import { ThemeContext } from '../contexts/ThemeContext';
import { TrendingUpIcon } from './icons';

interface SystemHealthChartProps {
  metrics: Metric[];
}

export const SystemHealthChart: React.FC<SystemHealthChartProps> = ({ metrics }) => {
  const { theme } = useContext(ThemeContext);

  const chartData = useMemo(() => {
    const cpuMetric = metrics.find(m => m.type === 'cpu');
    const memoryMetric = metrics.find(m => m.type === 'memory');
    const diskMetric = metrics.find(m => m.type === 'disk');

    if (!cpuMetric || !memoryMetric || !diskMetric) {
      return [];
    }

    // Assuming all metrics have the same time points
    return cpuMetric.data.map((point, index) => ({
      time: point.time.replace(' ago', ''),
      CPU: cpuMetric.data[index].value,
      Memory: memoryMetric.data[index].value,
      Disk: diskMetric.data[index].value,
    })).reverse(); // reverse to show time progressing left-to-right
  }, [metrics]);

  // if (chartData.length === 0) {
  //   return null;
  // }

  // Force disable for debugging
  if (chartData.length === 0) {
    return null;
  }

  const gridColor = theme === 'dark' ? '#374151' : '#e5e7eb';
  const textColor = theme === 'dark' ? '#d1d5db' : '#374151';

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 shadow-md" style={{ height: '300px', width: '100%' }}>
      <div className="p-4 border-b border-gray-200 dark:border-gray-700">
        <h3 className="text-lg font-semibold flex items-center">
          <TrendingUpIcon className="mr-2 text-primary-500" />
          Overall System Health (Last 30 Mins)
        </h3>
      </div>
      <div className="p-4" style={{ height: 'calc(100% - 60px)', width: '100%' }}>
        <ResponsiveContainer width="99%" height="100%" minHeight={200}>
          <LineChart data={chartData} margin={{ top: 5, right: 20, left: -10, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
            <XAxis dataKey="time" stroke={textColor} fontSize={12} tickLine={false} axisLine={false} />
            <YAxis stroke={textColor} fontSize={12} tickLine={false} axisLine={false} unit="%" />
            <Tooltip
              contentStyle={{
                backgroundColor: theme === 'dark' ? '#1f2937' : '#ffffff',
                border: '1px solid',
                borderColor: theme === 'dark' ? '#374151' : '#e5e7eb',
                borderRadius: '0.5rem',
                fontSize: '0.875rem'
              }}
              labelStyle={{ color: textColor }}
            />
            <Legend wrapperStyle={{ fontSize: "12px" }} />
            <Line type="monotone" dataKey="CPU" stroke="#3b82f6" strokeWidth={2} dot={{ r: 2 }} />
            <Line type="monotone" dataKey="Memory" stroke="#10b981" strokeWidth={2} dot={{ r: 2 }} />
            <Line type="monotone" dataKey="Disk" stroke="#f97316" strokeWidth={2} dot={{ r: 2 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};
