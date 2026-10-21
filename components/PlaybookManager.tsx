import React, { useState } from 'react';
import { Playbook, PlaybookStepType } from '../types';
import { BotIcon, ChevronDownIcon, ActivityIcon, ShieldIcon, FileTextIcon, MessageSquareWarningIcon, SparklesIcon, TerminalSquareIcon, ShieldSearchIcon, ZapIcon } from './icons';
import { useUser } from '../contexts/UserContext';

interface PlaybookManagerProps {
  playbooks: Playbook[];
  onExecutePlaybook: (playbook: Playbook) => void;
  onGeneratePlaybook: () => void;
  onTogglePlaybook?: (playbook: Playbook) => void;
}

const stepTypeIcons: Record<PlaybookStepType, React.ReactNode> = {
  Analysis: <FileTextIcon size={15} className="text-blue-600 dark:text-blue-400" />,
  Enrichment: <ShieldSearchIcon size={15} className="text-primary-600 dark:text-primary-400" />,
  Containment: <ShieldIcon size={15} className="text-red-600 dark:text-red-400" />,
  Eradication: <ActivityIcon size={15} className="text-orange-600 dark:text-orange-400" />,
  Communication: <MessageSquareWarningIcon size={15} className="text-emerald-600 dark:text-emerald-400" />,
};

export const PlaybookManager: React.FC<PlaybookManagerProps> = ({ playbooks, onExecutePlaybook, onGeneratePlaybook, onTogglePlaybook }) => {
  const [expandedPlaybook, setExpandedPlaybook] = useState<string | null>(playbooks.length > 0 ? playbooks[0].id : null);
  const { hasPermission } = useUser();
  const canManagePlaybooks = hasPermission('manage:security_playbooks');

  const togglePlaybook = (id: string) => {
    setExpandedPlaybook(expandedPlaybook === id ? null : id);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-[15px] font-semibold text-gray-900 dark:text-white flex items-center gap-2">
          <BotIcon size={16} className="text-primary-500" />
          Playbook library
        </h3>
        {canManagePlaybooks && (
          <button
            onClick={onGeneratePlaybook}
            className="flex items-center gap-2 h-9 px-4 text-sm font-semibold text-white rounded-xl bg-primary-600 hover:bg-primary-700 transition-all active:scale-[0.98]"
          >
            <SparklesIcon size={15} />
            Generate with AI
          </button>
        )}
      </div>

      {playbooks.length === 0 ? (
        <div className="rounded-2xl bg-white dark:bg-gray-800 border border-gray-200/80 dark:border-white/[0.07] shadow-card p-10 text-center">
          <BotIcon size={28} className="mx-auto text-gray-400" />
          <p className="mt-3 text-sm font-medium text-gray-700 dark:text-gray-300">No playbooks yet</p>
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            {canManagePlaybooks ? 'Describe a response and generate one with AI.' : 'Playbooks your administrators create appear here.'}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {playbooks.map(playbook => {
            const isExpanded = expandedPlaybook === playbook.id;
            const isDisabled = playbook.enabled === false;
            return (
              <div key={playbook.id} className="rounded-2xl bg-white dark:bg-gray-800 border border-gray-200/80 dark:border-white/[0.07] shadow-card overflow-hidden">
                <button
                  className="w-full text-left px-5 py-4 hover:bg-gray-50/80 dark:hover:bg-white/[0.02] transition-colors"
                  onClick={() => togglePlaybook(playbook.id)}
                  aria-expanded={isExpanded}
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <h4 className={`font-semibold ${isDisabled ? 'text-gray-500 dark:text-gray-400' : 'text-gray-900 dark:text-gray-100'}`}>{playbook.name}</h4>
                        {isDisabled && (
                          <span className="px-1.5 py-px rounded-full text-[11px] font-semibold text-gray-600 dark:text-gray-300 bg-gray-500/10 ring-1 ring-inset ring-gray-500/20">Disabled</span>
                        )}
                        {playbook.source === 'AI-Generated' && (
                          <span className="flex items-center gap-1 px-1.5 py-px rounded-full text-[11px] font-semibold text-primary-700 dark:text-primary-300 bg-primary-500/10 ring-1 ring-inset ring-primary-500/20">
                            <SparklesIcon size={11} />
                            AI-generated
                          </span>
                        )}
                      </div>
                      <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{playbook.description}</p>
                      <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                        Trigger <code className="ml-1 px-1.5 py-0.5 rounded-md font-mono text-[11px] text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-white/[0.06]">{playbook.trigger}</code>
                      </p>
                    </div>
                    <ChevronDownIcon size={18} className={`flex-shrink-0 mt-0.5 text-gray-500 dark:text-gray-400 transition-transform duration-300 ${isExpanded ? 'rotate-180' : ''}`} />
                  </div>
                </button>

                {isExpanded && (
                  <div className="px-5 pb-5 pt-4 border-t border-gray-100 dark:border-white/[0.06]">
                    {canManagePlaybooks && (
                      <div className="flex justify-end gap-2 mb-5">
                        {onTogglePlaybook && (
                          <button
                            onClick={() => onTogglePlaybook(playbook)}
                            className="h-9 px-3.5 text-sm font-medium text-gray-700 dark:text-gray-200 glass rounded-xl transition-all hover:border-primary-500/40 active:scale-[0.98]"
                          >
                            {isDisabled ? 'Enable' : 'Disable'}
                          </button>
                        )}
                        <button
                          onClick={() => onExecutePlaybook(playbook)}
                          disabled={isDisabled}
                          title={isDisabled ? 'Enable this playbook to run it' : undefined}
                          className="flex items-center gap-2 h-9 px-4 text-sm font-semibold text-white rounded-xl bg-primary-600 hover:bg-primary-700 transition-all active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          <ZapIcon size={15} />
                          Run playbook
                        </button>
                      </div>
                    )}
                    {playbook.steps.length === 0 ? (
                      <p className="text-sm text-gray-500 dark:text-gray-400">This playbook has no steps.</p>
                    ) : (
                      <ol className="relative space-y-5">
                        {playbook.steps.length > 1 && (
                          <span className="absolute left-4 top-4 bottom-4 w-px bg-gray-200 dark:bg-white/10" aria-hidden="true" />
                        )}
                        {playbook.steps.map(step => (
                          <li key={step.id} className="relative flex gap-3">
                            <span className="relative grid place-items-center h-8 w-8 flex-shrink-0 rounded-xl bg-gray-100 dark:bg-gray-900 ring-1 ring-inset ring-gray-200/80 dark:ring-white/[0.07]">
                              {stepTypeIcons[step.type]}
                            </span>
                            <div className="min-w-0 pt-0.5">
                              <p className="font-medium text-sm text-gray-800 dark:text-gray-200">
                                {step.name} <span className="text-xs font-normal text-gray-500 dark:text-gray-400">{step.type}</span>
                              </p>
                              <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{step.description}</p>
                              {step.command && (
                                <div className="mt-2 flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400 min-w-0">
                                  <TerminalSquareIcon size={14} className="flex-shrink-0" />
                                  <code className="px-1.5 py-0.5 rounded-md font-mono text-[11px] text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-white/[0.06] truncate">{step.command}</code>
                                </div>
                              )}
                            </div>
                          </li>
                        ))}
                      </ol>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
