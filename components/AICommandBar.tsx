import React, { useState, useEffect, useRef } from 'react';
import { getCommandFromQuery } from '../services/geminiService';
import { SparklesIcon, XIcon, ArrowRightIcon } from './icons';

export interface Command {
    name: string;
    args: Record<string, any>;
}

interface AICommandBarProps {
    isOpen: boolean;
    onClose: () => void;
    onExecuteCommand: (command: Command) => void;
}

const suggestedPrompts = [
    "Show me agents that have an error",
    "Navigate to asset management",
    "Find assets with critical vulnerabilities",
    "Go to the security dashboard"
];

export const AICommandBar: React.FC<AICommandBarProps> = ({ isOpen, onClose, onExecuteCommand }) => {
    const [query, setQuery] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const inputRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        if (isOpen) {
            setQuery('');
            setError(null);
            setTimeout(() => inputRef.current?.focus(), 100);
        }
    }, [isOpen]);

    const handleQueryChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        setQuery(e.target.value);
        setError(null);
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!query.trim()) return;

        setIsLoading(true);
        setError(null);
        try {
            const commands = await getCommandFromQuery(query);
            if (commands && commands.length > 0) {
                // Execute all commands returned by the AI
                commands.forEach(onExecuteCommand);
            } else {
                setError("Sorry, I couldn't determine an action for that query.");
            }
        } catch (err) {
            const message = err instanceof Error ? err.message : "An unknown error occurred";
            setError(`Failed to process command: ${message}`);
        } finally {
            setIsLoading(false);
        }
    };
    
    const handleSuggestionClick = (prompt: string) => {
        setQuery(prompt);
        // Focus and submit
        inputRef.current?.focus();
        // We need a slight delay for the state to update before submitting
        setTimeout(() => {
            const form = inputRef.current?.closest('form');
            form?.requestSubmit();
        }, 0);
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 bg-black/60 z-50 flex justify-center items-start pt-20" onClick={onClose}>
            <div 
                className="bg-white dark:bg-gray-800 rounded-lg shadow-2xl w-full max-w-2xl transform transition-all" 
                onClick={e => e.stopPropagation()}
            >
                <form onSubmit={handleSubmit}>
                    <div className="relative">
                        <SparklesIcon className="absolute left-4 top-1/2 -translate-y-1/2 text-primary-500" size={20} />
                        <input
                            ref={inputRef}
                            type="text"
                            value={query}
                            onChange={handleQueryChange}
                            placeholder="Type a command or ask a question..."
                            className="w-full bg-transparent p-4 pl-12 text-lg text-gray-800 dark:text-gray-100 focus:outline-none"
                        />
                        {isLoading && (
                            <div className="absolute right-4 top-1/2 -translate-y-1/2">
                                <svg className="animate-spin h-5 w-5 text-primary-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                </svg>
                            </div>
                        )}
                    </div>
                </form>
                <div className="p-4 border-t border-gray-100 dark:border-gray-700">
                    {error && <p className="text-sm text-red-500 px-2">{error}</p>}
                    {!query && !error && (
                        <div>
                             <p className="text-xs font-semibold text-gray-400 dark:text-gray-500 px-2 mb-2">SUGGESTIONS</p>
                             <div className="space-y-1">
                                {suggestedPrompts.map(prompt => (
                                    <button 
                                        key={prompt}
                                        onClick={() => handleSuggestionClick(prompt)}
                                        className="w-full text-left flex items-center justify-between p-2 rounded-md hover:bg-gray-100 dark:hover:bg-gray-700/50"
                                    >
                                        <span className="text-sm text-gray-600 dark:text-gray-300">{prompt}</span>
                                        <ArrowRightIcon size={16} className="text-gray-400" />
                                    </button>
                                ))}
                             </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};
