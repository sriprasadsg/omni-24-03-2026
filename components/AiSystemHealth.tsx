import React from 'react';
import { AiSystem, Agent } from '../types';
import { BotIcon, CheckIcon, AlertTriangleIcon, XCircleIcon } from './icons';

interface AiSystemHealthProps {
  aiSystems: AiSystem[];
  agents?: Agent[];  // Optional agents prop
}

export const AiSystemHealth: React.FC<AiSystemHealthProps> = ({ aiSystems, agents = [] }) => {
  // If we have actual AI systems data, use it
  // Otherwise, fall back to counting agents
  const activeSystems = aiSystems.length > 0
    ? aiSystems.filter(s => s.status === 'Active').length
    : agents.filter(a => a.status === 'Online').length;

  const inactiveSystems = aiSystems.length > 0
    ? aiSystems.filter(s => s.status !== 'Active').length
    : agents.filter(a => a.status !== 'Online').length;

  const atRiskSystems = aiSystems.filter(s =>
    s.risks?.some(r => r.status === 'Open' && (r.severity === 'Critical' || r.severity === 'High'))
  ).length;

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 h-full flex flex-col shadow-md">
      <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex-shrink-0">
        <h3 className="text-lg font-semibold flex items-center">
          <BotIcon className="mr-2 text-primary-500" />
          AI System Health
        </h3>
      </div>
      <div className="p-4 space-y-3 flex-grow">
        <div className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
          <div className="flex items-center">
            <CheckIcon className="mr-3 text-green-500" size={20} />
            <span className="font-medium text-gray-700 dark:text-gray-300">Active Systems</span>
          </div>
          <span className="font-bold text-lg text-gray-800 dark:text-white">{activeSystems}</span>
        </div>
        <div className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
          <div className="flex items-center">
            <XCircleIcon className="mr-3 text-gray-500" size={20} />
            <span className="font-medium text-gray-700 dark:text-gray-300">Inactive Systems</span>
          </div>
          <span className="font-bold text-lg text-gray-800 dark:text-white">{inactiveSystems}</span>
        </div>
        <div className={`flex items-center justify-between p-3 rounded-lg ${atRiskSystems > 0 ? 'bg-red-50 dark:bg-red-900/50' : 'bg-gray-50 dark:bg-gray-700/50'}`}>
          <div className="flex items-center">
            <AlertTriangleIcon className={`mr-3 ${atRiskSystems > 0 ? 'text-red-500' : 'text-gray-500'}`} size={20} />
            <span className={`font-medium ${atRiskSystems > 0 ? 'text-red-700 dark:text-red-300' : 'text-gray-700 dark:text-gray-300'}`}>At-Risk Systems</span>
          </div>
          <span className={`font-bold text-lg ${atRiskSystems > 0 ? 'text-red-800 dark:text-red-200' : 'text-gray-800 dark:text-white'}`}>{atRiskSystems}</span>
        </div>
      </div>
    </div>
  );
};
