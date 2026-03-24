import React, { useState } from 'react';
import { Playbook, PlaybookStepType } from '../types';
import { BotIcon, ChevronDownIcon, ActivityIcon, ShieldIcon, FileTextIcon, MessageSquareWarningIcon, SparklesIcon, TerminalSquareIcon, PlusCircleIcon, ShieldSearchIcon, ZapIcon } from './icons';
import { useUser } from '../contexts/UserContext';

interface PlaybookManagerProps {
  playbooks: Playbook[];
  onExecutePlaybook: (playbook: Playbook) => void;
  onGeneratePlaybook: () => void;
}

const stepTypeIcons: Record<PlaybookStepType, React.ReactNode> = {
  Analysis: <FileTextIcon size={16} className="text-blue-500" />,
  Enrichment: <ShieldSearchIcon size={16} className="text-purple-500" />,
  Containment: <ShieldIcon size={16} className="text-red-500" />,
  Eradication: <ActivityIcon size={16} className="text-orange-500" />,
  Communication: <MessageSquareWarningIcon size={16} className="text-green-500" />,
};

export const PlaybookManager: React.FC<PlaybookManagerProps> = ({ playbooks, onExecutePlaybook, onGeneratePlaybook }) => {
  const [expandedPlaybook, setExpandedPlaybook] = useState<string | null>(playbooks.length > 0 ? playbooks[0].id : null);
  const { hasPermission } = useUser();
  const canManagePlaybooks = hasPermission('manage:security_playbooks');

  const togglePlaybook = (id: string) => {
    setExpandedPlaybook(expandedPlaybook === id ? null : id);
  };

  return (
    <div>
        <div className="flex justify-between items-center mb-4">
            <h3 className="text-lg font-semibold">Playbook Library</h3>
            {canManagePlaybooks && (
                <button 
                  onClick={onGeneratePlaybook}
                  className="flex items-center px-3 py-1.5 text-xs font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500"
                >
                    <SparklesIcon size={16} className="mr-1.5" />
                    AI-Generate Playbook
                </button>
            )}
        </div>
        <div className="space-y-4">
          {playbooks.map(playbook => (
            <div key={playbook.id} className="bg-gray-50 dark:bg-gray-800/50 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700">
              <button
                className="w-full text-left p-4"
                onClick={() => togglePlaybook(playbook.id)}
                aria-expanded={expandedPlaybook === playbook.id}
              >
                <div className="flex justify-between items-start">
                    <div>
                      <h3 className="font-semibold text-gray-800 dark:text-gray-200">{playbook.name}</h3>
                      <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{playbook.description}</p>
                      <p className="text-xs text-amber-600 dark:text-amber-400 mt-2 font-mono">Trigger: {playbook.trigger}</p>
                    </div>
                    <div className="flex items-center flex-shrink-0">
                      {playbook.source === 'AI-Generated' && (
                          <span className="hidden sm:flex items-center text-xs font-medium text-indigo-700 bg-indigo-100 dark:text-indigo-200 dark:bg-indigo-900/50 px-2 py-1 rounded-full">
                              <SparklesIcon size={14} className="mr-1.5" />
                              AI-Generated
                          </span>
                      )}
                      <ChevronDownIcon size={20} className={`ml-4 text-gray-500 dark:text-gray-400 transition-transform duration-300 ${expandedPlaybook === playbook.id ? 'rotate-180' : ''}`} />
                    </div>
                </div>
              </button>
              
              {expandedPlaybook === playbook.id && (
                <div className="px-4 pb-4 border-t border-gray-200 dark:border-gray-700 pt-4">
                  <div className="flex justify-end mb-4">
                     {canManagePlaybooks && (
                        <button 
                            onClick={() => onExecutePlaybook(playbook)}
                            className="flex items-center px-3 py-1.5 text-xs font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500"
                        >
                            <ZapIcon size={16} className="mr-1.5" />
                            Execute Playbook
                        </button>
                     )}
                  </div>
                  <div className="relative pl-8">
                    {/* Vertical line */}
                    {playbook.steps.length > 1 && (
                      <div className="absolute left-4 top-4 bottom-4 w-0.5 bg-gray-200 dark:bg-gray-600" aria-hidden="true"></div>
                    )}
                    
                    {playbook.steps.map((step) => (
                      <div key={step.id} className="relative mb-6 last:mb-0">
                        <div className="absolute -left-[0.8rem] top-0.5 flex items-center justify-center w-8 h-8 rounded-full bg-gray-100 dark:bg-gray-700 ring-4 ring-gray-50 dark:ring-gray-800/50">
                          {stepTypeIcons[step.type]}
                        </div>
                        <div className="ml-6">
                          <p className="font-medium text-sm text-gray-700 dark:text-gray-300">{step.name} <span className="text-xs text-gray-400">({step.type})</span></p>
                          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{step.description}</p>
                          <div className="mt-2">
                              <div className="flex items-center text-xs text-gray-400">
                                  <TerminalSquareIcon size={14} className="mr-2 flex-shrink-0"/>
                                  <code className="bg-gray-100 dark:bg-gray-900 rounded px-1.5 py-0.5 text-gray-600 dark:text-gray-300 text-[11px] font-mono">
                                      {step.command}
                                  </code>
                              </div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
    </div>
  );
};
