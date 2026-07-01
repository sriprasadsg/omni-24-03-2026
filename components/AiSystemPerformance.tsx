import React, { useContext } from 'react';
import { AiSystem } from '../types';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { TrendingUpIcon } from './icons';
import { ThemeContext } from '../contexts/ThemeContext';

interface AiSystemPerformanceProps {
  system: AiSystem;
}

export const AiSystemPerformance: React.FC<AiSystemPerformanceProps> = ({ system }) => {
  const { theme } = useContext(ThemeContext);
  const { performanceData } = system;

  if (!performanceData || performanceData.length === 0) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md">
        <div className="p-4 border-b border-gray-200 dark:border-gray-700">
          <h3 className="text-lg font-semibold flex items-center">
            <TrendingUpIcon className="mr-2 text-primary-500" />
            Model Performance
          </h3>
        </div>
        <div className="p-4 text-center text-sm text-gray-500 dark:text-gray-400">
          No performance data available for this system.
        </div>
      </div>
    );
  }

  const gridColor = theme === 'dark' ? '#374151' : '#e5e7eb';
  const textColor = theme === 'dark' ? '#d1d5db' : '#374151';

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md">
      <div className="p-4 border-b border-gray-200 dark:border-gray-700">
        <h3 className="text-lg font-semibold flex items-center">
          <TrendingUpIcon className="mr-2 text-primary-500" />
          Model Performance (Last 30 Mins)
        </h3>
      </div>
      <div className="p-4 h-80">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={performanceData} margin={{ top: 5, right: 20, left: -10, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
            <XAxis dataKey="time" stroke={textColor} fontSize={12} tickLine={false} axisLine={false} />
            <YAxis yAxisId="left" stroke={textColor} fontSize={12} tickLine={false} axisLine={false} label={{ value: 'Latency (ms) / Throughput', angle: -90, position: 'insideLeft', fill: textColor, fontSize: 12, dx: -10 }} />
            <YAxis yAxisId="right" orientation="right" stroke={textColor} fontSize={12} tickLine={false} axisLine={false} label={{ value: 'Error Rate (%)', angle: 90, position: 'insideRight', fill: textColor, fontSize: 12, dx: 10 }} />
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
            <Legend wrapperStyle={{fontSize: "12px"}} />
            <Line yAxisId="left" type="monotone" dataKey="latency" name="Latency (ms)" stroke="#8884d8" strokeWidth={2} dot={{ r: 3 }} />
            <Line yAxisId="left" type="monotone" dataKey="throughput" name="Throughput (req/s)" stroke="#82ca9d" strokeWidth={2} dot={{ r: 3 }} />
            <Line yAxisId="right" type="monotone" dataKey="errorRate" name="Error Rate (%)" stroke="#ffc658" strokeWidth={2} dot={{ r: 3 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};
