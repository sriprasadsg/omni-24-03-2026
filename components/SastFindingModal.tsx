import React, { useState, useEffect } from 'react';
import { SastFinding } from '../types';
import { XIcon, CodeIcon, SparklesIcon, CogIcon } from './icons';
import { generateSastFix } from '../services/geminiService';

interface SastFindingModalProps {
  isOpen: boolean;
  onClose: () => void;
  finding: SastFinding | null;
}

const CodeBlock: React.FC<{ code: string; language?: string }> = ({ code, language }) => (
    <pre className="bg-gray-900 text-white p-3 rounded-md text-xs whitespace-pre-wrap">
        <code className={`language-${language}`}>{code}</code>
    </pre>
);

export const SastFindingModal: React.FC<SastFindingModalProps> = ({ isOpen, onClose, finding }) => {
    const [isLoading, setIsLoading] = useState(false);
    const [fixedCode, setFixedCode] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (isOpen) {
            setIsLoading(false);
            setFixedCode(null);
            setError(null);
        }
    }, [isOpen]);

    const handleGenerateFix = async () => {
        if (!finding) return;
        setIsLoading(true);
        setError(null);
        setFixedCode(null);
        try {
            const result = await generateSastFix(finding);
            setFixedCode(result.fixedCode);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to generate fix.');
        } finally {
            setIsLoading(false);
        }
    };

    if (!isOpen || !finding) return null;

    return (
        <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex justify-center items-center" onClick={onClose}>
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-3xl p-6 m-4 max-h-[90vh] flex flex-col" onClick={e => e.stopPropagation()}>
                <div className="flex-shrink-0 flex justify-between items-start mb-4">
                    <div>
                        <h2 className="text-xl font-bold text-gray-900 dark:text-white flex items-center">
                            <CodeIcon className="mr-3 text-primary-500" />
                            SAST Finding: {finding.type}
                        </h2>
                        <p className="text-sm text-gray-500 dark:text-gray-400 font-mono">{finding.fileName}:{finding.line}</p>
                    </div>
                    <button onClick={onClose} className="p-1 rounded-full text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700">
                        <XIcon size={20} />
                    </button>
                </div>

                <div className="flex-grow space-y-4 overflow-y-auto pr-2">
                    <div>
                        <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2">Vulnerable Code Snippet</h3>
                        <CodeBlock code={finding.codeSnippet} />
                    </div>

                    <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
                        <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2 flex items-center">
                            <SparklesIcon size={16} className="mr-2 text-primary-500" />
                            AI-Powered Remediation
                        </h3>
                        {fixedCode && !isLoading && (
                            <div>
                                <p className="text-xs text-green-700 dark:text-green-300 mb-2">Suggested secure code:</p>
                                <CodeBlock code={fixedCode} />
                            </div>
                        )}
                        {isLoading && <div className="flex items-center text-sm text-gray-500"><CogIcon size={16} className="animate-spin mr-2" /> Generating fix...</div>}
                        {error && <p className="text-sm text-red-500">{error}</p>}
                        {!fixedCode && !isLoading && (
                            <button onClick={handleGenerateFix} className="flex items-center px-3 py-1.5 text-xs font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700">
                                Generate AI Fix
                            </button>
                        )}
                    </div>
                </div>

                <div className="flex-shrink-0 mt-6 flex justify-end items-center pt-4 border-t border-gray-200 dark:border-gray-700">
                    <button type="button" onClick={onClose} className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700">
                        Close
                    </button>
                </div>
            </div>
        </div>
    );
};
