
import React from 'react';
import { AiSystem, FairnessMetric } from '../types';
import { ScaleIcon } from './icons';

interface FairnessMetricsProps {
  system: AiSystem;
}

const statusClasses: Record<FairnessMetric['status'], { text: string; bg: string; ring: string; }> = {
  Pass: { text: 'text-green-700 dark:text-green-300', bg: 'bg-green-50 dark:bg-green-900/50', ring: 'ring-green-500' },
  Warning: { text: 'text-amber-700 dark:text-amber-300', bg: 'bg-amber-50 dark:bg-amber-900/50', ring: 'ring-amber-500' },
  Fail: { text: 'text-red-700 dark:text-red-300', bg: 'bg-red-50 dark:bg-red-900/50', ring: 'ring-red-500' },
};

export const FairnessMetrics: React.FC<FairnessMetricsProps> = ({ system }) => {
  const { fairnessMetrics } = system;

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md">
      <div className="p-4 border-b border-gray-200 dark:border-gray-700">
        <h3 className="text-lg font-semibold flex items-center">
          <ScaleIcon className="mr-2 text-primary-500" />
          Fairness & Bias Metrics
        </h3>
      </div>
      <div className="p-4 space-y-4">
        {fairnessMetrics && fairnessMetrics.length > 0 ? (
          fairnessMetrics.map(metric => {
            const styles = statusClasses[metric.status];
            return (
                <div key={metric.id} className="p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg border border-gray-200 dark:border-gray-600">
                    <div className="flex justify-between items-center mb-2">
                        <span className="font-medium text-gray-800 dark:text-gray-200">{metric.name}</span>
                        <span className={`px-2 py-1 text-xs font-medium rounded-full ring-1 ring-inset ${styles.bg} ${styles.text} ${styles.ring}`}>
                            {metric.status}
                        </span>
                    </div>
                    <div className="flex justify-between items-end">
                        <p className="text-sm text-gray-500 dark:text-gray-400">{metric.description}</p>
                        <p className="text-lg font-bold text-gray-800 dark:text-white">{metric.value}</p>
                    </div>
                </div>
            );
          })
        ) : (
          <p className="text-sm text-center text-gray-500 dark:text-gray-400 py-4">
            No fairness metrics have been configured for this system.
          </p>
        )}
      </div>
    </div>
  );
};
