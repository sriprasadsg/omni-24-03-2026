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

  useEffect(() => {
    // Automatically run analysis on dashboard view when data is available
    if (!isSecurityContext && !analysis && !isLoading && metrics && metrics.length > 0 && alerts && alerts.length > 0) {
      handleGenerateAnalysis();
    }
  }, [analysis, isLoading, metrics, alerts, isSecurityContext, handleGenerateAnalysis]);

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
  const buttonText = isLoading ? 'Analyzing...' : analysis ? 'Refresh Analysis' : 'Generate Analysis';
  const placeholderText = isSecurityContext
    ? "Click 'Generate Analysis' for an AI-powered summary of the selected security events."
    : "AI analysis is running automatically. Results will appear here shortly.";


  return (
    <div className="glass dark:glass rounded-2xl border border-white/20 dark:border-white/5 h-full flex flex-col shadow-xl overflow-hidden">
      <div className="p-6 border-b border-white/10 dark:border-white/5 flex justify-between items-center flex-shrink-0 bg-primary-500/5">
        <h3 className="text-xl font-extrabold flex items-center tracking-tight text-gray-800 dark:text-white">
          <div className="p-2 bg-white/50 dark:bg-white/5 rounded-xl mr-3">
            <BotIcon className="text-primary-600 dark:text-primary-400" size={24} />
          </div>
          {title}
        </h3>
        <button
          onClick={handleGenerateAnalysis}
          disabled={isLoading}
          className="px-5 py-2.5 text-sm font-bold text-white bg-gradient-to-r from-primary-600 to-indigo-600 rounded-xl shadow-lg shadow-primary-500/20 hover:shadow-primary-500/40 transition-all active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {buttonText}
        </button>
      </div>
      <div className="p-6 flex-grow min-h-[200px] overflow-y-auto bg-white/30 dark:bg-transparent">
        {isLoading && <LoadingSkeleton />}
        {error && <div className="p-4 bg-rose-50 dark:bg-rose-900/30 border border-rose-200 dark:border-rose-800 rounded-xl text-rose-600 dark:text-rose-400 text-sm font-medium">{error}</div>}
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
