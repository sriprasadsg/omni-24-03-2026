import React from 'react';
import { AgenticStep } from '../types';
import { ZapIcon, MessageSquareQuoteIcon, TerminalIcon, EyeIcon, CogIcon } from './icons';

const stepIcons: Record<AgenticStep['type'], { icon: React.ReactNode; color: string; }> = {
  goal: { icon: <ZapIcon />, color: 'text-indigo-500 dark:text-indigo-400' },
  thought: { icon: <MessageSquareQuoteIcon />, color: 'text-sky-500 dark:text-sky-400' },
  action: { icon: <TerminalIcon />, color: 'text-amber-500 dark:text-amber-400' },
  observation: { icon: <EyeIcon />, color: 'text-green-500 dark:text-green-400' },
};

interface RemediationPlanLogProps {
  steps: AgenticStep[];
  isLoading: boolean;
}

export const RemediationPlanLog: React.FC<RemediationPlanLogProps> = ({ steps, isLoading }) => {
  if (isLoading && (!steps || steps.length === 0)) {
    return (
      <div className="flex items-center text-sm text-gray-500 dark:text-gray-400 p-4">
        <CogIcon size={16} className="animate-spin mr-2" />
        Generating AI-powered remediation plan...
      </div>
    );
  }

  if (!steps) {
    return null;
  }

  return (
    <div className="p-3 bg-gray-900 dark:bg-black rounded-md max-h-64 overflow-y-auto font-mono text-sm">
      <div className="space-y-3">
        {steps.map((step, index) => {
          const { icon, color } = stepIcons[step.type];
          return (
            <div key={index} className="flex items-start">
              <div className={`flex-shrink-0 w-28 flex items-center ${color}`}>
                <span className="mr-2">{icon}</span>
                <span className="font-semibold capitalize">{step.type}</span>
              </div>
              <p className="flex-1 text-gray-300 whitespace-pre-wrap">
                {step.content}
              </p>
            </div>
          );
        })}
        {isLoading && (
            <div className="flex items-start">
                <div className="flex-shrink-0 w-28 flex items-center text-gray-400">
                    <CogIcon size={16} className="animate-spin mr-2" />
                    <span>Thinking...</span>
                </div>
            </div>
        )}
      </div>
    </div>
  );
};
