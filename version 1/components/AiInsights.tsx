
import React, { useState, useCallback, useEffect } from 'react';
import { fetchHealthAnalysis, fetchSecurityAnalysis } from '../services/apiService';
import { Metric, Alert, FeedbackLog, SecurityEvent } from '../types';
import { BotIcon, ThumbsUpIcon, ThumbsDownIcon } from './icons';
import { FeedbackHistory } from './FeedbackHistory';

interface AiInsightsProps {
  metrics?: Metric[];
  alerts?: Alert[];
  securityEvents?: SecurityEvent[];
}

const LoadingSkeleton: React.FC = () => (
    <div className="space-y-4">
        <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-1/4 animate-pulse"></div>
        <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded w-full animate-pulse"></div>
        <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded w-5/6 animate-pulse"></div>
        <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-1/3 mt-4 animate-pulse"></div>
        <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded w-full animate-pulse"></div>
        <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded w-full animate-pulse"></div>
    </div>
);

const FormattedMarkdown: React.FC<{ content: string }> = ({ content }) => {
    const lines = content.split('\n');
    return (
        <div className="prose prose-sm dark:prose-invert max-w-none">
            {lines.map((line, index) => {
                if (line.startsWith('## ')) {
                    return <h2 key={index} className="text-base font-semibold mt-4 mb-2">{line.substring(3)}</h2>;
                }
                if (line.startsWith('1. ') || line.startsWith('2. ') || line.startsWith('3. ') || line.startsWith('- ')) {
                    return <p key={index} className="my-1">{line}</p>;
                }
                return <p key={index}>{line}</p>;
            })}
        </div>
    );
};

export const AiInsights: React.FC<AiInsightsProps> = ({ metrics, alerts, securityEvents }) => {
  const [analysis, setAnalysis] = useState<string>('');
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>('');
  const [feedback, setFeedback] = useState<'up' | 'down' | null>(null);
  const [history, setHistory] = useState<FeedbackLog[]>([]);

  const isSecurityContext = securityEvents && securityEvents.length > 0;

  useEffect(() => {
    try {
        const storedHistoryJSON = localStorage.getItem('aiFeedbackHistory');
        if (storedHistoryJSON) {
            const allHistory = JSON.parse(storedHistoryJSON);
            if (Array.isArray(allHistory)) {
                setHistory(allHistory.slice(0, 5));
            } else {
                setHistory([]);
                localStorage.removeItem('aiFeedbackHistory');
            }
        }
    } catch (error) {
        console.error("Failed to parse feedback history from localStorage", error);
        localStorage.removeItem('aiFeedbackHistory');
        setHistory([]);
    }
  }, []);

  const handleGenerateAnalysis = useCallback(async () => {
    setIsLoading(true);
    setError('');
    setAnalysis('');
    setFeedback(null);
    try {
      let result;
      if (isSecurityContext && securityEvents) {
        result = await fetchSecurityAnalysis(securityEvents);
      } else if (metrics && alerts) {
        result = await fetchHealthAnalysis(metrics, alerts);
      } else {
        throw new Error("Insufficient data for analysis.");
      }
      setAnalysis(result.analysis);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'An unknown error occurred.';
      setError(`Failed to generate analysis: ${message}`);
    } finally {
      setIsLoading(false);
    }
  }, [metrics, alerts, securityEvents, isSecurityContext]);

  const handleFeedback = (vote: 'up' | 'down') => {
    setFeedback(vote);
    
    const newFeedback: FeedbackLog = {
      id: new Date().toISOString(),
      timestamp: new Date().toISOString(),
      vote: vote,
    };

    try {
        const updatedHistory = [newFeedback, ...history].slice(0, 5);
        setHistory(updatedHistory);
        localStorage.setItem('aiFeedbackHistory', JSON.stringify(updatedHistory));
    } catch (error) {
        console.error("Failed to save feedback to localStorage", error);
    }
  };

  const title = isSecurityContext ? "AI-Powered Security Analysis" : "AI-Driven Health Analysis";
  const buttonText = isLoading ? 'Analyzing...' : 'Generate Analysis';
  const placeholderText = isSecurityContext 
    ? "Click 'Generate Analysis' for an AI-powered summary of the selected security events."
    : "Click 'Generate Analysis' for an AI-powered summary of the current system health.";


  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 h-full flex flex-col">
      <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex justify-between items-center flex-shrink-0">
        <h3 className="text-lg font-semibold flex items-center">
            <BotIcon className="mr-2 text-primary-500" />
            {title}
        </h3>
        <button
          onClick={handleGenerateAnalysis}
          disabled={isLoading}
          className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 disabled:bg-primary-400 disabled:cursor-not-allowed transition-colors"
        >
          {buttonText}
        </button>
      </div>
      <div className="p-4 flex-grow min-h-[200px] overflow-y-auto">
        {isLoading && <LoadingSkeleton />}
        {error && <p className="text-red-500">{error}</p>}
        {analysis && !isLoading && (
          <div>
            <FormattedMarkdown content={analysis} />
            <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
                {!feedback ? (
                    <div className="flex items-center space-x-4">
                        <p className="text-sm text-gray-500 dark:text-gray-400">Was this analysis helpful?</p>
                        <button
                            onClick={() => handleFeedback('up')}
                            className="p-2 rounded-full text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 hover:text-green-500 focus:outline-none transition-colors"
                            aria-label="Helpful"
                        >
                            <ThumbsUpIcon size={18} />
                        </button>
                        <button
                            onClick={() => handleFeedback('down')}
                            className="p-2 rounded-full text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 hover:text-red-500 focus:outline-none transition-colors"
                            aria-label="Not helpful"
                        >
                            <ThumbsDownIcon size={18} />
                        </button>
                    </div>
                ) : (
                    <p className="text-sm font-medium text-green-600 dark:text-green-400">Thank you for your feedback!</p>
                )}
            </div>
          </div>
        )}
        {!analysis && !isLoading && !error && (
          <div className="text-center text-gray-500 dark:text-gray-400 flex items-center justify-center h-full">
            <p>{placeholderText}</p>
          </div>
        )}
      </div>
      <FeedbackHistory history={history} />
    </div>
  );
};