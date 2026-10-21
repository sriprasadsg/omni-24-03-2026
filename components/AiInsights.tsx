import React, { useState, useCallback, useEffect } from 'react';
import { fetchHealthAnalysis, fetchSecurityAnalysis } from '../services/apiService';
import { Metric, Alert, FeedbackLog, SecurityEvent } from '../types';
import { BotIcon, ThumbsUpIcon, ThumbsDownIcon, AlertTriangleIcon } from './icons';
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
  const [limitedMode, setLimitedMode] = useState<boolean>(false);
  const [feedback, setFeedback] = useState<'up' | 'down' | null>(null);
  const [history, setHistory] = useState<FeedbackLog[]>([]);

  const isSecurityContext = securityEvents !== undefined;

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
    setLimitedMode(false);
    setFeedback(null);
    try {
      let result;
      if (isSecurityContext) {
        result = await fetchSecurityAnalysis(securityEvents ?? []);
      } else if (metrics && alerts) {
        result = await fetchHealthAnalysis(metrics, alerts);
      } else {
        throw new Error("Insufficient data for analysis.");
      }
      setAnalysis(result.analysis);
      setLimitedMode(result.limitedMode ?? false);
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
    ? "Generate an AI summary of the events in the feed."
    : "AI analysis is running automatically. Results will appear here shortly.";


  return (
    <section aria-label={title} className="rounded-2xl bg-white dark:bg-gray-800 border border-gray-200/80 dark:border-white/[0.07] shadow-card h-full flex flex-col overflow-hidden">
      <div className="px-5 pt-4 pb-3 border-b border-gray-100 dark:border-white/[0.06] flex justify-between items-center gap-3 flex-shrink-0">
        <h3 className="text-[15px] font-semibold flex items-center gap-2 text-gray-900 dark:text-white">
          <BotIcon className="text-primary-500" size={16} />
          {title}
        </h3>
        <button
          onClick={handleGenerateAnalysis}
          disabled={isLoading}
          className="flex-shrink-0 h-9 px-4 text-sm font-semibold text-white rounded-xl bg-primary-600 hover:bg-primary-700 transition-all active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {buttonText}
        </button>
      </div>
      <div className="p-5 flex-grow min-h-[200px] overflow-y-auto">
        {isLoading && <LoadingSkeleton />}
        {error && <div className="p-3.5 rounded-xl text-sm font-medium text-red-700 dark:text-red-300 bg-red-500/[0.06] ring-1 ring-inset ring-red-500/20">{error}</div>}
        {limitedMode && !isLoading && (
          <div className="mb-4 flex items-start gap-2 p-3 rounded-xl text-xs font-medium text-amber-800 dark:text-amber-300 bg-amber-500/[0.08] ring-1 ring-inset ring-amber-500/25">
            <AlertTriangleIcon size={15} className="flex-shrink-0 mt-px" />
            <span>
              <strong>AI running in limited mode</strong> — no LLM provider is configured.
              Configure an LLM (Anthropic, Gemini, or Ollama) in{' '}
              <strong>Settings → AI Configuration</strong> for full analysis capabilities.
            </span>
          </div>
        )}
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
          <div className="text-center text-sm text-gray-500 dark:text-gray-400 flex items-center justify-center h-full">
            <p>{placeholderText}</p>
          </div>
        )}
      </div>
      <FeedbackHistory history={history} />
    </section>
  );
};
