import React from 'react';
import { FeedbackLog } from '../types';
import { HistoryIcon, ThumbsUpIcon, ThumbsDownIcon } from './icons';

interface FeedbackHistoryProps {
  history: FeedbackLog[];
}

export const FeedbackHistory: React.FC<FeedbackHistoryProps> = ({ history }) => {
  return (
    <div className="border-t border-gray-200 dark:border-gray-700 px-4 py-3 flex-shrink-0">
      <h4 className="text-sm font-semibold flex items-center text-gray-700 dark:text-gray-300 mb-2">
        <HistoryIcon className="mr-2" size={16} />
        Feedback History
      </h4>
      {history.length > 0 ? (
        <div className="space-y-2 max-h-24 overflow-y-auto pr-2">
          {history.map((log) => (
            <div key={log.id} className="flex justify-between items-center text-xs">
              <span className="text-gray-500 dark:text-gray-400">
                {new Date(log.timestamp).toLocaleString()}
              </span>
              {log.vote === 'up' ? (
                <ThumbsUpIcon size={14} className="text-green-500" />
              ) : (
                <ThumbsDownIcon size={14} className="text-red-500" />
              )}
            </div>
          ))}
        </div>
      ) : (
        <p className="text-xs text-center text-gray-500 dark:text-gray-400 py-2">
          No feedback has been recorded yet.
        </p>
      )}
    </div>
  );
};
