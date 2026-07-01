
import React from 'react';
import { Metric, MetricType } from '../types';
import { ArrowUpRightIcon, ArrowDownRightIcon, CpuIcon, MemoryStickIcon, HardDriveIcon, WifiIcon, AlertTriangleIcon } from './icons';

interface MetricCardProps {
  metric: Metric;
}

const METRIC_ICONS: Record<MetricType, React.ReactNode> = {
    cpu: <CpuIcon className="w-6 h-6 text-blue-500" />,
    memory: <MemoryStickIcon className="w-6 h-6 text-green-500" />,
    disk: <HardDriveIcon className="w-6 h-6 text-orange-500" />,
    network: <WifiIcon className="w-6 h-6 text-purple-500" />,
    security_event: <AlertTriangleIcon className="w-6 h-6 text-red-500" />,
};

export const MetricCard: React.FC<MetricCardProps> = ({ metric }) => {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 flex items-center justify-between transition-colors hover:bg-gray-50 dark:hover:bg-gray-800/50">
      <div className="flex items-center">
          <div className="mr-4">
              {METRIC_ICONS[metric.type]}
          </div>
          <div>
              <p className="text-sm font-medium text-gray-500 dark:text-gray-400">{metric.title}</p>
              <p className="text-2xl font-bold text-gray-800 dark:text-white">{metric.value}</p>
          </div>
      </div>
      <span className={`text-xs font-semibold px-2 py-1 rounded-full ${
        metric.changeType === 'increase' ? 'bg-red-100 dark:bg-red-900/50 text-red-600 dark:text-red-400' : 'bg-green-100 dark:bg-green-900/50 text-green-600 dark:text-green-400'
      }`}>
        <span className="inline-flex items-center">
          {metric.changeType === 'increase' ? <ArrowUpRightIcon size={12}/> : <ArrowDownRightIcon size={12}/>}
          {metric.change}
        </span>
      </span>
    </div>
  );
};