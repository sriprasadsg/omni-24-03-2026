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
    <div className="glass rounded-2xl p-6 flex items-center justify-between transition-all duration-300 transform hover:scale-[1.03] hover:shadow-[0_0_20px_rgba(0,210,255,0.3)] hover:border-primary-400 group cursor-pointer">
      <div className="flex items-center">
        <div className="mr-5 p-3 rounded-2xl bg-gray-50 dark:bg-gray-700 transition-transform duration-300 group-hover:rotate-12">
          {METRIC_ICONS[metric.type]}
        </div>
        <div>
          <p className="text-xs font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-1">{metric.title}</p>
          <p className="text-3xl font-extrabold text-gray-900 dark:text-white tracking-tight">{metric.value}</p>
        </div>
      </div>
      <div className={`flex items-center px-3 py-1 transparent rounded-xl border ${metric.changeType === 'increase' ? 'border-rose-200 dark:border-rose-900/50 text-rose-600 dark:text-rose-400' : 'border-emerald-200 dark:border-emerald-900/50 text-emerald-600 dark:text-emerald-400'
        }`}>
        <span className="text-xs font-black inline-flex items-center">
          {metric.changeType === 'increase' ? <ArrowUpRightIcon size={14} className="mr-1" /> : <ArrowDownRightIcon size={14} className="mr-1" />}
          {metric.change}
        </span>
      </div>
    </div>
  );
};
