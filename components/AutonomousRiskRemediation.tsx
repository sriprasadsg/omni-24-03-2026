import React, { useRef, useEffect } from 'react';
import { AgenticStep, AiSystem, AiRisk } from '../types';
import { ZapIcon, MessageSquareQuoteIcon, TerminalIcon, EyeIcon, CogIcon, CheckIcon, AlertTriangleIcon } from './icons';

interface AutonomousRiskRemediationProps {
  runState: {
    status: 'idle' | 'running' | 'completed' | 'failed';
    steps: AgenticStep[];
    targetSystem: AiSystem | null;
    targetRisk: AiRisk | null;
  };
  onClose: () => void;
}

const stepIcons: Record<AgenticStep['type'], { icon: React.ReactNode; color: string; }> = {
  goal: { icon: <ZapIcon />, color: 'text-indigo-500 dark:text-indigo-400' },
  thought: { icon: <MessageSquareQuoteIcon />, color: 'text-sky-500 dark:text-sky-400' },
  action: { icon: <TerminalIcon />, color: 'text-amber-500 dark:text-amber-400' },
  observation: { icon: <EyeIcon />, color: 'text-green-500 dark:text-green-400' },
};

export const AutonomousRiskRemediation: React.FC<AutonomousRiskRemediationProps> = ({ runState, onClose }) => {
  const logContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [runState.steps]);

  return (
    <div className="mb-6 bg-white dark:bg-gray-800 rounded-lg shadow-md">
      <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex justify-between items-center">
        <h3 className="text-lg font-semibold flex items-center">
          <ZapIcon className="mr-2 text-primary-500" />
          Autonomous Risk Remediation
        </h3>
        {runState.status !== 'running' && (
            <button onClick={onClose} className="text-xs font-medium text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-white">Close</button>
        )}
      </div>
      <div className="p-4">
        <div>
          <div className="flex justify-between items-center mb-4">
            <p className="font-semibold">
              Remediation Log for:{' '}
              <span className="font-mono text-primary-600 dark:text-primary-400 text-xs">
                {runState.targetSystem?.name} - {runState.targetRisk?.title}
              </span>
            </p>
            {runState.status === 'running' && <span className="flex items-center text-sm font-medium text-amber-600 dark:text-amber-400"><CogIcon size={16} className="animate-spin mr-2"/>Running...</span>}
            {runState.status === 'completed' && <span className="flex items-center text-sm font-medium text-green-600 dark:text-green-400"><CheckIcon size={16} className="mr-2"/>Completed</span>}
            {runState.status === 'failed' && <span className="flex items-center text-sm font-medium text-red-600 dark:text-red-400"><AlertTriangleIcon size={16} className="mr-2"/>Failed</span>}
          </div>
          <div
            ref={logContainerRef}
            className="p-3 bg-gray-900 dark:bg-black rounded-md max-h-64 overflow-y-auto font-mono text-sm"
          >
            <div className="space-y-3">
              {runState.steps.map((step, index) => {
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
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
