
import React from 'react';
import { AiSystem } from '../types';
import { BookTextIcon, PlusCircleIcon } from './icons';
import { useUser } from '../contexts/UserContext';

interface AiSystemRegistryProps {
  systems: AiSystem[];
  selectedSystem: AiSystem | null;
  onSelectSystem: (system: AiSystem) => void;
  onAddNewSystem: () => void;
}

const statusClasses: Record<AiSystem['status'], string> = {
    Active: 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300',
    'In Development': 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300',
    Sunset: 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300',
};

export const AiSystemRegistry: React.FC<AiSystemRegistryProps> = ({ systems, selectedSystem, onSelectSystem, onAddNewSystem }) => {
  const { hasPermission } = useUser();
  const canManage = hasPermission('manage:ai_risks');
  
  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md">
      <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex justify-between items-center">
        <h3 className="text-lg font-semibold flex items-center">
          <BookTextIcon className="mr-2 text-primary-500" />
          AI System Registry
        </h3>
        {canManage && (
            <button
                onClick={onAddNewSystem}
                className="flex items-center px-3 py-1.5 text-xs font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500"
            >
                <PlusCircleIcon size={16} className="mr-1.5" />
                Add System
            </button>
        )}
      </div>
      <div className="p-2 space-y-2">
        {systems.map(system => {
          const isSelected = selectedSystem?.id === system.id;
          return (
            <button
              key={system.id}
              onClick={() => onSelectSystem(system)}
              className={`w-full text-left p-3 rounded-lg transition-colors duration-150 ${
                isSelected 
                ? 'bg-primary-100 dark:bg-primary-900/50 ring-2 ring-primary-500' 
                : 'hover:bg-gray-100 dark:hover:bg-gray-700/50'
              }`}
            >
              <div className="flex justify-between items-center">
                <p className="font-semibold text-gray-800 dark:text-gray-100">{system.name}</p>
                <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${statusClasses[system.status]}`}>{system.status}</span>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
};
