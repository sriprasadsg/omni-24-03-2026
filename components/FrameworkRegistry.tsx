import React from 'react';
import { ComplianceFramework } from '../types';
// FIX: Replaced non-existent LockIcon with ShieldLockIcon.
import { ShieldCheckIcon, BotIcon, ShieldLockIcon, GavelIcon, HeartPulseIcon, CreditCardIcon, BookOpenCheckIcon } from './icons';

interface FrameworkRegistryProps {
  frameworks: ComplianceFramework[];
  selectedFramework: ComplianceFramework | null;
  onSelectFramework: (framework: ComplianceFramework) => void;
}

const statusClasses: Record<ComplianceFramework['status'], string> = {
    Compliant: 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300',
    Pending: 'bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-300',
    'At Risk': 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300',
};

const frameworkIcons: Record<string, React.ReactNode> = {
    'iso42001': <BotIcon size={20} />,
    'iso27001': <ShieldLockIcon size={20} />,
    'soc2': <ShieldCheckIcon size={20} />,
    'gdpr': <GavelIcon size={20} />,
    'hipaa': <HeartPulseIcon size={20} />,
    'pci-dss': <CreditCardIcon size={20} />,
    'nistcsf': <BookOpenCheckIcon size={20} />,
};

export const FrameworkRegistry: React.FC<FrameworkRegistryProps> = ({ frameworks, selectedFramework, onSelectFramework }) => {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md h-full">
      <div className="p-4 border-b border-gray-200 dark:border-gray-700">
        <h3 className="text-lg font-semibold flex items-center">
          <ShieldCheckIcon className="mr-2 text-primary-500" />
          Frameworks
        </h3>
      </div>
      <div className="p-2 space-y-2">
        {frameworks.map(framework => (
          <button
            key={framework.id}
            onClick={() => onSelectFramework(framework)}
            className={`w-full text-left p-3 rounded-lg transition-colors duration-150 ${
                selectedFramework?.id === framework.id 
                ? 'bg-primary-100 dark:bg-primary-900/50 ring-2 ring-primary-500' 
                : 'hover:bg-gray-100 dark:hover:bg-gray-700/50'
            }`}
          >
            <div className="flex justify-between items-start">
                <div className="flex items-center">
                    <span className="text-primary-500 w-5">{frameworkIcons[framework.id] || <ShieldCheckIcon size={20} />}</span>
                    <p className="ml-2 font-semibold text-gray-800 dark:text-gray-100">{framework.shortName}</p>
                </div>
                <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${statusClasses[framework.status]}`}>{framework.status}</span>
            </div>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{framework.name}</p>
          </button>
        ))}
      </div>
    </div>
  );
};
